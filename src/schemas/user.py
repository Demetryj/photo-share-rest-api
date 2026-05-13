"""Pydantic schemas for user input and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.entity.user import Role

SPECIAL_CHARS = "!@#$%^&*"


class BaseUserSchema(BaseModel):
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
            raise ValueError("Password must contain at least one lowercase letter.")
        if not any(ch.isupper() for ch in value):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(ch.isdigit() for ch in value):
            raise ValueError("Password must contain at least one digit.")
        if not any(ch in SPECIAL_CHARS for ch in value):
            raise ValueError(
                "Password must contain at least one special character: "
                f"{SPECIAL_CHARS}."
            )
        return value


class UserSchema(BaseUserSchema):
    """User registration request schema."""

    username: str = Field(min_length=3, max_length=60)


class UserResponse(BaseModel):
    """User response schema returned by profile and auth endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    avatar: str | None
    role: Role
    created_at: datetime
    updated_at: datetime
