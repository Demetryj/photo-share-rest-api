"""Authentication service helpers for passwords, JWTs, and current-user lookup."""

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import HTTPStatusMessages
from src.config.settings import settings
from src.database.db import get_db
from src.entity.user import User
from src.helpers.create_exception import create_exception
from src.repository import auth as repository_auth
from src.repository import user as repository_user
from src.services.token_blacklist import token_blacklist_service


class AuthService:
    """Application authentication service for passwords, JWTs, and user lookup."""

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    SECRET_KEY = settings.secret_key
    ALGORITHM = settings.hash_algorithm
    security = HTTPBearer()
    access_token_expire_minutes = 15
    refresh_token_expire_days = 7
    email_confirm_token_expire_minutes = 10
    password_reset_token_minutes = 15
    access_token_name = "access_token"
    refresh_token_name = "refresh_token"
    email_confirm_token_name = "email_token"
    password_reset_token = "password_reset_token"
    refresh_cookie_max_age = (
        refresh_token_expire_days * 24 * 60 * 60
    )  # seconds

    # Checks whether a plain-text password matches its stored hash.
    def verify_password(
        self, plain_password: str, hashed_password: str
    ) -> bool:
        """Verify that the provided password matches the stored password hash."""

        return self.pwd_context.verify(
            plain_password, hashed_password
        )

    # Creates a bcrypt hash from a plain-text password.
    def create_hashed_password(self, plain_password: str) -> str:
        """Generate a secure hash for a plain-text user password with bcrypt."""

        return self.pwd_context.hash(plain_password)

    # Build stable hash for storing and looking up tokens (refresh, reset password).
    def get_token_hash(self, token: str) -> str:
        """Build a deterministic SHA-256 hash for a token."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Build a JWT together with its generated JTI so callers can persist the
    # active token identifier without decoding the freshly created token.
    def create_token(
        self,
        payload: dict[str, Any],
        token_scope: str,
        expires_delta: timedelta,
    ) -> tuple[str, str]:
        """Create a signed JWT token together with its generated JTI."""

        current_datetime = datetime.now(timezone.utc)
        expire_datetime = current_datetime + expires_delta
        jti = str(uuid4())

        payload = payload.copy()
        payload.update(
            {
                "iat": current_datetime,
                "exp": expire_datetime,
                "scope": token_scope,
                "jti": jti,
            }
        )

        token = jwt.encode(
            payload, self.SECRET_KEY, algorithm=self.ALGORITHM
        )
        return token, jti

    # Create an access token and return it together with its generated JTI.
    def create_access_token(
        self,
        payload: dict[str, Any],
        expires_delta: Optional[float] = None,
    ) -> tuple[str, str]:
        """Create an access token for user authentication and return its JTI."""

        return self.create_token(
            payload=payload,
            token_scope=self.access_token_name,
            expires_delta=timedelta(
                minutes=(
                    expires_delta
                    if expires_delta
                    else self.access_token_expire_minutes
                )
            ),
        )

    # Create a refresh token JWT used to renew user authentication.
    def create_refresh_token(
        self,
        payload: dict[str, Any],
        expires_delta: Optional[float] = None,
    ) -> str:
        """Create a refresh token for renewing user authentication."""

        token, _ = self.create_token(
            payload=payload,
            token_scope=self.refresh_token_name,
            expires_delta=timedelta(
                days=(
                    expires_delta
                    if expires_delta
                    else self.refresh_token_expire_days
                )
            ),
        )
        return token

    # Generates an email confirmation token with a configurable lifetime.
    def create_email_confirm_token(
        self,
        payload: dict[str, Any],
        expires_value: Optional[int] = None,
    ) -> str:
        """Create a JWT token used to confirm a user's email address."""

        token, _ = self.create_token(
            payload=payload,
            token_scope=self.email_confirm_token_name,
            expires_delta=timedelta(
                minutes=(
                    expires_value
                    if expires_value
                    else self.email_confirm_token_expire_minutes
                )
            ),
        )
        return token

    # Decode and validate JWT signature/expiration.
    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode and validate a JWT."""

        return jwt.decode(token, self.SECRET_KEY, self.ALGORITHM)

    # Decode a JWT without checking expiration to read technical claims.
    def decode_token_without_exp_verification(
        self, token: str
    ) -> dict[str, Any] | None:
        """Decode a JWT while ignoring expiration validation.

        This is used for technical token metadata reads such as ``jti`` and
        ``exp`` when a token may be near expiration but still needs to be
        revoked or inspected.
        """
        try:
            return jwt.decode(
                token,
                self.SECRET_KEY,
                algorithms=[self.ALGORITHM],
                options={"verify_exp": False},
            )
        except JWTError:
            return None

    # Extract the JTI claim from a token for active-session validation or revocation.
    def get_token_jti(self, token: str) -> str | None:
        """Extract the token ``jti`` claim or return ``None``."""
        payload = self.decode_token_without_exp_verification(token)
        if payload is None:
            return None

        jti = payload.get("jti")
        if not isinstance(jti, str) or not jti:
            return None

        return jti

    # Extract the expiration timestamp claim from a token for TTL calculations.
    def get_token_exp(self, token: str) -> int | None:
        """Extract the token ``exp`` claim as a Unix timestamp."""
        payload = self.decode_token_without_exp_verification(token)
        if payload is None:
            return None

        exp = payload.get("exp")
        if not isinstance(exp, int):
            return None

        return exp

    # Extract email from a refresh token and ensure the owning session exists.
    async def get_email_from_refresh_token(
        self, refresh_token: str, db: AsyncSession
    ) -> str:
        """Extract the user email from a valid persisted refresh-token session."""

        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=HTTPStatusMessages.could_not_validate_credentials.value,
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = self.decode_token(refresh_token)
            if payload.get("scope") != self.refresh_token_name:
                raise credentials_exception

            # The refresh token must still belong to an active persisted
            # user session; otherwise it has been revoked or rotated away.
            refresh_token_hash = self.get_token_hash(refresh_token)
            session = await repository_auth.get_user_session_by_refresh_token_hash(
                refresh_token_hash=refresh_token_hash,
                db=db,
            )
            if session is None:
                raise credentials_exception

            email = payload.get("sub")
            if email is None:
                raise credentials_exception

            return email
        except JWTError:
            raise credentials_exception

    # Validate email-confirmation token and extract user's email from `sub`.
    def get_email_from_email_token(self, token: str) -> str:
        """Extract the user email from an email confirmation token."""

        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=HTTPStatusMessages.invalid_token_for_email_verification.value,
        )

        try:
            payload = self.decode_token(token)
            if payload.get("scope") != self.email_confirm_token_name:
                raise credentials_exception
            email = payload.get("sub")
            if email is None:
                raise credentials_exception
            return email
        except JWTError:
            create_exception(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message=HTTPStatusMessages.invalid_token_for_email_verification.value,
            )

    # Validate an access token against the Redis blacklist, JWT claims, the
    # persisted user-session record, and the current user state before
    # allowing access to protected routes.
    async def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        """Authorize a request and return the current active user.

        The method rejects blacklisted access tokens, validates the JWT
        signature, expiration, and scope, ensures that the token contains
        both ``sub`` and ``jti`` claims, verifies that the access-token JTI
        still belongs to an active persisted user session, loads the
        corresponding user, and finally rejects blocked users.
        """

        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=HTTPStatusMessages.could_not_validate_credentials.value,
            headers={"WWW-Authenticate": "Bearer"},
        )

        token = credentials.credentials
        # Reject tokens that were explicitly revoked during logout.
        is_blacklisted = await token_blacklist_service.is_blacklisted(
            token=token
        )
        if is_blacklisted:
            raise credentials_exception

        try:
            # Decode the JWT and ensure it is an access token with the
            # required identity claims.
            payload = self.decode_token(token)
            if payload.get("scope") == self.access_token_name:
                email = payload.get("sub")
                jti = payload.get("jti")
                if email is None or jti is None:
                    raise credentials_exception
            else:
                raise credentials_exception
        except JWTError:
            raise credentials_exception

        # The token JTI must still be present in an active user-session
        # record; otherwise the token has been revoked or rotated away.
        session = await repository_auth.get_user_session_by_access_token_jti(
            access_token_jti=jti,
            db=db,
        )

        if session is None:
            raise credentials_exception

        # Resolve the user account referenced by the token subject.
        user = await repository_user.get_user_by_email(
            email=email, db=db
        )
        if user is None:
            raise credentials_exception

        # Blocked users must not be allowed to access protected endpoints.
        if user.blocked:
            create_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                message=HTTPStatusMessages.forbidden.value,
            )
        return user


auth_service = AuthService()
