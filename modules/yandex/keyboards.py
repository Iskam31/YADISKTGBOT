"""Telegram keyboards for Yandex Disk module."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List


def get_folder_selection_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for folder selection during setup.

    Returns:
        Inline keyboard with options to create folder or use root
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📁 Создать папку", callback_data="folder_create")],
        [InlineKeyboardButton(text="📂 Использовать корень диска", callback_data="folder_root")],
    ])
    return keyboard


def get_folder_name_keyboard() -> ReplyKeyboardMarkup:
    """Get keyboard with suggested folder names.

    Returns:
        Reply keyboard with folder name suggestions
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="TelegramBot")],
            [KeyboardButton(text="TelegramFiles")],
            [KeyboardButton(text="BotUploads")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Введите название папки"
    )
    return keyboard


def get_file_list_keyboard(files: List[dict], offset: int = 0) -> InlineKeyboardMarkup:
    """Get keyboard with file list and delete buttons.

    Args:
        files: List of file dicts with 'id', 'file_name', 'file_size', 'uploaded_at'
        offset: Current offset for pagination

    Returns:
        Inline keyboard with file list and navigation
    """
    buttons = []

    # File entries with delete buttons
    for file in files:
        file_id = file['id']
        file_name = file['file_name']
        # Truncate long filenames
        display_name = file_name if len(file_name) <= 30 else file_name[:27] + "..."

        buttons.append([
            InlineKeyboardButton(text=f"📄 {display_name}", callback_data=f"file_info_{file_id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"delete_{file_id}"),
        ])

    # Navigation buttons (if needed for pagination in future)
    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"list_prev_{offset}"))
    if len(files) >= 10:  # Show next if we have full page
        nav_buttons.append(InlineKeyboardButton(text="➡️ Далее", callback_data=f"list_next_{offset}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    # Close button
    buttons.append([InlineKeyboardButton(text="❌ Закрыть", callback_data="close_list")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard


def get_delete_confirmation_keyboard(file_id: int) -> InlineKeyboardMarkup:
    """Get confirmation keyboard for file deletion.

    Args:
        file_id: ID of file to delete

    Returns:
        Inline keyboard with confirm/cancel buttons
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete_{file_id}"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"),
        ]
    ])
    return keyboard


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Get keyboard with cancel button for FSM states.

    Returns:
        Reply keyboard with cancel button
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard


def remove_keyboard() -> ReplyKeyboardMarkup:
    """Get empty keyboard to remove reply keyboard.

    Returns:
        ReplyKeyboardRemove equivalent
    """
    from aiogram.types import ReplyKeyboardRemove
    return ReplyKeyboardRemove()
