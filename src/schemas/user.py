"""Pydantic schemas for auth, public profile, and self-profile flows."""

import re
from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
)

from src.config.messages import UserValidationMessages
from src.entity.user import Role

PASSWORD_SPECIAL_CHARS = "!@#$%^&*"
USERNAME_PATTERN = re.compile(r"^[a-z](?:[a-z0-9_]*[a-z0-9])?$")


class BaseAuthUserRequestSchema(BaseModel):
    """Base schema with common user identity fields for auth-related requests."""

    email: EmailStr = Field(max_length=150)
    password: str = Field(
        min_length=8,
        max_length=16,
        description=(
            "Password must contain at least one lowercase letter, one uppercase "
            f"letter, one digit, and one special character from {PASSWORD_SPECIAL_CHARS}."
        ),
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(ch.islower() for ch in value):
            raise ValueError(
                UserValidationMessages.password_requires_lowercase.value
            )
        if not any(ch.isupper() for ch in value):
            raise ValueError(
                UserValidationMessages.password_requires_uppercase.value
            )
        if not any(ch.isdigit() for ch in value):
            raise ValueError(
                UserValidationMessages.password_requires_digit.value
            )
        if not any(ch in PASSWORD_SPECIAL_CHARS for ch in value):
            raise ValueError(
                f"{UserValidationMessages.password_requires_special_character.value} {PASSWORD_SPECIAL_CHARS}."
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
                UserValidationMessages.username_has_invalid_format.value
            )
        return value


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


class PublicProfileResponseSchema(BaseModel):
    """Public user profile response schema."""

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
    display_name: str | None = None
    avatar: HttpUrl | None


class MyUserInfoResponseSchema(BaseModel):
    """Response schema for detailed information about the current user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str | None = None
    email: EmailStr
    avatar: HttpUrl | None
    role: Role
    confirmed: bool
    photos_count: int = 0
    comments_count: int = 0
    created_at: datetime
    updated_at: datetime


class PaginatedUsersResponseSchema(BaseModel):
    """Response schema for a paginated list of public user profiles."""

    page: int
    per_page: int
    total: int
    total_pages: int
    items: list[PublicProfileResponseSchema]


class AssignableRole(str, Enum):
    """User roles that administrators are currently allowed to assign."""

    user = Role.user.value
    moderator = Role.moderator.value


class UserRoleRequestSchema(BaseModel):
    """Request schema for changing a user's role."""

    role: AssignableRole


class UserRoleResponseSchema(BaseModel):
    """Response schema for a user whose role was updated by an administrator."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: AssignableRole
    updated_at: datetime
