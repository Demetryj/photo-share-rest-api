"""Pydantic schemas for photo rating requests and responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PhotoRatingRequestSchema(BaseModel):
    """Request payload for creating a user rating for a photo."""

    rating: int = Field(ge=1, le=5)


class PhotoRatingResponseSchema(BaseModel):
    """Response payload for a persisted photo rating."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int
    user_id: int
    rating: int = Field(ge=1, le=5)
    created_at: datetime


class PaginatedPhotoRatingResponseSchema(BaseModel):
    """Paginated response payload for a list of photo ratings."""

    page: int
    per_page: int
    total: int
    total_pages: int
    items: list[PhotoRatingResponseSchema]
