"""
Database session management for async SQLAlchemy.
Provides a session manager and FastAPI dependency (`get_db`)
with commit/rollback behavior per request.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config.settings import settings

logger = logging.getLogger(__name__)


class DatabaseSessionManager:
    """Create async engine/session factory and manage session lifecycle."""

    def __init__(self, db_url: str):
        """Initialize the async database engine and session maker.

        :param db_url: SQLAlchemy async database URL.
        :type db_url: str
        """

        self._engine: AsyncEngine | None = create_async_engine(db_url)
        self._session_maker: async_sessionmaker | None = async_sessionmaker(
            autoflush=False, autocommit=False, bind=self._engine
        )

    @asynccontextmanager
    async def get_session(self):
        """Yield an asynchronous database session.

        :raises Exception: Raised when the session maker is not initialized.
        :raises SQLAlchemyError: Re-raised after rolling back failed database
            operations.
        :return: Async context manager yielding an ``AsyncSession``.
        :rtype: AsyncGenerator[AsyncSession, None]
        """

        if self._session_maker is None:
            raise Exception("Session is not initialized")
        session = self._session_maker()
        try:
            yield session
            # await session.commit()
        except SQLAlchemyError:
            await session.rollback()
            logger.exception("Database transaction failed")
            raise
        finally:
            await session.close()


sessionmanager = DatabaseSessionManager(settings.DB_URL)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async database session.

    :return: Async generator with one ``AsyncSession``.
    :rtype: AsyncGenerator[AsyncSession, None]
    """
    async with sessionmanager.get_session() as session:
        yield session
