"""Service helpers for building comment API responses."""

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import HTTPStatusMessages
from src.entity.comment import Comment
from src.entity.photo import Photo
from src.entity.user import User
from src.helpers.create_exception import create_exception
from src.repository import photo as repository_photo
from src.schemas.comment import (
    CommentResponseSchema,
    CommentUserSchema,
)


def build_comment_response(
    comment: Comment, user: User
) -> CommentResponseSchema:
    """Build a serialized comment response with public author data."""

    return CommentResponseSchema(
        id=comment.id,
        content=comment.content,
        photo_id=comment.photo_id,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        user=CommentUserSchema(
            id=user.id,
            username=user.username,
        ),
    )


async def get_photo_or_404(photo_id: int, db: AsyncSession) -> Photo:
    """Return a photo by id or raise a 404 error if it does not exist."""

    photo = await repository_photo.get_photo_by_id(
        photo_id=photo_id, db=db
    )
    if photo is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    return photo
