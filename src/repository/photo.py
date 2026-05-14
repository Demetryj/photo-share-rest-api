from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.photo import Photo, Tag


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
