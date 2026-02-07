"""Database models for Yandex Disk module."""

from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean
from sqlalchemy.sql import func
from core.database import Base


class YandexToken(Base):
    """Yandex Disk OAuth token storage.

    Stores encrypted OAuth tokens for users to access their Yandex Disk.
    """
    __tablename__ = "yandex_tokens"

    user_id = Column(BigInteger, primary_key=True, index=True, doc="Telegram user ID")
    encrypted_token = Column(String, nullable=False, doc="Fernet-encrypted OAuth token")
    folder_name = Column(String, nullable=False, default="TelegramBot", doc="Default folder for uploads")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, doc="Token creation timestamp")
    is_valid = Column(Boolean, default=True, nullable=False, doc="Token validity status")

    def __repr__(self) -> str:
        return f"<YandexToken(user_id={self.user_id}, folder='{self.folder_name}', valid={self.is_valid})>"


class UploadedFile(Base):
    """Metadata for files uploaded to Yandex Disk.

    Tracks all files uploaded through the bot for listing and deletion.
    """
    __tablename__ = "uploaded_files"

    id = Column(Integer, primary_key=True, autoincrement=True, doc="Unique file record ID")
    user_id = Column(BigInteger, nullable=False, index=True, doc="Telegram user ID who uploaded the file")
    file_name = Column(String, nullable=False, doc="Original file name")
    yandex_path = Column(String, nullable=False, doc="Full path on Yandex Disk")
    public_url = Column(String, nullable=True, doc="Public sharing URL")
    file_size = Column(BigInteger, nullable=False, doc="File size in bytes")
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, doc="Upload timestamp")

    def __repr__(self) -> str:
        return f"<UploadedFile(id={self.id}, user={self.user_id}, name='{self.file_name}')>"
