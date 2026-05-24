"""Pydantic schemas for authentication-related request and response payloads."""

from pydantic import BaseModel, EmailStr


class SignInResponse(BaseModel):
    """Response returned after successful sign-in with refresh token in cookie."""

    access_token: str
    token_type: str = "bearer"


class RequestEmail(BaseModel):
    """Request payload containing a user email address."""

    email: EmailStr


class MessageResponseSchema(BaseModel):
    """Generic response payload containing a single message."""

    message: str


class ResetPasswordRequestSchema(BaseModel):
    """Request payload for confirming a password reset."""

    token: str
    password: str
