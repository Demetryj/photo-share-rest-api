"""Repository helpers for persisted user-session records.

This module contains database operations for managing authenticated user
sessions. Each session row represents one device or browser context and
stores the refresh-token hash together with the currently active
access-token JTI for that session.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.user import PasswordResetToken, UserSession


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


# Create or replace the single active password-reset token for one user.
async def create_password_reset_token(
    user_id: int,
    token_hash: str,
    expires_at: datetime,
    db: AsyncSession,
) -> None:
    """Create or update the user's single password-reset token record.

    The function keeps at most one password-reset token row per user. If a
    record already exists for that user, its token hash, expiration time,
    and usage marker are replaced with the new values. Otherwise, a new
    record is created.
    """

    # Keep at most one active password reset token row per user.
    stmt = select(PasswordResetToken).filter_by(user_id=user_id)
    result = await db.execute(stmt)
    reset_token = result.scalar_one_or_none()

    # Reuse the existing per-user token row when it already exists.
    if reset_token is None:
        # Create the initial token row for this user.
        reset_token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        db.add(reset_token)

    # Store the new token metadata and mark the token as not yet used.
    reset_token.token_hash = token_hash
    reset_token.expires_at = expires_at
    reset_token.used_at = None

    await db.commit()
    await db.refresh(reset_token)


# Fetch one password-reset token record by its stored token hash.
async def get_password_reset_token_by_hash(
    token_hash: str,
    db: AsyncSession,
) -> PasswordResetToken | None:
    """Return one password-reset token record by its stored token hash."""

    stmt = select(PasswordResetToken).filter_by(token_hash=token_hash)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# Mark a stored password-reset token as used by setting its usage timestamp.
async def mark_password_reset_token_as_used(
    token_hash: str,
    db: AsyncSession,
) -> None:
    """Mark the password-reset token as used."""

    db_token_obj = await get_password_reset_token_by_hash(
        token_hash=token_hash,
        db=db,
    )
    if not db_token_obj:
        return

    db_token_obj.used_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(db_token_obj)


# Delete old password-reset token records that are no longer needed.
async def delete_old_password_reset_tokens(
    older_than_days: int,
    db: AsyncSession,
) -> int:
    """Delete old used or long-expired password reset tokens.

    Deletes:
    - tokens that were used more than ``older_than_days`` ago
    - tokens that expired more than ``older_than_days`` ago

    Returns the number of deleted rows.
    """

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=older_than_days
    )

    stmt = (
        delete(PasswordResetToken)
        .where(
            or_(
                # Used tokens can be safely removed after retention window.
                PasswordResetToken.used_at.is_not(None),
                PasswordResetToken.expires_at < cutoff,
            )
        )
        .where(
            or_(
                # Remove used tokens only after they are old enough.
                PasswordResetToken.used_at < cutoff,
                # Remove expired unused tokens after the same retention window.
                PasswordResetToken.expires_at < cutoff,
            )
        )
    )

    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount or 0
