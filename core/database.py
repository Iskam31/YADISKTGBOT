"""Database setup using SQLAlchemy.

Provides Base class for models and session management.
"""

from contextlib import asynccontextmanager
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from typing import AsyncGenerator
import logging

logger = logging.getLogger(__name__)

# Base class for all models
Base = declarative_base()

# Global session maker
_session_maker: async_sessionmaker[AsyncSession] | None = None
_engine = None


def init_database(database_url: str) -> None:
    """Initialize database engine and session maker.

    Args:
        database_url: SQLAlchemy database URL (e.g., 'sqlite+aiosqlite:///bot.db')
    """
    global _session_maker, _engine

    logger.info(f"Initializing database with URL: {database_url}")

    # Create async engine
    _engine = create_async_engine(
        database_url,
        echo=False,  # Set to True for SQL query debugging
        future=True,
    )

    # Create session maker
    _session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    logger.info("Database initialized successfully")


async def create_tables() -> None:
    """Create all tables in the database.

    Should be called once during application startup.
    """
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    logger.info("Creating database tables...")

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database tables created successfully")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for dependency injection.

    Yields:
        AsyncSession: Database session

    Example:
        async with get_session() as session:
            result = await session.execute(query)
    """
    if _session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    async with _session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_database() -> None:
    """Close database engine.

    Should be called during application shutdown.
    """
    global _engine

    if _engine is None:
        return

    logger.info("Closing database connection...")
    await _engine.dispose()
    _engine = None
    logger.info("Database connection closed")
