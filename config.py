"""Application configuration.

Loads settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from typing import List

# Base directory
BASE_DIR = Path(__file__).parent


class Config:
    """Application configuration loaded from environment variables."""

    # Telegram Bot
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # Local Bot API Server (for files > 20 MB, up to 2 GB)
    USE_LOCAL_API: bool = os.getenv("USE_LOCAL_API", "false").lower() == "true"
    LOCAL_API_SERVER: str = os.getenv("LOCAL_API_SERVER", "http://telegram-bot-api:8081")
    TELEGRAM_API_ID: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    TELEGRAM_API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")

    # Encryption
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")

    # Yandex OAuth (for user instructions)
    YANDEX_CLIENT_ID: str = os.getenv("YANDEX_CLIENT_ID", "")
    YANDEX_AUTH_URL: str = "https://oauth.yandex.ru/authorize?response_type=token&client_id={client_id}"

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{BASE_DIR / 'bot.db'}"
    )

    # File upload limits
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", 2 * 1024 * 1024 * 1024))  # 2 GB

    # Rate limiting
    RATE_LIMIT: int = int(os.getenv("RATE_LIMIT", 5))  # requests per second per user

    # Temporary files
    TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "/tmp/telegram_bot_files"))
    CLEANUP_INTERVAL_HOURS: int = int(os.getenv("CLEANUP_INTERVAL_HOURS", 24))

    # Enabled modules
    ENABLED_MODULES: List[str] = os.getenv(
        "ENABLED_MODULES",
        "modules.common,modules.yandex,modules.github"
    ).split(",")

    # GitHub Webhooks
    WEBHOOK_HOST: str = os.getenv("WEBHOOK_HOST", "")  # Public IP or domain
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration.

        Raises:
            ValueError: If required settings are missing
        """
        # Validate bot token
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN environment variable is required")

        # Validate encryption key
        if not cls.ENCRYPTION_KEY:
            raise ValueError("ENCRYPTION_KEY environment variable is required")

        # Validate encryption key format (should be base64)
        try:
            import base64
            base64.urlsafe_b64decode(cls.ENCRYPTION_KEY)
        except Exception:
            raise ValueError(
                "ENCRYPTION_KEY must be a valid base64-encoded Fernet key. "
                "Generate one with: from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
            )

        # Validate local API configuration
        if cls.USE_LOCAL_API:
            if not cls.TELEGRAM_API_ID:
                raise ValueError(
                    "TELEGRAM_API_ID is required when USE_LOCAL_API is enabled. "
                    "Get your API credentials from https://my.telegram.org"
                )
            if not cls.TELEGRAM_API_HASH:
                raise ValueError(
                    "TELEGRAM_API_HASH is required when USE_LOCAL_API is enabled. "
                    "Get your API credentials from https://my.telegram.org"
                )

        # Create temp directory if it doesn't exist
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_yandex_auth_url(cls) -> str:
        """Get Yandex OAuth authorization URL for users.

        Returns:
            Full OAuth URL or error message if CLIENT_ID not set
        """
        if not cls.YANDEX_CLIENT_ID:
            return "⚠️ YANDEX_CLIENT_ID not configured"

        return cls.YANDEX_AUTH_URL.format(client_id=cls.YANDEX_CLIENT_ID)

    @classmethod
    def print_config(cls) -> None:
        """Print current configuration (without sensitive data)."""
        print("=" * 50)
        print("Configuration:")
        print("=" * 50)
        print(f"Database URL: {cls.DATABASE_URL}")
        print(f"Max file size: {cls.MAX_FILE_SIZE / (1024**3):.1f} GB")
        print(f"Rate limit: {cls.RATE_LIMIT} req/sec")
        print(f"Temp directory: {cls.TEMP_DIR}")
        print(f"Cleanup interval: {cls.CLEANUP_INTERVAL_HOURS} hours")
        print(f"Enabled modules: {', '.join(cls.ENABLED_MODULES)}")
        print(f"Log level: {cls.LOG_LEVEL}")
        print(f"Bot token: {'*' * 10}{cls.BOT_TOKEN[-4:]}")
        print(f"Encryption key: {'*' * 10}")
        print(f"Local Bot API: {'ENABLED' if cls.USE_LOCAL_API else 'DISABLED'}")
        if cls.USE_LOCAL_API:
            print(f"Local API Server: {cls.LOCAL_API_SERVER}")
            print(f"Telegram API ID: {cls.TELEGRAM_API_ID}")
        print("=" * 50)


# Validate configuration on import
Config.validate()
