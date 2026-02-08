"""Telegram handlers for GitHub module."""

import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, update, delete

from core.database import get_session
from core.crypto import get_encryption
from modules.common.keyboards import get_main_menu
from .models import GitHubToken, GitHubRepo
from .service import GitHubAPI
from .keyboards import (
    get_github_menu_keyboard,
    get_repo_list_keyboard,
    get_repo_actions_keyboard,
    get_issues_keyboard,
    get_issue_detail_keyboard,
    get_pulls_keyboard,
    get_pr_detail_keyboard,
    get_cancel_keyboard,
    get_repo_select_keyboard,
    get_import_repos_keyboard,
)

logger = logging.getLogger(__name__)

router = Router(name="github")


# ==================== FSM States ====================

class GitHubSetup(StatesGroup):
    waiting_for_token = State()


class GitHubRepoAdd(StatesGroup):
    waiting_for_repo = State()


class GitHubIssueCreate(StatesGroup):
    waiting_for_title = State()
    waiting_for_body = State()


# ==================== Helpers ====================

async def get_user_github(user_id: int) -> tuple:
    """Get user's GitHub token and API client.

    Returns:
        (GitHubAPI, GitHubToken) or (None, None)
    """
    try:
        async with get_session() as session:
            result = await session.execute(
                select(GitHubToken).where(GitHubToken.user_id == user_id)
            )
            token_record = result.scalar_one_or_none()

            if not token_record or not token_record.is_valid:
                return None, None

            encryption = get_encryption()
            plain_token = encryption.decrypt(token_record.encrypted_token)
            return GitHubAPI(plain_token), token_record
    except Exception as e:
        logger.error(f"Error getting GitHub token: {e}")
        return None, None


async def get_default_repo(user_id: int) -> GitHubRepo | None:
    """Get user's default repository."""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(GitHubRepo).where(
                    GitHubRepo.user_id == user_id,
                    GitHubRepo.is_default == True
                )
            )
            return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting default repo: {e}")
        return None


async def get_user_repos(user_id: int) -> list:
    """Get all user's linked repos."""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(GitHubRepo)
                .where(GitHubRepo.user_id == user_id)
                .order_by(GitHubRepo.is_default.desc(), GitHubRepo.added_at.desc())
            )
            repos = result.scalars().all()
            return [
                {"full_name": r.full_name, "is_default": r.is_default, "owner": r.owner, "name": r.name}
                for r in repos
            ]
    except Exception as e:
        logger.error(f"Error getting user repos: {e}")
        return []


def parse_repo_name(text: str) -> tuple | None:
    """Parse 'owner/name' string. Returns (owner, name) or None."""
    text = text.strip()
    if "/" not in text:
        return None
    parts = text.split("/", 1)
    owner = parts[0].strip()
    name = parts[1].strip()
    if not owner or not name:
        return None
    return owner, name


def format_datetime_short(dt_str: str | None) -> str:
    """Format ISO datetime string to short form."""
    if not dt_str:
        return "N/A"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return dt_str[:10] if dt_str else "N/A"


# ==================== GitHub Menu ====================

@router.message(Command("github"))
async def cmd_github(message: Message) -> None:
    """Handle /github command — show GitHub submenu."""
    api, _ = await get_user_github(message.from_user.id)
    has_token = api is not None

    await message.answer(
        "🐙 <b>GitHub</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=get_github_menu_keyboard(has_token)
    )


@router.message(F.text == "🐙 GitHub")
async def button_github(message: Message) -> None:
    """Handle GitHub button from main menu."""
    await cmd_github(message)


@router.callback_query(F.data == "gh_back_menu")
async def callback_back_menu(callback: CallbackQuery) -> None:
    """Return to GitHub main menu."""
    api, _ = await get_user_github(callback.from_user.id)
    has_token = api is not None

    await callback.message.edit_text(
        "🐙 <b>GitHub</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=get_github_menu_keyboard(has_token)
    )
    await callback.answer()


@router.callback_query(F.data == "gh_close")
async def callback_close(callback: CallbackQuery) -> None:
    """Close GitHub menu."""
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


# ==================== Token Setup ====================

@router.message(Command("gh_token"))
async def cmd_gh_token(message: Message, state: FSMContext) -> None:
    """Handle /gh_token command — start token setup."""
    await start_token_setup(message, state)


@router.callback_query(F.data == "gh_connect")
async def callback_gh_connect(callback: CallbackQuery, state: FSMContext) -> None:
    """Start token setup from menu."""
    await callback.message.delete()
    await start_token_setup(callback.message, state, from_user_id=callback.from_user.id)
    await callback.answer()


async def start_token_setup(message: Message, state: FSMContext, from_user_id: int = None) -> None:
    """Start GitHub token setup flow."""
    await state.set_state(GitHubSetup.waiting_for_token)
    if from_user_id:
        await state.update_data(from_user_id=from_user_id)

    await message.answer(
        "🔑 <b>Подключение GitHub</b>\n\n"
        "Для работы нужен Personal Access Token (PAT).\n\n"
        "<b>Как получить:</b>\n"
        "1. Откройте github.com → Settings → Developer settings\n"
        "2. Personal access tokens → Tokens (classic)\n"
        "3. Generate new token (classic)\n"
        "4. Выберите scopes: <code>repo</code> (полный доступ к репозиториям)\n"
        "5. Скопируйте токен и отправьте его сюда\n\n"
        "🔒 <i>Сообщение с токеном будет удалено автоматически</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(GitHubSetup.waiting_for_token)
async def process_gh_token(message: Message, state: FSMContext, bot: Bot) -> None:
    """Process GitHub PAT from user."""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Подключение GitHub отменено", reply_markup=get_main_menu())
        return

    token = message.text.strip()

    # Delete message with token
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        logger.warning(f"Could not delete token message: {e}")

    status_msg = await message.answer("⏳ Проверяю токен...")

    # Validate token
    api = GitHubAPI(token)
    user_info = await api.check_token()

    if not user_info:
        await status_msg.edit_text(
            "❌ <b>Неверный токен</b>\n\n"
            "Токен не прошёл проверку. Убедитесь, что скопировали его полностью.\n\n"
            "Используйте /gh_token для повторной попытки.",
            parse_mode="HTML"
        )
        await state.clear()
        await message.answer("Используйте меню:", reply_markup=get_main_menu())
        return

    # Get user_id
    state_data = await state.get_data()
    user_id = state_data.get("from_user_id") or message.from_user.id

    # Save encrypted token
    try:
        encryption = get_encryption()
        encrypted_token = encryption.encrypt(token)

        async with get_session() as session:
            result = await session.execute(
                select(GitHubToken).where(GitHubToken.user_id == user_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.encrypted_token = encrypted_token
                existing.github_username = user_info["login"]
                existing.is_valid = True
            else:
                session.add(GitHubToken(
                    user_id=user_id,
                    encrypted_token=encrypted_token,
                    github_username=user_info["login"],
                    is_valid=True,
                ))
            await session.commit()

        username = user_info["login"]
        display_name = user_info.get("name") or username

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        after_connect_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Импортировать репозитории", callback_data="gh_repo_import")],
            [InlineKeyboardButton(text="📂 Открыть меню GitHub", callback_data="gh_back_menu")],
        ])

        await status_msg.edit_text(
            f"✅ <b>GitHub подключён!</b>\n\n"
            f"👤 {display_name} (<code>@{username}</code>)\n\n"
            f"Импортируйте ваши репозитории или добавьте вручную.",
            parse_mode="HTML",
            reply_markup=after_connect_kb
        )
        await state.clear()
        await message.answer("Используйте меню:", reply_markup=get_main_menu())

    except Exception as e:
        logger.error(f"Error saving GitHub token: {e}")
        await status_msg.edit_text("❌ Ошибка сохранения токена. Попробуйте позже.")
        await state.clear()
        await message.answer("Используйте меню:", reply_markup=get_main_menu())


# ==================== Repository Management ====================

@router.message(Command("repo"))
async def cmd_repo(message: Message, state: FSMContext) -> None:
    """Handle /repo command with subcommands: add, list, set."""
    args = message.text.split(maxsplit=2)

    if len(args) < 2:
        # No subcommand — show help
        await message.answer(
            "📂 <b>Управление репозиториями</b>\n\n"
            "<code>/repo add owner/name</code> — добавить репозиторий\n"
            "<code>/repo list</code> — список репозиториев\n"
            "<code>/repo set owner/name</code> — установить по умолчанию",
            parse_mode="HTML"
        )
        return

    subcmd = args[1].lower()

    if subcmd == "list":
        await show_repo_list(message)
    elif subcmd == "add":
        if len(args) < 3:
            await state.set_state(GitHubRepoAdd.waiting_for_repo)
            await message.answer(
                "Введите имя репозитория в формате <code>owner/name</code>:",
                parse_mode="HTML",
                reply_markup=get_cancel_keyboard()
            )
        else:
            await add_repo(message, args[2])
    elif subcmd == "set":
        if len(args) < 3:
            await message.answer(
                "Укажите репозиторий: <code>/repo set owner/name</code>",
                parse_mode="HTML"
            )
        else:
            await set_default_repo(message, args[2])
    else:
        await message.answer(
            "Неизвестная подкоманда. Доступны: <code>add</code>, <code>list</code>, <code>set</code>",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "gh_repos")
async def callback_repos(callback: CallbackQuery) -> None:
    """Show repo list via callback."""
    repos = await get_user_repos(callback.from_user.id)

    if not repos:
        await callback.message.edit_text(
            "📂 <b>Репозитории</b>\n\n"
            "У вас нет добавленных репозиториев.\n\n"
            "Добавьте: <code>/repo add owner/name</code>",
            parse_mode="HTML",
            reply_markup=get_repo_list_keyboard([])
        )
    else:
        await callback.message.edit_text(
            "📂 <b>Ваши репозитории</b>\n\n"
            "⭐ — репозиторий по умолчанию",
            parse_mode="HTML",
            reply_markup=get_repo_list_keyboard(repos)
        )
    await callback.answer()


async def show_repo_list(message: Message) -> None:
    """Show user's repo list."""
    repos = await get_user_repos(message.from_user.id)

    if not repos:
        await message.answer(
            "📂 <b>Репозитории</b>\n\n"
            "У вас нет добавленных репозиториев.\n\n"
            "Добавьте: <code>/repo add owner/name</code>",
            parse_mode="HTML"
        )
        return

    text = "📂 <b>Ваши репозитории:</b>\n\n"
    for repo in repos:
        prefix = "⭐ " if repo["is_default"] else "• "
        text += f"{prefix}<code>{repo['full_name']}</code>\n"

    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data == "gh_repo_add")
async def callback_repo_add(callback: CallbackQuery, state: FSMContext) -> None:
    """Start repo add flow from callback."""
    await state.set_state(GitHubRepoAdd.waiting_for_repo)
    await callback.message.answer(
        "Введите имя репозитория в формате <code>owner/name</code>:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


# ==================== Repository Import ====================

@router.callback_query(F.data == "gh_repo_import")
async def callback_repo_import(callback: CallbackQuery) -> None:
    """Show GitHub repos available for import."""
    await show_import_page(callback, page=1)


@router.callback_query(F.data.startswith("gh_import_page_"))
async def callback_import_page(callback: CallbackQuery) -> None:
    """Handle import pagination."""
    page = int(callback.data[len("gh_import_page_"):])
    if page < 1:
        page = 1
    await show_import_page(callback, page)


async def show_import_page(callback: CallbackQuery, page: int) -> None:
    """Fetch and display GitHub repos for import."""
    user_id = callback.from_user.id
    api, _ = await get_user_github(user_id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    repos = await api.list_repos(per_page=20, page=page)
    if repos is None:
        await callback.answer("❌ Ошибка загрузки репозиториев", show_alert=True)
        return

    if not repos:
        await callback.message.edit_text(
            "📥 <b>Импорт репозиториев</b>\n\nРепозитории не найдены.",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Get already added repos
    existing = await get_user_repos(user_id)
    already_added = {r["full_name"] for r in existing}

    await callback.message.edit_text(
        "📥 <b>Импорт репозиториев</b>\n\n"
        "Нажмите на репозиторий чтобы добавить.\n"
        "✅ — уже добавлен",
        parse_mode="HTML",
        reply_markup=get_import_repos_keyboard(repos, already_added, page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gh_import_repo_"))
async def callback_import_repo(callback: CallbackQuery) -> None:
    """Import a single repo from the list."""
    full_name = callback.data[len("gh_import_repo_"):]
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    user_id = callback.from_user.id

    try:
        async with get_session() as session:
            # Check if already added
            result = await session.execute(
                select(GitHubRepo).where(
                    GitHubRepo.user_id == user_id,
                    GitHubRepo.owner == owner,
                    GitHubRepo.name == name
                )
            )
            if result.scalar_one_or_none():
                await callback.answer(f"✅ {full_name} уже добавлен")
                return

            # Check if first repo — make it default
            count_result = await session.execute(
                select(GitHubRepo).where(GitHubRepo.user_id == user_id)
            )
            has_repos = count_result.scalars().first() is not None

            session.add(GitHubRepo(
                user_id=user_id,
                owner=owner,
                name=name,
                is_default=not has_repos,
            ))
            await session.commit()

        await callback.answer(f"✅ {full_name} добавлен!")

        # Refresh the import page
        await show_import_page(callback, page=1)

    except Exception as e:
        logger.error(f"Error importing repo: {e}")
        await callback.answer("❌ Ошибка добавления", show_alert=True)


@router.message(GitHubRepoAdd.waiting_for_repo)
async def process_repo_add(message: Message, state: FSMContext) -> None:
    """Process repo name from FSM."""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Отменено", reply_markup=get_main_menu())
        return

    await add_repo(message, message.text)
    await state.clear()


async def add_repo(message: Message, repo_text: str) -> None:
    """Add a repository for the user."""
    parsed = parse_repo_name(repo_text)
    if not parsed:
        await message.answer(
            "❌ Неверный формат. Используйте: <code>owner/name</code>",
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        return

    owner, name = parsed
    user_id = message.from_user.id

    # Check token
    api, _ = await get_user_github(user_id)
    if not api:
        await message.answer(
            "⚠️ Сначала подключите GitHub: /gh_token",
            reply_markup=get_main_menu()
        )
        return

    # Validate repo exists
    status_msg = await message.answer("⏳ Проверяю репозиторий...")
    repo_info = await api.get_repo(owner, name)

    if not repo_info:
        await status_msg.edit_text(
            f"❌ Репозиторий <code>{owner}/{name}</code> не найден или нет доступа.",
            parse_mode="HTML"
        )
        await message.answer("Используйте меню:", reply_markup=get_main_menu())
        return

    # Save to DB
    try:
        async with get_session() as session:
            # Check if already added
            result = await session.execute(
                select(GitHubRepo).where(
                    GitHubRepo.user_id == user_id,
                    GitHubRepo.owner == owner,
                    GitHubRepo.name == name
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                await status_msg.edit_text(
                    f"ℹ️ Репозиторий <code>{owner}/{name}</code> уже добавлен.",
                    parse_mode="HTML"
                )
                await message.answer("Используйте меню:", reply_markup=get_main_menu())
                return

            # Check if user has any repos — if not, make this default
            count_result = await session.execute(
                select(GitHubRepo).where(GitHubRepo.user_id == user_id)
            )
            has_repos = count_result.scalars().first() is not None

            new_repo = GitHubRepo(
                user_id=user_id,
                owner=owner,
                name=name,
                is_default=not has_repos,
            )
            session.add(new_repo)
            await session.commit()

        private_badge = "🔒" if repo_info.get("private") else "🌐"
        default_badge = " (по умолчанию)" if not has_repos else ""
        lang = repo_info.get("language") or "—"

        await status_msg.edit_text(
            f"✅ <b>Репозиторий добавлен!</b>\n\n"
            f"{private_badge} <code>{owner}/{name}</code>{default_badge}\n"
            f"📝 {repo_info.get('description') or 'Без описания'}\n"
            f"💻 {lang}",
            parse_mode="HTML"
        )
        await message.answer("Используйте меню:", reply_markup=get_main_menu())

    except Exception as e:
        logger.error(f"Error adding repo: {e}")
        await status_msg.edit_text("❌ Ошибка сохранения репозитория.")
        await message.answer("Используйте меню:", reply_markup=get_main_menu())


async def set_default_repo(message: Message, repo_text: str) -> None:
    """Set a repository as default."""
    parsed = parse_repo_name(repo_text)
    if not parsed:
        await message.answer(
            "❌ Неверный формат. Используйте: <code>/repo set owner/name</code>",
            parse_mode="HTML"
        )
        return

    owner, name = parsed
    user_id = message.from_user.id

    try:
        async with get_session() as session:
            # Check repo exists in user's list
            result = await session.execute(
                select(GitHubRepo).where(
                    GitHubRepo.user_id == user_id,
                    GitHubRepo.owner == owner,
                    GitHubRepo.name == name
                )
            )
            repo = result.scalar_one_or_none()

            if not repo:
                await message.answer(
                    f"❌ Репозиторий <code>{owner}/{name}</code> не найден в вашем списке.\n"
                    f"Сначала добавьте: <code>/repo add {owner}/{name}</code>",
                    parse_mode="HTML"
                )
                return

            # Unset all defaults
            await session.execute(
                update(GitHubRepo)
                .where(GitHubRepo.user_id == user_id)
                .values(is_default=False)
            )
            # Set new default
            repo.is_default = True
            await session.commit()

        await message.answer(
            f"⭐ Репозиторий по умолчанию: <code>{owner}/{name}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error setting default repo: {e}")
        await message.answer("❌ Ошибка. Попробуйте позже.")


@router.callback_query(F.data.startswith("gh_repo_default_"))
async def callback_set_default(callback: CallbackQuery) -> None:
    """Set repo as default from callback."""
    full_name = callback.data[len("gh_repo_default_"):]
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    user_id = callback.from_user.id

    try:
        async with get_session() as session:
            await session.execute(
                update(GitHubRepo)
                .where(GitHubRepo.user_id == user_id)
                .values(is_default=False)
            )
            await session.execute(
                update(GitHubRepo)
                .where(
                    GitHubRepo.user_id == user_id,
                    GitHubRepo.owner == owner,
                    GitHubRepo.name == name
                )
                .values(is_default=True)
            )
            await session.commit()

        await callback.answer(f"⭐ {full_name} — по умолчанию")
        # Refresh repo actions view
        await callback.message.edit_text(
            f"📂 <b>{full_name}</b>\n\n⭐ Репозиторий по умолчанию",
            parse_mode="HTML",
            reply_markup=get_repo_actions_keyboard(owner, name, is_default=True)
        )
    except Exception as e:
        logger.error(f"Error setting default repo: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("gh_repo_remove_"))
async def callback_remove_repo(callback: CallbackQuery) -> None:
    """Remove repo from user's list."""
    full_name = callback.data[len("gh_repo_remove_"):]
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    user_id = callback.from_user.id

    try:
        async with get_session() as session:
            await session.execute(
                delete(GitHubRepo).where(
                    GitHubRepo.user_id == user_id,
                    GitHubRepo.owner == owner,
                    GitHubRepo.name == name
                )
            )
            await session.commit()

        await callback.answer(f"🗑 {full_name} удалён")
        # Return to repo list
        repos = await get_user_repos(user_id)
        await callback.message.edit_text(
            "📂 <b>Ваши репозитории</b>\n\n⭐ — репозиторий по умолчанию",
            parse_mode="HTML",
            reply_markup=get_repo_list_keyboard(repos)
        )
    except Exception as e:
        logger.error(f"Error removing repo: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


# ==================== Issues ====================

@router.message(Command("issues"))
async def cmd_issues(message: Message) -> None:
    """Handle /issues — list issues for default repo."""
    user_id = message.from_user.id
    api, _ = await get_user_github(user_id)
    if not api:
        await message.answer("⚠️ Сначала подключите GitHub: /gh_token")
        return

    repo = await get_default_repo(user_id)
    if not repo:
        repos = await get_user_repos(user_id)
        if repos:
            await message.answer(
                "Выберите репозиторий:",
                reply_markup=get_repo_select_keyboard(repos, "repo_issues")
            )
        else:
            await message.answer("⚠️ Добавьте репозиторий: <code>/repo add owner/name</code>", parse_mode="HTML")
        return

    await show_issues(message, api, repo.owner, repo.name)


@router.message(Command("issue"))
async def cmd_issue(message: Message, state: FSMContext) -> None:
    """Handle /issue — create issue or show specific issue.

    /issue Текст — create issue with title
    /issue owner/name Текст — create in specific repo
    """
    user_id = message.from_user.id
    api, _ = await get_user_github(user_id)
    if not api:
        await message.answer("⚠️ Сначала подключите GitHub: /gh_token")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        # No arguments — show usage
        await message.answer(
            "📝 <b>Создание issue</b>\n\n"
            "<code>/issue Текст</code> — создать в репо по умолчанию\n"
            "<code>/issue owner/name Текст</code> — создать в конкретном репо",
            parse_mode="HTML"
        )
        return

    text = args[1]
    # Check if first word is owner/name
    parts = text.split(maxsplit=1)
    parsed = parse_repo_name(parts[0]) if parts else None

    if parsed and len(parts) > 1:
        owner, name = parsed
        title = parts[1]
    else:
        repo = await get_default_repo(user_id)
        if not repo:
            await message.answer("⚠️ Установите репо по умолчанию: <code>/repo set owner/name</code>", parse_mode="HTML")
            return
        owner, name = repo.owner, repo.name
        title = text

    # Create issue
    status_msg = await message.answer("⏳ Создаю issue...")
    result = await api.create_issue(owner, name, title)

    if result:
        await status_msg.edit_text(
            f"✅ <b>Issue создан!</b>\n\n"
            f"<code>{owner}/{name}</code> #{result['number']}\n"
            f"📝 {result['title']}\n\n"
            f"🔗 {result['html_url']}",
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text(
            f"❌ Не удалось создать issue в <code>{owner}/{name}</code>.\n"
            f"Проверьте доступ к репозиторию.",
            parse_mode="HTML"
        )


@router.message(Command("issue_close"))
async def cmd_issue_close(message: Message) -> None:
    """Handle /issue_close NUMBER — close issue."""
    user_id = message.from_user.id
    api, _ = await get_user_github(user_id)
    if not api:
        await message.answer("⚠️ Сначала подключите GitHub: /gh_token")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: <code>/issue_close 123</code>", parse_mode="HTML")
        return

    try:
        number = int(args[1])
    except ValueError:
        await message.answer("❌ Номер issue должен быть числом.")
        return

    repo = await get_default_repo(user_id)
    if not repo:
        await message.answer("⚠️ Установите репо по умолчанию: <code>/repo set owner/name</code>", parse_mode="HTML")
        return

    result = await api.close_issue(repo.owner, repo.name, number)
    if result:
        await message.answer(
            f"🔴 <b>Issue закрыт</b>\n\n"
            f"#{result['number']} {result['title']}",
            parse_mode="HTML"
        )
    else:
        await message.answer(f"❌ Не удалось закрыть issue #{number}.")


@router.callback_query(F.data == "gh_issues")
async def callback_issues(callback: CallbackQuery) -> None:
    """Show issues — select repo if no default."""
    user_id = callback.from_user.id
    api, _ = await get_user_github(user_id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    repo = await get_default_repo(user_id)
    if not repo:
        repos = await get_user_repos(user_id)
        if repos:
            await callback.message.edit_text(
                "Выберите репозиторий для просмотра issues:",
                reply_markup=get_repo_select_keyboard(repos, "repo_issues")
            )
        else:
            await callback.message.edit_text(
                "⚠️ Добавьте репозиторий: <code>/repo add owner/name</code>",
                parse_mode="HTML"
            )
        await callback.answer()
        return

    await show_issues_callback(callback, api, repo.owner, repo.name)


@router.callback_query(F.data.startswith("gh_repo_issues_"))
async def callback_repo_issues(callback: CallbackQuery) -> None:
    """Show issues for a specific repo."""
    full_name = callback.data[len("gh_repo_issues_"):]
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    api, _ = await get_user_github(callback.from_user.id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    await show_issues_callback(callback, api, owner, name)


async def show_issues(message: Message, api: GitHubAPI, owner: str, name: str, page: int = 1) -> None:
    """Show issues list as a message."""
    issues = await api.list_issues(owner, name, per_page=10, page=page)

    if issues is None:
        await message.answer(f"❌ Не удалось получить issues для <code>{owner}/{name}</code>", parse_mode="HTML")
        return

    if not issues:
        await message.answer(
            f"📝 <b>Issues — {owner}/{name}</b>\n\nОткрытых issues нет.",
            parse_mode="HTML"
        )
        return

    text = f"📝 <b>Issues — {owner}/{name}</b>\n\n"
    for issue in issues:
        labels = " ".join(f"[{l}]" for l in issue.get("labels", []))
        text += f"🟢 <b>#{issue['number']}</b> {issue['title']}"
        if labels:
            text += f" {labels}"
        text += f"\n   👤 {issue['user']} | 💬 {issue['comments']}\n\n"

    await message.answer(text, parse_mode="HTML")


async def show_issues_callback(
    callback: CallbackQuery, api: GitHubAPI, owner: str, name: str, page: int = 1
) -> None:
    """Show issues list as edited message."""
    issues = await api.list_issues(owner, name, per_page=10, page=page)

    if issues is None:
        await callback.message.edit_text(
            f"❌ Не удалось получить issues для <code>{owner}/{name}</code>",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    if not issues:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать issue", callback_data=f"gh_issue_create_{owner}/{name}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"gh_repo_{owner}/{name}")],
        ])
        await callback.message.edit_text(
            f"📝 <b>Issues — {owner}/{name}</b>\n\nОткрытых issues нет.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"📝 <b>Issues — {owner}/{name}</b>",
        parse_mode="HTML",
        reply_markup=get_issues_keyboard(issues, owner, name, page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gh_issues_page_"))
async def callback_issues_page(callback: CallbackQuery) -> None:
    """Handle issues pagination."""
    # Format: gh_issues_page_{owner}/{name}_{page}
    data = callback.data[len("gh_issues_page_"):]
    # Split from the right to get page number
    parts = data.rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    full_name, page_str = parts
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    page = int(page_str)
    if page < 1:
        page = 1

    api, _ = await get_user_github(callback.from_user.id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    await show_issues_callback(callback, api, owner, name, page)


@router.callback_query(F.data.startswith("gh_issue_create_"))
async def callback_issue_create(callback: CallbackQuery, state: FSMContext) -> None:
    """Start issue creation flow from callback."""
    full_name = callback.data[len("gh_issue_create_"):]
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    await state.set_state(GitHubIssueCreate.waiting_for_title)
    await state.update_data(issue_repo_owner=owner, issue_repo_name=name)

    await callback.message.answer(
        f"📝 <b>Создание issue в {owner}/{name}</b>\n\n"
        f"Введите заголовок issue:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@router.message(GitHubIssueCreate.waiting_for_title)
async def process_issue_title(message: Message, state: FSMContext) -> None:
    """Process issue title."""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Создание issue отменено", reply_markup=get_main_menu())
        return

    title = message.text.strip()
    await state.update_data(issue_title=title)
    await state.set_state(GitHubIssueCreate.waiting_for_body)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить описание", callback_data="gh_issue_skip_body")]
    ])
    await message.answer(
        f"Заголовок: <b>{title}</b>\n\n"
        f"Введите описание issue (или нажмите кнопку чтобы пропустить):",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "gh_issue_skip_body", GitHubIssueCreate.waiting_for_body)
async def callback_skip_body(callback: CallbackQuery, state: FSMContext) -> None:
    """Skip issue body and create issue."""
    await create_issue_from_state(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.message(GitHubIssueCreate.waiting_for_body)
async def process_issue_body(message: Message, state: FSMContext) -> None:
    """Process issue body."""
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Создание issue отменено", reply_markup=get_main_menu())
        return

    await state.update_data(issue_body=message.text.strip())
    await create_issue_from_state(message, state, message.from_user.id)


async def create_issue_from_state(message: Message, state: FSMContext, user_id: int) -> None:
    """Create issue from FSM state data."""
    data = await state.get_data()
    owner = data.get("issue_repo_owner")
    name = data.get("issue_repo_name")
    title = data.get("issue_title")
    body = data.get("issue_body")

    await state.clear()

    api, _ = await get_user_github(user_id)
    if not api:
        await message.answer("⚠️ Токен GitHub не найден.", reply_markup=get_main_menu())
        return

    status_msg = await message.answer("⏳ Создаю issue...")
    result = await api.create_issue(owner, name, title, body)

    if result:
        await status_msg.edit_text(
            f"✅ <b>Issue создан!</b>\n\n"
            f"<code>{owner}/{name}</code> #{result['number']}\n"
            f"📝 {result['title']}\n\n"
            f"🔗 {result['html_url']}",
            parse_mode="HTML"
        )
    else:
        await status_msg.edit_text(
            f"❌ Не удалось создать issue в <code>{owner}/{name}</code>.",
            parse_mode="HTML"
        )
    await message.answer("Используйте меню:", reply_markup=get_main_menu())


@router.callback_query(F.data.startswith("gh_issue_close_"))
async def callback_issue_close(callback: CallbackQuery) -> None:
    """Close issue from callback."""
    # Format: gh_issue_close_{owner}/{name}_{number}
    data = callback.data[len("gh_issue_close_"):]
    parts = data.rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    full_name, number_str = parts
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    number = int(number_str)

    api, _ = await get_user_github(callback.from_user.id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    result = await api.close_issue(owner, name, number)
    if result:
        await callback.answer(f"🔴 Issue #{number} закрыт")
        await callback.message.edit_text(
            f"🔴 <b>Issue #{number} закрыт</b>\n\n{result['title']}",
            parse_mode="HTML",
            reply_markup=get_issue_detail_keyboard(owner, name, number, "closed")
        )
    else:
        await callback.answer("❌ Не удалось закрыть issue", show_alert=True)


@router.callback_query(F.data.startswith("gh_issue_"))
async def callback_issue_detail(callback: CallbackQuery) -> None:
    """Show issue details."""
    # Skip sub-handlers
    data = callback.data
    for prefix in ("gh_issue_create_", "gh_issue_close_", "gh_issue_skip_body"):
        if data.startswith(prefix):
            return

    # Format: gh_issue_{owner}/{name}_{number}
    rest = data[len("gh_issue_"):]
    parts = rest.rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    full_name, number_str = parts
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    number = int(number_str)

    api, _ = await get_user_github(callback.from_user.id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    issue = await api.get_issue(owner, name, number)
    if not issue:
        await callback.answer("❌ Issue не найден", show_alert=True)
        return

    state_icon = "🟢" if issue["state"] == "open" else "🔴"
    labels = " ".join(f"<code>{l}</code>" for l in issue.get("labels", []))
    body_preview = ""
    if issue.get("body"):
        body = issue["body"]
        body_preview = f"\n\n{body[:300]}{'...' if len(body) > 300 else ''}"

    text = (
        f"{state_icon} <b>#{issue['number']} {issue['title']}</b>\n\n"
        f"👤 {issue['user']} | 📅 {format_datetime_short(issue['created_at'])}\n"
        f"💬 Комментариев: {issue['comments']}"
    )
    if labels:
        text += f"\n🏷 {labels}"
    text += body_preview

    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_issue_detail_keyboard(owner, name, number, issue["state"])
    )
    await callback.answer()


# ==================== Pull Requests ====================

@router.message(Command("prs"))
async def cmd_prs(message: Message) -> None:
    """Handle /prs — list PRs. Optionally /prs owner/name."""
    user_id = message.from_user.id
    api, _ = await get_user_github(user_id)
    if not api:
        await message.answer("⚠️ Сначала подключите GitHub: /gh_token")
        return

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        parsed = parse_repo_name(args[1])
        if parsed:
            owner, name = parsed
            await show_pulls(message, api, owner, name)
            return

    repo = await get_default_repo(user_id)
    if not repo:
        repos = await get_user_repos(user_id)
        if repos:
            await message.answer(
                "Выберите репозиторий:",
                reply_markup=get_repo_select_keyboard(repos, "repo_pulls")
            )
        else:
            await message.answer("⚠️ Добавьте репозиторий: <code>/repo add owner/name</code>", parse_mode="HTML")
        return

    await show_pulls(message, api, repo.owner, repo.name)


@router.message(Command("pr"))
async def cmd_pr(message: Message) -> None:
    """Handle /pr NUMBER — show PR details."""
    user_id = message.from_user.id
    api, _ = await get_user_github(user_id)
    if not api:
        await message.answer("⚠️ Сначала подключите GitHub: /gh_token")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: <code>/pr 15</code>", parse_mode="HTML")
        return

    try:
        number = int(args[1])
    except ValueError:
        await message.answer("❌ Номер PR должен быть числом.")
        return

    repo = await get_default_repo(user_id)
    if not repo:
        await message.answer("⚠️ Установите репо по умолчанию: <code>/repo set owner/name</code>", parse_mode="HTML")
        return

    pr = await api.get_pull(repo.owner, repo.name, number)
    if not pr:
        await message.answer(f"❌ PR #{number} не найден.")
        return

    await message.answer(
        format_pr_detail(repo.owner, repo.name, pr),
        parse_mode="HTML",
        reply_markup=get_pr_detail_keyboard(repo.owner, repo.name, number)
    )


@router.callback_query(F.data == "gh_pulls")
async def callback_pulls(callback: CallbackQuery) -> None:
    """Show PRs — select repo if no default."""
    user_id = callback.from_user.id
    api, _ = await get_user_github(user_id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    repo = await get_default_repo(user_id)
    if not repo:
        repos = await get_user_repos(user_id)
        if repos:
            await callback.message.edit_text(
                "Выберите репозиторий:",
                reply_markup=get_repo_select_keyboard(repos, "repo_pulls")
            )
        else:
            await callback.message.edit_text(
                "⚠️ Добавьте репозиторий: <code>/repo add owner/name</code>",
                parse_mode="HTML"
            )
        await callback.answer()
        return

    await show_pulls_callback(callback, api, repo.owner, repo.name)


@router.callback_query(F.data.startswith("gh_repo_pulls_"))
async def callback_repo_pulls(callback: CallbackQuery) -> None:
    """Show PRs for a specific repo."""
    full_name = callback.data[len("gh_repo_pulls_"):]
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    api, _ = await get_user_github(callback.from_user.id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    await show_pulls_callback(callback, api, owner, name)


async def show_pulls(message: Message, api: GitHubAPI, owner: str, name: str, page: int = 1) -> None:
    """Show PRs list as message."""
    pulls = await api.list_pulls(owner, name, per_page=10, page=page)

    if pulls is None:
        await message.answer(f"❌ Не удалось получить PR для <code>{owner}/{name}</code>", parse_mode="HTML")
        return

    if not pulls:
        await message.answer(
            f"🔀 <b>Pull Requests — {owner}/{name}</b>\n\nОткрытых PR нет.",
            parse_mode="HTML"
        )
        return

    text = f"🔀 <b>Pull Requests — {owner}/{name}</b>\n\n"
    for pr in pulls:
        icon = "📝" if pr.get("draft") else "🟢"
        text += (
            f"{icon} <b>#{pr['number']}</b> {pr['title']}\n"
            f"   {pr['head_branch']} → {pr['base_branch']} | 👤 {pr['user']}\n\n"
        )

    await message.answer(text, parse_mode="HTML")


async def show_pulls_callback(
    callback: CallbackQuery, api: GitHubAPI, owner: str, name: str, page: int = 1
) -> None:
    """Show PRs list as edited message."""
    pulls = await api.list_pulls(owner, name, per_page=10, page=page)

    if pulls is None:
        await callback.message.edit_text(
            f"❌ Не удалось получить PR для <code>{owner}/{name}</code>",
            parse_mode="HTML"
        )
        await callback.answer()
        return

    if not pulls:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"gh_repo_{owner}/{name}")],
        ])
        await callback.message.edit_text(
            f"🔀 <b>Pull Requests — {owner}/{name}</b>\n\nОткрытых PR нет.",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"🔀 <b>Pull Requests — {owner}/{name}</b>",
        parse_mode="HTML",
        reply_markup=get_pulls_keyboard(pulls, owner, name, page)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gh_pulls_page_"))
async def callback_pulls_page(callback: CallbackQuery) -> None:
    """Handle PRs pagination."""
    data = callback.data[len("gh_pulls_page_"):]
    parts = data.rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    full_name, page_str = parts
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    page = int(page_str)
    if page < 1:
        page = 1

    api, _ = await get_user_github(callback.from_user.id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    await show_pulls_callback(callback, api, owner, name, page)


@router.callback_query(F.data.startswith("gh_pr_"))
async def callback_pr_detail(callback: CallbackQuery) -> None:
    """Show PR details."""
    # Format: gh_pr_{owner}/{name}_{number}
    rest = callback.data[len("gh_pr_"):]
    parts = rest.rsplit("_", 1)
    if len(parts) != 2:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    full_name, number_str = parts
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    number = int(number_str)

    api, _ = await get_user_github(callback.from_user.id)
    if not api:
        await callback.answer("⚠️ Подключите GitHub", show_alert=True)
        return

    pr = await api.get_pull(owner, name, number)
    if not pr:
        await callback.answer("❌ PR не найден", show_alert=True)
        return

    await callback.message.edit_text(
        format_pr_detail(owner, name, pr),
        parse_mode="HTML",
        reply_markup=get_pr_detail_keyboard(owner, name, number)
    )
    await callback.answer()


def format_pr_detail(owner: str, name: str, pr: dict) -> str:
    """Format PR details for display."""
    if pr.get("merged_at"):
        state_icon = "🟣 Merged"
    elif pr["state"] == "open":
        state_icon = "🟢 Open"
    else:
        state_icon = "🔴 Closed"

    if pr.get("draft"):
        state_icon = "📝 Draft"

    # Merge status
    mergeable = pr.get("mergeable")
    merge_state = pr.get("mergeable_state", "unknown")
    if mergeable is True:
        merge_text = "✅ Можно мержить"
    elif mergeable is False:
        merge_text = "❌ Есть конфликты"
    else:
        merge_text = "⏳ Статус неизвестен"

    text = (
        f"🔀 <b>#{pr['number']} {pr['title']}</b>\n\n"
        f"Статус: {state_icon}\n"
        f"👤 {pr['user']}\n"
        f"🌿 {pr['head_branch']} → {pr['base_branch']}\n"
        f"📅 {format_datetime_short(pr['created_at'])}\n\n"
        f"Мерж: {merge_text}\n"
    )

    if pr.get("additions") is not None:
        text += f"📊 +{pr['additions']} / -{pr['deletions']} ({pr['changed_files']} файлов)\n"

    if pr.get("comments") or pr.get("review_comments"):
        text += f"💬 {pr.get('comments', 0)} комментариев, {pr.get('review_comments', 0)} ревью\n"

    body = pr.get("body")
    if body:
        preview = body[:200] + ("..." if len(body) > 200 else "")
        text += f"\n{preview}"

    return text


# ==================== Catch-all repo detail (must be LAST gh_repo_ handler) ====================

@router.callback_query(F.data.startswith("gh_repo_"))
async def callback_repo_detail(callback: CallbackQuery) -> None:
    """Show repo actions. Registered LAST so specific gh_repo_* handlers run first."""
    full_name = callback.data[len("gh_repo_"):]
    parsed = parse_repo_name(full_name)
    if not parsed:
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    owner, name = parsed
    user_id = callback.from_user.id

    # Check if default
    try:
        async with get_session() as session:
            result = await session.execute(
                select(GitHubRepo).where(
                    GitHubRepo.user_id == user_id,
                    GitHubRepo.owner == owner,
                    GitHubRepo.name == name
                )
            )
            repo = result.scalar_one_or_none()
            is_default = repo.is_default if repo else False
    except Exception:
        is_default = False

    # Get repo info
    api, _ = await get_user_github(user_id)
    if api:
        repo_info = await api.get_repo(owner, name)
        desc = repo_info.get("description", "Без описания") if repo_info else "—"
        lang = repo_info.get("language", "—") if repo_info else "—"
        issues_count = repo_info.get("open_issues_count", 0) if repo_info else 0
    else:
        desc, lang, issues_count = "—", "—", 0

    default_text = "\n⭐ Репозиторий по умолчанию" if is_default else ""
    await callback.message.edit_text(
        f"📂 <b>{owner}/{name}</b>{default_text}\n\n"
        f"📝 {desc}\n"
        f"💻 {lang} | 📝 Issues: {issues_count}",
        parse_mode="HTML",
        reply_markup=get_repo_actions_keyboard(owner, name, is_default)
    )
    await callback.answer()


# Module setup
def setup(dp) -> None:
    """Register GitHub module handlers."""
    dp.include_router(router)
    logger.info("GitHub module registered")
