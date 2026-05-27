"""Shared fixtures for repository unit tests."""

from collections.abc import Callable
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
def db_session_mock() -> AsyncMock:
    """Return an async session mock for repository unit tests."""

    return AsyncMock(spec=AsyncSession)


@pytest.fixture()
def scalar_result_factory() -> Callable[[object], Mock]:
    """Build execute-result stubs with scalar_one_or_none()."""

    def _build(value: object) -> Mock:
        result = Mock()
        result.scalar_one_or_none.return_value = value
        return result

    return _build


@pytest.fixture()
def scalars_result_factory() -> Callable[[object], Mock]:
    """Build execute-result stubs with scalars().all()."""

    def _build(values: object) -> Mock:
        scalars = Mock()
        scalars.all.return_value = values
        result = Mock()
        result.scalars.return_value = scalars
        return result

    return _build


@pytest.fixture()
def delete_result_factory() -> Callable[[int], Mock]:
    """Build execute-result stubs exposing rowcount."""

    def _build(rowcount: int) -> Mock:
        result = Mock()
        result.rowcount = rowcount
        return result

    return _build


@pytest.fixture()
def rows_result_factory() -> Callable[[object], Mock]:
    """Build execute-result stubs with all()."""

    def _build(values: object) -> Mock:
        result = Mock()
        result.all.return_value = values
        return result

    return _build
