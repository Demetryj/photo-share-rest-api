"""Pydantic schemas for user input and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.entity.models import Role


class UserShcema(BaseModel):
    """User registration request schema."""

    username: str = Field(min_length=3, max_length=60)
    email: EmailStr = Field(max_length=120)
    password: str = Field(min_length=6, max_length=16)


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
