"""Repository helpers for reading and writing photo rating records."""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.photo_rating import PhotoRating


async def get_photo_rating_by_photo_id_and_user_id(
    photo_id: int, user_id: int, db: AsyncSession
) -> PhotoRating | None:
    """Return one photo rating for the specified photo and user pair."""

    stmt = select(PhotoRating).filter_by(
        photo_id=photo_id,
        user_id=user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def create_photo_rating(
    photo_id: int, user_id: int, rating: int, db: AsyncSession
) -> PhotoRating:
    """Create and persist a new photo rating record."""

    record = PhotoRating(
        photo_id=photo_id,
        user_id=user_id,
        rating=rating,
    )

    db.add(record)
    await db.commit()
    await db.refresh(record)

    return record


async def get_all_photo_ratings(
    photo_id: int, limit: int, offset: int, db: AsyncSession
) -> list[PhotoRating]:
    """Return all stored ratings for the specified photo."""

    stmt = (
        select(PhotoRating)
        .filter_by(
            photo_id=photo_id,
        )
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_total_number_of_ratings_on_photo(
    photo_id: int, db: AsyncSession
) -> int:
    """Return the total number of ratings linked to the given photo."""

    stmt = select(func.count(PhotoRating.id)).filter_by(
        photo_id=photo_id
    )
    total = await db.scalar(stmt)
    return total


async def get_rating_by_id(
    rating_id: int, db: AsyncSession
) -> PhotoRating | None:
    """Return one photo rating by its identifier."""

    stmt = select(PhotoRating).filter_by(
        id=rating_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_rating(rating_id: int, db: AsyncSession) -> bool:
    """Delete one photo rating by its identifier."""

    stmt = delete(PhotoRating).filter_by(
        id=rating_id,
    )
    result = await db.execute(stmt)
    await db.commit()
    return (result.rowcount or 0) > 0
