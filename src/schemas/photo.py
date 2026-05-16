from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.entity.photo import BlurMode, TransformationType


class BaseTagSchema(BaseModel):
    """Base schema for tag data."""

    name: str = Field(max_length=50)


class AddTagsSchema(BaseModel):
    """Request schema for adding multiple tags to a photo."""

    tags: list[Annotated[str, StringConstraints(max_length=50)]]


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


class PhotoTransformationRequestSchema(BaseModel):
    """Request schema for previewing or saving a photo transformation.

    The schema supports a limited set of transformation types used by the
    application. Some parameters are only applicable to specific
    transformation types: ``angle`` is the rotation angle in degrees,
    ``expand`` controls whether the canvas is enlarged to avoid clipping
    after rotation, ``background`` sets the fill color for empty rotated
    corners, ``blur_mode`` selects the blur algorithm, and ``blur_radius``
    controls blur intensity.
    """

    transformation_type: TransformationType

    # Resize / crop params
    width: int | None = Field(default=None, ge=1, le=4000)
    height: int | None = Field(default=None, ge=1, le=4000)

    # Crop-only params
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)

    # Rotate params
    angle: int | None = Field(default=None, ge=0, le=360)
    expand: bool = False
    background: str | None = Field(default=None, max_length=20)

    # Blur params
    blur_mode: BlurMode = BlurMode.gaussian
    blur_radius: int | None = Field(default=None, ge=1, le=50)


class PhotoTransformationResponseSchema(BaseModel):
    """Response schema for a saved transformed photo link."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    photo_id: int
    user_id: int
    transformation_type: TransformationType
    transformation_params: dict
    transformed_url: str
    qr_code_url: str | None
    created_at: datetime
