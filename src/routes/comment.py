"""FastAPI routes for creating and managing photo comments."""

import math

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import (
    AUTHENTICATED_USERS_ACCESS,
    STAFF_ACCESS,
    HTTPStatusMessages,
)
from src.database.db import get_db
from src.entity.user import User
from src.helpers.create_exception import create_exception
from src.repository import comment as repository_comment
from src.schemas.comment import (
    CommentRequestSchema,
    CommentResponseSchema,
    PaginatedCommentResponseSchema,
)
from src.services.auth import auth_service
from src.services.comment import (
    build_comment_response,
    get_photo_or_404,
)
from src.services.role import authenticated_users, staff_only

router = APIRouter(prefix="/photos", tags=["comments"])


# Create comment to photo
@router.post(
    "/{photo_id}/comments",
    status_code=status.HTTP_201_CREATED,
    response_description=HTTPStatusMessages.successfully_created.value,
    response_model=CommentResponseSchema,
    description=(
        "Create a new comment for the specified photo.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(authenticated_users)],
)
async def create_comment_to_photo(
    photo_id: int,
    body: CommentRequestSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> CommentResponseSchema:
    """Create a comment for an existing photo and return it."""

    photo = await get_photo_or_404(photo_id=photo_id, db=db)

    comment = await repository_comment.create_comment_to_photo(
        photo_id=photo.id, user_id=current_user.id, body=body, db=db
    )

    return build_comment_response(comment=comment, user=current_user)


# Get all comments by photo ID
@router.get(
    "/{photo_id}/comments",
    response_model=PaginatedCommentResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return a paginated list of comments for the specified photo.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(authenticated_users)],
)
async def get_all_comments_by_photo_id(
    photo_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=50),
    _: User = Depends(auth_service.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of comments for the specified photo."""

    photo = await get_photo_or_404(photo_id=photo_id, db=db)

    offset = (page - 1) * per_page
    comment_list = (
        await repository_comment.get_all_comments_by_photo_id(
            photo_id=photo_id, limit=per_page, offset=offset, db=db
        )
    )

    resp_comments = [
        build_comment_response(comment=comment, user=comment.user)
        for comment in comment_list
    ]

    total_comments = await repository_comment.get_total_number_of_comments_on_photo(
        photo_id=photo.id, db=db
    )
    total_pages = (
        math.ceil(total_comments / per_page) if total_comments else 0
    )

    return {
        "page": page,
        "per_page": per_page,
        "total": total_comments,
        "total_pages": total_pages,
        "items": resp_comments,
    }


# Update photo comment
@router.patch(
    "/{photo_id}/comments/{comment_id}",
    response_model=CommentResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Update a comment for the specified photo.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(authenticated_users)],
)
async def update_photo_comment(
    photo_id: int,
    comment_id: int,
    body: CommentRequestSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> CommentResponseSchema:
    """Update one user's comment for the specified photo."""

    photo = await get_photo_or_404(photo_id=photo_id, db=db)

    updated_comment = await repository_comment.update_photo_comment(
        photo_id=photo.id,
        comment_id=comment_id,
        user_id=current_user.id,
        new_content=body.content,
        db=db,
    )

    if updated_comment is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    return build_comment_response(
        comment=updated_comment, user=current_user
    )


# Delete photo comment
@router.delete(
    "/{photo_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Delete a comment from the specified photo.\n\n"
        f"{STAFF_ACCESS}"
    ),
    dependencies=[Depends(staff_only)],
)
async def delete_photo_comment(
    photo_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(auth_service.get_current_user),
) -> None:
    """Delete a comment from the specified photo."""

    photo = await get_photo_or_404(photo_id=photo_id, db=db)

    deleted_comment = await repository_comment.delete_photo_comment(
        comment_id=comment_id, photo_id=photo.id, db=db
    )

    if deleted_comment is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
