from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
import logging

from core.database import get_session
from core.crypto import get_encryption
from modules.yandex.models import YandexToken
from modules.yandex.service import YandexDiskAPI
from .keyboards import get_main_menu

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command('start'))
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start"""
    await message.answer(
        "👋 <b>Привет! Я бот для загрузки файлов на Яндекс Диск.</b>\n\n"
        "📋 <b>Основные команды:</b>\n"
        "• /menu - показать главное меню\n"
        "• /token - настроить OAuth токен Яндекс Диска\n"
        "• /help - подробная справка по использованию\n\n"
        "📎 <b>Как использовать:</b>\n"
        "Просто отправь мне любой файл, и я загружу его на твой Яндекс Диск "
        "и пришлю публичную ссылку для скачивания!\n\n"
        "Начни с настройки токена: /token",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )


@router.message(Command('help'))
async def cmd_help(message: Message) -> None:
    """Обработчик команды /help"""
    await message.answer(
        "ℹ️ <b>Подробная справка</b>\n\n"

        "<b>📝 Как начать работу:</b>\n"
        "1. Получи OAuth токен Яндекс Диска по ссылке:\n"
        "   https://oauth.yandex.ru/authorize?response_type=token&client_id=YOUR_ID\n"
        "2. Отправь токен командой /token\n"
        "3. Создай или выбери папку для хранения файлов\n"
        "4. Готово! Теперь просто отправляй файлы\n\n"

        "<b>📤 Загрузка файлов:</b>\n"
        "• Отправь любой файл (документ, фото, видео, архив)\n"
        "• Бот покажет прогресс загрузки\n"
        "• Получишь публичную ссылку для скачивания\n"
        "• Файл будет доступен на твоём Яндекс Диске\n\n"

        "<b>📋 Управление файлами:</b>\n"
        "• /list - показать последние загруженные файлы\n"
        "• Удалить файл можно через кнопку в списке\n\n"

        "<b>🔒 Безопасность:</b>\n"
        "• Токены шифруются перед сохранением в базу данных\n"
        "• Сообщения с токенами автоматически удаляются\n"
        "• Временные файлы удаляются сразу после загрузки\n"
        "• Никто кроме тебя не имеет доступа к твоим файлам\n\n"

        "<b>⚙️ Технические лимиты:</b>\n"
        "• Максимальный размер файла: 2 GB (Telegram Premium)\n"
        "• Поддерживаются все типы файлов\n"
        "• Скорость загрузки зависит от вашего интернета\n\n"

        "<b>❓ Возникли проблемы?</b>\n"
        "• Проверь валидность OAuth токена\n"
        "• Убедись что на Яндекс Диске есть свободное место\n"
        "• Попробуй переотправить файл\n"
        "• Перенастрой токен: /token"
    )


@router.message(Command('menu'))
async def cmd_menu(message: Message) -> None:
    """Обработчик команды /menu - показать главное меню"""
    await message.answer(
        "📋 <b>Главное меню</b>\n\n"
        "Используйте кнопки ниже для работы с ботом:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )


@router.message(F.text == "ℹ️ Помощь")
async def button_help(message: Message) -> None:
    """Handle Help button press."""
    await cmd_help(message)


@router.message(F.text == "📁 Мои файлы")
async def button_my_files(message: Message) -> None:
    """Handle My Files button - show mode selection."""
    # Import to avoid circular dependency
    from modules.yandex.keyboards import get_mode_selection_keyboard

    await message.answer(
        "Выберите режим просмотра:",
        reply_markup=get_mode_selection_keyboard()
    )


@router.message(F.text == "📤 Загрузить")
async def button_upload(message: Message) -> None:
    """Handle Upload button press."""
    await message.answer(
        "📤 <b>Загрузка файлов</b>\n\n"
        "Отправьте мне любой файл (документ, фото, видео, аудио), "
        "и я загружу его на ваш Яндекс Диск с публичной ссылкой.\n\n"
        "Поддерживаются все типы файлов до 2 GB.",
        parse_mode="HTML"
    )


@router.message(F.text == "⚙️ Настройки")
async def button_settings(message: Message) -> None:
    """Handle Settings button press - show settings menu."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Настроить токен", callback_data="settings_token")],
        [InlineKeyboardButton(text="💾 Информация о диске", callback_data="settings_disk_info")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="settings_close")]
    ])

    await message.answer(
        "⚙️ <b>Настройки</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "settings_token")
async def callback_settings_token(callback: CallbackQuery) -> None:
    """Handle settings token callback."""
    await callback.message.answer(
        "🔑 <b>Настройка токена</b>\n\n"
        "Используйте /token для настройки токена доступа к Яндекс Диску.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "settings_disk_info")
async def callback_settings_disk_info(callback: CallbackQuery) -> None:
    """Handle settings disk info callback - show Yandex Disk statistics."""
    user_id = callback.from_user.id

    try:
        async with get_session() as session:
            # Get user token from database
            result = await session.execute(
                select(YandexToken).where(YandexToken.user_id == user_id)
            )
            token_record = result.scalar_one_or_none()

            if not token_record or not token_record.is_valid:
                await callback.message.answer(
                    "⚠️ <b>Токен не настроен</b>\n\n"
                    "Сначала настройте токен через /token",
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Decrypt token
            encryption = get_encryption()
            oauth_token = encryption.decrypt(token_record.encrypted_token)

            # Get disk info from Yandex API
            api = YandexDiskAPI(oauth_token)
            disk_info = await api.get_disk_info()

            if not disk_info:
                await callback.message.answer(
                    "❌ <b>Ошибка получения данных</b>\n\n"
                    "Не удалось получить информацию о диске. "
                    "Проверьте токен или попробуйте позже.",
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Convert bytes to GB
            total_gb = disk_info["total_space"] / (1024 ** 3)
            used_gb = disk_info["used_space"] / (1024 ** 3)
            trash_gb = disk_info["trash_size"] / (1024 ** 3)
            free_gb = total_gb - used_gb

            # Calculate percentage
            used_percent = (used_gb / total_gb * 100) if total_gb > 0 else 0

            info_text = (
                "💾 <b>Информация о Яндекс Диске</b>\n\n"
                f"<b>Всего места:</b> {total_gb:.2f} GB\n"
                f"<b>Использовано:</b> {used_gb:.2f} GB ({used_percent:.1f}%)\n"
                f"<b>Свободно:</b> {free_gb:.2f} GB\n"
                f"<b>В корзине:</b> {trash_gb:.2f} GB\n"
            )

            await callback.message.answer(info_text, parse_mode="HTML")
            await callback.answer()

    except Exception as e:
        logger.error(f"Error getting disk info: {e}")
        await callback.message.answer(
            "❌ <b>Ошибка</b>\n\n"
            "Произошла ошибка при получении информации о диске.",
            parse_mode="HTML"
        )
        await callback.answer()


@router.callback_query(F.data == "settings_close")
async def callback_settings_close(callback: CallbackQuery) -> None:
    """Handle settings close callback - delete settings message."""
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        # Message already deleted or can't be deleted
        pass
    except Exception as e:
        logger.warning(f"Unexpected error deleting settings message: {e}")
    await callback.answer()


def setup(dp):
    """Register common module handlers."""
    dp.include_router(router)
