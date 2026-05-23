"""Repository helpers for photos, tags, and saved transformations."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.entity.photo import (
    Photo,
    PhotoSortBy,
    PhotoTransformation,
    Tag,
    TransformationType,
    photo_tags,
)
from src.entity.photo_rating import PhotoRating


async def create_photo(
    user_id: int,
    photo_url: str,
    public_id: str,
    description: str | None,
    tags: list[Tag] | None,
    db: AsyncSession,
) -> Photo:
    """Create and persist a new photo record with its resolved tags.

    The function builds a ``Photo`` ORM entity for the uploaded Cloudinary
    asset, links it to the owning user, attaches any tag entities that were
    resolved earlier, commits the transaction, refreshes the saved row, and
    returns the persisted ``Photo`` object.
    """
    new_photo = Photo(
        image_url=photo_url,
        public_id=public_id,
        owner_id=user_id,
        description=description,
        tags=tags,
    )

    db.add(new_photo)
    await db.commit()
    await db.refresh(new_photo)

    return new_photo


async def get_photo_by_id(
    photo_id: int, db: AsyncSession
) -> Photo | None:
    """Return one photo by its primary key or ``None`` if it does not exist."""

    stmt = (
        select(Photo)
        # Eager-load tags together with the photo so response serialization
        # does not trigger async lazy loading later.
        .options(selectinload(Photo.tags)).filter_by(id=photo_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_photos_by_user_id(
    user_id: int, limit: int, offset: int, db: AsyncSession
) -> list[Photo]:
    """Return all photos that belong to the specified user."""

    stmt = (
        select(Photo)
        .options(selectinload(Photo.tags))
        .filter_by(owner_id=user_id)
        .offset(offset)
        .limit(limit)
        .order_by(Photo.created_at.desc(), Photo.id.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


def _build_filtered_photos_stmt(
    query: str | None = None,
    min_rating: float | None = None,
):
    """Build the shared filtered-photo query for listing and counting.

    Search pagination needs two separate queries: one to fetch the current
    page of results and another to calculate the total number of matching
    photos. Both queries must use identical filtering rules, so this helper
    centralizes the shared statement construction in one place.
    """

    # Photos without ratings should get an aggregated value of 0 instead of NULL.
    avg_rating = func.coalesce(func.avg(PhotoRating.rating), 0).label(
        "avg_rating"
    )

    stmt = (
        select(Photo, avg_rating)
        # Preload tags because callers usually serialize the returned Photo
        # objects, and lazy loading there may fail in async response code.
        .options(selectinload(Photo.tags))
        # Use outer joins so photos without ratings or tags still remain in the result set.
        .outerjoin(PhotoRating, PhotoRating.photo_id == Photo.id)
        .outerjoin(photo_tags, photo_tags.c.photo_id == Photo.id)
        .outerjoin(Tag, Tag.id == photo_tags.c.tag_id)
        .group_by(Photo.id)
    )

    if query:
        query = query.strip()

    if query:
        if query.startswith("#"):
            # `#tag` means search in tag names instead of description text.
            tag = query[1:].strip()
            if tag:
                stmt = stmt.where(Tag.name.ilike(f"%{tag}%"))
        else:
            stmt = stmt.where(Photo.description.ilike(f"%{query}%"))

    if min_rating is not None:
        # Rating is an aggregate value, so the filter must be applied via HAVING.
        stmt = stmt.having(avg_rating >= min_rating)

    return stmt, avg_rating


async def get_filtered_photos_by_keyword_or_tag(
    db: AsyncSession,
    limit: int,
    offset: int,
    query: str | None = None,
    min_rating: float | None = None,
    sort_by: PhotoSortBy | None = None,
) -> list[tuple[Photo, float]]:
    """Search photos by description or tag and optionally filter by rating.

    The query is interpreted as a tag search when it starts with ``#``.
    Results always include the aggregated average rating for each photo and
    can be sorted either by that rating or by photo creation date.
    """
    stmt, avg_rating = _build_filtered_photos_stmt(
        query=query,
        min_rating=min_rating,
    )

    match sort_by:
        case PhotoSortBy.rating:
            stmt = stmt.order_by(
                avg_rating.desc(), Photo.created_at.desc()
            )
        case PhotoSortBy.date:
            stmt = stmt.order_by(Photo.created_at.desc())
        case _:
            stmt = stmt.order_by(Photo.created_at.desc())

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)

    return result.all()


async def count_filtered_photos_by_keyword_or_tag(
    db: AsyncSession,
    query: str | None = None,
    min_rating: float | None = None,
) -> int:
    """Return the total number of photos matching the current search filters.

    Pagination metadata must reflect the full filtered result set rather than
    only the current page after ``limit`` and ``offset``. This method reuses
    the same filtered query as the list method and counts its grouped rows in
    a subquery, which keeps the total correct even with joins and aggregates.
    """

    stmt, _ = _build_filtered_photos_stmt(
        query=query,
        min_rating=min_rating,
    )

    # Count grouped filtered rows in a subquery so the total is based on
    # unique photos that matched the filters, not on joined child rows.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt)
    return int(total or 0)


async def get_total_number_of_photos(
    user_id: int, db: AsyncSession
) -> int:
    """Return the total number of photos that belong to the user."""

    stmt = select(func.count(Photo.id)).where(
        Photo.owner_id == user_id
    )
    total = await db.scalar(stmt)
    return total


async def delete_photo(photo: Photo, db: AsyncSession) -> Photo:
    """Delete a persisted photo record and return the deleted ORM object."""

    await db.delete(photo)
    await db.commit()

    return photo


async def get_existing_tags(
    tags: list[str], db: AsyncSession
) -> list[Tag]:
    """Fetch all existing tag entities whose names match the provided list.

    The function queries the database for tags whose names match any value
    from the provided list and returns the corresponding ORM objects.
    """

    stmt = select(Tag).where(Tag.name.in_(tags))
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_tag_by_name(tag: str, db: AsyncSession) -> Tag | None:
    """Fetch a single tag entity by its unique name."""

    stmt = select(Tag).filter_by(name=tag)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_tag(tag: str, db: AsyncSession) -> Tag:
    """Return an existing tag by name or create a new one within the current transaction."""

    existing_tag = await get_tag_by_name(tag=tag, db=db)
    if existing_tag:
        return existing_tag

    new_tag = Tag(name=tag)
    db.add(new_tag)
    # Flush assigns the new tag id inside the current transaction without
    # committing early, so photo creation can still be saved atomically later.
    await db.flush()
    return new_tag


async def update_photo_description(
    photo: Photo, description: str, db: AsyncSession
) -> Photo:
    """Update the description of a persisted photo and return the updated object."""

    photo.description = description
    await db.commit()
    await db.refresh(photo)

    return photo


async def add_photo_tags(
    photo: Photo, tags: list[Tag], db: AsyncSession
) -> Photo:
    """Replace the tags of a persisted photo and return the updated object.

    The function assigns a new list of tag entities to the target photo,
    replacing any previously linked tags, commits the change to the
    database, refreshes the ORM object, and returns the updated photo.
    """

    photo.tags = tags
    await db.commit()
    await db.refresh(photo)

    return photo


async def create_photo_transformation(
    photo_id: int,
    user_id: int,
    transformation_type: TransformationType,
    transformation_params: dict,
    transformed_url: str,
    qr_code_url: str | None,
    db: AsyncSession,
) -> PhotoTransformation:
    """Create and persist a new transformed photo link record.

    The function builds a ``PhotoTransformation`` ORM entity for a saved
    transformed photo URL, links it to the target photo and user, stores the
    transformation type and parameters, commits the transaction, refreshes
    the saved row, and returns the persisted record.
    """

    record = PhotoTransformation(
        photo_id=photo_id,
        user_id=user_id,
        transformation_type=transformation_type,
        transformation_params=transformation_params,
        transformed_url=transformed_url,
        qr_code_url=qr_code_url,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return record


async def get_photo_transformations_by_photo_id(
    photo_id: int, db: AsyncSession
) -> list[PhotoTransformation]:
    """Return all saved transformation links for the specified photo.

    The function queries the database for transformation records that belong
    to the given photo identifier, orders them from newest to oldest, and
    returns the corresponding ORM objects.
    """

    stmt = (
        select(PhotoTransformation)
        .where(PhotoTransformation.photo_id == photo_id)
        .order_by(PhotoTransformation.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_photo_transformation_by_id(
    transformation_id: int, db: AsyncSession
) -> PhotoTransformation | None:
    """Return one saved transformation link by its identifier."""

    stmt = select(PhotoTransformation).where(
        PhotoTransformation.id == transformation_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_photo_average_rating(
    photo_id: int, db: AsyncSession
) -> float:
    """Return the average rating value for the specified photo."""

    stmt = select(func.avg(PhotoRating.rating)).filter_by(
        photo_id=photo_id
    )
    average_rating = await db.scalar(stmt)
    return float(average_rating or 0)
