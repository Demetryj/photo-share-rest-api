import math

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import rate_limiters
from src.config.messages import (
    AUTHENTICATED_USERS_ACCESS,
    STAFF_ACCESS,
    HTTPStatusMessages,
)
from src.database.db import get_db
from src.entity.user import User
from src.helpers.create_exception import create_exception
from src.repository import photo as repository_photo
from src.repository import photo_rating as repository_photo_rating
from src.schemas.photo_rating import (
    PaginatedPhotoRatingResponseSchema,
    PhotoRatingRequestSchema,
    PhotoRatingResponseSchema,
)
from src.services import role as role_service
from src.services.auth import auth_service

router = APIRouter(
    prefix="/photos",
    tags=["photo-rating"],
    dependencies=[
        Depends(
            RateLimiter(
                limiter=rate_limiters.photo_rating_base_limiter
            )
        )
    ],
)


# Create one user rating for a photo if the user has not rated it before.
@router.post(
    "/{photo_id}/rating",
    response_model=PhotoRatingResponseSchema,
    response_description=HTTPStatusMessages.successfully_created.value,
    description=(
        "Create one rating for the specified photo.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}\n\n"
        "A user can rate the same photo only once and cannot rate their own photo."
    ),
    dependencies=[Depends(role_service.authenticated_users)],
)
async def create_photo_rating(
    photo_id: int,
    body: PhotoRatingRequestSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> PhotoRatingResponseSchema:
    """Create one user rating for a photo.

    The endpoint loads the target photo, returns 404 when that photo does
    not exist, rejects attempts to rate one's own photo, rejects duplicate
    ratings from the same user for the same photo, creates the rating
    record, and returns the stored rating payload.
    """

    photo = await repository_photo.get_photo_by_id(
        photo_id=photo_id, db=db
    )
    if photo is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    if photo.owner_id == current_user.id:
        create_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            message=HTTPStatusMessages.operation_forbidden.value,
        )

    # The same user can submit only one rating for the same photo.
    exists_rating = await repository_photo_rating.get_photo_rating_by_photo_id_and_user_id(
        photo_id=photo.id, user_id=current_user.id, db=db
    )
    if exists_rating:
        create_exception(
            status_code=status.HTTP_409_CONFLICT,
            message=HTTPStatusMessages.rating_already_exists.value,
        )

    rating_data = await repository_photo_rating.create_photo_rating(
        user_id=current_user.id,
        photo_id=photo.id,
        rating=body.rating,
        db=db,
    )

    return PhotoRatingResponseSchema.model_validate(rating_data)


# Return a paginated list of all ratings for one photo for staff members.
@router.get(
    "/{photo_id}/ratings",
    response_model=PaginatedPhotoRatingResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return a paginated list of ratings for the specified photo.\n\n"
        f"{STAFF_ACCESS}"
    ),
    dependencies=[Depends(role_service.staff_only)],
)
async def get_all_photo_ratings(
    photo_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(auth_service.get_current_user),
) -> PaginatedPhotoRatingResponseSchema:
    """Return a paginated list of ratings for the specified photo.

    The endpoint is available only to staff users. It loads the target photo,
    returns 404 when that photo does not exist, applies page/per-page
    pagination to the stored rating records, calculates pagination metadata,
    and returns the current page of ratings for that photo.
    """

    photo = await repository_photo.get_photo_by_id(
        photo_id=photo_id, db=db
    )
    if photo is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    offset = (page - 1) * per_page
    result = await repository_photo_rating.get_all_photo_ratings(
        photo_id=photo.id, limit=per_page, offset=offset, db=db
    )

    total = await repository_photo_rating.get_total_number_of_ratings_on_photo(
        photo_id=photo.id,
        db=db,
    )
    total_pages = math.ceil(total / per_page) if total else 0

    response = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "items": result,
    }

    return response


# Return one rating record by its identifier for staff members.
@router.get(
    "/ratings/{rating_id}",
    response_model=PhotoRatingResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return one rating by its identifier.\n\n" f"{STAFF_ACCESS}"
    ),
    dependencies=[Depends(role_service.staff_only)],
)
async def get_rating_by_id(
    rating_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(auth_service.get_current_user),
) -> PhotoRatingResponseSchema:
    """Return one stored rating by its identifier.

    The endpoint is available only to staff users. It looks up the target
    rating by its identifier, returns 404 when that rating does not exist,
    and otherwise returns the stored rating payload.
    """

    rating = await repository_photo_rating.get_rating_by_id(
        rating_id=rating_id,
        db=db,
    )
    if rating is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    return rating


# Delete one rating record by its identifier for staff members.
@router.delete(
    "/ratings/{rating_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.successfully_deleted.value,
    description=(
        "Delete one rating by its identifier.\n\n" f"{STAFF_ACCESS}"
    ),
    dependencies=[Depends(role_service.staff_only)],
)
async def delete_rating(
    rating_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(auth_service.get_current_user),
) -> None:
    """Delete one stored rating by its identifier.

    The endpoint is available only to staff users. It attempts to delete the
    target rating by its identifier, returns 404 when that rating does not
    exist, and otherwise responds with ``204 No Content``.
    """

    deleted_rating = await repository_photo_rating.delete_rating(
        rating_id=rating_id,
        db=db,
    )

    if not deleted_rating:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
