"""GitHub webhook HTTP server.

Runs an aiohttp web server alongside the Telegram bot polling
to receive GitHub webhook POST requests at /github/webhook.
"""

import asyncio
import hashlib
import hmac
import json
import logging

from aiohttp import web
from aiogram import Bot

from config import Config

logger = logging.getLogger(__name__)


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature.

    Args:
        payload: Raw request body bytes
        signature: X-Hub-Signature-256 header value
        secret: Webhook secret string

    Returns:
        True if signature is valid
    """
    if not signature.startswith("sha256="):
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", signature)


def create_webhook_handler(bot: Bot):
    """Create the webhook POST handler with bot instance in closure.

    Args:
        bot: Telegram Bot instance for sending notifications
    """

    async def handle_webhook(request: web.Request) -> web.Response:
        """Handle incoming GitHub webhook POST request."""
        # Read body
        body = await request.read()

        # Get headers
        event_type = request.headers.get("X-GitHub-Event")
        delivery_id = request.headers.get("X-GitHub-Delivery")
        signature = request.headers.get("X-Hub-Signature-256")

        if not event_type:
            return web.Response(status=400, text="Missing X-GitHub-Event header")

        # Ping event — GitHub sends this when webhook is first created
        if event_type == "ping":
            logger.info(f"Webhook ping received (delivery={delivery_id})")
            return web.Response(status=200, text="pong")

        if not signature:
            return web.Response(status=400, text="Missing signature")

        # Parse body
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return web.Response(status=400, text="Invalid JSON")

        # Get repo info for secret lookup
        repo = payload.get("repository", {})
        repo_full_name = repo.get("full_name", "")

        if not repo_full_name:
            return web.Response(status=400, text="Missing repository info")

        # Look up webhook secret and verify signature
        from .webhook_handlers import get_webhook_secret, process_event

        secret = await get_webhook_secret(repo_full_name)
        if not secret:
            logger.warning(f"No webhook found for repo {repo_full_name}")
            return web.Response(status=404, text="Webhook not found")

        if not verify_signature(body, signature, secret):
            logger.warning(f"Invalid signature for {repo_full_name}, delivery={delivery_id}")
            return web.Response(status=401, text="Invalid signature")

        logger.info(f"Webhook received: {event_type} for {repo_full_name} (delivery={delivery_id})")

        # Process event
        try:
            await process_event(event_type, payload, bot)
        except Exception as e:
            logger.error(f"Error processing webhook event: {e}", exc_info=True)

        return web.Response(status=200, text="OK")

    return handle_webhook


def create_app(bot: Bot) -> web.Application:
    """Create aiohttp web application for webhooks.

    Args:
        bot: Telegram Bot instance
    """
    app = web.Application()
    app.router.add_post("/github/webhook", create_webhook_handler(bot))
    return app


async def start_webhook_server(bot: Bot) -> None:
    """Start the webhook HTTP server.

    Runs indefinitely until cancelled. Designed to be used with
    asyncio.create_task() alongside bot polling.

    Args:
        bot: Telegram Bot instance for sending notifications
    """
    port = Config.WEBHOOK_PORT

    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"Webhook server started on 0.0.0.0:{port}")
    logger.info(f"Webhook URL: http://{Config.WEBHOOK_HOST}:{port}/github/webhook")

    try:
        # Keep running until cancelled
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()
        logger.info("Webhook server stopped")
