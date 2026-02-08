"""Utility functions for Yandex Disk module."""

import os
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def create_progress_bar(percent: int, length: int = 10) -> str:
    """Create visual progress bar.

    Args:
        percent: Progress percentage (0-100)
        length: Length of progress bar in characters

    Returns:
        Progress bar string like "[████████░░] 80%"
    """
    percent = max(0, min(100, percent))  # Clamp to 0-100
    filled = int((percent / 100) * length)
    empty = length - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {percent}%"


def format_size(bytes_size: int) -> str:
    """Format file size in human-readable format.

    Args:
        bytes_size: Size in bytes

    Returns:
        Formatted string like "1.5 MB" or "234 KB"
    """
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 ** 2:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 ** 3:
        return f"{bytes_size / (1024 ** 2):.1f} MB"
    else:
        return f"{bytes_size / (1024 ** 3):.2f} GB"


def format_datetime(dt: datetime) -> str:
    """Format datetime for display.

    Args:
        dt: Datetime object

    Returns:
        Formatted string like "07.02.2026 15:30"
    """
    return dt.strftime("%d.%m.%Y %H:%M")


async def download_telegram_file(
    bot,
    file_id: str,
    temp_dir: str,
    file_name: str,
    use_local_api: bool = False
) -> Optional[str]:
    """Download file from Telegram to temporary directory.

    Args:
        bot: Telegram Bot instance
        file_id: Telegram file ID
        temp_dir: Temporary directory path
        file_name: Name for the downloaded file
        use_local_api: Whether local Bot API server is being used

    Returns:
        Path to downloaded file or None on error
    """
    try:
        # Ensure temp directory exists
        Path(temp_dir).mkdir(parents=True, exist_ok=True)

        # Get file from Telegram
        file = await bot.get_file(file_id)

        # Log download method
        api_type = "LOCAL" if use_local_api else "PUBLIC"
        file_size = file.file_size or "unknown"
        logger.info(f"Downloading file via {api_type} API (file_id: {file_id}, size: {file_size})")
        logger.info(f"File path from Telegram: {file.file_path}")
        logger.info(f"File unique_id: {file.file_unique_id}")

        # Create destination path
        file_path = os.path.join(temp_dir, file_name)

        # Download file
        logger.info(f"Attempting download from: {file.file_path} to: {file_path}")
        await bot.download_file(file.file_path, file_path)

        logger.info(f"Downloaded Telegram file to {file_path}")
        return file_path

    except Exception as e:
        logger.error(f"Error downloading Telegram file: {e}")
        return None


def cleanup_temp_file(file_path: str) -> bool:
    """Delete temporary file.

    Args:
        file_path: Path to file to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up temp file: {file_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"Error cleaning up temp file {file_path}: {e}")
        return False


async def cleanup_old_temp_files(temp_dir: str, max_age_hours: int = 24) -> int:
    """Clean up temporary files older than specified age.

    Args:
        temp_dir: Temporary directory path
        max_age_hours: Maximum age in hours (default 24)

    Returns:
        Number of files cleaned up
    """
    cleaned = 0
    try:
        if not os.path.exists(temp_dir):
            return 0

        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        for file_path in Path(temp_dir).glob("*"):
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_time:
                    try:
                        file_path.unlink()
                        cleaned += 1
                        logger.debug(f"Cleaned up old temp file: {file_path}")
                    except Exception as e:
                        logger.error(f"Error deleting old temp file {file_path}: {e}")

        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} old temp files")

    except Exception as e:
        logger.error(f"Error during temp file cleanup: {e}")

    return cleaned


async def start_periodic_cleanup(temp_dir: str, interval_hours: int = 24, max_age_hours: int = 24):
    """Start periodic cleanup task in background.

    Args:
        temp_dir: Temporary directory path
        interval_hours: Cleanup interval in hours
        max_age_hours: Maximum file age in hours
    """
    logger.info(f"Starting periodic cleanup task (every {interval_hours}h, max age {max_age_hours}h)")

    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)
            await cleanup_old_temp_files(temp_dir, max_age_hours)
        except asyncio.CancelledError:
            logger.info("Periodic cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic cleanup task: {e}")


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for filesystem and Yandex Disk
    """
    # Remove or replace unsafe characters
    unsafe_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    sanitized = filename

    for char in unsafe_chars:
        sanitized = sanitized.replace(char, '_')

    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')

    # Ensure filename is not empty
    if not sanitized:
        sanitized = "unnamed_file"

    return sanitized


def get_file_extension(filename: str) -> str:
    """Get file extension from filename.

    Args:
        filename: Filename with extension

    Returns:
        Extension including dot (e.g., '.jpg') or empty string
    """
    return Path(filename).suffix.lower()


def generate_unique_filename(base_name: str, existing_names: list) -> str:
    """Generate unique filename if name already exists.

    Args:
        base_name: Base filename
        existing_names: List of existing filenames

    Returns:
        Unique filename with counter if needed (e.g., 'file_1.txt')
    """
    if base_name not in existing_names:
        return base_name

    name_part = Path(base_name).stem
    ext_part = Path(base_name).suffix

    counter = 1
    while True:
        new_name = f"{name_part}_{counter}{ext_part}"
        if new_name not in existing_names:
            return new_name
        counter += 1
