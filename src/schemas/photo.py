from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PhotoResponseSchema(BaseModel):
    """Response schema for returning a stored photo with its basic metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    description: str | None
    image_url: str
    tags: list[str]
    created_at: datetime
