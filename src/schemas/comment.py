"""Pydantic schemas for photo comment requests and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentRequestSchema(BaseModel):
    """Validate payload for creating or updating a comment."""

    content: str = Field(max_length=300)


class CommentUserSchema(BaseModel):
    """Serialized public author data returned with a comment."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class CommentResponseSchema(BaseModel):
    """Serialized comment payload returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    photo_id: int
    created_at: datetime
    updated_at: datetime
    user: CommentUserSchema


class PaginatedCommentResponseSchema(BaseModel):
    """Response schema for a paginated list of photo comments."""

    page: int
    per_page: int
    total: int
    total_pages: int
    items: list[CommentResponseSchema]
