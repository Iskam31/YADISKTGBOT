"""Middleware for aiogram bot.

Provides:
- AuthMiddleware: Check user registration
- LoggingMiddleware: Log all events
- RateLimitMiddleware: Rate limiting per user
"""

from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Log all incoming updates."""

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Process update and log it.

        Args:
            handler: Next handler in chain
            event: Incoming update
            data: Context data

        Returns:
            Handler result
        """
        user_id = None
        event_type = "unknown"

        if event.message:
            user_id = event.message.from_user.id
            event_type = "message"
            logger.info(
                f"Message from user {user_id}: {event.message.text[:50] if event.message.text else 'media'}"
            )
        elif event.callback_query:
            user_id = event.callback_query.from_user.id
            event_type = "callback"
            logger.info(
                f"Callback from user {user_id}: {event.callback_query.data}"
            )

        try:
            result = await handler(event, data)
            logger.debug(f"Successfully processed {event_type} from user {user_id}")
            return result
        except Exception as e:
            logger.error(f"Error processing {event_type} from user {user_id}: {e}", exc_info=True)
            raise


class RateLimitMiddleware(BaseMiddleware):
    """Rate limit users to prevent spam.

    Limits users to N requests per second.
    """

    def __init__(self, rate_limit: int = 5):
        """Initialize rate limiter.

        Args:
            rate_limit: Maximum requests per second per user
        """
        super().__init__()
        self.rate_limit = rate_limit
        self.user_requests: Dict[int, list] = defaultdict(list)
        logger.info(f"Rate limit middleware initialized: {rate_limit} req/sec")

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Check rate limit and process update.

        Args:
            handler: Next handler in chain
            event: Incoming update
            data: Context data

        Returns:
            Handler result or None if rate limited
        """
        user_id = None

        if event.message:
            user_id = event.message.from_user.id
        elif event.callback_query:
            user_id = event.callback_query.from_user.id

        if user_id is None:
            return await handler(event, data)

        # Check rate limit
        current_time = time.time()
        user_times = self.user_requests[user_id]

        # Remove old timestamps (older than 1 second)
        user_times[:] = [t for t in user_times if current_time - t < 1.0]

        if len(user_times) >= self.rate_limit:
            logger.warning(f"Rate limit exceeded for user {user_id}")

            # Send warning message
            if event.message:
                await event.message.answer(
                    "⚠️ Слишком много запросов. Подождите немного."
                )
            elif event.callback_query:
                await event.callback_query.answer(
                    "⚠️ Слишком много запросов. Подождите немного.",
                    show_alert=True
                )
            return None

        # Add current request
        user_times.append(current_time)

        return await handler(event, data)


class AuthMiddleware(BaseMiddleware):
    """Check if user is registered (has Yandex token).

    Only checks for commands that require authentication.
    """

    # Commands that don't require authentication
    ALLOWED_COMMANDS = {'/start', '/help', '/token'}

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        """Check authentication and process update.

        Args:
            handler: Next handler in chain
            event: Incoming update
            data: Context data

        Returns:
            Handler result or None if not authenticated
        """
        # Only check messages (not callbacks)
        if not event.message:
            return await handler(event, data)

        message = event.message

        # Check if it's a command
        if not message.text or not message.text.startswith('/'):
            # Not a command, might be file upload or token input
            # Let handlers decide if auth is needed
            return await handler(event, data)

        # Extract command
        command = message.text.split()[0].split('@')[0]

        # Allow certain commands without auth
        if command in self.ALLOWED_COMMANDS:
            return await handler(event, data)

        # For other commands, check if user has token
        # This is a simplified check - actual implementation will query database
        # For now, we'll let all commands through and let handlers check
        # TODO: Add database check here once models are ready
        logger.debug(f"Auth check for command {command} from user {message.from_user.id}")

        return await handler(event, data)
