"""FastAPI routes for photo management and transformation workflows."""

import math
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import Field, StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import (
    AUTHENTICATED_USERS_ACCESS,
    OWNER_OR_ADMIN_ACCESS,
    HTTPStatusMessages,
    ValidationMessages,
)
from src.config.settings import settings
from src.database.db import get_db
from src.entity.models import SortBy
from src.entity.photo import SortField
from src.entity.user import Role, User
from src.helpers.create_exception import create_exception
from src.repository import comment as repository_comment
from src.repository import photo as repository_photo
from src.repository import user as repository_user
from src.schemas.photo import (
    AddTagsSchema,
    PaginatedPhotoResponseSchema,
    PhotoResponseSchema,
    PhotoTransformationRequestSchema,
    PhotoTransformationResponseSchema,
    UpdatePhotoDescriptionSchema,
)
from src.services import photo as photo_service
from src.services import role as role_service
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
TargetUserId = Annotated[
    int | None,
    Form(
        description=(
            "Optional target user ID. Available only for admin users; "
            "when omitted, the photo is uploaded for the current user."
        ),
    ),
]


# Upload photo
@router.post(
    "/",
    response_model=PhotoResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Upload a photo along with a description (optional) and tags (optional).\n\n"
        f"{OWNER_OR_ADMIN_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def upload_photo(
    file: UploadFile = File(
        ...,
        description=f"Image file. Max size: {photo_service.MAX_IMAGE_SIZE} MB. Allowed formats: {photo_service.ALLOWED_FORMATS}",
    ),
    description: PhotoDescription = None,
    tags: PhotoTags = None,
    user_id: TargetUserId = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PhotoResponseSchema:
    """Upload a photo, resolve its tags, and store its metadata.

    The endpoint optionally lets an administrator upload a photo for another
    existing user. It first validates that permission and target user
    existence when ``user_id`` is provided, then validates the uploaded
    image, normalizes the optional tag names, reuses existing tag entities or
    creates missing ones, uploads the binary file to Cloudinary, saves the
    resulting photo record in the database, and returns a response payload
    with tag names.
    """
    owner_id = await photo_service.resolve_photo_owner_id(
        current_user=current_user,
        db=db,
        target_user_id=user_id,
    )

    # Validate the uploaded binary and reset the file pointer before upload.
    await photo_service.validate_image_file(file=file)

    tag_list, tags_for_resp = await photo_service.prepare_photo_tags(
        tags=tags, db=db
    )

    # Build a unique Cloudinary public_id per photo for stable storage and
    # future operations like delete or transformation generation.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    public_id = f"{settings.CLOUDINARY_PUBLIC_ID_PREFIX}/{owner_id}/{timestamp}_{uuid4().hex}"
    photo_url = await photo_service.cloudinary_upload(
        file=file, public_id=public_id
    )

    # Persist the photo metadata only after the external upload succeeds.
    new_photo = await repository_photo.create_photo(
        user_id=owner_id,
        public_id=public_id,
        photo_url=photo_url,
        description=description,
        tags=tag_list,
        db=db,
    )

    return photo_service.build_photo_response(
        photo=new_photo, tags=tags_for_resp
    )


# Get photo by photo ID:
@router.get(
    "/{photo_id}",
    response_model=PhotoResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return one photo by ID.\n\n" f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def get_photo_by_photo_id(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(auth_service.get_current_user),
) -> PhotoResponseSchema:
    """Return one photo by its identifier for the owner or an admin.

    The endpoint fetches the requested photo by its identifier, checks that
    it exists, and returns the serialized photo data.
    """

    photo = await repository_photo.get_photo_by_id(
        photo_id=photo_id, db=db
    )
    if photo is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    comments_count = await repository_comment.get_total_number_of_comments_on_photo(
        photo_id=photo.id, db=db
    )

    # Calculate the average rating with a dedicated aggregate query instead
    # of loading all rating rows into the ORM object.
    average_rating = await repository_photo.get_photo_average_rating(
        photo_id=photo.id,
        db=db,
    )

    return photo_service.build_photo_response(
        photo=photo,
        comments_count=comments_count,
        average_rating=average_rating,
    )


# Get all user photos by user ID
@router.get(
    "/user/{user_id}",
    response_model=PaginatedPhotoResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return a paginated list of photos for the specified user.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def get_all_photo_by_user_id(
    user_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(auth_service.get_current_user),
) -> PaginatedPhotoResponseSchema:
    """Return a paginated list of the specified user's photos.

    The endpoint checks that the target user exists, applies
    page/per_page pagination, fetches the matching photos, calculates
    pagination metadata, and returns the current page of serialized photos.
    """

    offset = (page - 1) * per_page

    user = await repository_user.get_user_by_id(
        user_id=user_id, db=db
    )

    if user is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    photo_list = await repository_photo.get_photos_by_user_id(
        user_id=user_id, limit=per_page, offset=offset, db=db
    )

    resp_photos = []
    for photo in photo_list:
        comments_count = await repository_comment.get_total_number_of_comments_on_photo(
            photo_id=photo.id, db=db
        )

        # Build each list item with an aggregated SQL average to avoid lazy
        # relationship access and per-item Python-side rating calculation.
        average_rating = (
            await repository_photo.get_photo_average_rating(
                photo_id=photo.id,
                db=db,
            )
        )
        item = photo_service.build_photo_response(
            photo=photo,
            comments_count=comments_count,
            average_rating=average_rating,
        )
        resp_photos.append(item)

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


@router.get(
    "/",
    response_model=PaginatedPhotoResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Search photos by description keyword or tag and return a paginated list of results.\n\n"
        "Use `query` for text search. If the value starts with `#`, it is treated as a tag search.\n\n"
        "Moderators and administrators can additionally filter results by uploader username via `author_username`.\n\n"
        "You can additionally filter results by open rating and date ranges.\n\n"
        "Supported combinations: `min_rating`, `max_rating`, `date_from`, `date_to`, or any combination of them.\n\n"
        "Sorting is controlled by `sort_field` (`rating` or `date`) together with `sort_by` (`asc` or `desc`).\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def get_filtered_photos_by_keyword_or_tag(
    author_username: str | None = Query(default=None),
    query: str | None = Query(default=None),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    max_rating: float | None = Query(default=None, ge=0, le=5),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_field: SortField | None = Query(default=None),
    sort_by: SortBy | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PaginatedPhotoResponseSchema:
    """Return a paginated filtered photo list for authenticated users.

    The endpoint supports searching by photo description text or by tag when
    the query starts with ``#``. Staff users can additionally filter photos
    by uploader username. After search is applied, results can be filtered by
    open rating and date ranges. Sorting is configured explicitly by the
    requested field and direction.
    """
    if (
        min_rating is not None
        and max_rating is not None
        and min_rating > max_rating
    ):
        create_exception(
            message=ValidationMessages.min_rating_must_be_less_than_or_equal_to_max_rating.value
        )

    if (
        date_from is not None
        and date_to is not None
        and date_from > date_to
    ):
        create_exception(
            message=ValidationMessages.date_from_must_be_less_than_or_equal_to_date_to.value
        )

    # Filtering by uploader username is reserved for staff roles.
    if author_username is not None and current_user.role not in {
        Role.admin,
        Role.moderator,
    }:
        create_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            message=HTTPStatusMessages.access_denied.value,
        )

    offset = (page - 1) * per_page

    photo_list = (
        await repository_photo.get_filtered_photos_by_keyword_or_tag(
            db=db,
            author_username=author_username,
            query=query,
            min_rating=min_rating,
            max_rating=max_rating,
            date_from=date_from,
            date_to=date_to,
            sort_field=sort_field,
            sort_by=sort_by,
            offset=offset,
            limit=per_page,
        )
    )

    resp_photos = []
    for photo, avg_rating in photo_list:
        comments_count = await repository_comment.get_total_number_of_comments_on_photo(
            photo_id=photo.id, db=db
        )

        # Reuse the aggregated rating returned by the repository instead of
        # running one more average-rating query per photo.
        item = photo_service.build_photo_response(
            photo=photo,
            comments_count=comments_count,
            average_rating=avg_rating,
        )
        resp_photos.append(item)

    # Total pagination metadata must be based on the full filtered result set,
    # not just on the current page after limit/offset are applied.
    total_photos = await repository_photo.count_filtered_photos_by_keyword_or_tag(
        db=db,
        author_username=author_username,
        query=query,
        min_rating=min_rating,
        max_rating=max_rating,
        date_from=date_from,
        date_to=date_to,
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
    description=(
        "Delete a photo by ID.\n\n" f"{OWNER_OR_ADMIN_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
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
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Update the description of a photo.\n\n"
        f"{OWNER_OR_ADMIN_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
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

    comments_count = await repository_comment.get_total_number_of_comments_on_photo(
        photo_id=photo_id, db=db
    )

    # Recalculate the average rating before returning the updated photo.
    average_rating = await repository_photo.get_photo_average_rating(
        photo_id=photo.id,
        db=db,
    )

    return photo_service.build_photo_response(
        photo=updated_photo,
        comments_count=comments_count,
        average_rating=average_rating,
    )


# Replace the tag set of an existing photo.
@router.patch(
    "/{photo_id}/tags",
    response_model=PhotoResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Replace the tags of a photo with up to 5 tags.\n\n"
        f"{OWNER_OR_ADMIN_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def add_photo_tags(
    photo_id: int,
    body: AddTagsSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PhotoResponseSchema:
    """Replace the tags of a photo for the owner or an admin.

    The endpoint fetches the target photo by its identifier, checks that it
    exists, verifies that the current user is either the photo owner or an
    administrator, normalizes and resolves up to 5 provided tags, replaces
    any previously linked tags, and returns the updated serialized photo
    data.
    """

    photo = await photo_service.get_photo_for_owner_or_admin(
        photo_id=photo_id, current_user=current_user, db=db
    )

    tag_list, tags_for_resp = await photo_service.prepare_photo_tags(
        tags=body.tags, db=db
    )

    updated_photo = await repository_photo.add_photo_tags(
        photo=photo, tags=tag_list, db=db
    )

    comments_count = await repository_comment.get_total_number_of_comments_on_photo(
        photo_id=photo_id, db=db
    )

    # Recalculate the average rating before returning the updated photo.
    average_rating = await repository_photo.get_photo_average_rating(
        photo_id=photo.id,
        db=db,
    )

    return photo_service.build_photo_response(
        photo=updated_photo,
        tags=tags_for_resp,
        comments_count=comments_count,
        average_rating=average_rating,
    )


# Generate a non-persistent preview for a requested photo transformation.
@router.post(
    "/{photo_id}/transform-preview",
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Generate a temporary preview of a transformed photo without saving it.\n\n"
        f"{OWNER_OR_ADMIN_ACCESS}\n\n"
        "Parameter rules by transformation type:\n"
        "- `resize` requires `width` and `height`\n"
        "- `crop` requires `width`, `height`, `x`, and `y`\n"
        "- `rotate` requires `angle`, where `angle` is the rotation in "
        "degrees; it optionally accepts `expand`, which enlarges the canvas "
        "to avoid clipping, and `background`, which sets the fill color of "
        "empty corners\n"
        "- `blur` requires `blur_radius`; it optionally accepts `blur_mode` "
        "(`gaussian` or `box`), where `blur_radius` controls blur intensity\n"
        "- `grayscale` does not require additional parameters"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def preview_photo_transformation(
    photo_id: int,
    body: PhotoTransformationRequestSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> StreamingResponse:
    """Generate a temporary preview for a transformed photo.

    The endpoint fetches the target photo by its identifier, checks that it
    exists, verifies that the current user is either the photo owner or an
    administrator, validates the transformation parameters, applies the
    transformation locally with Pillow, and returns the preview image without
    saving anything to the database or Cloudinary.
    """

    photo = await photo_service.get_photo_for_owner_or_admin(
        photo_id=photo_id,
        current_user=current_user,
        db=db,
    )

    params = photo_service.build_transformation_params(body)

    return await photo_service.build_preview_response(
        photo=photo,
        transformation_type=body.transformation_type,
        params=params,
    )


# Create and persist a transformed photo link together with its QR code.
@router.post(
    "/{photo_id}/transformations",
    response_model=PhotoTransformationResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    status_code=status.HTTP_201_CREATED,
    description=(
        "Create and save a transformed photo link with a QR code.\n\n"
        f"{OWNER_OR_ADMIN_ACCESS}\n\n"
        "Parameter rules by transformation type:\n"
        "- `resize` requires `width` and `height`\n"
        "- `crop` requires `width`, `height`, `x`, and `y`\n"
        "- `rotate` requires `angle`, where `angle` is the rotation in "
        "degrees; it optionally accepts `expand`, which enlarges the canvas "
        "to avoid clipping, and `background`, which sets the fill color of "
        "empty corners\n"
        "- `blur` requires `blur_radius`; it optionally accepts `blur_mode` "
        "(`gaussian` or `box`), where `blur_radius` controls blur intensity\n"
        "- `grayscale` does not require additional parameters"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def create_photo_transformation(
    photo_id: int,
    body: PhotoTransformationRequestSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PhotoTransformationResponseSchema:
    """Create and save a transformed photo link with its QR code.

    The endpoint fetches the target photo by its identifier, checks that it
    exists, verifies that the current user is either the photo owner or an
    administrator, validates the transformation parameters, builds the final
    Cloudinary URL, generates a QR code image, stores the transformation
    record in the database, and returns the saved transformation data.
    """

    photo = await photo_service.get_photo_for_owner_or_admin(
        photo_id=photo_id,
        current_user=current_user,
        db=db,
    )

    params = photo_service.build_transformation_params(body)

    transformed_url = photo_service.build_transformed_photo_url(
        photo=photo,
        transformation_type=body.transformation_type,
        params=params,
    )

    qr_code_url = await photo_service.generate_qr_code_url(
        transformed_url=transformed_url,
        photo_id=photo.id,
        user_id=photo.owner_id,
    )

    transformation = (
        await repository_photo.create_photo_transformation(
            photo_id=photo.id,
            user_id=photo.owner_id,
            transformation_type=body.transformation_type,
            transformation_params=params,
            transformed_url=transformed_url,
            qr_code_url=qr_code_url,
            db=db,
        )
    )

    return transformation


# List all saved transformation records for one photo.
@router.get(
    "/{photo_id}/transformations",
    response_model=list[PhotoTransformationResponseSchema],
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return all saved transformations for a photo.\n\n"
        f"{OWNER_OR_ADMIN_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def get_all_photo_transformations(
    photo_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PhotoTransformationResponseSchema]:
    """Return all saved transformation links for a photo.

    The endpoint fetches the target photo by its identifier, checks that it
    exists, verifies that the current user is either the photo owner or an
    administrator, and returns the saved transformation records for that
    photo.
    """

    photo = await photo_service.get_photo_for_owner_or_admin(
        photo_id=photo_id,
        current_user=current_user,
        db=db,
    )

    transformations = (
        await repository_photo.get_photo_transformations_by_photo_id(
            photo_id=photo.id,
            db=db,
        )
    )

    return transformations


# Return one saved transformation record by its identifier.
@router.get(
    "/transformations/{transformation_id}",
    response_model=PhotoTransformationResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return one saved transformation by ID.\n\n"
        f"{OWNER_OR_ADMIN_ACCESS}"
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def get_photo_transformation_by_id(
    transformation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PhotoTransformationResponseSchema:
    """Return one saved transformation link by its identifier.

    The endpoint fetches the requested transformation record by its
    identifier, checks that it exists, verifies that the current user is
    either the owner of the related photo or an administrator, and returns
    the saved transformation data.
    """

    transformation = (
        await repository_photo.get_photo_transformation_by_id(
            transformation_id=transformation_id,
            db=db,
        )
    )

    if transformation is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    await photo_service.get_photo_for_owner_or_admin(
        photo_id=transformation.photo_id,
        current_user=current_user,
        db=db,
    )

    return transformation
