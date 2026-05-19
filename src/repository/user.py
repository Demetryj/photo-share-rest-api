"""Database operations for user accounts."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.user import Role, User
from src.schemas.user import SignUpRequestSchema


async def get_user_by_email(
    email: str, db: AsyncSession
) -> User | None:
    """Return a user by email."""

    stmt = select(User).filter_by(email=email)
    user = await db.execute(stmt)
    return user.scalar_one_or_none()


async def get_user_by_id(
    user_id: str, db: AsyncSession
) -> User | None:
    """Return a user by ID."""

    stmt = select(User).filter_by(id=user_id)
    user = await db.execute(stmt)
    return user.scalar_one_or_none()


async def has_any_users(db: AsyncSession) -> bool:
    """Return True if at least one user exists in the database."""

    stmt = select(User.id).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def create_user(
    body: SignUpRequestSchema, db: AsyncSession
) -> User:
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


async def get_profile_by_username(
    username: str, db: AsyncSession
) -> User | None:
    """Return a user entity by username for public profile lookups."""

    stmt = select(User).filter_by(username=username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_all_users(
    limit: int, offset: int, db: AsyncSession
) -> list[User]:
    """Return a paginated slice of users."""

    stmt = select(User).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_total_number_of_users(db: AsyncSession) -> int:
    """Return the total number of users in the database."""

    stmt = select(func.count(User.id))
    total = await db.scalar(stmt)
    return total


async def update_own_user_profile(
    user_id: int,
    avatar_url: str | None,
    display_name: str | None,
    db: AsyncSession,
) -> User | None:
    """Update the current user's editable profile fields and return the user."""

    user = await get_user_by_id(user_id=user_id, db=db)

    if user is None:
        return None

    if avatar_url is not None:
        user.avatar = avatar_url
    if display_name is not None:
        user.display_name = display_name

    await db.commit()
    await db.refresh(user)

    return user


async def change_user_role(
    user_id: int, new_role: Role, db: AsyncSession
) -> User | None:
    """Change a user's role and return the updated user."""

    user = await get_user_by_id(user_id=user_id, db=db)

    if user is None:
        return None

    if user.role.value == new_role.value:
        return user

    user.role = new_role
    await db.commit()
    await db.refresh(user)

    return user
