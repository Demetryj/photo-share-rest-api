"""Integration tests for comment routes."""

from src.config.messages import HTTPStatusMessages
from src.entity.user import Role

PREFIX = "/api/photos"
INITIAL_COMMENT = "Initial comment"
UPDATED_COMMENT = "Updated comment"
MISSING_ENTITY_ID = 999999


def test_create_comment_returns_created_comment_payload(
    client, auth_headers, user_factory, photo_factory
) -> None:
    """Create a comment for an existing photo."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)

    response = client.post(
        f"{PREFIX}/{photo.id}/comments",
        headers=auth_headers,
        json={"content": INITIAL_COMMENT},
    )

    assert response.status_code == 201, response.text
    data = response.json()

    assert data["content"] == INITIAL_COMMENT
    assert data["photo_id"] == photo.id
    assert data["user"]["username"] is not None


def test_create_comment_returns_404_for_missing_photo(
    client, auth_headers
) -> None:
    """Reject comment creation when the target photo does not exist."""

    response = client.post(
        f"{PREFIX}/{MISSING_ENTITY_ID}/comments",
        headers=auth_headers,
        json={"content": INITIAL_COMMENT},
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_get_all_comments_returns_paginated_photo_comments(
    client,
    auth_headers,
    user_factory,
    photo_factory,
    comment_factory,
    seeded_current_user,
) -> None:
    """Return paginated comments for the specified photo."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)
    comment_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        content=INITIAL_COMMENT,
    )

    response = client.get(
        f"{PREFIX}/{photo.id}/comments",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["total"] >= 1
    assert data["total_pages"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["content"] == INITIAL_COMMENT


def test_get_all_comments_returns_404_for_missing_photo(
    client, auth_headers
) -> None:
    """Reject comment listing when the target photo does not exist."""

    response = client.get(
        f"{PREFIX}/{MISSING_ENTITY_ID}/comments",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_update_comment_returns_updated_comment_payload(
    client,
    auth_headers,
    user_factory,
    photo_factory,
    comment_factory,
    seeded_current_user,
) -> None:
    """Update the current user's comment for the specified photo."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)
    comment = comment_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        content=INITIAL_COMMENT,
    )

    response = client.patch(
        f"{PREFIX}/{photo.id}/comments/{comment.id}",
        headers=auth_headers,
        json={"content": UPDATED_COMMENT},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == comment.id
    assert data["content"] == UPDATED_COMMENT


def test_update_comment_returns_404_for_missing_comment(
    client,
    auth_headers,
    user_factory,
    photo_factory,
) -> None:
    """Reject comment update when the target comment does not exist."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)

    response = client.patch(
        f"{PREFIX}/{photo.id}/comments/{MISSING_ENTITY_ID}",
        headers=auth_headers,
        json={"content": UPDATED_COMMENT},
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_delete_comment_returns_204_for_staff_user(
    client,
    auth_headers,
    user_factory,
    photo_factory,
    comment_factory,
    seeded_current_user,
) -> None:
    """Delete a comment when the current user has staff-level access."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)
    comment = comment_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        content=INITIAL_COMMENT,
    )

    response = client.delete(
        f"{PREFIX}/{photo.id}/comments/{comment.id}",
        headers=auth_headers,
    )

    assert response.status_code == 204, response.text


def test_delete_comment_returns_404_for_missing_comment(
    client,
    auth_headers,
    user_factory,
    photo_factory,
) -> None:
    """Reject comment deletion when the target comment does not exist."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)

    response = client.delete(
        f"{PREFIX}/{photo.id}/comments/{MISSING_ENTITY_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_delete_comment_returns_403_for_non_staff_user(
    client,
    auth_headers,
    user_factory,
    photo_factory,
    comment_factory,
    seeded_current_user,
    set_route_current_user,
) -> None:
    """Reject comment deletion when the current user is not staff."""

    current_user = user_factory(role=Role.user)
    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)
    comment = comment_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        content=INITIAL_COMMENT,
    )
    set_route_current_user(current_user)

    response = client.delete(
        f"{PREFIX}/{photo.id}/comments/{comment.id}",
        headers=auth_headers,
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.operation_forbidden.value
    )
