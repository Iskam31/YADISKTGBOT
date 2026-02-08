"""Telegram keyboards for Yandex Disk module."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List
import base64


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


# Navigation helper functions

def encode_path(path: str) -> str:
    """Encode file path to base64 for use in callback_data.

    Telegram limits callback_data to 64 bytes, so we encode paths
    to make them more compact.

    Args:
        path: File system path

    Returns:
        Base64 encoded path (URL-safe, no padding)
    """
    encoded_bytes = base64.urlsafe_b64encode(path.encode('utf-8'))
    # Remove padding to save space
    encoded_str = encoded_bytes.decode('utf-8').rstrip('=')
    return encoded_str


def decode_path(encoded: str) -> str:
    """Decode base64 encoded path from callback_data.

    Args:
        encoded: Base64 encoded path

    Returns:
        Original file system path
    """
    # Add padding back if needed
    padding = 4 - (len(encoded) % 4)
    if padding != 4:
        encoded += '=' * padding

    decoded_bytes = base64.urlsafe_b64decode(encoded.encode('utf-8'))
    return decoded_bytes.decode('utf-8')


def truncate(text: str, max_len: int = 30) -> str:
    """Truncate long text with ellipsis.

    Args:
        text: Text to truncate
        max_len: Maximum length (default: 30)

    Returns:
        Truncated text with "..." if longer than max_len
    """
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text


def format_breadcrumb(path: str, max_parts: int = 3) -> str:
    """Format path as breadcrumb navigation.

    Args:
        path: File system path (e.g., "/folder1/folder2/folder3")
        max_parts: Maximum number of path parts to show (default: 3)

    Returns:
        Formatted breadcrumb (e.g., "📂 / > folder2 > folder3")

    Examples:
        "/" -> "📂 /"
        "/folder1" -> "📂 / > folder1"
        "/folder1/folder2/folder3/folder4" -> "📂 ... > folder3 > folder4"
    """
    if path == "/" or path == "":
        return "📂 /"

    # Split path and filter empty strings
    parts = [p for p in path.split('/') if p]

    if len(parts) <= max_parts:
        # Show all parts
        return "📂 / > " + " > ".join(parts)
    else:
        # Show last max_parts with ellipsis
        visible_parts = parts[-max_parts:]
        return "📂 ... > " + " > ".join(visible_parts)


def get_file_browser_keyboard(
    items: list[dict],
    current_path: str,
    offset: int,
    total: int,
    mode: str = "browse"
) -> InlineKeyboardMarkup:
    """Create navigation keyboard for file browser.

    Args:
        items: List of file/folder dicts from Yandex API
        current_path: Current directory path
        offset: Current pagination offset
        total: Total number of items in directory
        mode: "browse" for viewing, "select" for choosing upload folder

    Returns:
        InlineKeyboardMarkup with:
            - Breadcrumb header (current path)
            - Folders (📁 name) - opens folder
            - Files (📄 name | 🔗 | 🗑) - info, publish, delete
            - Pagination (⬅️ Назад | ➡️ Далее) if needed
            - Up button (⬆️ Уровень выше) if not at root
            - Select button (📤 Загрузить сюда) if mode == "select"
            - Close button (❌ Закрыть)

    Callback data format:
        - Folder: "nav_open_{encoded_path}"
        - Info: "nav_info_{encoded_path}"
        - Publish: "nav_publish_{encoded_path}"
        - Delete: "nav_delete_{encoded_path}"
        - Page prev: "nav_page_{offset-limit}_{encoded_path}"
        - Page next: "nav_page_{offset+limit}_{encoded_path}"
        - Up: "nav_up_{encoded_parent_path}"
        - Select: "nav_select_{encoded_path}"
        - Close: "nav_close"
    """
    buttons = []
    limit = 20  # Fixed limit for pagination

    # Breadcrumb header
    breadcrumb = format_breadcrumb(current_path)
    buttons.append([InlineKeyboardButton(text=breadcrumb, callback_data="noop")])

    # Sort items: folders first, then files
    folders = [item for item in items if item.get("type") == "dir"]
    files = [item for item in items if item.get("type") == "file"]

    # Add folder buttons
    for folder in folders:
        folder_name = folder.get("name", "Unknown")
        folder_path = folder.get("path", "")
        encoded_path = encode_path(folder_path)

        # Truncate folder name if too long
        display_name = truncate(folder_name, 35)

        buttons.append([
            InlineKeyboardButton(
                text=f"📁 {display_name}",
                callback_data=f"nav_open_{encoded_path}"
            )
        ])

    # Add file buttons (3 buttons per row)
    for file in files:
        file_name = file.get("name", "Unknown")
        file_path = file.get("path", "")
        encoded_path = encode_path(file_path)
        is_published = "public_url" in file and file.get("public_url")

        # Truncate filename for display
        display_name = truncate(file_name, 20)

        # Create row with 3 buttons: info, publish/copy, delete
        file_row = [
            InlineKeyboardButton(
                text=f"📄 {display_name}",
                callback_data=f"nav_info_{encoded_path}"
            ),
            InlineKeyboardButton(
                text="📋" if is_published else "🔗",
                callback_data=f"nav_publish_{encoded_path}"
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"nav_delete_{encoded_path}"
            )
        ]
        buttons.append(file_row)

    # Pagination row
    if total > limit:
        nav_buttons = []
        if offset > 0:
            prev_offset = max(0, offset - limit)
            encoded_path = encode_path(current_path)
            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"nav_page_{prev_offset}_{encoded_path}"
                )
            )

        if offset + limit < total:
            next_offset = offset + limit
            encoded_path = encode_path(current_path)
            nav_buttons.append(
                InlineKeyboardButton(
                    text="➡️ Далее",
                    callback_data=f"nav_page_{next_offset}_{encoded_path}"
                )
            )

        if nav_buttons:
            buttons.append(nav_buttons)

    # Up button (if not at root)
    if current_path != "/" and current_path != "":
        # Calculate parent path
        parent_path = "/".join(current_path.rstrip('/').split('/')[:-1])
        if not parent_path:
            parent_path = "/"
        encoded_parent = encode_path(parent_path)

        buttons.append([
            InlineKeyboardButton(
                text="⬆️ Уровень выше",
                callback_data=f"nav_up_{encoded_parent}"
            )
        ])

    # Select button (if in select mode)
    if mode == "select":
        encoded_path = encode_path(current_path)
        buttons.append([
            InlineKeyboardButton(
                text="📤 Загрузить сюда",
                callback_data=f"nav_select_{encoded_path}"
            )
        ])

    # Close button
    buttons.append([
        InlineKeyboardButton(text="❌ Закрыть", callback_data="nav_close")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_mode_selection_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard for choosing file view mode.

    Returns:
        InlineKeyboardMarkup with 3 buttons:
            - "📤 Загруженные файлы" (callback: "view_uploaded")
            - "💿 Весь Яндекс.Диск" (callback: "view_all_disk")
            - "❌ Отмена" (callback: "nav_close")
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Загруженные файлы", callback_data="view_uploaded")],
        [InlineKeyboardButton(text="💿 Весь Яндекс.Диск", callback_data="view_all_disk")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="nav_close")],
    ])
    return keyboard
