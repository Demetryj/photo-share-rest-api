"""Database operations for user accounts."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.user import Role, User
from src.schemas.user import UserSchema


async def get_user_by_email(
    email: str, db: AsyncSession
) -> User | None:
    """Return a user by email."""

    stmt = select(User).filter_by(email=email)
    user = await db.execute(stmt)
    return user.scalar_one_or_none()


async def has_any_users(db: AsyncSession) -> bool:
    """Return True if at least one user exists in the database."""

    stmt = select(User.id).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def create_user(body: UserSchema, db: AsyncSession) -> User:
    """Create a user and assign the admin role only to the first account."""

    has_users = await has_any_users(db)

    user_data = body.model_dump(
        include={"username", "email", "password"}
    )
    user_data["role"] = Role.admin if not has_users else Role.user

    new_user = User(**user_data)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


async def confirm_email(email: str, db: AsyncSession) -> None:
    """Mark a user email as confirmed."""

    user: User | None = await get_user_by_email(email=email, db=db)
    if user is None:
        return
    user.confirmed = True
    await db.commit()
    await db.refresh(user)
