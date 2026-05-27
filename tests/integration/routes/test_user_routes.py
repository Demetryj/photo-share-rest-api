"""Integration tests for user routes."""

from unittest.mock import AsyncMock

from src.config.messages import HTTPStatusMessages, ValidationMessages
from src.entity.user import Role
from src.services import photo as photo_service
from tests.conftest import test_user

PREFIX = "/api/users"


def test_get_me_returns_current_user_profile(
    client, auth_headers
) -> None:
    """Return the current authenticated user's profile payload."""

    response = client.get(f"{PREFIX}/me", headers=auth_headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["email"] == test_user["email"]


def test_get_all_users_returns_user_profile_list(
    client, auth_headers
) -> None:
    """Return paginated public user profiles with the expected schema."""

    response = client.get(f"{PREFIX}/all", headers=auth_headers)

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["total"] >= 1
    assert data["total_pages"] >= 1
    assert isinstance(data["items"], list)
    assert len(data["items"]) >= 1

    first_item = data["items"][0]
    assert "id" in first_item
    assert "username" in first_item
    assert "display_name" in first_item
    assert "avatar" in first_item
    assert "created_at" in first_item
    assert "photos_count" in first_item
    assert "comments_count" in first_item


def test_get_all_users_returns_requested_page_slice(
    client, auth_headers
) -> None:
    """Return the requested pagination metadata for custom page parameters."""

    response = client.get(
        f"{PREFIX}/all?page=1&per_page=1",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["page"] == 1
    assert data["per_page"] == 1
    assert len(data["items"]) == 1


def test_get_profile_by_username_returns_public_profile(
    client, auth_headers
) -> None:
    """Return the public profile for an existing username."""

    response = client.get(
        f"{PREFIX}/profile/{test_user['username']}",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["username"] == test_user["username"]
    assert "photos_count" in data
    assert "comments_count" in data


def test_get_profile_by_username_returns_404_for_missing_user(
    client, auth_headers
) -> None:
    """Return 404 when the requested public profile does not exist."""

    response = client.get(
        f"{PREFIX}/profile/missing_user",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_get_profile_returns_current_users_editable_profile(
    client, auth_headers
) -> None:
    """Return the authenticated user's editable profile payload."""

    response = client.get(f"{PREFIX}/profile", headers=auth_headers)

    assert response.status_code == 200, response.text
    data = response.json()

    assert "id" in data
    assert "display_name" in data
    assert "avatar" in data


def test_update_profile_returns_updated_display_name(
    client, auth_headers
) -> None:
    """Update the current user's profile when only display name is provided."""

    response = client.patch(
        f"{PREFIX}/profile",
        headers=auth_headers,
        data={"display_name": "Test User"},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["display_name"] == "Test User"


def test_update_profile_returns_updated_avatar_url(
    client, auth_headers, monkeypatch
) -> None:
    """Update the current user's avatar using mocked image validation/upload."""

    monkeypatch.setattr(
        photo_service,
        "validate_image_file",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        photo_service,
        "cloudinary_upload",
        AsyncMock(return_value="https://example.com/avatar.png"),
    )

    files = {
        "file": (
            "avatar.png",
            b"fake image content",
            "image/png",
        )
    }

    response = client.patch(
        f"{PREFIX}/profile",
        headers=auth_headers,
        files=files,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["avatar"] == "https://example.com/avatar.png"


def test_update_profile_returns_400_for_invalid_display_name(
    client, auth_headers
) -> None:
    """Return 400 when display name contains disallowed characters."""

    response = client.patch(
        f"{PREFIX}/profile",
        headers=auth_headers,
        data={"display_name": "Test123"},
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == ValidationMessages.display_name_contains_invalid_characters.value
    )


def test_update_profile_returns_400_for_empty_payload(
    client, auth_headers
) -> None:
    """Return 400 when profile update request contains no fields to change."""

    response = client.patch(
        f"{PREFIX}/profile",
        headers=auth_headers,
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.bad_request.value
    )


def test_change_user_role_returns_updated_role_for_target_user(
    client, auth_headers, user_factory
) -> None:
    """Allow the seeded admin user to promote a regular user to moderator."""

    target_user = user_factory(role=Role.user)

    response = client.patch(
        f"{PREFIX}/role/{target_user.id}",
        headers=auth_headers,
        json={"role": Role.moderator.value},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == target_user.id
    assert data["role"] == Role.moderator.value


def test_change_user_role_returns_404_for_missing_target_user(
    client, auth_headers
) -> None:
    """Return 404 when an admin changes the role of a missing user."""

    response = client.patch(
        f"{PREFIX}/role/999999",
        headers=auth_headers,
        json={"role": Role.moderator.value},
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_change_user_role_returns_403_for_self_update(
    client, auth_headers
) -> None:
    """Return 403 when an admin attempts to change their own role."""

    response = client.patch(
        f"{PREFIX}/role/1",
        headers=auth_headers,
        json={"role": Role.moderator.value},
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.forbidden.value
    )


def test_change_user_role_returns_403_for_admin_target(
    client, auth_headers, user_factory
) -> None:
    """Return 403 when an admin attempts to change another admin's role."""

    target_user = user_factory(role=Role.admin)

    response = client.patch(
        f"{PREFIX}/role/{target_user.id}",
        headers=auth_headers,
        json={"role": Role.moderator.value},
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.forbidden.value
    )


def test_change_user_role_returns_403_for_non_admin_user(
    client, auth_headers, user_factory, set_route_current_user
) -> None:
    """Return 403 when a non-admin user calls the admin-only role endpoint."""

    current_user = user_factory(role=Role.user)
    target_user = user_factory(role=Role.user)
    set_route_current_user(current_user)

    response = client.patch(
        f"{PREFIX}/role/{target_user.id}",
        headers=auth_headers,
        json={"role": Role.moderator.value},
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.operation_forbidden.value
    )


def test_change_user_blocked_status_returns_updated_block_flag(
    client, auth_headers, user_factory
) -> None:
    """Allow the seeded admin user to block another regular user."""

    target_user = user_factory(role=Role.user, blocked=False)

    response = client.patch(
        f"{PREFIX}/{target_user.id}/blocked",
        headers=auth_headers,
        json={"blocked": True},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == target_user.id
    assert data["blocked"] is True


def test_change_user_blocked_status_returns_404_for_missing_target_user(
    client, auth_headers
) -> None:
    """Return 404 when an admin blocks or unblocks a missing user."""

    response = client.patch(
        f"{PREFIX}/999999/blocked",
        headers=auth_headers,
        json={"blocked": True},
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_change_user_blocked_status_returns_400_for_no_op_request(
    client, auth_headers, user_factory
) -> None:
    """Return 400 when the requested blocked status is already set."""

    target_user = user_factory(role=Role.user, blocked=True)

    response = client.patch(
        f"{PREFIX}/{target_user.id}/blocked",
        headers=auth_headers,
        json={"blocked": True},
    )

    assert response.status_code == 400, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.bad_request.value
    )


def test_change_user_blocked_status_returns_403_for_self_update(
    client, auth_headers
) -> None:
    """Return 403 when an admin attempts to block or unblock themselves."""

    response = client.patch(
        f"{PREFIX}/1/blocked",
        headers=auth_headers,
        json={"blocked": True},
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.forbidden.value
    )


def test_change_user_blocked_status_returns_403_for_admin_target(
    client, auth_headers, user_factory
) -> None:
    """Return 403 when an admin attempts to block another admin."""

    target_user = user_factory(role=Role.admin, blocked=False)

    response = client.patch(
        f"{PREFIX}/{target_user.id}/blocked",
        headers=auth_headers,
        json={"blocked": True},
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.forbidden.value
    )


def test_change_user_blocked_status_returns_403_for_non_admin_user(
    client, auth_headers, user_factory, set_route_current_user
) -> None:
    """Return 403 when a non-admin user calls the admin-only block endpoint."""

    current_user = user_factory(role=Role.user)
    target_user = user_factory(role=Role.user, blocked=False)
    set_route_current_user(current_user)

    response = client.patch(
        f"{PREFIX}/{target_user.id}/blocked",
        headers=auth_headers,
        json={"blocked": True},
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.operation_forbidden.value
    )
