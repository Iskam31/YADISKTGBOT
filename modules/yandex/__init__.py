"""Yandex Disk module.

This module provides functionality to upload files to Yandex Disk via Telegram bot.

Features:
- OAuth token setup and management
- File uploads (all types: documents, photos, videos, audio, voice)
- Progress bar during upload
- File listing and deletion
- Public URL generation
"""

from .handlers import setup

__all__ = ['setup']
