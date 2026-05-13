from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.user import RefreshToken


# Create and persist a refresh token hash for a user session.
async def add_refresh_token(
    hash_token: str, user_id: int, db: AsyncSession
) -> RefreshToken:
    """Store a refresh token hash for a user session."""

    record = RefreshToken(rf_token=hash_token, user_id=user_id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_refresh_token_by_token(
    hash_token: str, db: AsyncSession
) -> RefreshToken | None:
    """Return a stored refresh token by its hash."""

    stmt = select(RefreshToken).where(RefreshToken.rf_token == hash_token)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# Delete one stored refresh token hash.
async def delete_refresh_token_by_token(hash_token: str, db: AsyncSession) -> bool:
    """Delete one refresh token by its stored hash."""

    stmt = delete(RefreshToken).where(RefreshToken.rf_token == hash_token)
    result = await db.execute(stmt)
    await db.commit()
    return (result.rowcount or 0) > 0


# Delete all stored refresh token hashes for a user.
async def delete_all_refresh_tokens_by_user_id(user_id: int, db: AsyncSession) -> None:
    """Delete all refresh tokens that belong to a user."""

    stmt = delete(RefreshToken).where(RefreshToken.user_id == user_id)
    await db.execute(stmt)
    await db.commit()
