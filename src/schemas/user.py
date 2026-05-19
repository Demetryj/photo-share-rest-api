"""Pydantic schemas for auth, public profile, and self-profile flows."""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
)

from src.entity.user import Role

SPECIAL_CHARS = "!@#$%^&*"
USERNAME_PATTERN = re.compile(r"^[a-z](?:[a-z0-9_]*[a-z0-9])?$")
DISPLAY_NAME_PATTERN = re.compile(
    r"^[^\W\d_][^\W\d_'\- ]*$", re.UNICODE
)


class BaseAuthUserRequestSchema(BaseModel):
    """Base schema with common user identity fields for auth-related requests."""

    email: EmailStr = Field(max_length=150)
    password: str = Field(
        min_length=8,
        max_length=16,
        description=(
            "Password must contain at least one lowercase letter, one uppercase "
            f"letter, one digit, and one special character from {SPECIAL_CHARS}."
        ),
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(ch.islower() for ch in value):
            raise ValueError(
                "Password must contain at least one lowercase letter."
            )
        if not any(ch.isupper() for ch in value):
            raise ValueError(
                "Password must contain at least one uppercase letter."
            )
        if not any(ch.isdigit() for ch in value):
            raise ValueError(
                "Password must contain at least one digit."
            )
        if not any(ch in SPECIAL_CHARS for ch in value):
            raise ValueError(
                "Password must contain at least one special character: "
                f"{SPECIAL_CHARS}."
            )
        return value


class SignUpRequestSchema(BaseAuthUserRequestSchema):
    """User registration request schema."""

    username: str = Field(min_length=3, max_length=30)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Username must start with a lowercase letter and contain "
                "only lowercase letters, digits, and underscores, and it "
                "must not end with an underscore."
            )
        return value


class UpdateMyProfileRequestSchema(BaseModel):
    """Schema for updating editable fields of the current user."""

    email: EmailStr | None = None
    display_name: str | None = Field(
        default=None, min_length=2, max_length=60
    )
    avatar: HttpUrl | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return value

        normalized_value = value.strip()

        if not normalized_value:
            raise ValueError("Display name must not be empty.")

        if not DISPLAY_NAME_PATTERN.fullmatch(normalized_value):
            raise ValueError(
                "Display name may contain only letters, spaces, hyphens, "
                "and apostrophes."
            )

        return normalized_value


class SignUpResponseSchema(BaseModel):
    """User response schema returned by auth endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    avatar: HttpUrl | None
    role: Role
    created_at: datetime
    updated_at: datetime


class ProfileResponseSchema(BaseModel):
    """User profile response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str | None = None
    avatar: HttpUrl | None
    created_at: datetime
    photos_count: int = 0
    comments_count: int = 0


class MyProfileResponseSchema(BaseModel):
    """Response schema for the current user's editable profile data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str | None = None
    email: EmailStr
    avatar: HttpUrl | None
    role: Role
    confirmed: bool
    created_at: datetime
    updated_at: datetime
