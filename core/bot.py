"""Bot initialization and module loading.

Provides BotCore class for:
- Creating Bot and Dispatcher
- Registering middleware
- Loading modules
- Running polling
"""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from typing import List, Callable, Awaitable, Optional
import logging
import importlib

from core.middleware import LoggingMiddleware, RateLimitMiddleware, AuthMiddleware

logger = logging.getLogger(__name__)


class BotCore:
    """Core bot class handling initialization and module management."""

    def __init__(
        self,
        token: str,
        rate_limit: int = 5,
        use_local_api: bool = False,
        local_api_url: Optional[str] = None
    ):
        """Initialize bot core.

        Args:
            token: Telegram bot token
            rate_limit: Rate limit per user (requests per second)
            use_local_api: Whether to use local Bot API server
            local_api_url: URL of local Bot API server (if use_local_api is True)
        """
        logger.info("Initializing BotCore...")

        # Create session for local API if needed
        session: Optional[AiohttpSession] = None
        if use_local_api:
            if not local_api_url:
                raise ValueError("local_api_url is required when use_local_api is True")

            logger.info(f"Using LOCAL Bot API Server: {local_api_url}")
            try:
                # Note: is_local=True because telegram-bot-api-data volume is mounted
                # Files are accessed directly from filesystem
                session = AiohttpSession(
                    api=TelegramAPIServer.from_base(local_api_url, is_local=True)
                )
            except Exception as e:
                raise ConnectionError(
                    f"Failed to connect to local Bot API server at {local_api_url}. "
                    f"Make sure the telegram-bot-api service is running and accessible. "
                    f"Error: {e}"
                )
        else:
            logger.info("Using PUBLIC Telegram Bot API")

        # Create bot with default properties
        self.bot = Bot(
            token=token,
            session=session,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML,
            )
        )

        # Create dispatcher with FSM storage
        self.dp = Dispatcher(storage=MemoryStorage())

        # Register middleware
        self._register_middleware(rate_limit)

        # Store loaded modules
        self._loaded_modules: List[str] = []

        logger.info("BotCore initialized successfully")

    def _register_middleware(self, rate_limit: int) -> None:
        """Register middleware in correct order.

        Args:
            rate_limit: Rate limit for RateLimitMiddleware
        """
        logger.info("Registering middleware...")

        # Order matters: Logging -> RateLimit -> Auth
        self.dp.update.middleware(LoggingMiddleware())
        self.dp.update.middleware(RateLimitMiddleware(rate_limit=rate_limit))
        self.dp.update.middleware(AuthMiddleware())

        logger.info("Middleware registered: Logging, RateLimit, Auth")

    def load_module(self, module_path: str) -> None:
        """Load a module and register its handlers.

        Args:
            module_path: Python import path (e.g., 'modules.yandex')

        Raises:
            ImportError: If module cannot be imported
            AttributeError: If module doesn't have setup() function
        """
        logger.info(f"Loading module: {module_path}")

        try:
            # Import module
            module = importlib.import_module(module_path)

            # Check if module has setup function
            if not hasattr(module, 'setup'):
                raise AttributeError(f"Module {module_path} must have a setup() function")

            # Call setup function with dispatcher
            setup_func = getattr(module, 'setup')
            setup_func(self.dp)

            self._loaded_modules.append(module_path)
            logger.info(f"Module loaded successfully: {module_path}")

        except ImportError as e:
            logger.error(f"Failed to import module {module_path}: {e}")
            raise
        except AttributeError as e:
            logger.error(f"Module {module_path} missing setup() function: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading module {module_path}: {e}", exc_info=True)
            raise

    def load_modules(self, module_paths: List[str]) -> None:
        """Load multiple modules.

        Args:
            module_paths: List of Python import paths
        """
        logger.info(f"Loading {len(module_paths)} modules...")

        for module_path in module_paths:
            try:
                self.load_module(module_path)
            except Exception as e:
                logger.error(f"Skipping module {module_path} due to error: {e}")
                # Continue loading other modules
                continue

        logger.info(f"Loaded {len(self._loaded_modules)}/{len(module_paths)} modules successfully")

    async def on_startup(self) -> None:
        """Execute startup tasks.

        Called when bot starts.
        """
        logger.info("Bot starting up...")
        logger.info(f"Loaded modules: {', '.join(self._loaded_modules)}")

        # Get bot info
        me = await self.bot.get_me()
        logger.info(f"Bot started: @{me.username} (ID: {me.id})")

    async def on_shutdown(self) -> None:
        """Execute shutdown tasks.

        Called when bot stops.
        """
        logger.info("Bot shutting down...")

        # Close bot session
        await self.bot.session.close()

        logger.info("Bot shutdown complete")

    async def start_polling(self) -> None:
        """Start bot polling.

        Blocks until stopped (Ctrl+C).
        """
        logger.info("Starting polling...")

        try:
            # Execute startup tasks
            await self.on_startup()

            # Start polling
            await self.dp.start_polling(
                self.bot,
                allowed_updates=self.dp.resolve_used_update_types(),
            )

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error during polling: {e}", exc_info=True)
            raise
        finally:
            # Execute shutdown tasks
            await self.on_shutdown()

    def get_loaded_modules(self) -> List[str]:
        """Get list of loaded modules.

        Returns:
            List of module paths
        """
        return self._loaded_modules.copy()
