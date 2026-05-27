"""Shared fixtures for service unit tests."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.auth import auth_service


@pytest.fixture()
def db_session_mock() -> AsyncMock:
    """Return an async session mock for service unit tests."""

    return AsyncMock(spec=AsyncSession)


@pytest.fixture()
def access_token_with_jti() -> tuple[str, str]:
    """Return an access token together with its generated JTI."""

    token, jti = auth_service.create_access_token(
        payload={"sub": "test_user@mail.com"}
    )
    return token, jti
