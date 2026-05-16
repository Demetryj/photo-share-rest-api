from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BaseTagSchema(BaseModel):
    """Base schema for tag data."""

    name: str = Field(max_length=50)


class AddTagsSchema(BaseModel):
    """Request schema for adding multiple tags to a photo."""

    tags: list[BaseTagSchema]


class TagResponseShema(BaseTagSchema):
    """Response schema for returning one tag attached to a photo."""

    model_config = ConfigDict(from_attributes=True)

    id: int


class PhotoResponseSchema(BaseModel):
    """Response schema for returning a stored photo with its basic metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    description: str | None
    image_url: str
    tags: list[TagResponseShema]
    created_at: datetime


class PaginatedPhotoResponseSchema(BaseModel):
    """Response schema for a paginated list of user photos."""

    page: int
    per_page: int
    total: int
    total_pages: int
    items: list[PhotoResponseSchema]


class UpdatePhotoDescriptionSchema(BaseModel):
    """Request schema for updating a photo description."""

    description: str = Field(max_length=300)
