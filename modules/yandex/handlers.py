"""Telegram handlers for Yandex Disk module.

Handles all user interactions: token setup, folder creation, file uploads, listing, and deletion.
"""

import os
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.crypto import TokenEncryption
from .models import YandexToken, UploadedFile
from .service import YandexDiskAPI
from .keyboards import (
    get_folder_selection_keyboard,
    get_folder_name_keyboard,
    get_file_list_keyboard,
    get_delete_confirmation_keyboard,
    get_cancel_keyboard,
)
from .utils import (
    create_progress_bar,
    format_size,
    format_datetime,
    download_telegram_file,
    cleanup_temp_file,
    sanitize_filename,
)

logger = logging.getLogger(__name__)

# Create router for this module
router = Router(name="yandex")


# FSM States
class TokenSetup(StatesGroup):
    """States for token setup flow."""
    waiting_for_token = State()
    waiting_for_folder_name = State()


class FileUpload(StatesGroup):
    """States for file upload flow."""
    uploading = State()


# ==================== TOKEN SETUP ====================

@router.message(Command("token"))
async def cmd_token(message: Message, state: FSMContext):
    """Handle /token command to set up OAuth token.

    User flow:
    1. User sends /token
    2. Bot asks for OAuth token
    3. User sends token
    4. Bot validates token
    5. Bot asks for folder name
    6. Token and folder saved to database
    """
    await state.set_state(TokenSetup.waiting_for_token)
    await message.answer(
        "🔑 <b>Настройка токена Яндекс Диска</b>\n\n"
        "Для работы бота нужен OAuth-токен с доступом к вашему Яндекс Диску.\n\n"
        "<b>Как получить токен:</b>\n"
        "1. Перейдите на https://oauth.yandex.ru\n"
        "2. Войдите в аккаунт\n"
        "3. Создайте приложение или используйте существующее\n"
        "4. Получите OAuth-токен с правами на Яндекс Диск\n\n"
        "📤 Отправьте токен в ответном сообщении:\n"
        "(сообщение с токеном будет автоматически удалено для безопасности)",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )


@router.message(TokenSetup.waiting_for_token)
async def process_token(message: Message, state: FSMContext, bot: Bot):
    """Process OAuth token from user."""

    # Check for cancel
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Настройка токена отменена", reply_markup=None)
        return

    token = message.text.strip()

    # Delete message with token for security
    try:
        await bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        logger.warning(f"Could not delete token message: {e}")

    # Validate token
    status_msg = await message.answer("⏳ Проверяю токен...")

    api = YandexDiskAPI(token)
    is_valid = await api.check_token()

    if not is_valid:
        await status_msg.edit_text(
            "❌ <b>Неверный токен</b>\n\n"
            "Токен не прошёл проверку. Проверьте правильность токена и попробуйте снова.\n\n"
            "Используйте /token для повторной попытки.",
            parse_mode="HTML"
        )
        await state.clear()
        return

    # Token valid, save to FSM and ask for folder
    await state.update_data(token=token)
    await state.set_state(TokenSetup.waiting_for_folder_name)

    await status_msg.edit_text(
        "✅ <b>Токен действителен!</b>\n\n"
        "Теперь выберите папку для загрузки файлов:",
        parse_mode="HTML",
        reply_markup=get_folder_selection_keyboard()
    )


@router.callback_query(F.data == "folder_create", TokenSetup.waiting_for_folder_name)
async def select_create_folder(callback: CallbackQuery, state: FSMContext):
    """User chose to create a custom folder."""
    await callback.message.edit_text(
        "📁 <b>Создание папки</b>\n\n"
        "Введите название папки для загрузки файлов:\n"
        "(можно использовать русские буквы, цифры и пробелы)",
        parse_mode="HTML"
    )
    await callback.message.answer(
        "Введите название папки:",
        reply_markup=get_folder_name_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "folder_root", TokenSetup.waiting_for_folder_name)
async def select_root_folder(callback: CallbackQuery, state: FSMContext):
    """User chose to use root folder."""
    await finalize_token_setup(callback.message, state, "/")


@router.message(TokenSetup.waiting_for_folder_name)
async def process_folder_name(message: Message, state: FSMContext):
    """Process folder name from user."""

    # Check for cancel
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("❌ Настройка отменена", reply_markup=None)
        return

    folder_name = message.text.strip()

    # Validate folder name
    if not folder_name or len(folder_name) > 100:
        await message.answer(
            "❌ Некорректное название папки. Используйте от 1 до 100 символов.",
            reply_markup=get_folder_name_keyboard()
        )
        return

    await finalize_token_setup(message, state, folder_name)


async def finalize_token_setup(message: Message, state: FSMContext, folder_name: str):
    """Finalize token setup by creating folder and saving to database."""

    data = await state.get_data()
    token = data.get("token")

    if not token:
        await message.answer("❌ Ошибка: токен не найден. Начните заново с /token")
        await state.clear()
        return

    status_msg = await message.answer("⏳ Настраиваю доступ к Яндекс Диску...")

    # Create folder if not root
    api = YandexDiskAPI(token)
    if folder_name != "/":
        folder_created = await api.create_folder(folder_name)
        if not folder_created:
            await status_msg.edit_text(
                "❌ <b>Ошибка создания папки</b>\n\n"
                "Не удалось создать папку на Яндекс Диске. Попробуйте другое название или выберите корневую папку.",
                parse_mode="HTML"
            )
            await state.clear()
            return

    # Encrypt and save token to database
    try:
        encryption = TokenEncryption()
        encrypted_token = encryption.encrypt(token)

        async for session in get_session():
            # Check if token already exists
            result = await session.execute(
                select(YandexToken).where(YandexToken.user_id == message.from_user.id)
            )
            existing_token = result.scalar_one_or_none()

            if existing_token:
                # Update existing token
                existing_token.encrypted_token = encrypted_token
                existing_token.folder_name = folder_name
                existing_token.is_valid = True
            else:
                # Create new token record
                new_token = YandexToken(
                    user_id=message.from_user.id,
                    encrypted_token=encrypted_token,
                    folder_name=folder_name,
                    is_valid=True
                )
                session.add(new_token)

            await session.commit()

        folder_display = "корневой папки" if folder_name == "/" else f"папки '{folder_name}'"
        await status_msg.edit_text(
            f"✅ <b>Настройка завершена!</b>\n\n"
            f"Токен сохранён, будет использоваться {folder_display}.\n\n"
            f"Теперь вы можете отправлять файлы боту для загрузки на Яндекс Диск.",
            parse_mode="HTML",
            reply_markup=None
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Error saving token: {e}")
        await status_msg.edit_text(
            "❌ <b>Ошибка сохранения</b>\n\n"
            "Не удалось сохранить токен в базу данных. Попробуйте позже.",
            parse_mode="HTML"
        )
        await state.clear()


# ==================== FILE UPLOAD ====================

async def handle_file_upload(message: Message, bot: Bot, file_id: str, file_name: str, file_size: int):
    """Common handler for all file uploads.

    Args:
        message: Telegram message with file
        bot: Bot instance
        file_id: Telegram file ID
        file_name: Original file name
        file_size: File size in bytes
    """
    user_id = message.from_user.id

    # Check file size (2GB limit)
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    if file_size > MAX_FILE_SIZE:
        await message.answer(
            f"❌ <b>Файл слишком большой</b>\n\n"
            f"Размер: {format_size(file_size)}\n"
            f"Максимум: {format_size(MAX_FILE_SIZE)}\n\n"
            f"Telegram Bot API поддерживает файлы до 2 GB.",
            parse_mode="HTML"
        )
        return

    # Get user token from database
    try:
        async for session in get_session():
            result = await session.execute(
                select(YandexToken).where(YandexToken.user_id == user_id)
            )
            token_record = result.scalar_one_or_none()

            if not token_record or not token_record.is_valid:
                await message.answer(
                    "⚠️ <b>Токен не настроен</b>\n\n"
                    "Сначала настройте доступ к Яндекс Диску командой /token",
                    parse_mode="HTML"
                )
                return

            # Decrypt token
            encryption = TokenEncryption()
            oauth_token = encryption.decrypt(token_record.encrypted_token)
            folder_name = token_record.folder_name

    except Exception as e:
        logger.error(f"Error getting token: {e}")
        await message.answer("❌ Ошибка получения токена из базы данных")
        return

    # Start upload process
    status_msg = await message.answer(
        f"⏳ <b>Загружаю файл на Яндекс Диск...</b>\n\n"
        f"📄 {file_name}\n"
        f"📊 {format_size(file_size)}\n\n"
        f"{create_progress_bar(0)}",
        parse_mode="HTML"
    )

    # Download from Telegram
    temp_dir = os.getenv("TEMP_DIR", "/tmp/telegram_bot_files")
    sanitized_name = sanitize_filename(file_name)
    local_path = await download_telegram_file(bot, file_id, temp_dir, sanitized_name)

    if not local_path:
        await status_msg.edit_text("❌ Ошибка скачивания файла из Telegram")
        return

    try:
        # Get upload URL from Yandex
        api = YandexDiskAPI(oauth_token)
        yandex_path = f"{folder_name}/{sanitized_name}" if folder_name != "/" else sanitized_name
        upload_url = await api.get_upload_url(yandex_path)

        if not upload_url:
            await status_msg.edit_text("❌ Не удалось получить ссылку для загрузки на Яндекс Диск")
            cleanup_temp_file(local_path)
            return

        # Upload to Yandex with progress
        last_percent = 0

        async def progress_callback(percent: int):
            nonlocal last_percent
            # Update message every 10%
            if percent - last_percent >= 10 or percent >= 100:
                last_percent = percent
                try:
                    await status_msg.edit_text(
                        f"⏳ <b>Загружаю файл на Яндекс Диск...</b>\n\n"
                        f"📄 {file_name}\n"
                        f"📊 {format_size(file_size)}\n\n"
                        f"{create_progress_bar(percent)}",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass  # Ignore rate limit errors

        upload_success = await api.upload_file(upload_url, local_path, progress_callback)

        if not upload_success:
            await status_msg.edit_text("❌ Ошибка загрузки файла на Яндекс Диск")
            cleanup_temp_file(local_path)
            return

        # Publish file and get public URL
        public_url = await api.publish_file(yandex_path)

        # Save to database
        try:
            async for session in get_session():
                new_file = UploadedFile(
                    user_id=user_id,
                    file_name=file_name,
                    yandex_path=yandex_path,
                    public_url=public_url,
                    file_size=file_size
                )
                session.add(new_file)
                await session.commit()
        except Exception as e:
            logger.error(f"Error saving file metadata: {e}")

        # Success message
        success_text = (
            f"✅ <b>Файл загружен!</b>\n\n"
            f"📄 {file_name}\n"
            f"📊 {format_size(file_size)}\n"
            f"📁 {yandex_path}\n"
        )
        if public_url:
            success_text += f"\n🔗 <a href='{public_url}'>Публичная ссылка</a>"

        await status_msg.edit_text(success_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error during file upload: {e}")
        await status_msg.edit_text(f"❌ Ошибка при загрузке: {str(e)}")

    finally:
        # Always cleanup temp file
        cleanup_temp_file(local_path)


# File type handlers
@router.message(F.document)
async def handle_document(message: Message, bot: Bot):
    """Handle document uploads."""
    doc = message.document
    await handle_file_upload(message, bot, doc.file_id, doc.file_name, doc.file_size)


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot):
    """Handle photo uploads."""
    # Get largest photo
    photo = message.photo[-1]
    file_name = f"photo_{message.message_id}.jpg"
    await handle_file_upload(message, bot, photo.file_id, file_name, photo.file_size)


@router.message(F.video)
async def handle_video(message: Message, bot: Bot):
    """Handle video uploads."""
    video = message.video
    file_name = video.file_name or f"video_{message.message_id}.mp4"
    await handle_file_upload(message, bot, video.file_id, file_name, video.file_size)


@router.message(F.audio)
async def handle_audio(message: Message, bot: Bot):
    """Handle audio uploads."""
    audio = message.audio
    file_name = audio.file_name or f"audio_{message.message_id}.mp3"
    await handle_file_upload(message, bot, audio.file_id, file_name, audio.file_size)


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    """Handle voice messages."""
    voice = message.voice
    file_name = f"voice_{message.message_id}.ogg"
    await handle_file_upload(message, bot, voice.file_id, file_name, voice.file_size)


@router.message(F.video_note)
async def handle_video_note(message: Message, bot: Bot):
    """Handle video notes (circles)."""
    video_note = message.video_note
    file_name = f"video_note_{message.message_id}.mp4"
    await handle_file_upload(message, bot, video_note.file_id, file_name, video_note.file_size)


# ==================== FILE LISTING AND DELETION ====================

@router.message(Command("list"))
async def cmd_list_files(message: Message):
    """Handle /list command to show uploaded files."""
    user_id = message.from_user.id

    try:
        async for session in get_session():
            # Get last 10 files
            result = await session.execute(
                select(UploadedFile)
                .where(UploadedFile.user_id == user_id)
                .order_by(UploadedFile.uploaded_at.desc())
                .limit(10)
            )
            files = result.scalars().all()

            if not files:
                await message.answer(
                    "📋 <b>Список файлов</b>\n\n"
                    "У вас пока нет загруженных файлов.\n"
                    "Отправьте боту любой файл для загрузки на Яндекс Диск.",
                    parse_mode="HTML"
                )
                return

            # Format file list
            file_list = []
            for file in files:
                file_info = {
                    'id': file.id,
                    'file_name': file.file_name,
                    'file_size': file.file_size,
                    'uploaded_at': file.uploaded_at
                }
                file_list.append(file_info)

            # Create message text
            text = f"📋 <b>Ваши файлы</b> (последние {len(files)})\n\n"
            for idx, file in enumerate(files, 1):
                text += (
                    f"{idx}. <b>{file.file_name}</b>\n"
                    f"   📊 {format_size(file.file_size)} | "
                    f"📅 {format_datetime(file.uploaded_at)}\n\n"
                )

            text += "Нажмите 🗑 для удаления файла"

            await message.answer(
                text,
                parse_mode="HTML",
                reply_markup=get_file_list_keyboard(file_list)
            )

    except Exception as e:
        logger.error(f"Error listing files: {e}")
        await message.answer("❌ Ошибка получения списка файлов")


@router.callback_query(F.data.startswith("file_info_"))
async def show_file_info(callback: CallbackQuery):
    """Show detailed file information."""
    file_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    try:
        async for session in get_session():
            result = await session.execute(
                select(UploadedFile)
                .where(UploadedFile.id == file_id, UploadedFile.user_id == user_id)
            )
            file = result.scalar_one_or_none()

            if not file:
                await callback.answer("❌ Файл не найден", show_alert=True)
                return

            info_text = (
                f"📄 <b>Информация о файле</b>\n\n"
                f"<b>Название:</b> {file.file_name}\n"
                f"<b>Размер:</b> {format_size(file.file_size)}\n"
                f"<b>Путь:</b> {file.yandex_path}\n"
                f"<b>Загружен:</b> {format_datetime(file.uploaded_at)}\n"
            )
            if file.public_url:
                info_text += f"\n🔗 <a href='{file.public_url}'>Открыть на Яндекс Диске</a>"

            await callback.message.answer(info_text, parse_mode="HTML")
            await callback.answer()

    except Exception as e:
        logger.error(f"Error showing file info: {e}")
        await callback.answer("❌ Ошибка получения информации о файле", show_alert=True)


@router.callback_query(F.data.startswith("delete_"))
async def confirm_delete(callback: CallbackQuery):
    """Ask for deletion confirmation."""
    file_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    try:
        async for session in get_session():
            result = await session.execute(
                select(UploadedFile)
                .where(UploadedFile.id == file_id, UploadedFile.user_id == user_id)
            )
            file = result.scalar_one_or_none()

            if not file:
                await callback.answer("❌ Файл не найден", show_alert=True)
                return

            await callback.message.answer(
                f"🗑 <b>Удаление файла</b>\n\n"
                f"Вы уверены, что хотите удалить файл?\n\n"
                f"📄 {file.file_name}\n"
                f"📊 {format_size(file.file_size)}\n\n"
                f"<i>Файл будет удалён с Яндекс Диска навсегда.</i>",
                parse_mode="HTML",
                reply_markup=get_delete_confirmation_keyboard(file_id)
            )
            await callback.answer()

    except Exception as e:
        logger.error(f"Error in delete confirmation: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data.startswith("confirm_delete_"))
async def execute_delete(callback: CallbackQuery):
    """Execute file deletion."""
    file_id = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id

    try:
        async for session in get_session():
            # Get file info
            result = await session.execute(
                select(UploadedFile)
                .where(UploadedFile.id == file_id, UploadedFile.user_id == user_id)
            )
            file = result.scalar_one_or_none()

            if not file:
                await callback.answer("❌ Файл не найден", show_alert=True)
                return

            # Get user token
            token_result = await session.execute(
                select(YandexToken).where(YandexToken.user_id == user_id)
            )
            token_record = token_result.scalar_one_or_none()

            if not token_record:
                await callback.answer("❌ Токен не найден", show_alert=True)
                return

            # Decrypt token and delete from Yandex
            encryption = TokenEncryption()
            oauth_token = encryption.decrypt(token_record.encrypted_token)
            api = YandexDiskAPI(oauth_token)

            status_msg = await callback.message.answer("⏳ Удаляю файл с Яндекс Диска...")

            deleted = await api.delete_file(file.yandex_path)

            if deleted:
                # Delete from database
                await session.execute(
                    delete(UploadedFile).where(UploadedFile.id == file_id)
                )
                await session.commit()

                await status_msg.edit_text(
                    f"✅ <b>Файл удалён</b>\n\n"
                    f"📄 {file.file_name}",
                    parse_mode="HTML"
                )
            else:
                await status_msg.edit_text(
                    "❌ Не удалось удалить файл с Яндекс Диска\n\n"
                    "Возможно, файл уже был удалён вручную."
                )

            await callback.answer()

    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        await callback.message.answer("❌ Ошибка при удалении файла")
        await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    """Cancel file deletion."""
    await callback.message.edit_text("❌ Удаление отменено")
    await callback.answer()


@router.callback_query(F.data == "close_list")
async def close_list(callback: CallbackQuery):
    """Close file list."""
    await callback.message.delete()
    await callback.answer()


# Module setup function
def setup(dp) -> None:
    """Register Yandex Disk module handlers.

    Args:
        dp: Aiogram Dispatcher instance
    """
    dp.include_router(router)
    logger.info("Yandex Disk module registered")
