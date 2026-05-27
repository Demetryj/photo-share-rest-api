"""Integration tests for auth routes."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.config.messages import EmailMessages, HTTPStatusMessages
from src.entity.user import Role
from src.repository import auth as repository_auth
from src.repository import user as repository_user
from src.routes import auth as auth_routes
from src.services.auth import auth_service
from src.services.token_blacklist import token_blacklist_service
from tests.conftest import TestingSessionLocal, app, test_user

PREFIX = "/api/auth"
TOKEN_TYPE_BEARER = "bearer"
VALID_PASSWORD = "Qwerty1!"
NEW_VALID_PASSWORD = "Asdfgh1!"
INVALID_TOKEN = "invalid-token"


@pytest.fixture(autouse=True)
def clear_auth_test_cookies(client):
    """Ensure auth route tests do not leak cookies into each other."""

    client.cookies.clear()
    yield
    client.cookies.clear()


@pytest.fixture()
def signup_payload() -> dict[str, str]:
    """Build a unique signup payload for auth route tests."""

    unique_suffix = uuid4().hex[:8]
    return {
        "username": f"signup_{unique_suffix}",
        "email": f"signup_{unique_suffix}@mail.com",
        "password": VALID_PASSWORD,
    }


@pytest.fixture()
def seeded_admin_user():
    """Return the seeded authenticated admin user from the test database."""

    async def _get_user():
        async with TestingSessionLocal() as session:
            return await repository_user.get_user_by_email(
                email=test_user["email"],
                db=session,
            )

    return asyncio.run(_get_user())


@pytest.fixture()
def persist_user_session():
    """Persist one refresh-token session for auth route tests."""

    async def _persist(user_email: str, user_id: int):
        access_token, access_token_jti = (
            auth_service.create_access_token(
                payload={"sub": user_email}
            )
        )
        refresh_token = auth_service.create_refresh_token(
            payload={"sub": user_email}
        )
        refresh_token_hash = auth_service.get_token_hash(
            refresh_token
        )

        async with TestingSessionLocal() as session:
            await repository_auth.create_user_session(
                refresh_token_hash=refresh_token_hash,
                access_token_jti=access_token_jti,
                user_id=user_id,
                db=session,
            )

        return access_token, refresh_token

    return lambda **kwargs: asyncio.run(_persist(**kwargs))


@pytest.fixture()
def persist_password_reset_token():
    """Persist one password reset token for auth route tests."""

    async def _persist(user_id: int, user_email: str) -> str:
        token = auth_service.create_reset_password_token(
            {"sub": user_email}
        )
        token_hash = auth_service.get_token_hash(token)

        async with TestingSessionLocal() as session:
            await repository_auth.create_password_reset_token(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=datetime.now(timezone.utc)
                + timedelta(
                    minutes=auth_service.password_reset_token_minutes
                ),
                db=session,
            )

        return token

    return lambda **kwargs: asyncio.run(_persist(**kwargs))


@pytest.fixture()
def mock_send_email(monkeypatch):
    """Disable real email sending for auth route tests."""

    send_email_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(auth_routes, "send_email", send_email_mock)
    return send_email_mock


@pytest.fixture()
def mock_blacklist_service(monkeypatch):
    """Disable Redis-backed blacklist writes for logout route tests."""

    blacklist_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        token_blacklist_service,
        "add_access_token_jti_to_blacklist",
        blacklist_mock,
    )
    return blacklist_mock


@pytest.fixture()
def mock_blacklist_lookup(monkeypatch):
    """Disable Redis-backed blacklist reads for auth token tests."""

    lookup_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(
        token_blacklist_service,
        "is_blacklisted",
        lookup_mock,
    )
    return lookup_mock


@pytest.fixture()
def disable_route_auth_override():
    """Temporarily disable the route-level auth override for token tests."""

    original_override = app.dependency_overrides.pop(
        auth_service.get_current_user, None
    )
    yield
    if original_override is not None:
        app.dependency_overrides[auth_service.get_current_user] = (
            original_override
        )


def test_signup_returns_created_user_and_schedules_email(
    client, signup_payload, mock_send_email
) -> None:
    """Register a new user and schedule a confirmation email."""

    response = client.post(f"{PREFIX}/signup", json=signup_payload)

    assert response.status_code == 201, response.text
    data = response.json()

    assert data["username"] == signup_payload["username"]
    assert data["email"] == signup_payload["email"]
    assert data["role"] == Role.user.value


def test_signin_returns_access_token_and_refresh_cookie(
    client, user_factory
) -> None:
    """Authenticate a confirmed user and issue a refresh cookie."""

    user = user_factory(
        password=VALID_PASSWORD,
        confirmed=True,
    )

    response = client.post(
        f"{PREFIX}/signin",
        json={
            "email": user.email,
            "password": VALID_PASSWORD,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["token_type"] == TOKEN_TYPE_BEARER
    assert "access_token" in data
    assert auth_routes.REFRESH_TOKEN in response.headers["set-cookie"]


def test_signin_returns_401_for_invalid_password(
    client, user_factory
) -> None:
    """Reject sign-in when the submitted password is invalid."""

    user = user_factory(
        password=VALID_PASSWORD,
        confirmed=True,
    )

    response = client.post(
        f"{PREFIX}/signin",
        json={
            "email": user.email,
            "password": NEW_VALID_PASSWORD,
        },
    )

    assert response.status_code == 401, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.invalid_email_or_password.value
    )


def test_logout_returns_204_and_clears_refresh_cookie(
    client,
    seeded_admin_user,
    persist_user_session,
    mock_blacklist_service,
) -> None:
    """Log out the current session and clear the refresh-token cookie."""

    access_token, refresh_token = persist_user_session(
        user_email=seeded_admin_user.email,
        user_id=seeded_admin_user.id,
    )
    client.cookies.set(auth_routes.REFRESH_TOKEN, refresh_token)

    response = client.post(
        f"{PREFIX}/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 204, response.text
    assert auth_routes.REFRESH_TOKEN in response.headers["set-cookie"]


def test_logout_returns_401_for_invalid_access_token(
    client,
    disable_route_auth_override,
    mock_blacklist_lookup,
) -> None:
    """Reject logout when the bearer access token is invalid."""

    response = client.post(
        f"{PREFIX}/logout",
        headers={"Authorization": f"Bearer {INVALID_TOKEN}"},
    )

    assert response.status_code == 401, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.could_not_validate_credentials.value
    )


def test_logout_from_all_devices_returns_204(
    client,
    seeded_admin_user,
    persist_user_session,
    mock_blacklist_service,
) -> None:
    """Log out all stored sessions for the current authenticated user."""

    access_token, _ = persist_user_session(
        user_email=seeded_admin_user.email,
        user_id=seeded_admin_user.id,
    )

    response = client.post(
        f"{PREFIX}/logout-from-all-devices",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 204, response.text


def test_logout_from_all_devices_returns_401_for_invalid_access_token(
    client,
    disable_route_auth_override,
    mock_blacklist_lookup,
) -> None:
    """Reject logout-from-all-devices when the bearer token is invalid."""

    response = client.post(
        f"{PREFIX}/logout-from-all-devices",
        headers={"Authorization": f"Bearer {INVALID_TOKEN}"},
    )

    assert response.status_code == 401, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.could_not_validate_credentials.value
    )


def test_confirm_email_returns_success_message(
    client, user_factory
) -> None:
    """Confirm a user's email when the token is valid."""

    user = user_factory(
        password=VALID_PASSWORD,
        confirmed=False,
    )
    token = auth_service.create_email_confirm_token(
        {"sub": user.email}
    )

    response = client.get(f"{PREFIX}/confirm-email/{token}")

    assert response.status_code == 200, response.text
    assert (
        response.json()["message"]
        == EmailMessages.email_confirmed.value
    )


def test_confirm_email_returns_422_for_invalid_token(
    client,
) -> None:
    """Reject email confirmation when the token is invalid."""

    response = client.get(f"{PREFIX}/confirm-email/{INVALID_TOKEN}")

    assert response.status_code == 422, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.invalid_token_for_email_verification.value
    )


def test_request_confirm_email_returns_generic_success_message(
    client, user_factory, mock_send_email
) -> None:
    """Request a new confirmation email for an unconfirmed user."""

    user = user_factory(
        password=VALID_PASSWORD,
        confirmed=False,
    )

    response = client.post(
        f"{PREFIX}/request-confirm-email",
        json={"email": user.email},
    )

    assert response.status_code == 200, response.text
    assert (
        response.json()["message"]
        == EmailMessages.check_email_forconfirmation.value
    )


def test_refresh_returns_new_access_token_and_rotated_cookie(
    client, user_factory, persist_user_session
) -> None:
    """Refresh an authenticated session using the refresh-token cookie."""

    user = user_factory(
        password=VALID_PASSWORD,
        confirmed=True,
    )
    access_token, refresh_token = persist_user_session(
        user_email=user.email,
        user_id=user.id,
    )
    client.cookies.set(auth_routes.REFRESH_TOKEN, refresh_token)

    response = client.post(f"{PREFIX}/refresh")

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["token_type"] == TOKEN_TYPE_BEARER
    assert "access_token" in data
    assert data["access_token"] != access_token
    assert auth_routes.REFRESH_TOKEN in response.headers["set-cookie"]


def test_refresh_returns_401_without_refresh_cookie(client) -> None:
    """Reject refresh when the refresh-token cookie is missing."""

    response = client.post(f"{PREFIX}/refresh")

    assert response.status_code == 401, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.could_not_validate_token.value
    )


def test_refresh_returns_401_for_invalid_refresh_token(
    client,
) -> None:
    """Reject refresh when the refresh-token cookie is invalid."""

    client.cookies.set(auth_routes.REFRESH_TOKEN, INVALID_TOKEN)

    response = client.post(f"{PREFIX}/refresh")

    assert response.status_code == 401, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.could_not_validate_credentials.value
    )


def test_password_reset_request_returns_generic_message(
    client, user_factory, mock_send_email
) -> None:
    """Request a password reset email without exposing account existence."""

    user = user_factory(
        password=VALID_PASSWORD,
        confirmed=True,
    )

    response = client.post(
        f"{PREFIX}/password-reset/request",
        json={"email": user.email},
    )

    assert response.status_code == 200, response.text
    assert (
        response.json()["message"]
        == EmailMessages.reset_password_email_exists.value
    )


def test_password_reset_verify_returns_204_for_valid_token(
    client,
    user_factory,
    persist_password_reset_token,
    monkeypatch,
) -> None:
    """Validate a stored password reset token with a mocked DB token row."""

    user = user_factory(
        password=VALID_PASSWORD,
        confirmed=True,
    )
    token = persist_password_reset_token(
        user_id=user.id,
        user_email=user.email,
    )
    monkeypatch.setattr(
        repository_auth,
        "get_password_reset_token_by_hash",
        AsyncMock(
            return_value=SimpleNamespace(
                used_at=None,
                expires_at=datetime.now(timezone.utc)
                + timedelta(
                    minutes=auth_service.password_reset_token_minutes
                ),
            )
        ),
    )

    response = client.get(f"{PREFIX}/password-reset/verify/{token}")

    assert response.status_code == 204, response.text


def test_password_reset_verify_returns_400_for_invalid_token(
    client,
) -> None:
    """Reject password reset verification when the token is invalid."""

    response = client.get(
        f"{PREFIX}/password-reset/verify/{INVALID_TOKEN}"
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.invalid_or_expired_password_reset_token.value
    )


def test_password_reset_confirm_returns_204_and_updates_password(
    client,
    user_factory,
    persist_password_reset_token,
    monkeypatch,
) -> None:
    """Confirm a password reset and persist the new password hash."""

    user = user_factory(
        password=VALID_PASSWORD,
        confirmed=True,
    )
    token = persist_password_reset_token(
        user_id=user.id,
        user_email=user.email,
    )
    monkeypatch.setattr(
        repository_auth,
        "get_password_reset_token_by_hash",
        AsyncMock(
            return_value=SimpleNamespace(
                used_at=None,
                expires_at=datetime.now(timezone.utc)
                + timedelta(
                    minutes=auth_service.password_reset_token_minutes
                ),
            )
        ),
    )
    monkeypatch.setattr(
        repository_auth,
        "mark_password_reset_token_as_used",
        AsyncMock(return_value=None),
    )

    response = client.patch(
        f"{PREFIX}/password-reset/confirm",
        json={
            "token": token,
            "password": NEW_VALID_PASSWORD,
        },
    )

    assert response.status_code == 204, response.text


def test_password_reset_confirm_returns_400_for_invalid_token(
    client,
) -> None:
    """Reject password reset confirmation when the token is invalid."""

    response = client.patch(
        f"{PREFIX}/password-reset/confirm",
        json={
            "token": INVALID_TOKEN,
            "password": NEW_VALID_PASSWORD,
        },
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.invalid_or_expired_password_reset_token.value
    )
