"""Unit tests for user service helpers."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.user import Role, User
from src.services import user as user_service


@pytest.mark.asyncio
async def test_get_photos_and_comments_counts_returns_both_aggregates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return both photo and comment counters from repository helpers."""

    db = AsyncMock(spec=AsyncSession)
    photo_count_mock = AsyncMock(return_value=6)
    comment_count_mock = AsyncMock(return_value=9)
    monkeypatch.setattr(
        "src.services.user.repository_photo.get_total_number_of_photos",
        photo_count_mock,
    )
    monkeypatch.setattr(
        "src.services.user.repository_comment.get_total_number_of_comments",
        comment_count_mock,
    )

    result = await user_service.get_photos_and_comments_counts(
        user_id=4,
        db=db,
    )

    assert result == {"photos_count": 6, "comments_count": 9}


def test_validate_display_name_value_returns_normalized_value() -> (
    None
):
    """Trim and return a valid display name."""

    result = user_service.validate_display_name_value("  Test User  ")

    assert result == "Test User"


def test_validate_display_name_value_raises_for_empty_string() -> (
    None
):
    """Raise ValueError when the submitted display name is empty after trim."""

    with pytest.raises(ValueError):
        user_service.validate_display_name_value("   ")


def test_validate_display_name_value_raises_for_invalid_characters() -> (
    None
):
    """Raise ValueError when the display name contains unsupported symbols."""

    with pytest.raises(ValueError):
        user_service.validate_display_name_value("User_123")


def test_validate_admin_user_management_action_raises_for_self_update() -> (
    None
):
    """Raise 403 when an admin targets their own account."""

    current_user = User(id=1, role=Role.admin)
    target_user = User(id=1, role=Role.user)

    with pytest.raises(HTTPException) as exc_info:
        user_service.validate_admin_user_management_action(
            target_user=target_user,
            current_user=current_user,
        )

    assert exc_info.value.status_code == 403


def test_validate_admin_user_management_action_raises_for_admin_target() -> (
    None
):
    """Raise 403 when an admin tries to manage another admin."""

    current_user = User(id=1, role=Role.admin)
    target_user = User(id=2, role=Role.admin)

    with pytest.raises(HTTPException) as exc_info:
        user_service.validate_admin_user_management_action(
            target_user=target_user,
            current_user=current_user,
        )

    assert exc_info.value.status_code == 403


def test_validate_admin_user_management_action_raises_for_assign_admin_role() -> (
    None
):
    """Raise 403 when a management action tries to assign the admin role."""

    current_user = User(id=1, role=Role.admin)
    target_user = User(id=2, role=Role.user)

    with pytest.raises(HTTPException) as exc_info:
        user_service.validate_admin_user_management_action(
            target_user=target_user,
            current_user=current_user,
            new_role=Role.admin,
        )

    assert exc_info.value.status_code == 403


def test_validate_admin_user_management_action_allows_regular_target_role_change() -> (
    None
):
    """Allow valid admin actions against a non-admin target user."""

    current_user = User(id=1, role=Role.admin)
    target_user = User(id=2, role=Role.user)

    user_service.validate_admin_user_management_action(
        target_user=target_user,
        current_user=current_user,
        new_role=Role.moderator,
    )
