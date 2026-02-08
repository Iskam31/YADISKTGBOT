# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Telegram bot for uploading files to Yandex Disk with automatic public link generation. Built with aiogram 3 and async SQLAlchemy, featuring encrypted OAuth token storage and modular architecture.

## Development Commands

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run bot locally
python main.py

# Generate encryption key (required for .env)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Docker Development

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f bot

# Rebuild after code changes
docker-compose up -d --build

# Stop and remove
docker-compose down
```

### Environment Setup

1. Copy `.env.example` to `.env`
2. Set `BOT_TOKEN` (from @BotFather)
3. Set `ENCRYPTION_KEY` (generated with Fernet)
4. Optionally set `YANDEX_CLIENT_ID` for OAuth URL display

## Architecture

### Core Components

**BotCore** (`core/bot.py`): Central bot initialization and module loader
- Creates Bot and Dispatcher with FSM storage
- Registers middleware in order: Logging → RateLimit → Auth
- Dynamically loads modules via `setup()` function pattern
- Modules are registered by calling `bot_core.load_module('modules.name')`

**Database** (`core/database.py`): Async SQLAlchemy setup
- Global session maker initialized via `init_database(url)`
- Use `get_session()` context manager for queries
- Base declarative class for all models
- Must call `create_tables()` on startup

**Token Encryption** (`core/crypto.py`): Fernet-based encryption
- Global singleton pattern with `init_encryption()` and `get_encryption()`
- OAuth tokens are encrypted before database storage
- All token operations must use this encryption layer

**Middleware** (`core/middleware.py`):
- LoggingMiddleware: Logs all updates with user context
- RateLimitMiddleware: Per-user rate limiting (default 5 req/sec)
- AuthMiddleware: Placeholder for future authentication checks

### Module System

Modules are self-contained packages in `modules/` directory. Each module must:

1. Implement a `setup(dp)` function in `__init__.py`
2. Create an aiogram Router for handlers
3. Register the router via `dp.include_router(router)`
4. Be added to `ENABLED_MODULES` in `.env` to load

**Example module structure:**
```python
# modules/example/__init__.py
def setup(dp):
    from .handlers import router
    dp.include_router(router)
    print("✅ Example module loaded")

# modules/example/handlers.py
from aiogram import Router
router = Router(name="example")
# Define handlers here
```

### Yandex Disk Module

**Service Layer** (`modules/yandex/service.py`): YandexDiskAPI class
- REST API client for Yandex Disk operations
- Methods: upload, delete, create folder, list files
- Handles OAuth token in headers
- All operations are async with aiohttp

**Handlers** (`modules/yandex/handlers.py`): FSM-based interaction flow
- TokenSetup states: waiting_for_token → waiting_for_folder_name
- FileUpload state: uploading (shows progress)
- Uses inline keyboards for user choices
- Automatically deletes messages containing tokens

**Models** (`modules/yandex/models.py`): Database tables
- YandexToken: Encrypted OAuth tokens per user
- UploadedFile: File metadata and public URLs

**Utilities** (`modules/yandex/utils.py`):
- Progress bar rendering
- File size/date formatting
- Temporary file management
- Filename sanitization

## Key Patterns

### FSM (Finite State Machine)
States are defined as StatesGroup classes and managed via FSMContext:
```python
class ExampleFlow(StatesGroup):
    step1 = State()
    step2 = State()

@router.message(Command('start'))
async def start_flow(message: Message, state: FSMContext):
    await state.set_state(ExampleFlow.step1)
```

### Database Sessions
Always use the async context manager:
```python
from core.database import get_session

async with get_session() as session:
    result = await session.execute(query)
    # Session commits automatically on success
```

### Token Encryption
Encrypt before storing, decrypt before using:
```python
from core.crypto import get_encryption

encryption = get_encryption()
encrypted = encryption.encrypt(plain_token)  # Store this
plain = encryption.decrypt(encrypted)  # Use this
```

### File Uploads
Temporary files are downloaded from Telegram, uploaded to Yandex, then cleaned up:
```python
from modules.yandex.utils import download_telegram_file, cleanup_temp_file

file_path = await download_telegram_file(bot, file_id, user_id)
try:
    # Upload to Yandex
    pass
finally:
    await cleanup_temp_file(file_path)
```

## Important Notes

- **Startup Order**: Environment → Database → Encryption → BotCore → Modules
- **Middleware Order**: Registration order determines execution order
- **Module Loading**: Modules fail silently if not in ENABLED_MODULES
- **Docker Database**: Uses named volume `bot_data` to persist SQLite database
- **Cleanup Task**: Background task runs every CLEANUP_INTERVAL_HOURS to remove old temp files
- **Token Security**: Always delete messages containing OAuth tokens immediately
- **Error Handling**: Handlers should catch exceptions and provide user-friendly messages

## Testing Notes

No automated tests currently exist. When testing:
- Test with various file types (document, photo, video, audio, voice)
- Verify token encryption/decryption round-trip
- Test rate limiting with rapid requests
- Verify temp file cleanup
- Test FSM state transitions

## Future Module Examples

To add a new module like GitHub integration:
1. Create `modules/github/` directory
2. Implement `setup(dp)` in `__init__.py`
3. Create handlers with Router
4. Add to `ENABLED_MODULES` in `.env`
5. Follow same patterns as yandex module
