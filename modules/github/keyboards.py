"""Telegram keyboards for GitHub module."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Optional


def get_github_menu_keyboard(has_token: bool = False) -> InlineKeyboardMarkup:
    """Main GitHub submenu."""
    buttons = []
    if not has_token:
        buttons.append([InlineKeyboardButton(text="🔑 Подключить GitHub", callback_data="gh_connect")])
    else:
        buttons.append([InlineKeyboardButton(text="📂 Репозитории", callback_data="gh_repos")])
        buttons.append([
            InlineKeyboardButton(text="📝 Issues", callback_data="gh_issues"),
            InlineKeyboardButton(text="🔀 Pull Requests", callback_data="gh_pulls"),
        ])
        buttons.append([InlineKeyboardButton(text="🔑 Переподключить токен", callback_data="gh_connect")])
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="gh_close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_repo_list_keyboard(repos: List[dict], page: int = 1) -> InlineKeyboardMarkup:
    """Keyboard with list of user's repos."""
    buttons = []
    for repo in repos:
        full_name = repo["full_name"]
        is_default = repo.get("is_default", False)
        prefix = "⭐ " if is_default else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{prefix}{full_name}",
                callback_data=f"gh_repo_{full_name}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="📥 Импорт из GitHub", callback_data="gh_repo_import")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить вручную", callback_data="gh_repo_add")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="gh_back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_repo_actions_keyboard(owner: str, name: str, is_default: bool) -> InlineKeyboardMarkup:
    """Actions for a specific repo."""
    full_name = f"{owner}/{name}"
    buttons = [
        [InlineKeyboardButton(text="📝 Issues", callback_data=f"gh_repo_issues_{full_name}")],
        [InlineKeyboardButton(text="🔀 Pull Requests", callback_data=f"gh_repo_pulls_{full_name}")],
    ]
    if not is_default:
        buttons.append([
            InlineKeyboardButton(text="⭐ Сделать по умолчанию", callback_data=f"gh_repo_default_{full_name}")
        ])
    buttons.append([
        InlineKeyboardButton(text="🗑 Удалить из списка", callback_data=f"gh_repo_remove_{full_name}")
    ])
    buttons.append([InlineKeyboardButton(text="⬅️ К репозиториям", callback_data="gh_repos")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_issues_keyboard(
    issues: List[dict], owner: str, name: str, page: int = 1
) -> InlineKeyboardMarkup:
    """Keyboard with list of issues."""
    buttons = []
    for issue in issues:
        number = issue["number"]
        title = issue["title"]
        display = title if len(title) <= 35 else title[:32] + "..."
        state_icon = "🟢" if issue["state"] == "open" else "🔴"
        buttons.append([
            InlineKeyboardButton(
                text=f"{state_icon} #{number} {display}",
                callback_data=f"gh_issue_{owner}/{name}_{number}"
            )
        ])

    # Pagination
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"gh_issues_page_{owner}/{name}_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page}", callback_data="noop"))
    nav.append(InlineKeyboardButton(text="➡️", callback_data=f"gh_issues_page_{owner}/{name}_{page + 1}"))
    buttons.append(nav)

    buttons.append([
        InlineKeyboardButton(text="➕ Создать issue", callback_data=f"gh_issue_create_{owner}/{name}")
    ])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"gh_repo_{owner}/{name}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_issue_detail_keyboard(owner: str, name: str, number: int, state: str) -> InlineKeyboardMarkup:
    """Actions for a specific issue."""
    full_name = f"{owner}/{name}"
    buttons = []
    if state == "open":
        buttons.append([
            InlineKeyboardButton(text="🔴 Закрыть issue", callback_data=f"gh_issue_close_{full_name}_{number}")
        ])
    buttons.append([
        InlineKeyboardButton(text="🔗 Открыть на GitHub", url=f"https://github.com/{full_name}/issues/{number}")
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ К issues", callback_data=f"gh_repo_issues_{full_name}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_pulls_keyboard(
    pulls: List[dict], owner: str, name: str, page: int = 1
) -> InlineKeyboardMarkup:
    """Keyboard with list of pull requests."""
    buttons = []
    for pr in pulls:
        number = pr["number"]
        title = pr["title"]
        display = title if len(title) <= 35 else title[:32] + "..."
        if pr.get("draft"):
            icon = "📝"
        elif pr["state"] == "open":
            icon = "🟢"
        else:
            icon = "🟣"
        buttons.append([
            InlineKeyboardButton(
                text=f"{icon} #{number} {display}",
                callback_data=f"gh_pr_{owner}/{name}_{number}"
            )
        ])

    # Pagination
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"gh_pulls_page_{owner}/{name}_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page}", callback_data="noop"))
    nav.append(InlineKeyboardButton(text="➡️", callback_data=f"gh_pulls_page_{owner}/{name}_{page + 1}"))
    buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"gh_repo_{owner}/{name}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_pr_detail_keyboard(owner: str, name: str, number: int) -> InlineKeyboardMarkup:
    """Actions for a specific PR."""
    full_name = f"{owner}/{name}"
    buttons = [
        [InlineKeyboardButton(
            text="🔗 Открыть на GitHub",
            url=f"https://github.com/{full_name}/pull/{number}"
        )],
        [InlineKeyboardButton(text="⬅️ К PR", callback_data=f"gh_repo_pulls_{full_name}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Cancel keyboard for FSM states."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_repo_select_keyboard(repos: List[dict], action: str) -> InlineKeyboardMarkup:
    """Keyboard to select repo for an action (issues, prs)."""
    buttons = []
    for repo in repos:
        full_name = repo["full_name"]
        is_default = repo.get("is_default", False)
        prefix = "⭐ " if is_default else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{prefix}{full_name}",
                callback_data=f"gh_{action}_{full_name}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="gh_close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_import_repos_keyboard(
    repos: List[dict], already_added: set, page: int = 1
) -> InlineKeyboardMarkup:
    """Keyboard to select repos to import from GitHub.

    Args:
        repos: List of repo dicts from GitHub API
        already_added: Set of full_name strings already in user's list
        page: Current page number
    """
    buttons = []
    for repo in repos:
        full_name = repo["full_name"]
        if full_name in already_added:
            buttons.append([
                InlineKeyboardButton(text=f"✅ {full_name}", callback_data="noop")
            ])
        else:
            private = "🔒" if repo.get("private") else "🌐"
            buttons.append([
                InlineKeyboardButton(
                    text=f"{private} {full_name}",
                    callback_data=f"gh_import_repo_{full_name}"
                )
            ])

    # Pagination
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"gh_import_page_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page}", callback_data="noop"))
    if len(repos) >= 20:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"gh_import_page_{page + 1}"))
    buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="⬅️ К репозиториям", callback_data="gh_repos")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
