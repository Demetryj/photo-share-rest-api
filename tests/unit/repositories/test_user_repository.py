"""Unit tests for user repository helpers."""

from unittest.mock import AsyncMock

import pytest

from src.entity.user import Role, User
from src.repository import user as user_repository
from src.schemas.user import SignUpRequestSchema


@pytest.mark.asyncio
async def test_get_user_by_email_returns_scalar_result(
    db_session_mock: AsyncMock,
    scalar_result_factory,
) -> None:
    """Return the user resolved by scalar_one_or_none()."""

    user = User(id=1, email="user@mail.com")
    db_session_mock.execute.return_value = scalar_result_factory(user)

    result = await user_repository.get_user_by_email(
        email="user@mail.com",
        db=db_session_mock,
    )

    assert result is user
    db_session_mock.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_has_any_users_returns_true_when_user_exists(
    db_session_mock: AsyncMock,
    scalar_result_factory,
) -> None:
    """Return True when the select query returns at least one user id."""

    db_session_mock.execute.return_value = scalar_result_factory(1)

    result = await user_repository.has_any_users(db=db_session_mock)

    assert result is True


@pytest.mark.asyncio
async def test_create_user_creates_admin_when_no_users_exist(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assign the admin role to the first created user."""

    body = SignUpRequestSchema(
        username="new_user",
        email="new_user@mail.com",
        password="Qwerty123!",
    )
    monkeypatch.setattr(
        "src.repository.user.has_any_users",
        AsyncMock(return_value=False),
    )

    result = await user_repository.create_user(
        body=body,
        db=db_session_mock,
    )

    assert isinstance(result, User)
    assert result.role == Role.admin
    assert result.username == body.username
    db_session_mock.add.assert_called_once_with(result)
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_create_user_creates_regular_user_when_users_exist(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assign the regular user role when accounts already exist."""

    body = SignUpRequestSchema(
        username="member",
        email="member@mail.com",
        password="Qwerty123!",
    )
    monkeypatch.setattr(
        "src.repository.user.has_any_users",
        AsyncMock(return_value=True),
    )

    result = await user_repository.create_user(
        body=body,
        db=db_session_mock,
    )

    assert result.role == Role.user


@pytest.mark.asyncio
async def test_confirm_email_updates_user_when_found(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mark the user as confirmed and persist the change."""

    user = User(id=2, email="confirm@mail.com", confirmed=False)
    monkeypatch.setattr(
        "src.repository.user.get_user_by_email",
        AsyncMock(return_value=user),
    )

    await user_repository.confirm_email(
        email="confirm@mail.com",
        db=db_session_mock,
    )

    assert user.confirmed is True
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_update_own_user_profile_returns_none_when_user_not_found(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return None when the current user does not exist."""

    monkeypatch.setattr(
        "src.repository.user.get_user_by_id",
        AsyncMock(return_value=None),
    )

    result = await user_repository.update_own_user_profile(
        user_id=4,
        avatar_url="https://cdn.example.com/avatar.jpg",
        display_name="Tester",
        db=db_session_mock,
    )

    assert result is None
    db_session_mock.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_user_role_updates_role_and_persists(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Update the target user's role when it changes."""

    user = User(id=3, role=Role.user)
    monkeypatch.setattr(
        "src.repository.user.get_user_by_id",
        AsyncMock(return_value=user),
    )

    result = await user_repository.change_user_role(
        user_id=3,
        new_role=Role.moderator,
        db=db_session_mock,
    )

    assert result is user
    assert user.role == Role.moderator
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_update_user_password_updates_hash_and_returns_user(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist the new password hash for the existing user."""

    user = User(id=5, email="user@mail.com", password="old-hash")
    monkeypatch.setattr(
        "src.repository.user.get_user_by_email",
        AsyncMock(return_value=user),
    )

    result = await user_repository.update_user_password(
        email="user@mail.com",
        hashed_password="new-hash",
        db=db_session_mock,
    )

    assert result is user
    assert user.password == "new-hash"
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(user)
