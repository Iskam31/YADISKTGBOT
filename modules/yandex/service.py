"""Yandex Disk API client.

Handles all interactions with Yandex Disk REST API.
Documentation: https://cloud-api.yandex.net/v1/disk
"""

import aiohttp
from typing import Optional, Callable, Any
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class YandexDiskAPI:
    """Async client for Yandex Disk REST API."""

    BASE_URL = "https://cloud-api.yandex.net/v1/disk"

    def __init__(self, oauth_token: str):
        """Initialize API client.

        Args:
            oauth_token: OAuth token for Yandex Disk API
        """
        self.oauth_token = oauth_token
        self.headers = {
            "Authorization": f"OAuth {oauth_token}",
            "Content-Type": "application/json",
        }

    async def check_token(self) -> bool:
        """Check if OAuth token is valid.

        Returns:
            True if token is valid, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info("Token validation successful")
                        return True
                    else:
                        logger.warning(f"Token validation failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False

    async def create_folder(self, path: str) -> bool:
        """Create a folder on Yandex Disk.

        Args:
            path: Full path for the folder (e.g., 'TelegramBot')

        Returns:
            True if folder created or already exists, False on error
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    f"{self.BASE_URL}/resources",
                    headers=self.headers,
                    params={"path": path},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status in (201, 409):  # 409 = already exists
                        logger.info(f"Folder '{path}' ready")
                        return True
                    else:
                        logger.error(f"Folder creation failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Folder creation error: {e}")
            return False

    async def get_upload_url(self, path: str) -> Optional[str]:
        """Get upload URL for a file.

        Args:
            path: Full path where file will be uploaded (e.g., 'TelegramBot/photo.jpg')

        Returns:
            Upload URL if successful, None on error
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/resources/upload",
                    headers=self.headers,
                    params={"path": path, "overwrite": "true"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        upload_url = data.get("href")
                        logger.info(f"Upload URL obtained for '{path}'")
                        return upload_url
                    else:
                        logger.error(f"Get upload URL failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Get upload URL error: {e}")
            return None

    async def upload_file(
        self,
        upload_url: str,
        file_path: str,
        progress_callback: Optional[Callable[[int], Any]] = None
    ) -> bool:
        """Upload file to Yandex Disk using upload URL.

        Args:
            upload_url: Upload URL from get_upload_url()
            file_path: Local file path to upload
            progress_callback: Optional callback function called with percentage (0-100)

        Returns:
            True if upload successful, False otherwise
        """
        try:
            file_size = Path(file_path).stat().st_size
            uploaded = 0

            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    async def file_sender():
                        nonlocal uploaded
                        chunk_size = 65536  # 64KB chunks
                        while True:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            uploaded += len(chunk)
                            if progress_callback and file_size > 0:
                                percentage = int((uploaded / file_size) * 100)
                                await progress_callback(percentage)
                            yield chunk

                    async with session.put(
                        upload_url,
                        data=file_sender(),
                        timeout=aiohttp.ClientTimeout(total=3600)  # 1 hour for large files
                    ) as response:
                        if response.status in (201, 202):
                            logger.info(f"File uploaded successfully: {file_path}")
                            return True
                        else:
                            logger.error(f"File upload failed: {response.status}")
                            return False
        except Exception as e:
            logger.error(f"File upload error: {e}")
            return False

    async def publish_file(self, path: str) -> Optional[str]:
        """Publish file and get public URL.

        Args:
            path: Full path to file on Yandex Disk

        Returns:
            Public URL if successful, None on error
        """
        try:
            async with aiohttp.ClientSession() as session:
                # Publish the file
                async with session.put(
                    f"{self.BASE_URL}/resources/publish",
                    headers=self.headers,
                    params={"path": path},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.error(f"File publish failed: {response.status}")
                        return None

                # Get public URL
                async with session.get(
                    f"{self.BASE_URL}/resources",
                    headers=self.headers,
                    params={"path": path},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        public_url = data.get("public_url")
                        logger.info(f"File published: {public_url}")
                        return public_url
                    else:
                        logger.error(f"Get public URL failed: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"File publish error: {e}")
            return None

    async def delete_file(self, path: str) -> bool:
        """Delete file from Yandex Disk.

        Args:
            path: Full path to file on Yandex Disk

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.delete(
                    f"{self.BASE_URL}/resources",
                    headers=self.headers,
                    params={"path": path, "permanently": "true"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status in (204, 202):  # 202 = async deletion started
                        logger.info(f"File deleted: {path}")
                        return True
                    else:
                        logger.error(f"File deletion failed: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"File deletion error: {e}")
            return False

    async def get_disk_info(self) -> Optional[dict]:
        """Get disk space information.

        Returns:
            Dict with 'total_space', 'used_space', 'trash_size' or None on error
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.BASE_URL}/",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "total_space": data.get("total_space", 0),
                            "used_space": data.get("used_space", 0),
                            "trash_size": data.get("trash_size", 0),
                        }
                    else:
                        return None
        except Exception as e:
            logger.error(f"Get disk info error: {e}")
            return None
