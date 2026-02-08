"""Database models for GitHub module."""

from sqlalchemy import Column, Integer, String, BigInteger, DateTime, Boolean, UniqueConstraint, Text
from sqlalchemy.sql import func
from core.database import Base


class GitHubToken(Base):
    """GitHub Personal Access Token storage.

    Stores encrypted PAT tokens for users to access GitHub API.
    """
    __tablename__ = "github_tokens"

    user_id = Column(BigInteger, primary_key=True, index=True, doc="Telegram user ID")
    encrypted_token = Column(String, nullable=False, doc="Fernet-encrypted PAT token")
    github_username = Column(String, nullable=True, doc="GitHub username")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_valid = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<GitHubToken(user_id={self.user_id}, github_username='{self.github_username}', valid={self.is_valid})>"


class GitHubRepo(Base):
    """User's linked GitHub repositories."""
    __tablename__ = "github_repos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, doc="Telegram user ID")
    owner = Column(String, nullable=False, doc="Repository owner")
    name = Column(String, nullable=False, doc="Repository name")
    is_default = Column(Boolean, default=False, nullable=False, doc="Default repository flag")
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'owner', 'name', name='uq_user_repo'),
    )

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    def __repr__(self) -> str:
        return f"<GitHubRepo(user_id={self.user_id}, repo='{self.owner}/{self.name}', default={self.is_default})>"


class GitHubWebhook(Base):
    """GitHub webhook registration per repository.

    Stores the GitHub-side webhook ID and the secret used for signature verification.
    One webhook per repo — shared across all subscribed users.
    """
    __tablename__ = "github_webhooks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_owner = Column(String, nullable=False, doc="Repository owner")
    repo_name = Column(String, nullable=False, doc="Repository name")
    github_webhook_id = Column(Integer, nullable=False, doc="Webhook ID from GitHub API")
    encrypted_secret = Column(String, nullable=False, doc="Fernet-encrypted webhook secret")
    created_by_user_id = Column(BigInteger, nullable=False, doc="User who created the webhook")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('repo_owner', 'repo_name', name='uq_webhook_repo'),
    )

    @property
    def full_name(self) -> str:
        return f"{self.repo_owner}/{self.repo_name}"

    def __repr__(self) -> str:
        return f"<GitHubWebhook(repo='{self.repo_owner}/{self.repo_name}', gh_id={self.github_webhook_id}, active={self.is_active})>"


class GitHubWebhookSub(Base):
    """User subscription to webhook notifications for a repository.

    Presence of a record means the user wants notifications for this repo.
    """
    __tablename__ = "github_webhook_subs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, doc="Telegram user ID")
    repo_owner = Column(String, nullable=False, doc="Repository owner")
    repo_name = Column(String, nullable=False, doc="Repository name")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'repo_owner', 'repo_name', name='uq_webhook_sub'),
    )

    def __repr__(self) -> str:
        return f"<GitHubWebhookSub(user_id={self.user_id}, repo='{self.repo_owner}/{self.repo_name}')>"
