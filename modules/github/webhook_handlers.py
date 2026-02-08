"""GitHub webhook event handlers.

Parses webhook payloads, formats notification messages,
and sends them to subscribed Telegram users.
"""

import logging
from typing import Optional, List

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from core.database import get_session
from core.crypto import get_encryption
from .models import GitHubWebhook, GitHubWebhookSub

logger = logging.getLogger(__name__)

# Events we send notifications for (action filtering)
NOTIFY_ACTIONS = {
    "pull_request": {"opened", "closed", "reopened"},
    "issues": {"opened", "closed", "reopened"},
    "pull_request_review": {"submitted"},
    "issue_comment": {"created"},
    "check_run": {"completed"},
}


async def get_webhook_secret(repo_full_name: str) -> Optional[str]:
    """Look up and decrypt the webhook secret for a repository.

    Args:
        repo_full_name: "owner/name" format

    Returns:
        Decrypted secret string or None if not found
    """
    parts = repo_full_name.split("/", 1)
    if len(parts) != 2:
        return None

    owner, name = parts

    try:
        async with get_session() as session:
            result = await session.execute(
                select(GitHubWebhook).where(
                    GitHubWebhook.repo_owner == owner,
                    GitHubWebhook.repo_name == name,
                    GitHubWebhook.is_active == True,
                )
            )
            webhook = result.scalar_one_or_none()

            if not webhook:
                return None

            encryption = get_encryption()
            return encryption.decrypt(webhook.encrypted_secret)
    except Exception as e:
        logger.error(f"Error getting webhook secret for {repo_full_name}: {e}")
        return None


async def get_subscribed_users(owner: str, name: str) -> List[int]:
    """Get all user_ids subscribed to notifications for a repository."""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(GitHubWebhookSub.user_id).where(
                    GitHubWebhookSub.repo_owner == owner,
                    GitHubWebhookSub.repo_name == name,
                )
            )
            return [row[0] for row in result.all()]
    except Exception as e:
        logger.error(f"Error getting subscribed users for {owner}/{name}: {e}")
        return []


async def process_event(event_type: str, payload: dict, bot: Bot) -> None:
    """Process a GitHub webhook event and send notifications.

    Args:
        event_type: GitHub event type header value
        payload: Parsed JSON payload
        bot: Telegram Bot instance for sending messages
    """
    repo = payload.get("repository", {})
    owner = repo.get("owner", {}).get("login", "")
    name = repo.get("name", "")

    if not owner or not name:
        logger.warning(f"Missing repo info in webhook payload for event {event_type}")
        return

    # Filter by action for events that have one
    action = payload.get("action")
    if event_type in NOTIFY_ACTIONS:
        if action not in NOTIFY_ACTIONS[event_type]:
            logger.debug(f"Skipping {event_type} action={action} for {owner}/{name}")
            return

    # Format notification
    text, url = format_event(event_type, payload, owner, name)
    if not text:
        logger.debug(f"No notification text for {event_type} in {owner}/{name}")
        return

    # Build inline keyboard with link
    keyboard = None
    if url:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Открыть на GitHub", url=url)]
        ])

    # Get subscribed users and send notifications
    user_ids = await get_subscribed_users(owner, name)
    if not user_ids:
        logger.debug(f"No subscribers for {owner}/{name}")
        return

    logger.info(f"Sending {event_type} notification for {owner}/{name} to {len(user_ids)} users")

    for user_id in user_ids:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.warning(f"Failed to send notification to {user_id}: {e}")


def format_event(event_type: str, payload: dict, owner: str, name: str) -> tuple:
    """Format a webhook event into notification text and URL.

    Returns:
        (text, url) tuple. text may be None if event should be skipped.
    """
    formatters = {
        "push": _format_push,
        "pull_request": _format_pull_request,
        "issues": _format_issues,
        "pull_request_review": _format_pr_review,
        "issue_comment": _format_issue_comment,
        "check_run": _format_check_run,
    }

    formatter = formatters.get(event_type)
    if not formatter:
        return None, None

    return formatter(payload, owner, name)


def _format_push(payload: dict, owner: str, name: str) -> tuple:
    """Format push event notification."""
    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "")
    pusher = payload.get("pusher", {}).get("name", "unknown")
    commits = payload.get("commits", [])
    compare_url = payload.get("compare", "")

    if not commits:
        return None, None

    text = (
        f"🔄 <b>Push в {owner}/{name}</b>\n\n"
        f"👤 {pusher} → <code>{branch}</code>\n"
        f"📦 {len(commits)} commit(s):\n"
    )

    for commit in commits[:5]:
        sha = commit.get("id", "")[:7]
        msg = commit.get("message", "").split("\n")[0]
        if len(msg) > 60:
            msg = msg[:57] + "..."
        text += f"• <code>{sha}</code> {msg}\n"

    if len(commits) > 5:
        text += f"  ... и ещё {len(commits) - 5}\n"

    return text, compare_url


def _format_pull_request(payload: dict, owner: str, name: str) -> tuple:
    """Format pull_request event notification."""
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    number = pr.get("number")
    title = pr.get("title", "")
    user = pr.get("user", {}).get("login", "unknown")
    html_url = pr.get("html_url", "")
    head = pr.get("head", {}).get("ref", "")
    base = pr.get("base", {}).get("ref", "")
    merged = pr.get("merged", False)

    if action == "closed" and merged:
        action_text = "merged"
        icon = "🟣"
    elif action == "closed":
        action_text = "closed"
        icon = "🔴"
    elif action == "opened":
        action_text = "opened"
        icon = "🟢"
    elif action == "reopened":
        action_text = "reopened"
        icon = "🔵"
    else:
        action_text = action
        icon = "🔀"

    text = (
        f"{icon} <b>PR #{number} {action_text}</b> в {owner}/{name}\n\n"
        f"📝 {title}\n"
        f"👤 {user}\n"
        f"🌿 <code>{head}</code> → <code>{base}</code>"
    )

    return text, html_url


def _format_issues(payload: dict, owner: str, name: str) -> tuple:
    """Format issues event notification."""
    action = payload.get("action", "")
    issue = payload.get("issue", {})
    number = issue.get("number")
    title = issue.get("title", "")
    user = issue.get("user", {}).get("login", "unknown")
    html_url = issue.get("html_url", "")

    if action == "opened":
        icon = "🟢"
    elif action == "closed":
        icon = "🔴"
    elif action == "reopened":
        icon = "🔵"
    else:
        icon = "📝"

    text = (
        f"{icon} <b>Issue #{number} {action}</b> в {owner}/{name}\n\n"
        f"📌 {title}\n"
        f"👤 {user}"
    )

    return text, html_url


def _format_pr_review(payload: dict, owner: str, name: str) -> tuple:
    """Format pull_request_review event notification."""
    review = payload.get("review", {})
    pr = payload.get("pull_request", {})
    number = pr.get("number")
    reviewer = review.get("user", {}).get("login", "unknown")
    state = review.get("state", "")
    body = review.get("body") or ""
    html_url = review.get("html_url", "")

    state_map = {
        "approved": ("✅", "approved"),
        "changes_requested": ("🔶", "requested changes"),
        "commented": ("💬", "commented"),
    }
    icon, state_text = state_map.get(state, ("👀", state))

    text = (
        f"{icon} <b>Review на PR #{number}</b> в {owner}/{name}\n\n"
        f"👤 {reviewer}: {state_text}"
    )

    if body:
        preview = body[:150] + ("..." if len(body) > 150 else "")
        text += f"\n💬 {preview}"

    return text, html_url


def _format_issue_comment(payload: dict, owner: str, name: str) -> tuple:
    """Format issue_comment event notification."""
    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    number = issue.get("number")
    user = comment.get("user", {}).get("login", "unknown")
    body = comment.get("body", "")
    html_url = comment.get("html_url", "")

    # Determine if it's an issue or PR comment
    is_pr = "pull_request" in issue
    item_type = "PR" if is_pr else "Issue"

    preview = body[:200] + ("..." if len(body) > 200 else "")

    text = (
        f"💬 <b>Комментарий к {item_type} #{number}</b> в {owner}/{name}\n\n"
        f"👤 {user}:\n"
        f"{preview}"
    )

    return text, html_url


def _format_check_run(payload: dict, owner: str, name: str) -> tuple:
    """Format check_run event notification."""
    check_run = payload.get("check_run", {})
    cr_name = check_run.get("name", "unknown")
    conclusion = check_run.get("conclusion")
    status = check_run.get("status", "")
    html_url = check_run.get("html_url", "")
    head_branch = check_run.get("check_suite", {}).get("head_branch", "")

    if status != "completed":
        return None, None

    conclusion_map = {
        "success": ("✅", "passed"),
        "failure": ("❌", "failed"),
        "cancelled": ("⏹", "cancelled"),
        "timed_out": ("⏰", "timed out"),
        "action_required": ("⚠️", "action required"),
        "neutral": ("➖", "neutral"),
        "skipped": ("⏭", "skipped"),
    }
    icon, conclusion_text = conclusion_map.get(conclusion, ("❓", conclusion or "unknown"))

    text = (
        f"{icon} <b>CI: {cr_name} {conclusion_text}</b>\n\n"
        f"📂 {owner}/{name}"
    )
    if head_branch:
        text += f" | 🌿 <code>{head_branch}</code>"

    return text, html_url
