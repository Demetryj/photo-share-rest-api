"""Unit tests for auth repository helpers."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.entity.user import PasswordResetToken, UserSession
from src.repository import auth as auth_repository


@pytest.mark.asyncio
async def test_create_user_session_adds_and_persists_record(
    db_session_mock: AsyncMock,
) -> None:
    """Create a session record and persist it."""

    result = await auth_repository.create_user_session(
        refresh_token_hash="refresh-hash",
        access_token_jti="access-jti",
        user_id=10,
        db=db_session_mock,
    )

    assert isinstance(result, UserSession)
    assert result.refresh_token_hash == "refresh-hash"
    assert result.access_token_jti == "access-jti"
    assert result.user_id == 10
    db_session_mock.add.assert_called_once_with(result)
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_get_user_session_by_refresh_token_hash_returns_scalar_result(
    db_session_mock: AsyncMock,
    scalar_result_factory,
) -> None:
    """Return the session found by refresh token hash."""

    session = UserSession(
        refresh_token_hash="refresh-hash",
        access_token_jti="jti",
    )
    db_session_mock.execute.return_value = scalar_result_factory(
        session
    )

    result = (
        await auth_repository.get_user_session_by_refresh_token_hash(
            refresh_token_hash="refresh-hash",
            db=db_session_mock,
        )
    )

    assert result is session


@pytest.mark.asyncio
async def test_update_user_session_tokens_returns_none_when_session_missing(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return None when the existing session cannot be found."""

    monkeypatch.setattr(
        "src.repository.auth.get_user_session_by_refresh_token_hash",
        AsyncMock(return_value=None),
    )

    result = await auth_repository.update_user_session_tokens(
        old_refresh_token_hash="old",
        new_refresh_token_hash="new",
        new_access_token_jti="new-jti",
        db=db_session_mock,
    )

    assert result is None
    db_session_mock.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_session_tokens_updates_existing_session(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replace stored token identifiers on the existing session."""

    session = UserSession(
        refresh_token_hash="old",
        access_token_jti="old-jti",
    )
    monkeypatch.setattr(
        "src.repository.auth.get_user_session_by_refresh_token_hash",
        AsyncMock(return_value=session),
    )

    result = await auth_repository.update_user_session_tokens(
        old_refresh_token_hash="old",
        new_refresh_token_hash="new",
        new_access_token_jti="new-jti",
        db=db_session_mock,
    )

    assert result is session
    assert session.refresh_token_hash == "new"
    assert session.access_token_jti == "new-jti"
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(session)


@pytest.mark.asyncio
async def test_delete_user_session_by_refresh_token_hash_returns_true_when_row_deleted(
    db_session_mock: AsyncMock,
    delete_result_factory,
) -> None:
    """Return True when the delete query affects at least one row."""

    db_session_mock.execute.return_value = delete_result_factory(1)

    result = await auth_repository.delete_user_session_by_refresh_token_hash(
        refresh_token_hash="refresh-hash",
        db=db_session_mock,
    )

    assert result is True
    db_session_mock.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_password_reset_token_creates_new_record_when_missing(
    db_session_mock: AsyncMock,
    scalar_result_factory,
) -> None:
    """Create a new password reset token when no record exists for the user."""

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db_session_mock.execute.return_value = scalar_result_factory(None)

    await auth_repository.create_password_reset_token(
        user_id=3,
        token_hash="token-hash",
        expires_at=expires_at,
        db=db_session_mock,
    )

    added_record = db_session_mock.add.call_args.args[0]
    assert isinstance(added_record, PasswordResetToken)
    assert added_record.user_id == 3
    assert added_record.token_hash == "token-hash"
    assert added_record.expires_at == expires_at
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(added_record)


@pytest.mark.asyncio
async def test_mark_password_reset_token_as_used_does_nothing_when_missing(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit without commit when the token record does not exist."""

    monkeypatch.setattr(
        "src.repository.auth.get_password_reset_token_by_hash",
        AsyncMock(return_value=None),
    )

    await auth_repository.mark_password_reset_token_as_used(
        token_hash="missing-hash",
        db=db_session_mock,
    )

    db_session_mock.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_old_password_reset_tokens_returns_deleted_rows_count(
    db_session_mock: AsyncMock,
    delete_result_factory,
) -> None:
    """Return the rowcount reported by the delete statement."""

    db_session_mock.execute.return_value = delete_result_factory(4)

    result = await auth_repository.delete_old_password_reset_tokens(
        older_than_days=7,
        db=db_session_mock,
    )

    assert result == 4
    db_session_mock.commit.assert_awaited_once()
