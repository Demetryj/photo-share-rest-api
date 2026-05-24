"""FastAPI routes for public user profiles and self-profile management."""

import math
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import rate_limiters
from src.config.messages import (
    ADMIN_ACCESS,
    AUTHENTICATED_USERS_ACCESS,
    HTTPStatusMessages,
)
from src.config.settings import settings
from src.database.db import get_db
from src.entity.user import User
from src.helpers.create_exception import create_exception
from src.repository import auth as repository_auth
from src.repository import user as repository_user
from src.schemas.user import (
    MyProfileResponseSchema,
    MyUserInfoResponseSchema,
    PaginatedUsersResponseSchema,
    PublicProfileResponseSchema,
    UserBlockRequestSchema,
    UserBlockResponseSchema,
    UserRoleRequestSchema,
    UserRoleResponseSchema,
)
from src.services import photo as photo_service
from src.services import user as user_service
from src.services.auth import auth_service
from src.services.role import admin_only, authenticated_users

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[
        Depends(RateLimiter(limiter=rate_limiters.user_base_limiter))
    ],
)

ProfileDisplayNameForm = Annotated[
    str | None,
    Form(
        description="Display name\n\n"
        "Display name may contain only letters, spaces, hyphens, and apostrophes.",
        min_length=2,
        max_length=60,
    ),
]


# Detailed self-information visible to the authenticated user.
@router.get(
    "/me",
    response_model=MyUserInfoResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return detailed information about the authenticated user.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(authenticated_users)],
)
async def get_current_user_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> MyUserInfoResponseSchema:
    """Return detailed account information for the authenticated user.

    The endpoint resolves the current user from the access token, loads the
    latest user record from the database, calculates photo and comment
    counters, and returns the combined self-information payload.
    """

    user_data = await repository_user.get_user_by_id(
        user_id=current_user.id, db=db
    )

    counts = await user_service.get_photos_and_comments_counts(
        user_id=user_data.id, db=db
    )

    response_data = MyUserInfoResponseSchema.model_validate(
        user_data
    ).model_dump()
    response_data["photos_count"] = counts["photos_count"]
    response_data["comments_count"] = counts["comments_count"]
    return response_data


# Paginated public user profiles visible to authenticated users.
@router.get(
    "/all",
    response_model=PaginatedUsersResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return a paginated list of public user profiles.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(authenticated_users)],
)
async def get_all_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
) -> PaginatedUsersResponseSchema:
    """Return a paginated list of public user profiles.

    The endpoint is available only to authenticated users. It applies
    page/per_page pagination, loads the requested slice of users, calculates
    public photo and comment counters for each user, computes pagination
    metadata, and returns the paginated response payload.
    """

    offset = (page - 1) * per_page

    user_list = await repository_user.get_all_users(
        limit=per_page, offset=offset, db=db
    )

    resp_users = []
    for user in user_list:
        user_data = PublicProfileResponseSchema.model_validate(
            user
        ).model_dump()

        counts = await user_service.get_photos_and_comments_counts(
            user_id=user.id, db=db
        )
        user_data["photos_count"] = counts["photos_count"]
        user_data["comments_count"] = counts["comments_count"]
        resp_users.append(user_data)

    total_users = await repository_user.get_total_number_of_users(
        db=db
    )
    total_pages = (
        math.ceil(total_users / per_page) if total_users else 0
    )

    return {
        "page": page,
        "per_page": per_page,
        "total": total_users,
        "total_pages": total_pages,
        "items": resp_users,
    }


# Public profile visible to authenticated users by unique username.
@router.get(
    "/profile/{username}",
    response_model=PublicProfileResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return a user's public profile by unique username.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(authenticated_users)],
)
async def get_profile_by_username(
    username: str,
    db: AsyncSession = Depends(get_db),
) -> PublicProfileResponseSchema:
    """Return the public profile summary for the specified username.

    The endpoint is available only to authenticated users. It resolves the
    target user by username, returns a 404 error if the user does not exist,
    calculates the user's photo and comment counters, and returns the public
    profile data.
    """

    user_data: User | None = (
        await repository_user.get_profile_by_username(
            username=username, db=db
        )
    )

    if user_data is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    counts = await user_service.get_photos_and_comments_counts(
        user_id=user_data.id, db=db
    )

    return {
        "id": user_data.id,
        "username": user_data.username,
        "display_name": user_data.display_name,
        "avatar": user_data.avatar,
        "created_at": user_data.created_at,
        "photos_count": counts["photos_count"],
        "comments_count": counts["comments_count"],
    }


# Editable self-profile visible to the authenticated user.
@router.get(
    "/profile",
    response_model=MyProfileResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Return the authenticated user's editable profile data.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}"
    ),
    dependencies=[Depends(authenticated_users)],
)
async def get_own_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> MyProfileResponseSchema:
    """Return the authenticated user's editable profile fields.

    The endpoint resolves the current user from the access token, loads the
    latest user data from the database, and returns the fields that can be
    edited in the user's own profile settings.
    """

    user_data = await repository_user.get_user_by_id(
        user_id=current_user.id, db=db
    )

    return {
        "id": user_data.id,
        "display_name": user_data.display_name,
        "email": user_data.email,
        "avatar": user_data.avatar,
    }


# Update the authenticated user's editable profile fields.
@router.patch(
    "/profile",
    response_model=MyProfileResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Update the authenticated user's editable profile data.\n\n"
        f"{AUTHENTICATED_USERS_ACCESS}.\n\n"
        "You may update display name and avatar. "
        "At least one field must be provided."
    ),
    dependencies=[
        Depends(authenticated_users),
        Depends(
            RateLimiter(
                limiter=rate_limiters.user_update_profile_limiter
            )
        ),
    ],
)
async def update_own_user_profile(
    file: UploadFile | None = File(
        default=None,
        description=f"Image file. Max size: {photo_service.MAX_IMAGE_SIZE} MB. "
        f"Allowed formats: {photo_service.ALLOWED_FORMATS}",
    ),
    display_name: ProfileDisplayNameForm = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> MyProfileResponseSchema:
    """Update the authenticated user's editable profile fields.

    The endpoint accepts multipart form data, rejects empty update requests,
    validates the optional display name, optionally validates and uploads a
    new avatar image, persists the provided changes for the current user,
    and returns the updated profile payload.
    """

    if not file and not display_name:
        create_exception()

    normalized_display_name = (
        user_service.validate_display_name_value(display_name)
    )

    avatar_url = None
    if file is not None:
        await photo_service.validate_image_file(file=file)
        # Keep one stable avatar asset per user so a new upload replaces the
        # previous avatar in Cloudinary instead of creating a new file.
        public_id = (
            f"{settings.CLOUDINARY_PUBLIC_ID_PREFIX}/avatars/"
            f"{current_user.id}"
        )
        avatar_url = await photo_service.cloudinary_upload(
            file=file,
            public_id=public_id,
            overwrite=True,
        )

    updated_user = await repository_user.update_own_user_profile(
        user_id=current_user.id,
        avatar_url=avatar_url,
        display_name=normalized_display_name,
        db=db,
    )

    if updated_user is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    return MyProfileResponseSchema.model_validate(updated_user)


# Change another user's role as an administrator.
@router.patch(
    "/role/{user_id}",
    response_model=UserRoleResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Change a user's role by user ID.\n\n"
        f"{ADMIN_ACCESS}\n\n"
        "At the moment this endpoint allows assigning only `user` or `moderator` roles."
    ),
    dependencies=[Depends(admin_only)],
)
async def change_user_role(
    user_id: int,
    body: UserRoleRequestSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> UserRoleResponseSchema:
    """Change a target user's role and return the updated user data.

    The endpoint is restricted to administrators. It first loads the target
    user, returns 404 when that user does not exist, rejects self-role
    changes, rejects role-management actions against another admin, rejects
    attempts to assign the `admin` role, and then updates the target user's
    role by user ID.
    """

    target_user = await repository_user.get_user_by_id(
        user_id=user_id, db=db
    )

    # The role can be changed only for an existing target user.
    if target_user is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    # Reuse the shared admin-user-management rule set for role changes.
    user_service.validate_admin_user_management_action(
        target_user=target_user,
        current_user=current_user,
        new_role=body.role,
    )

    updated_user = await repository_user.change_user_role(
        user_id=user_id, new_role=body.role, db=db
    )

    if updated_user is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    return UserRoleResponseSchema.model_validate(updated_user)


# Change another user's blocked status as an administrator.
@router.patch(
    "/{user_id}/blocked",
    response_model=UserBlockResponseSchema,
    response_description=HTTPStatusMessages.success.value,
    description=(
        "Change a user's blocked status by user ID.\n\n"
        f"{ADMIN_ACCESS}\n\n"
        "Blocked users cannot start new sessions or access protected routes."
    ),
    dependencies=[Depends(admin_only)],
)
async def change_user_blocked_status(
    user_id: int,
    body: UserBlockRequestSchema,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> UserBlockResponseSchema:
    """Change a target user's blocked status and return the updated user.

    The endpoint is restricted to administrators. It loads the target user,
    returns 404 when that user does not exist, rejects forbidden management
    actions such as targeting self or another admin, rejects requests that do
    not actually change the blocked status, updates the target user's blocked
    flag, and when the user is blocked removes all stored user-session
    records for that user so existing authenticated sessions are revoked.
    """

    # The blocked status can be changed only for an existing target user.
    target_user = await repository_user.get_user_by_id(
        user_id=user_id, db=db
    )

    if target_user is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    # Reuse the shared admin-user-management rule set for block/unblock actions.
    user_service.validate_admin_user_management_action(
        target_user=target_user,
        current_user=current_user,
    )

    # Reject no-op requests when the user already has the requested status.
    if body.blocked == target_user.blocked:
        create_exception()

    updated_user = await repository_user.change_user_blocked_status(
        user_id=target_user.id, blocked_status=body.blocked, db=db
    )

    if updated_user is None:
        create_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            message=HTTPStatusMessages.not_found.value,
        )

    # Blocking a user must invalidate every persisted authenticated session.
    if updated_user.blocked:
        await repository_auth.delete_all_user_sessions_by_user_id(
            user_id=updated_user.id,
            db=db,
        )

    return UserBlockResponseSchema.model_validate(updated_user)
