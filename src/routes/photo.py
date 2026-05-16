import math
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import HTTPStatusMessages
from src.database.db import get_db
from src.entity.photo import Tag
from src.entity.user import Role, User
from src.repository import photo as repository_photo
from src.repository import user as repository_user
from src.schemas.photo import (
    PaginatedPhotoResponseSchema,
    PhotoResponseSchema,
    TagResponseShema,
    UpdatePhotoDescriptionSchema,
)
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
    description="Upload a photo along with a description (optional) and tags (optional)",
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
) -> PhotoResponseSchema:
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

    # Build response tag schemas before `create_photo()` commits the session,
    # because ORM tag objects may be expired after commit and trigger async
    # lazy loading when Pydantic tries to read their attributes.
    tags_for_resp = [
        TagResponseShema.model_validate(tag) for tag in tag_list
    ]

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

    return photo_service.build_photo_response(
        new_photo, tags_for_resp
    )


# Get photo by photo ID:
@router.get(
    "/{photo_id}",
    response_model=PhotoResponseSchema,
    description="Return one photo by ID. Accessible by the photo owner or an admin.",
)
async def get_photo_by_photo_id(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PhotoResponseSchema:
    """Return one photo by its identifier for the owner or an admin.

    The endpoint fetches the requested photo by its identifier, checks that
    it exists, verifies that the current user is either the photo owner or
    an administrator, and returns the serialized photo data.
    """

    photo = await photo_service.get_photo_for_owner_or_admin(
        photo_id=photo_id, current_user=current_user, db=db
    )

    return photo_service.build_photo_response(photo)


# Get all user photos by user ID
@router.get(
    "/user/{user_id}",
    response_model=PaginatedPhotoResponseSchema,
    description="Return a paginated list of photos for the specified user. Accessible by the user or an admin.",
)
async def get_all_photo_by_user_id(
    user_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PaginatedPhotoResponseSchema:
    """Return a paginated list of the specified user's photos.

    The endpoint checks that the target user exists, verifies that the
    current user is either that user or an administrator, applies
    page/per_page pagination, fetches the matching photos, calculates
    pagination metadata, and returns the current page of serialized photos.
    """

    offset = (page - 1) * per_page

    user = await repository_user.get_user_by_id(
        user_id=user_id, db=db
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=HTTPStatusMessages.not_found.value,
        )

    if user_id != current_user.id and current_user.role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=HTTPStatusMessages.access_denied.value,
        )

    photo_list = await repository_photo.get_photos_by_user_id(
        user_id=user_id, limit=per_page, offset=offset, db=db
    )

    resp_photos = [
        photo_service.build_photo_response(photo)
        for photo in photo_list
    ]

    total_photos = await repository_photo.get_total_number_of_photos(
        user_id=user_id, db=db
    )
    total_pages = (
        math.ceil(total_photos / per_page) if total_photos else 0
    )

    return {
        "page": page,
        "per_page": per_page,
        "total": total_photos,
        "total_pages": total_pages,
        "items": resp_photos,
    }


# Delete photo
@router.delete(
    "/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.successfully_deleted.value,
    description="Delete a photo by ID. Accessible by the photo owner or an admin.",
)
async def remove_photo(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> None:
    """Delete one photo for the owner or an admin after Cloudinary cleanup.

    The endpoint fetches the target photo by its identifier, checks that it
    exists, verifies that the current user is either the photo owner or an
    administrator, removes the image from Cloudinary, and then deletes the
    photo record from the database.
    """

    photo = await photo_service.get_photo_for_owner_or_admin(
        photo_id=photo_id, current_user=current_user, db=db
    )

    await photo_service.cloudinary_delete(public_id=photo.public_id)
    await repository_photo.delete_photo(photo=photo, db=db)


# Update photo description
@router.put(
    "/{photo_id}/description",
    response_model=PhotoResponseSchema,
    description="Update the description of a photo. Accessible by the photo owner or an admin.",
)
async def update_photo_description(
    photo_id: int,
    body: UpdatePhotoDescriptionSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PhotoResponseSchema:
    """Update the description of a photo for the owner or an admin.

    The endpoint fetches the target photo by its identifier, checks that it
    exists, verifies that the current user is either the photo owner or an
    administrator, updates the photo description, and returns the updated
    serialized photo data.
    """

    photo = await photo_service.get_photo_for_owner_or_admin(
        photo_id=photo_id, current_user=current_user, db=db
    )

    updated_photo = await repository_photo.update_photo_description(
        photo=photo, description=body.description, db=db
    )

    return photo_service.build_photo_response(photo=updated_photo)
