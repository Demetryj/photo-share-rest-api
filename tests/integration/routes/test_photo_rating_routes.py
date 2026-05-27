"""Integration tests for photo rating routes."""

from src.config.messages import HTTPStatusMessages
from src.entity.user import Role

PREFIX = "/api/photos"
RATING_VALUE = 5
UPDATED_RATING_VALUE = 4
MISSING_ENTITY_ID = 999999


def test_create_photo_rating_returns_created_rating(
    client,
    auth_headers,
    user_factory,
    photo_factory,
    seeded_current_user,
) -> None:
    """Create one rating for another user's photo."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)

    response = client.post(
        f"{PREFIX}/{photo.id}/rating",
        headers=auth_headers,
        json={"rating": RATING_VALUE},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["photo_id"] == photo.id
    assert data["user_id"] == seeded_current_user.id
    assert data["rating"] == RATING_VALUE


def test_create_photo_rating_returns_404_for_missing_photo(
    client,
    auth_headers,
) -> None:
    """Reject rating creation when the target photo does not exist."""

    response = client.post(
        f"{PREFIX}/{MISSING_ENTITY_ID}/rating",
        headers=auth_headers,
        json={"rating": RATING_VALUE},
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_create_photo_rating_returns_403_for_own_photo(
    client,
    auth_headers,
    photo_factory,
    seeded_current_user,
) -> None:
    """Reject attempts to rate the current user's own photo."""

    photo = photo_factory(owner_id=seeded_current_user.id)

    response = client.post(
        f"{PREFIX}/{photo.id}/rating",
        headers=auth_headers,
        json={"rating": RATING_VALUE},
    )

    assert response.status_code == 403, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.operation_forbidden.value
    )


def test_get_all_photo_ratings_returns_paginated_ratings(
    client,
    auth_headers,
    user_factory,
    photo_factory,
    rating_factory,
    seeded_current_user,
) -> None:
    """Return paginated ratings for a specified photo."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)
    rating_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        rating=UPDATED_RATING_VALUE,
    )

    response = client.get(
        f"{PREFIX}/{photo.id}/ratings",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["rating"] == UPDATED_RATING_VALUE


def test_get_all_photo_ratings_returns_404_for_missing_photo(
    client,
    auth_headers,
) -> None:
    """Reject rating listing when the target photo does not exist."""

    response = client.get(
        f"{PREFIX}/{MISSING_ENTITY_ID}/ratings",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_get_rating_by_id_returns_rating_payload(
    client,
    auth_headers,
    user_factory,
    photo_factory,
    rating_factory,
    seeded_current_user,
) -> None:
    """Return one stored rating by its identifier."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)
    rating = rating_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        rating=UPDATED_RATING_VALUE,
    )

    response = client.get(
        f"{PREFIX}/ratings/{rating.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == rating.id
    assert data["rating"] == UPDATED_RATING_VALUE


def test_get_rating_by_id_returns_404_for_missing_rating(
    client,
    auth_headers,
) -> None:
    """Reject rating lookup when the target rating does not exist."""

    response = client.get(
        f"{PREFIX}/ratings/{MISSING_ENTITY_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_delete_rating_returns_204_for_existing_rating(
    client,
    auth_headers,
    user_factory,
    photo_factory,
    rating_factory,
    seeded_current_user,
) -> None:
    """Delete one stored rating by its identifier."""

    owner = user_factory(role=Role.user)
    photo = photo_factory(owner_id=owner.id)
    rating = rating_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        rating=UPDATED_RATING_VALUE,
    )

    response = client.delete(
        f"{PREFIX}/ratings/{rating.id}",
        headers=auth_headers,
    )

    assert response.status_code == 204, response.text


def test_delete_rating_returns_404_for_missing_rating(
    client,
    auth_headers,
) -> None:
    """Reject rating deletion when the target rating does not exist."""

    response = client.delete(
        f"{PREFIX}/ratings/{MISSING_ENTITY_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )
