from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import HTTPStatusMessages
from src.database.db import get_db
from src.entity.photo import Tag
from src.entity.user import User
from src.repository import photo as repository_photo
from src.schemas.photo import PhotoResponseSchema
from src.services import photo as photo_service
from src.services.auth import auth_service

router = APIRouter(prefix="/photos", tags=["photos"])

# Use Annotated aliases for multipart form fields so Pydantic can apply
# validation constraints like max_length to the endpoint parameters.
PhotoDescription = Annotated[
    str | None,
    Form(description="Photo description"),
    Field(max_length=300),
]
PhotoTag = Annotated[str, StringConstraints(max_length=50)]
PhotoTags = Annotated[
    list[PhotoTag] | None,
    Form(description="Up to 5 tags (inclusive)"),
    Field(max_length=5),
]


# Upload photo
@router.post(
    "/",
    response_model=PhotoResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description="Upload a photo, resolve its tags, and store its metadata.",
)
async def upload_photo(
    file: UploadFile = File(
        ...,
        description=f"Image file. Max size: {int(photo_service.MAX_IMAGE_SIZE / (1024 * 1024))} MB. Allowed formats: {photo_service.ALLOWED_FORMATS}",
    ),
    description: PhotoDescription = None,
    tags: PhotoTags = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    """Upload a photo, resolve its tags, and store its metadata.

    The endpoint validates the uploaded image, normalizes the optional tag
    names, reuses existing tag entities or creates missing ones, uploads the
    binary file to Cloudinary, saves the resulting photo record in the
    database, and returns a response payload with tag names.
    """
    try:
        # Normalize user-provided tag names early, so invalid tag input fails
        # before we upload anything to Cloudinary or write to the database.
        normalized_tags = photo_service.normalize_image_tags(tags)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    # Validate the uploaded binary and reset the file pointer before upload.
    await photo_service.validate_image_file(file=file)

    # Reuse existing tags when possible; create missing ones in the same
    # transaction so the final photo save can commit everything together.
    tag_list: list[Tag] = [
        await repository_photo.get_or_create_tag(tag=tag, db=db)
        for tag in normalized_tags
    ]
    # Extract plain tag names before the photo commit in `create_photo()`,
    # because ORM tag objects may be expired after commit and trigger async
    # lazy loading on access.
    tags_for_resp = [tag.name for tag in tag_list]

    # Build a unique Cloudinary public_id per photo for stable storage and
    # future operations like delete or transformation generation.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    public_id = (
        f"photo_share/{current_user.id}/{timestamp}_{uuid4().hex}"
    )
    photo_url = await photo_service.cloudinary_upload(
        file=file, public_id=public_id
    )

    # Persist the photo metadata only after the external upload succeeds.
    new_photo = await repository_photo.create_photo(
        user_id=current_user.id,
        public_id=public_id,
        photo_url=photo_url,
        description=description,
        tags=tag_list,
        db=db,
    )

    # Convert ORM tags into plain tag names expected by the API schema.
    return PhotoResponseSchema(
        id=new_photo.id,
        owner_id=new_photo.owner_id,
        description=new_photo.description,
        image_url=new_photo.image_url,
        tags=tags_for_resp,
        created_at=new_photo.created_at,
    )


# Delete photo
@router.delete(
    "/",
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.successfully_deleted.value,
    description="Delete photo by id",
)
async def remove_photo(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    """Delete one photo after ownership check and Cloudinary cleanup."""

    photo = await repository_photo.get_photo_by_id(
        photo_id=photo_id, db=db
    )
    if photo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTPStatusMessages.not_found.value,
        )

    # Allow deletion only for the owner of the target photo or an admin.
    photo_service.check_photo_owner_or_admin_access(
        photo=photo, current_user=current_user
    )

    await photo_service.cloudinary_delete(public_id=photo.public_id)
    await repository_photo.delete_photo(photo=photo, db=db)
