"""Shared fixtures for service unit tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
def db_session_mock() -> AsyncMock:
    """Return an async session mock for service unit tests."""

    return AsyncMock(spec=AsyncSession)
