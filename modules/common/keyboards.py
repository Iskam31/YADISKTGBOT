"""Keyboard utilities for common module.

Provides keyboard layouts for the main menu and other common interactions.
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu() -> ReplyKeyboardMarkup:
    """Create persistent main menu with 6 buttons in 3x2 layout.

    Returns:
        ReplyKeyboardMarkup with Upload, My Files, GitHub, Settings, and Help buttons
    """
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📤 Загрузить"),
                KeyboardButton(text="📁 Мои файлы")
            ],
            [
                KeyboardButton(text="🐙 GitHub"),
                KeyboardButton(text="⚙️ Настройки")
            ],
            [
                KeyboardButton(text="ℹ️ Помощь")
            ]
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    return keyboard
