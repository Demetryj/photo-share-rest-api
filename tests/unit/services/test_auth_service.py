"""Unit tests for password and token helpers in AuthService."""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.user import PasswordResetToken, User, UserSession
from src.services.auth import auth_service

PLAIN_PASSWORD = "Qwerty123!"
EMAIL = "test@mail.com"


@pytest.fixture()
def refresh_token() -> str:
    """Generate an refresh token."""

    token = auth_service.create_refresh_token(payload={"sub": EMAIL})
    return token


@pytest.fixture()
def db_session_mock() -> AsyncMock:
    """Return an async session mock for isolated AuthService unit tests."""

    return AsyncMock(spec=AsyncSession)


def test_create_hashed_password_returns_hashed_value() -> None:
    """Create a password hash that differs from the original plain password."""

    plain_password = PLAIN_PASSWORD

    hashed_password = auth_service.create_hashed_password(
        plain_password=plain_password
    )

    assert hashed_password != plain_password
    assert isinstance(hashed_password, str)
    assert hashed_password


# ===========================================================================
def test_verify_password_returns_true_for_valid_password() -> None:
    """Return True when the provided plain password matches its hash."""

    plain_password = PLAIN_PASSWORD
    hashed_password = auth_service.create_hashed_password(
        plain_password=plain_password
    )

    result = auth_service.verify_password(
        plain_password=plain_password,
        hashed_password=hashed_password,
    )

    assert result is True


def test_verify_password_returns_false_for_invalid_password() -> None:
    """Return False when the provided plain password does not match the hash."""

    hashed_password = auth_service.create_hashed_password(
        plain_password=PLAIN_PASSWORD
    )

    result = auth_service.verify_password(
        plain_password="WrongPassword123!",
        hashed_password=hashed_password,
    )

    assert result is False


# ===========================================================================
def test_get_token_hash_returns_sha256_hash() -> None:
    """Return a deterministic SHA-256 hex digest for the provided token."""

    token = "sample-refresh-token"

    result = auth_service.get_token_hash(token=token)

    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    assert result == expected_hash


# ===========================================================================
def test_create_access_token_returns_token_and_jti() -> None:
    """Create an access token with the expected identity and JWT claims."""

    access_token, jti = auth_service.create_access_token(
        {"sub": EMAIL}
    )

    payload = auth_service.decode_token(access_token)

    assert access_token
    assert jti
    assert payload.get("scope") == auth_service.access_token_name
    assert payload.get("sub") == EMAIL
    assert payload.get("jti") == jti
    assert payload.get("exp") is not None


# ===========================================================================
def test_create_refresh_token_returns_refresh_token() -> None:
    """Create a refresh token with the expected identity and JWT claims."""

    refresh_token = auth_service.create_refresh_token({"sub": EMAIL})

    payload = auth_service.decode_token(refresh_token)

    assert refresh_token
    assert payload.get("scope") == auth_service.refresh_token_name
    assert payload.get("sub") == EMAIL
    assert payload.get("exp") is not None


# ===========================================================================
def test_create_email_confirm_token_returns_token() -> None:
    """Create an email confirm token with the expected identity and JWT claims."""

    email_confirm_token = auth_service.create_email_confirm_token(
        {"sub": EMAIL}
    )

    payload = auth_service.decode_token(email_confirm_token)

    assert email_confirm_token
    assert (
        payload.get("scope") == auth_service.email_confirm_token_name
    )
    assert payload.get("sub") == EMAIL
    assert payload.get("exp") is not None


# ===========================================================================
def test_create_reset_password_token_returns_token() -> None:
    """Create a reset password token with the expected identity and JWT claims."""

    password_reset_token = auth_service.create_reset_password_token(
        {"sub": EMAIL}
    )

    payload = auth_service.decode_token(password_reset_token)

    assert password_reset_token
    assert payload.get("scope") == auth_service.password_reset_token
    assert payload.get("sub") == EMAIL
    assert payload.get("exp") is not None


# ===========================================================================
def test_decode_token_returns_payload_for_valid_token() -> None:
    """Decode and return the payload for a valid signed token."""

    access_token, jti = auth_service.create_access_token(
        {"sub": EMAIL}
    )

    payload = auth_service.decode_token(access_token)

    assert payload.get("scope") == auth_service.access_token_name
    assert payload.get("sub") == EMAIL
    assert payload.get("jti") == jti
    assert payload.get("exp") is not None


def test_decode_token_raises_for_invalid_token() -> None:
    """Raise JWTError when the provided token is malformed or invalid."""

    with pytest.raises(JWTError):
        auth_service.decode_token("invalid-token")


def test_decode_token_without_exp_verification_returns_payload_for_expired_token() -> (
    None
):
    """Return payload even when the token is already expired."""

    expired_token, jti = auth_service.create_access_token(
        payload={"sub": EMAIL},
        expires_delta=-1,
    )

    payload = auth_service.decode_token_without_exp_verification(
        expired_token
    )

    assert payload is not None
    assert payload.get("scope") == auth_service.access_token_name
    assert payload.get("sub") == EMAIL
    assert payload.get("jti") == jti


def test_decode_token_without_exp_verification_returns_none_for_invalid_token() -> (
    None
):
    """Return None when the provided token is malformed or invalid."""

    payload = auth_service.decode_token_without_exp_verification(
        "invalid-token"
    )

    assert payload is None


# ===========================================================================
def test_get_token_jti_returns_jti_for_valid_token(
    access_token_with_jti: tuple[str, str],
) -> None:
    """Return the token JTI when the provided token is valid."""

    token, _ = access_token_with_jti

    jti = auth_service.get_token_jti(token)

    assert jti
    assert isinstance(jti, str)


def test_get_token_jti_returns_none_for_invalid_token() -> None:
    """Return None when the provided token is malformed or invalid."""

    jti = auth_service.get_token_jti("invalid_token")

    assert jti is None


def test_get_token_jti_returns_none_when_claim_is_missing() -> None:
    """Return None when the decoded token payload does not contain JTI."""

    token = jwt.encode(
        {
            "sub": EMAIL,
            "scope": auth_service.access_token_name,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        auth_service.SECRET_KEY,
        algorithm=auth_service.ALGORITHM,
    )

    jti = auth_service.get_token_jti(token)

    assert jti is None


def test_get_token_jti_returns_none_when_claim_is_empty() -> None:
    """Return None when the decoded token payload contains an empty JTI."""

    token = jwt.encode(
        {
            "sub": EMAIL,
            "scope": auth_service.access_token_name,
            "jti": "",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        auth_service.SECRET_KEY,
        algorithm=auth_service.ALGORITHM,
    )

    jti = auth_service.get_token_jti(token)

    assert jti is None


def test_get_token_jti_returns_none_when_claim_is_not_string() -> (
    None
):
    """Return None when the decoded token payload contains a non-string JTI."""

    token = jwt.encode(
        {
            "sub": EMAIL,
            "scope": auth_service.access_token_name,
            "jti": 123,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        auth_service.SECRET_KEY,
        algorithm=auth_service.ALGORITHM,
    )

    jti = auth_service.get_token_jti(token)

    assert jti is None


# ===========================================================================
def test_get_token_exp_returns_exp_for_valid_token(
    access_token_with_jti: tuple[str, str],
) -> None:
    """Return the exp claim when the provided token is valid."""

    token, _ = access_token_with_jti

    exp = auth_service.get_token_exp(token)

    assert exp is not None
    assert isinstance(exp, int)


def test_get_token_exp_returns_none_for_invalid_token() -> None:
    """Return None when the provided token is malformed or invalid."""

    exp = auth_service.get_token_exp("invalid_token")

    assert exp is None


def test_get_token_exp_returns_none_when_claim_is_missing() -> None:
    """Return None when the decoded token payload does not contain exp."""

    token = jwt.encode(
        {
            "sub": EMAIL,
            "scope": auth_service.access_token_name,
            "jti": "sample-jti",
        },
        auth_service.SECRET_KEY,
        algorithm=auth_service.ALGORITHM,
    )

    exp = auth_service.get_token_exp(token)

    assert exp is None


def test_get_token_exp_returns_none_when_claim_is_not_integer() -> (
    None
):
    """Return None when the decoded token payload contains a non-integer exp."""

    token = jwt.encode(
        {
            "sub": EMAIL,
            "scope": auth_service.access_token_name,
            "jti": "sample-jti",
            "exp": "not-an-int",
        },
        auth_service.SECRET_KEY,
        algorithm=auth_service.ALGORITHM,
    )

    exp = auth_service.get_token_exp(token)

    assert exp is None


# ===========================================================================
@pytest.mark.asyncio
async def test_get_email_from_refresh_token_returns_email_for_valid_refresh_token(
    refresh_token: str,
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return the email when the refresh token is valid and session exists."""

    refresh_token = refresh_token

    # Decode the token to compare the final returned email with its subject.
    payload = auth_service.decode_token(refresh_token)
    assert payload.get("scope") == auth_service.refresh_token_name

    # The service resolves the persisted session by the hashed refresh token.
    refresh_token_hash = auth_service.get_token_hash(refresh_token)
    session = UserSession(
        refresh_token_hash=refresh_token_hash,
        access_token_jti="sample-access-jti",
    )
    repository_mock = AsyncMock(return_value=session)
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_user_session_by_refresh_token_hash",
        repository_mock,
    )

    email = await auth_service.get_email_from_refresh_token(
        refresh_token=refresh_token, db=db_session_mock
    )

    repository_mock.assert_awaited_once_with(
        refresh_token_hash=refresh_token_hash,
        db=db_session_mock,
    )
    assert session
    assert email == payload.get("sub")


@pytest.mark.asyncio
async def test_get_email_from_refresh_token_raises_401_for_invalid_refresh_token(
    db_session_mock: AsyncMock,
) -> None:
    """Raise 401 when the provided refresh token is malformed or invalid."""

    with pytest.raises(JWTError):
        auth_service.decode_token("invalid-token")

    with pytest.raises(Exception) as exc_info:
        await auth_service.get_email_from_refresh_token(
            refresh_token="invalid-token",
            db=db_session_mock,
        )

    assert getattr(exc_info.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_get_email_from_refresh_token_raises_401_for_wrong_scope(
    db_session_mock: AsyncMock,
) -> None:
    """Raise 401 when the token scope is not refresh_token."""

    access_token, _ = auth_service.create_access_token(
        payload={"sub": EMAIL}
    )

    with pytest.raises(Exception) as exc_info:
        await auth_service.get_email_from_refresh_token(
            refresh_token=access_token,
            db=db_session_mock,
        )

    assert getattr(exc_info.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_get_email_from_refresh_token_raises_401_when_session_not_found(
    refresh_token: str,
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 401 when the refresh token session does not exist in the database."""

    refresh_token = refresh_token
    refresh_token_hash = auth_service.get_token_hash(refresh_token)

    repository_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_user_session_by_refresh_token_hash",
        repository_mock,
    )

    with pytest.raises(Exception) as exc_info:
        await auth_service.get_email_from_refresh_token(
            refresh_token=refresh_token,
            db=db_session_mock,
        )

    repository_mock.assert_awaited_once_with(
        refresh_token_hash=refresh_token_hash,
        db=db_session_mock,
    )
    assert getattr(exc_info.value, "status_code", None) == 401


@pytest.mark.asyncio
async def test_get_email_from_refresh_token_raises_401_when_payload_has_no_sub(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 401 when the decoded refresh token payload does not contain sub."""

    refresh_token = auth_service.create_refresh_token(payload={})
    refresh_token_hash = auth_service.get_token_hash(refresh_token)

    # Return an existing session so the failure comes specifically from the
    # missing subject claim instead of the repository lookup.
    session = UserSession(
        refresh_token_hash=refresh_token_hash,
        access_token_jti="sample-access-jti",
    )
    repository_mock = AsyncMock(return_value=session)
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_user_session_by_refresh_token_hash",
        repository_mock,
    )

    with pytest.raises(Exception) as exc_info:
        await auth_service.get_email_from_refresh_token(
            refresh_token=refresh_token,
            db=db_session_mock,
        )

    repository_mock.assert_awaited_once_with(
        refresh_token_hash=refresh_token_hash,
        db=db_session_mock,
    )
    assert getattr(exc_info.value, "status_code", None) == 401


# ===========================================================================
def test_get_email_from_email_token_returns_email_for_valid_token() -> (
    None
):
    """Return email when the provided email-confirm token is valid."""

    token = auth_service.create_email_confirm_token({"sub": EMAIL})

    email = auth_service.get_email_from_email_token(token)

    assert email == EMAIL


def test_get_email_from_email_token_raises_401_for_wrong_scope() -> (
    None
):
    """Raise 401 when the token scope is not email_token."""

    token = auth_service.create_access_token({"sub": EMAIL})[0]

    with pytest.raises(HTTPException) as exc_info:
        auth_service.get_email_from_email_token(token)

    assert exc_info.value.status_code == 401


def test_get_email_from_email_token_raises_401_when_payload_has_no_sub() -> (
    None
):
    """Raise 401 when the decoded email token payload does not contain sub."""

    token = auth_service.create_email_confirm_token({})

    with pytest.raises(HTTPException) as exc_info:
        auth_service.get_email_from_email_token(token)

    assert exc_info.value.status_code == 401


def test_get_email_from_email_token_raises_422_for_invalid_token() -> (
    None
):
    """Raise 422 when the provided email token is malformed or invalid."""

    with pytest.raises(HTTPException) as exc_info:
        auth_service.get_email_from_email_token("invalid-token")

    assert exc_info.value.status_code == 422


# ===========================================================================
def test_get_email_from_password_reset_token_returns_email_for_valid_token() -> (
    None
):
    """Return email when the provided password-reset token is valid."""

    token = auth_service.create_reset_password_token({"sub": EMAIL})

    email = auth_service.get_email_from_password_reset_token(token)

    assert email == EMAIL


def test_get_email_from_password_reset_token_raises_400_for_wrong_scope() -> (
    None
):
    """Raise 400 when the token scope is not password_reset_token."""

    token = auth_service.create_access_token({"sub": EMAIL})[0]

    with pytest.raises(HTTPException) as exc_info:
        auth_service.get_email_from_password_reset_token(token)

    assert exc_info.value.status_code == 400


def test_get_email_from_password_reset_token_raises_400_when_payload_has_no_sub() -> (
    None
):
    """Raise 400 when the decoded reset token payload does not contain sub."""

    token = auth_service.create_reset_password_token({})

    with pytest.raises(HTTPException) as exc_info:
        auth_service.get_email_from_password_reset_token(token)

    assert exc_info.value.status_code == 400


def test_get_email_from_password_reset_token_raises_400_for_invalid_token() -> (
    None
):
    """Raise 400 when the provided reset token is malformed or invalid."""

    with pytest.raises(HTTPException) as exc_info:
        auth_service.get_email_from_password_reset_token(
            "invalid-token"
        )

    assert exc_info.value.status_code == 400


# ===========================================================================
@pytest.mark.asyncio
async def test_validate_password_reset_token_returns_email_for_valid_token(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return email when the reset token exists, is unused, and not expired."""

    token = auth_service.create_reset_password_token({"sub": EMAIL})

    token_hash = auth_service.get_token_hash(token)

    password_reset_token_record = PasswordResetToken(
        user_id=1,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(
            minutes=auth_service.password_reset_token_minutes
        ),
        used_at=None,
    )

    repository_mock = AsyncMock(
        return_value=password_reset_token_record
    )
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_password_reset_token_by_hash",
        repository_mock,
    )

    email = await auth_service.validate_password_reset_token(
        token=token, db=db_session_mock
    )

    repository_mock.assert_awaited_once_with(
        token_hash=token_hash,
        db=db_session_mock,
    )
    assert email == EMAIL
    assert password_reset_token_record.used_at is None
    assert password_reset_token_record.expires_at > datetime.now(
        timezone.utc
    )


@pytest.mark.asyncio
async def test_validate_password_reset_token_raises_400_when_token_record_not_found(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 400 when the reset token record does not exist in the database."""

    token = auth_service.create_reset_password_token({"sub": EMAIL})
    token_hash = auth_service.get_token_hash(token)

    repository_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_password_reset_token_by_hash",
        repository_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.validate_password_reset_token(
            token=token,
            db=db_session_mock,
        )

    repository_mock.assert_awaited_once_with(
        token_hash=token_hash,
        db=db_session_mock,
    )
    assert getattr(exc_info.value, "status_code", None) == 400


@pytest.mark.asyncio
async def test_validate_password_reset_token_raises_400_when_used_at_is_not_none(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 400 when the reset token record has already been used."""

    token = auth_service.create_reset_password_token({"sub": EMAIL})
    token_hash = auth_service.get_token_hash(token)

    password_reset_token_record = PasswordResetToken(
        user_id=1,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(
            minutes=auth_service.password_reset_token_minutes
        ),
        used_at=datetime.now(timezone.utc),
    )

    repository_mock = AsyncMock(
        return_value=password_reset_token_record
    )
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_password_reset_token_by_hash",
        repository_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.validate_password_reset_token(
            token=token,
            db=db_session_mock,
        )

    repository_mock.assert_awaited_once_with(
        token_hash=token_hash,
        db=db_session_mock,
    )
    assert getattr(exc_info.value, "status_code", None) == 400
    assert password_reset_token_record.used_at is not None


@pytest.mark.asyncio
async def test_validate_password_reset_token_raises_400_when_expires_at_is_le_now(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 400 when the reset token record is already expired."""

    token = auth_service.create_reset_password_token({"sub": EMAIL})
    token_hash = auth_service.get_token_hash(token)

    password_reset_token_record = PasswordResetToken(
        user_id=1,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc),
        used_at=None,
    )

    repository_mock = AsyncMock(
        return_value=password_reset_token_record
    )
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_password_reset_token_by_hash",
        repository_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.validate_password_reset_token(
            token=token,
            db=db_session_mock,
        )

    repository_mock.assert_awaited_once_with(
        token_hash=token_hash,
        db=db_session_mock,
    )
    assert getattr(exc_info.value, "status_code", None) == 400
    assert password_reset_token_record.expires_at <= datetime.now(
        timezone.utc
    )


# ===========================================================================
@pytest.mark.asyncio
async def test_get_current_user_return_user_data_when_user_is_authorized(
    access_token_with_jti: tuple[str, str],
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    user_factory,
) -> None:
    """Return the current user when the access token and session are valid."""

    access_token, jti = access_token_with_jti

    payload = auth_service.decode_token(access_token)
    email = payload.get("sub")
    jti = payload.get("jti")

    assert email
    assert jti
    assert isinstance(jti, str)

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=access_token,
    )

    # The token must not be blacklisted for the request to continue.
    is_blacklisted = False
    repository_mock_is_blacklisted = AsyncMock(
        return_value=is_blacklisted
    )
    monkeypatch.setattr(
        "src.services.auth.token_blacklist_service.is_blacklisted",
        repository_mock_is_blacklisted,
    )

    # The access token JTI must still exist in an active persisted session.
    session = UserSession(
        refresh_token_hash="same_refresh_token_hash",
        access_token_jti=jti,
    )
    repository_mock_user_session = AsyncMock(return_value=session)
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_user_session_by_access_token_jti",
        repository_mock_user_session,
    )

    # The user lookup must resolve the authenticated account by token subject.
    user: User = await user_factory()
    repository_mock = AsyncMock(return_value=user)
    monkeypatch.setattr(
        "src.services.auth.repository_user.get_user_by_email",
        repository_mock,
    )

    result = await auth_service.get_current_user(
        credentials=credentials,
        db=db_session_mock,
    )

    repository_mock_is_blacklisted.assert_awaited_once_with(
        token=access_token
    )
    repository_mock_user_session.assert_awaited_once_with(
        access_token_jti=jti,
        db=db_session_mock,
    )
    repository_mock.assert_awaited_once_with(
        email=email,
        db=db_session_mock,
    )
    assert result == user
    assert user.blocked is False


@pytest.mark.asyncio
async def test_get_current_user_raises_401_when_token_is_blacklisted(
    access_token_with_jti: tuple[str, str],
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 401 when the provided access token is blacklisted."""

    access_token, _ = access_token_with_jti
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=access_token,
    )

    blacklist_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "src.services.auth.token_blacklist_service.is_blacklisted",
        blacklist_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.get_current_user(
            credentials=credentials,
            db=db_session_mock,
        )

    blacklist_mock.assert_awaited_once_with(token=access_token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_wrong_token_scope(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 401 when the provided token is not an access token."""

    refresh_token = auth_service.create_refresh_token({"sub": EMAIL})
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=refresh_token,
    )

    blacklist_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "src.services.auth.token_blacklist_service.is_blacklisted",
        blacklist_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.get_current_user(
            credentials=credentials,
            db=db_session_mock,
        )

    blacklist_mock.assert_awaited_once_with(token=refresh_token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_when_payload_has_no_sub(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 401 when the access token payload does not contain sub."""

    token = jwt.encode(
        {
            "scope": auth_service.access_token_name,
            "jti": "sample-access-jti",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        auth_service.SECRET_KEY,
        algorithm=auth_service.ALGORITHM,
    )
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    blacklist_mock = AsyncMock(return_value=False)
    session_mock = AsyncMock(
        return_value=UserSession(
            refresh_token_hash="sample-refresh-hash",
            access_token_jti="sample-access-jti",
        )
    )
    monkeypatch.setattr(
        "src.services.auth.token_blacklist_service.is_blacklisted",
        blacklist_mock,
    )
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_user_session_by_access_token_jti",
        session_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.get_current_user(
            credentials=credentials,
            db=db_session_mock,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_when_payload_has_no_jti(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 401 when the access token payload does not contain jti."""

    token = jwt.encode(
        {
            "sub": EMAIL,
            "scope": auth_service.access_token_name,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        auth_service.SECRET_KEY,
        algorithm=auth_service.ALGORITHM,
    )
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    blacklist_mock = AsyncMock(return_value=False)
    monkeypatch.setattr(
        "src.services.auth.token_blacklist_service.is_blacklisted",
        blacklist_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.get_current_user(
            credentials=credentials,
            db=db_session_mock,
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_when_session_not_found(
    access_token_with_jti: tuple[str, str],
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 401 when the access token JTI is not found in active sessions."""

    access_token, jti = access_token_with_jti
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=access_token,
    )

    blacklist_mock = AsyncMock(return_value=False)
    session_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.services.auth.token_blacklist_service.is_blacklisted",
        blacklist_mock,
    )
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_user_session_by_access_token_jti",
        session_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.get_current_user(
            credentials=credentials,
            db=db_session_mock,
        )

    session_mock.assert_awaited_once_with(
        access_token_jti=jti,
        db=db_session_mock,
    )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_when_user_not_found(
    access_token_with_jti: tuple[str, str],
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 401 when the access token subject user does not exist."""

    access_token, jti = access_token_with_jti
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=access_token,
    )
    payload = auth_service.decode_token(access_token)
    email = payload.get("sub")

    blacklist_mock = AsyncMock(return_value=False)
    session_mock = AsyncMock(
        return_value=UserSession(
            refresh_token_hash="sample-refresh-hash",
            access_token_jti=jti,
        )
    )
    user_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.services.auth.token_blacklist_service.is_blacklisted",
        blacklist_mock,
    )
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_user_session_by_access_token_jti",
        session_mock,
    )
    monkeypatch.setattr(
        "src.services.auth.repository_user.get_user_by_email",
        user_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.get_current_user(
            credentials=credentials,
            db=db_session_mock,
        )

    user_mock.assert_awaited_once_with(
        email=email,
        db=db_session_mock,
    )
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_403_when_user_is_blocked(
    access_token_with_jti: tuple[str, str],
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 403 when the resolved current user is blocked."""

    access_token, jti = access_token_with_jti
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=access_token,
    )
    user = User(
        username="blocked_user",
        email="blocked_user@mail.com",
        password="hashed-password",
        blocked=True,
        confirmed=True,
    )

    blacklist_mock = AsyncMock(return_value=False)
    session_mock = AsyncMock(
        return_value=UserSession(
            refresh_token_hash="sample-refresh-hash",
            access_token_jti=jti,
        )
    )
    user_mock = AsyncMock(return_value=user)
    monkeypatch.setattr(
        "src.services.auth.token_blacklist_service.is_blacklisted",
        blacklist_mock,
    )
    monkeypatch.setattr(
        "src.services.auth.repository_auth.get_user_session_by_access_token_jti",
        session_mock,
    )
    monkeypatch.setattr(
        "src.services.auth.repository_user.get_user_by_email",
        user_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await auth_service.get_current_user(
            credentials=credentials,
            db=db_session_mock,
        )

    assert user.blocked is True
    assert exc_info.value.status_code == 403
