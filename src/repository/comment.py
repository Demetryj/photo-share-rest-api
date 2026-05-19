"""Repository helpers for working with photo comments."""

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.entity.comment import Comment
from src.schemas.comment import CommentRequestSchema


async def get_total_number_of_comments_on_photo(
    photo_id: int, db: AsyncSession
) -> int:
    """Return the total number of comments linked to the given photo."""

    stmt = select(func.count(Comment.id)).filter_by(photo_id=photo_id)
    total = await db.scalar(stmt)
    return total


async def get_total_number_of_comments(
    user_id: int, db: AsyncSession
) -> int:
    """Return the total number of comments linked to all photos."""

    stmt = select(func.count(Comment.id)).filter_by(user_id=user_id)
    total = await db.scalar(stmt)
    return total


async def create_comment_to_photo(
    photo_id: int,
    user_id: int,
    body: CommentRequestSchema,
    db: AsyncSession,
) -> Comment:
    """Create a new comment for the given photo and user."""

    comment = Comment(
        **body.model_dump(exclude_unset=True),
        photo_id=photo_id,
        user_id=user_id,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


async def get_all_comments_by_photo_id(
    photo_id: int, limit: int, offset: int, db: AsyncSession
) -> list[Comment]:
    """Return a paginated slice of comments for the given photo."""

    stmt = (
        select(Comment)
        .options(selectinload(Comment.user))
        .filter_by(photo_id=photo_id)
        .order_by(Comment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_comment_by_id(
    comment_id: int, user_id: int, photo_id: int, db: AsyncSession
) -> Comment | None:
    """Return one user's comment for the given photo or ``None``."""

    stmt = select(Comment).where(
        and_(
            Comment.id == comment_id,
            Comment.user_id == user_id,
            Comment.photo_id == photo_id,
        )
    )

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_photo_comment(
    comment_id: int,
    user_id: int,
    photo_id: int,
    new_content: str,
    db: AsyncSession,
) -> Comment | None:
    """Update one user's comment for the given photo and return it."""

    current_comment: Comment | None = await get_comment_by_id(
        comment_id=comment_id,
        user_id=user_id,
        photo_id=photo_id,
        db=db,
    )

    if current_comment:
        current_comment.content = new_content
        await db.commit()
        await db.refresh(current_comment)

    return current_comment


async def delete_photo_comment(
    comment_id: int,
    photo_id: int,
    db: AsyncSession,
) -> Comment | None:
    """Delete one comment by its id within the given photo and return it."""

    stmt = select(Comment).filter_by(
        id=comment_id,
        photo_id=photo_id,
    )
    result = await db.execute(stmt)
    current_comment = result.scalar_one_or_none()

    if current_comment:
        await db.delete(current_comment)
        await db.commit()

    return current_comment
