"""Main entry point for Yandex Disk Telegram Bot.

This bot allows users to upload files to their Yandex Disk through Telegram
and get public download links.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        logging.info(f"Loaded environment from {env_file}")
except ImportError:
    logging.warning("python-dotenv not installed, skipping .env file loading")

# Import after loading .env
from config import Config
from core.bot import BotCore
from core.database import init_database, create_tables, close_database
from core.crypto import init_encryption
from modules.yandex.utils import cleanup_old_temp_files

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format=Config.LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


async def periodic_cleanup():
    """Background task to clean up old temporary files."""
    logger.info(f"Starting periodic cleanup task (interval: {Config.CLEANUP_INTERVAL_HOURS}h)")

    while True:
        try:
            await asyncio.sleep(Config.CLEANUP_INTERVAL_HOURS * 3600)
            logger.info("Running periodic cleanup of temporary files...")
            await cleanup_old_temp_files(max_age_hours=Config.CLEANUP_INTERVAL_HOURS)
            logger.info("Periodic cleanup completed")
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")


async def on_startup():
    """Execute on bot startup."""
    logger.info("=" * 60)
    logger.info("🚀 Starting Yandex Disk Telegram Bot")
    logger.info("=" * 60)

    # Print configuration
    Config.print_config()

    # Initialize database
    logger.info("Initializing database...")

    # Debug: Check database directory
    import os
    import re
    db_url = Config.DATABASE_URL
    logger.info(f"Database URL: {db_url}")

    # Extract file path from SQLite URL
    match = re.search(r'sqlite\+aiosqlite:///(.+)', db_url)
    if match:
        db_path = Path(match.group(1))
        db_dir = db_path.parent

        logger.info(f"Database file path: {db_path}")
        logger.info(f"Database directory: {db_dir}")
        logger.info(f"Directory exists: {db_dir.exists()}")
        logger.info(f"Directory is writable: {os.access(db_dir, os.W_OK) if db_dir.exists() else 'N/A'}")

        # Create directory if it doesn't exist
        if not db_dir.exists():
            logger.info(f"Creating directory: {db_dir}")
            db_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directory created successfully")

    init_database(Config.DATABASE_URL)

    # Import all models so Base.metadata knows about them before create_tables()
    import modules.yandex.models  # noqa: F401
    import modules.github.models  # noqa: F401

    await create_tables()
    logger.info("Database initialized successfully")

    # Initialize encryption
    logger.info("Initializing encryption...")
    init_encryption(Config.ENCRYPTION_KEY)
    logger.info("Encryption initialized successfully")

    logger.info("=" * 60)


async def on_shutdown():
    """Execute on bot shutdown."""
    logger.info("=" * 60)
    logger.info("🛑 Shutting down Yandex Disk Telegram Bot")
    logger.info("=" * 60)

    # Close database connections
    logger.info("Closing database connections...")
    await close_database()
    logger.info("Database connections closed")

    logger.info("Shutdown complete")
    logger.info("=" * 60)


async def main():
    """Main application entry point."""
    try:
        # Run startup tasks
        await on_startup()

        # Initialize bot core
        bot_core = BotCore(
            token=Config.BOT_TOKEN,
            rate_limit=Config.RATE_LIMIT,
            use_local_api=Config.USE_LOCAL_API,
            local_api_url=Config.LOCAL_API_SERVER
        )

        # Load common module (basic commands)
        logger.info("Loading modules...")
        bot_core.load_module('modules.common')

        # Load Yandex module if enabled
        if 'modules.yandex' in Config.ENABLED_MODULES:
            bot_core.load_module('modules.yandex')

        # Load GitHub module if enabled
        if 'modules.github' in Config.ENABLED_MODULES:
            bot_core.load_module('modules.github')

        logger.info(f"Loaded modules: {', '.join(bot_core.get_loaded_modules())}")

        # Start periodic cleanup task in background
        cleanup_task = asyncio.create_task(periodic_cleanup())

        # Start bot polling
        logger.info("=" * 60)
        logger.info("✅ Bot is running! Press Ctrl+C to stop")
        logger.info("=" * 60)

        try:
            await bot_core.start_polling()
        finally:
            # Cancel cleanup task
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        await on_shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
