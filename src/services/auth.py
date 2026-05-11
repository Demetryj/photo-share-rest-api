from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.config.messages import HTTPStatusMessages
from src.config.settings import settings


class AuthService:

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    SECRET_KEY = settings.secret_key
    ALGORITHM = settings.hash_algorithm
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/signin")
    access_token_expire_minutes = 15
    refresh_token_expire_days = 7
    email_confirm_token_expire_minutes = 10
    password_reset_token_minutes = 15
    access_token_name = "access_token"
    refresh_token_name = "refresh_token"
    email_confirm_token_name = "email_token"
    password_reset_token = "password_reset_token"

    # Checks whether a plain-text password matches its stored hash.
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify that the provided password matches the stored password hash."""

        return self.pwd_context.verify(plain_password, hashed_password)

    # Creates a bcrypt hash from a plain-text password.
    def create_hashed_password(self, plain_password: str) -> str:
        """Generate a secure hash for a plain-text user password with bcrypt."""

        return self.pwd_context.hash(plain_password)

    # Builds a JWT token with issue time, expiration, and scope claims.
    def create_token(
        self, payload: dict[str, Any], token_scope: str, expires_delta: timedelta
    ) -> str:
        """Create a signed JWT token for the provided payload and scope."""

        current_datetime = datetime.now(timezone.utc)
        expire_datetime = current_datetime + expires_delta

        payload = payload.copy()
        payload.update(
            {"iat": current_datetime, "exp": expire_datetime, "scope": token_scope}
        )

        return jwt.encode(payload, self.SECRET_KEY, algorithm=self.ALGORITHM)

    # Creates an access token with the default or overridden expiration time.
    def create_access_token(
        self, payload: dict[str, Any], expires_delta: Optional[float] = None
    ) -> str:
        """Create an access token for user authentication."""

        return self.create_token(
            payload=payload,
            token_scope=self.access_token_name,
            expires_delta=timedelta(
                minutes=(
                    expires_delta if expires_delta else self.access_token_expire_minutes
                )
            ),
        )

    # Creates a refresh token used to obtain a new access token after expiration.
    def create_refresh_token(
        self, payload: dict[str, Any], expires_delta: Optional[float] = None
    ) -> str:
        """Create a refresh token for renewing user authentication."""

        return self.create_token(
            payload=payload,
            token_scope=self.refresh_token_name,
            expires_delta=timedelta(
                days=expires_delta if expires_delta else self.refresh_token_expire_days
            ),
        )

    # Generates an email confirmation token with a configurable lifetime.
    def create_email_confirm_token(
        self, payload: dict[str, Any], expires_value: Optional[int] = None
    ) -> str:
        """Create a JWT token used to confirm a user's email address."""

        return self.create_token(
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

    # Decode and validate JWT signature/expiration.
    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode and validate a JWT."""

        return jwt.decode(token, self.SECRET_KEY, self.ALGORITHM)

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
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=HTTPStatusMessages.invalid_token_for_email_verification.value,
            )


auth_service = AuthService()
