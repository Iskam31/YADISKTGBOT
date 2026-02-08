# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Telegram bot for uploading files to Yandex Disk and managing GitHub repositories. Built with aiogram 3 and async SQLAlchemy, featuring encrypted OAuth token storage and modular architecture.

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
4. Set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` (from https://my.telegram.org)
5. Optionally set `YANDEX_CLIENT_ID` for OAuth URL display

**Local Bot API Server** (for files > 20MB, up to 2GB):
- `USE_LOCAL_API=true` - enables local Bot API server
- `LOCAL_API_SERVER=http://telegram-bot-api:8081` - local API URL
- `TELEGRAM_LOCAL=1` - enables --local flag on telegram-bot-api
- Volume `telegram-bot-api-data` must be mounted to both containers
- Bot uses `is_local=True` for direct filesystem access

## Architecture

### Core Components

**BotCore** (`core/bot.py`): Central bot initialization and module loader
- Creates Bot and Dispatcher with FSM storage
- Supports local Bot API server with `is_local=True` for large files
- Registers middleware in order: Logging → RateLimit → Auth
- Dynamically loads modules via `setup()` function pattern
- Modules are registered by calling `bot_core.load_module('modules.name')`

**Common Module** (`modules/common/`): Core bot commands and UI
- Commands: /start, /menu, /help
- Main menu with persistent ReplyKeyboard (5 buttons: Upload, My Files, GitHub, Settings, Help)
- Button handlers that delegate to specialized modules
- get_main_menu() must be used after ALL operations to restore UI

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

### GitHub Module

**Service Layer** (`modules/github/service.py`): GitHubAPI class
- REST API client for GitHub (base URL: https://api.github.com)
- Auth via Bearer token (Personal Access Token)
- Methods: check_token, get_repo, list_repos, list_issues, create_issue, close_issue, get_issue, list_pulls, get_pull
- list_repos uses `affiliation=owner,collaborator` to include collab repos
- list_issues fetches up to 300 items and filters out PRs (GitHub mixes them in /issues endpoint)
- All operations are async with aiohttp, 15s timeout

**Handlers** (`modules/github/handlers.py`): FSM-based interaction flow
- GitHubSetup states: waiting_for_token
- GitHubRepoAdd states: waiting_for_repo
- GitHubIssueCreate states: waiting_for_title → waiting_for_body
- Commands: /github, /gh_token, /repo (add|list|set), /issue, /issues, /issue_close, /prs, /pr
- Button "🐙 GitHub" in main menu opens inline submenu
- Import repos from GitHub API with one-click adding
- Automatically deletes messages containing tokens

**Keyboards** (`modules/github/keyboards.py`): UI components
- get_github_menu_keyboard: Main submenu (repos, issues, PRs)
- get_repo_list_keyboard: User's linked repos with import button
- get_import_repos_keyboard: GitHub repos available for import with pagination
- get_issues_keyboard / get_pulls_keyboard: Paginated lists
- get_repo_select_keyboard: Choose repo for actions when no default set

**Models** (`modules/github/models.py`): Database tables
- GitHubToken: Encrypted PAT per user with github_username
- GitHubRepo: Linked repos with owner/name, is_default flag, unique constraint on (user_id, owner, name)

### Yandex Disk Module

**Service Layer** (`modules/yandex/service.py`): YandexDiskAPI class
- REST API client for Yandex Disk operations
- Methods: upload, delete, create_folder, list_directory, publish_resource, get_resource_info
- Handles OAuth token in headers
- All operations are async with aiohttp

**Handlers** (`modules/yandex/handlers.py`): FSM-based interaction flow
- TokenSetup states: waiting_for_token → waiting_for_folder_name
- FileUpload state: uploading (shows progress)
- FileNavigation state: browsing (navigating through Yandex Disk)
- Uses inline keyboards for user choices
- Automatically deletes messages containing tokens
- Full disk navigation with breadcrumbs, pagination, public link generation

**Keyboards** (`modules/yandex/keyboards.py`): UI components
- get_file_browser_keyboard: Complex navigation with folders, files, pagination
- get_mode_selection_keyboard: Choose between uploaded files or full disk
- Smart path encoding (base64 for short paths, MD5 hash for long paths)
- Breadcrumb formatting for current directory path

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

### Main Menu and ReplyKeyboard
CRITICAL: Always return main menu after completing operations:
```python
from modules.common.keyboards import get_main_menu

# After finishing any operation (token setup, cancel, error)
await message.answer("Operation complete", reply_markup=get_main_menu())
```

**Common ReplyKeyboard pitfalls:**
- Never use `reply_markup=None` - it leaves old keyboards visible
- Always use `get_main_menu()` to restore main menu
- Import `get_main_menu` at module level, not locally
- After editing inline messages, send new message with main menu

## Important Notes

- **Startup Order**: Environment → Database → Import all models → create_tables() → Encryption → BotCore → Modules
- **Middleware Order**: Registration order determines execution order
- **Module Loading**: Modules fail silently if not in ENABLED_MODULES
- **Docker Database**: Uses named volume `bot_data` to persist SQLite database
- **Docker Volumes**: `telegram-bot-api-data` must be mounted to both bot and telegram-bot-api containers (read-only for bot)
- **Cleanup Task**: Background task runs every CLEANUP_INTERVAL_HOURS to remove old temp files
- **Token Security**: Always delete messages containing OAuth tokens immediately
- **Error Handling**: Handlers should catch exceptions and provide user-friendly messages
- **Large Files**: Files >20MB require local Bot API server with proper volume mounting
- **File Downloads**: With `is_local=True`, Telegram returns absolute filesystem paths, not HTTP URLs
- **Callback Data Limit**: 64 bytes max - use smart encoding (base64 or MD5 hash) for long paths

## Critical Bug Fixes

**0. Models must be imported before create_tables() (CRITICAL)**
```python
# In main.py — import ALL models before create_tables()
# Otherwise new module tables won't be created in the database
import modules.yandex.models  # noqa: F401
import modules.github.models  # noqa: F401
await create_tables()
```

**0b. Handler registration order matters in aiogram (CRITICAL)**
```python
# WRONG - generic handler catches specific callbacks and silently returns
@router.callback_query(F.data.startswith("gh_repo_"))  # Registered FIRST
async def generic_handler(...): ...

@router.callback_query(F.data.startswith("gh_repo_pulls_"))  # Never reached!
async def specific_handler(...): ...

# CORRECT - register specific handlers BEFORE generic catch-all
@router.callback_query(F.data.startswith("gh_repo_pulls_"))  # Registered FIRST
async def specific_handler(...): ...

@router.callback_query(F.data.startswith("gh_repo_"))  # Catch-all LAST
async def generic_handler(...): ...
```

**0c. Use scalars().first() not scalar_one_or_none() for existence checks**
```python
# WRONG - raises MultipleResultsFound when >1 row exists
result = await session.execute(select(Model).where(Model.user_id == uid))
has_any = result.scalar_one_or_none() is not None

# CORRECT
has_any = result.scalars().first() is not None
```

**1. Missing @asynccontextmanager (CRITICAL)**
```python
# WRONG - causes "async_generator does not support async context manager protocol"
async def get_session():
    async with _session_maker() as session:
        yield session

# CORRECT - must have decorator
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_session():
    async with _session_maker() as session:
        yield session
```

**2. Wrong user_id in callback handlers**
```python
# WRONG - callback.message.from_user.id returns BOT's ID
async def callback_handler(callback: CallbackQuery):
    user_id = callback.message.from_user.id  # BUG!

# CORRECT - use callback.from_user.id
async def callback_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
```

**3. Local Bot API configuration**
```python
# Required for Docker with separate containers:
# 1. Set TELEGRAM_LOCAL=1 to enable --local flag
# 2. Mount telegram-bot-api-data volume to both containers
# 3. Use is_local=True in TelegramAPIServer.from_base()

session = AiohttpSession(
    api=TelegramAPIServer.from_base(local_api_url, is_local=True)
)
```

## Testing Notes

No automated tests currently exist. All testing via Docker:
```bash
docker-compose up -d --build && docker-compose logs -f bot
```

**Yandex Disk testing:**
- Test with various file types (document, photo, video, audio, voice)
- Test files >20MB to verify local Bot API works
- Verify token encryption/decryption round-trip
- Test rate limiting with rapid requests
- Verify temp file cleanup
- Test disk navigation with long folder paths

**GitHub testing:**
- Connect with PAT (/gh_token), verify token deleted from chat
- Import repos — verify own + collaborator repos appear
- Add repo manually (/repo add owner/name)
- Set default repo (/repo set owner/name)
- Create issue (/issue Title), verify it appears on GitHub
- List issues (/issues) — verify PRs are filtered out
- Close issue (/issue_close 123)
- List PRs (/prs), view PR details (/pr 15) — check merge/conflict status
- Test pagination on repos with many issues/PRs

**General:**
- Verify main menu appears after all operations
- Test FSM state transitions (cancel mid-flow)

## Future Module Examples

To add a new module:
1. Create `modules/mymodule/` directory with models.py, service.py, keyboards.py, handlers.py
2. Implement `setup(dp)` in `__init__.py`
3. Import models in `main.py` before `create_tables()`
4. Add loading logic in `main.py`
5. Add to `ENABLED_MODULES` default in `config.py`
6. Follow same patterns as yandex/github modules
