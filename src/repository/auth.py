from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.models import RefreshToken


# Create and persist a refresh token row for a user.
async def add_refresh_token(token: str, user_id: int, db: AsyncSession) -> RefreshToken:
    """Store a refresh token."""

    record = RefreshToken(rf_token=token, user_id=user_id)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
