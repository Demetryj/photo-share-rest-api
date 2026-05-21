"""Repository helpers for persisted user-session records.

This module contains database operations for managing authenticated user
sessions. Each session row represents one device or browser context and
stores the refresh-token hash together with the currently active
access-token JTI for that session.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.user import UserSession


# Create and persist one user session for a device or browser.
async def create_user_session(
    refresh_token_hash: str,
    access_token_jti: str,
    user_id: int,
    db: AsyncSession,
) -> UserSession:
    """Create and persist a new user session record.

    The record stores the refresh-token hash and the currently active
    access-token JTI for one authenticated user session.
    """

    record = UserSession(
        refresh_token_hash=refresh_token_hash,
        access_token_jti=access_token_jti,
        user_id=user_id,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


# Fetch one stored session by its refresh-token hash.
async def get_user_session_by_refresh_token_hash(
    refresh_token_hash: str,
    db: AsyncSession,
) -> UserSession | None:
    """Return one user session by its stored refresh-token hash."""

    stmt = select(UserSession).where(
        UserSession.refresh_token_hash == refresh_token_hash
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# Fetch one stored session by its current access-token JTI.
async def get_user_session_by_access_token_jti(
    access_token_jti: str,
    db: AsyncSession,
) -> UserSession | None:
    """Return one user session by its stored access-token JTI."""

    stmt = select(UserSession).where(
        UserSession.access_token_jti == access_token_jti
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# Rotate both token identifiers for an existing session.
async def update_user_session_tokens(
    old_refresh_token_hash: str,
    new_refresh_token_hash: str,
    new_access_token_jti: str,
    db: AsyncSession,
) -> UserSession | None:
    """Update the token identifiers for an existing user session.

    The function finds the session by its current refresh-token hash, returns
    ``None`` when that session does not exist, and otherwise replaces both
    the stored refresh-token hash and the stored access-token JTI.
    """

    session = await get_user_session_by_refresh_token_hash(
        refresh_token_hash=old_refresh_token_hash,
        db=db,
    )

    if session is None:
        return None

    session.refresh_token_hash = new_refresh_token_hash
    session.access_token_jti = new_access_token_jti
    await db.commit()
    await db.refresh(session)
    return session


# Delete one stored session by its refresh-token hash.
async def delete_user_session_by_refresh_token_hash(
    refresh_token_hash: str,
    db: AsyncSession,
) -> bool:
    """Delete one user session by its stored refresh-token hash."""

    stmt = delete(UserSession).where(
        UserSession.refresh_token_hash == refresh_token_hash
    )
    result = await db.execute(stmt)
    await db.commit()
    return (result.rowcount or 0) > 0


# Delete one stored session by its current access-token JTI.
async def delete_user_session_by_access_token_jti(
    access_token_jti: str,
    db: AsyncSession,
) -> bool:
    """Delete one user session by its stored access-token JTI."""

    stmt = delete(UserSession).where(
        UserSession.access_token_jti == access_token_jti
    )
    result = await db.execute(stmt)
    await db.commit()
    return (result.rowcount or 0) > 0


# Delete all stored sessions that belong to a user.
async def delete_all_user_sessions_by_user_id(
    user_id: int,
    db: AsyncSession,
) -> None:
    """Delete all user sessions that belong to the specified user."""

    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    await db.execute(stmt)
    await db.commit()
