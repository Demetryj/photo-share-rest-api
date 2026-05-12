from pydantic import BaseModel, EmailStr


class SignInResponse(BaseModel):
    """Response returned after successful sign-in with refresh token in cookie."""

    access_token: str
    token_type: str = "bearer"


class RequestEmail(BaseModel):
    """Request payload containing a user email address."""

    email: EmailStr
