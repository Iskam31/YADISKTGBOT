"""GitHub module.

Provides GitHub integration for the Telegram bot:
- Connect via Personal Access Token
- Manage repositories (add, list, set default)
- Create, list, close issues
- View pull requests with merge/conflict status
"""

from .handlers import setup

__all__ = ['setup']
