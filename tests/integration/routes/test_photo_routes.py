"""Integration tests for photo routes."""

from io import BytesIO
from unittest.mock import AsyncMock

from fastapi.responses import StreamingResponse

from src.config.messages import HTTPStatusMessages
from src.entity.models import SortBy
from src.entity.photo import SortField, TransformationType
from src.entity.user import Role
from src.services import photo as photo_service

PREFIX = "/api/photos"
PHOTO_DESCRIPTION = "Sunset over the lake"
UPDATED_DESCRIPTION = "Updated sunset description"
PHOTO_URL = "https://example.com/photo.jpg"
TRANSFORMED_URL = "https://example.com/transformed.jpg"
QR_CODE_URL = "https://example.com/qr.png"
PREVIEW_MEDIA_TYPE = "image/jpeg"
PHOTO_TAGS = ["nature", "sunset"]
MISSING_ENTITY_ID = 999999


def test_upload_photo_returns_created_photo(
    client, auth_headers, monkeypatch
) -> None:
    """Upload a photo and return its stored metadata."""

    monkeypatch.setattr(
        photo_service,
        "validate_image_file",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        photo_service,
        "cloudinary_upload",
        AsyncMock(return_value=PHOTO_URL),
    )

    files = {
        "file": (
            "photo.png",
            b"fake image content",
            "image/png",
        )
    }

    response = client.post(
        f"{PREFIX}/",
        headers=auth_headers,
        files=files,
        data={"description": PHOTO_DESCRIPTION},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["description"] == PHOTO_DESCRIPTION
    assert data["image_url"] == PHOTO_URL


def test_get_photo_by_id_returns_photo_payload(
    client, auth_headers, seeded_current_user, photo_factory
) -> None:
    """Return one stored photo by its identifier."""

    photo = photo_factory(
        owner_id=seeded_current_user.id,
        description=PHOTO_DESCRIPTION,
    )

    response = client.get(
        f"{PREFIX}/{photo.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == photo.id
    assert data["description"] == PHOTO_DESCRIPTION


def test_get_photo_by_id_returns_404_for_missing_photo(
    client, auth_headers
) -> None:
    """Reject photo lookup when the target photo does not exist."""

    response = client.get(
        f"{PREFIX}/{MISSING_ENTITY_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_get_all_photos_by_user_id_returns_paginated_list(
    client, auth_headers, user_factory, photo_factory
) -> None:
    """Return paginated photos for the specified user."""

    owner = user_factory(role=Role.user)
    photo_factory(
        owner_id=owner.id,
        description=PHOTO_DESCRIPTION,
    )

    response = client.get(
        f"{PREFIX}/user/{owner.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["page"] == 1
    assert data["per_page"] == 10
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


def test_get_all_photos_by_user_id_returns_404_for_missing_user(
    client, auth_headers
) -> None:
    """Reject user photo listing when the target user does not exist."""

    response = client.get(
        f"{PREFIX}/user/{MISSING_ENTITY_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_get_filtered_photos_returns_matching_results(
    client, auth_headers, seeded_current_user, photo_factory
) -> None:
    """Return photos whose description matches the search query."""

    photo_factory(
        owner_id=seeded_current_user.id,
        description=PHOTO_DESCRIPTION,
    )

    response = client.get(
        f"{PREFIX}/?query=Sunset&sort_field={SortField.date.value}&sort_by={SortBy.desc.value}",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["page"] == 1
    assert len(data["items"]) >= 1


def test_delete_photo_returns_204_for_existing_photo(
    client,
    auth_headers,
    seeded_current_user,
    photo_factory,
    monkeypatch,
) -> None:
    """Delete a photo after Cloudinary cleanup succeeds."""

    photo = photo_factory(owner_id=seeded_current_user.id)
    monkeypatch.setattr(
        photo_service,
        "cloudinary_delete",
        AsyncMock(return_value=None),
    )

    response = client.delete(
        f"{PREFIX}/{photo.id}",
        headers=auth_headers,
    )

    assert response.status_code == 204, response.text


def test_delete_photo_returns_404_for_missing_photo(
    client,
    auth_headers,
) -> None:
    """Reject photo deletion when the target photo does not exist."""

    response = client.delete(
        f"{PREFIX}/{MISSING_ENTITY_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_update_photo_description_returns_updated_photo(
    client, auth_headers, seeded_current_user, photo_factory
) -> None:
    """Update the description of an existing photo."""

    photo = photo_factory(
        owner_id=seeded_current_user.id,
        description=PHOTO_DESCRIPTION,
    )

    response = client.put(
        f"{PREFIX}/{photo.id}/description",
        headers=auth_headers,
        json={"description": UPDATED_DESCRIPTION},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == photo.id
    assert data["description"] == UPDATED_DESCRIPTION


def test_update_photo_description_returns_404_for_missing_photo(
    client, auth_headers
) -> None:
    """Reject description update when the target photo does not exist."""

    response = client.put(
        f"{PREFIX}/{MISSING_ENTITY_ID}/description",
        headers=auth_headers,
        json={"description": UPDATED_DESCRIPTION},
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_add_photo_tags_returns_photo_with_updated_tags(
    client, auth_headers, seeded_current_user, photo_factory
) -> None:
    """Replace the tags of an existing photo and return the updated payload."""

    photo = photo_factory(owner_id=seeded_current_user.id)

    response = client.patch(
        f"{PREFIX}/{photo.id}/tags",
        headers=auth_headers,
        json={"tags": PHOTO_TAGS},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert [tag["name"] for tag in data["tags"]] == PHOTO_TAGS


def test_add_photo_tags_returns_404_for_missing_photo(
    client, auth_headers
) -> None:
    """Reject tag replacement when the target photo does not exist."""

    response = client.patch(
        f"{PREFIX}/{MISSING_ENTITY_ID}/tags",
        headers=auth_headers,
        json={"tags": PHOTO_TAGS},
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_preview_photo_transformation_returns_streaming_preview(
    client,
    auth_headers,
    seeded_current_user,
    photo_factory,
    monkeypatch,
) -> None:
    """Generate a temporary transformation preview for an existing photo."""

    photo = photo_factory(owner_id=seeded_current_user.id)
    preview_response = StreamingResponse(
        BytesIO(b"preview-bytes"),
        media_type=PREVIEW_MEDIA_TYPE,
    )
    monkeypatch.setattr(
        photo_service,
        "build_preview_response",
        AsyncMock(return_value=preview_response),
    )

    response = client.post(
        f"{PREFIX}/{photo.id}/transform-preview",
        headers=auth_headers,
        json={
            "transformation_type": TransformationType.resize.value,
            "width": 100,
            "height": 100,
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == PREVIEW_MEDIA_TYPE


def test_preview_photo_transformation_returns_404_for_missing_photo(
    client,
    auth_headers,
) -> None:
    """Reject preview generation when the target photo does not exist."""

    response = client.post(
        f"{PREFIX}/{MISSING_ENTITY_ID}/transform-preview",
        headers=auth_headers,
        json={
            "transformation_type": TransformationType.resize.value,
            "width": 100,
            "height": 100,
        },
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_create_photo_transformation_returns_created_record(
    client,
    auth_headers,
    seeded_current_user,
    photo_factory,
    monkeypatch,
) -> None:
    """Create and persist a transformed photo record for an existing photo."""

    photo = photo_factory(owner_id=seeded_current_user.id)
    monkeypatch.setattr(
        photo_service,
        "build_transformed_photo_url",
        lambda *args, **kwargs: TRANSFORMED_URL,
    )
    monkeypatch.setattr(
        photo_service,
        "generate_qr_code_url",
        AsyncMock(return_value=QR_CODE_URL),
    )

    response = client.post(
        f"{PREFIX}/{photo.id}/transformations",
        headers=auth_headers,
        json={
            "transformation_type": TransformationType.resize.value,
            "width": 100,
            "height": 100,
        },
    )

    assert response.status_code == 201, response.text
    data = response.json()

    assert data["photo_id"] == photo.id
    assert data["transformed_url"] == TRANSFORMED_URL
    assert data["qr_code_url"] == QR_CODE_URL


def test_create_photo_transformation_returns_404_for_missing_photo(
    client,
    auth_headers,
) -> None:
    """Reject transformation creation when the target photo does not exist."""

    response = client.post(
        f"{PREFIX}/{MISSING_ENTITY_ID}/transformations",
        headers=auth_headers,
        json={
            "transformation_type": TransformationType.resize.value,
            "width": 100,
            "height": 100,
        },
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_get_all_photo_transformations_returns_saved_records(
    client,
    auth_headers,
    seeded_current_user,
    photo_factory,
    transformation_factory,
) -> None:
    """Return all saved transformations for an existing photo."""

    photo = photo_factory(owner_id=seeded_current_user.id)
    transformation_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        transformation_type=TransformationType.resize,
        transformation_params={"width": 100, "height": 100},
        qr_code_url=QR_CODE_URL,
    )

    response = client.get(
        f"{PREFIX}/{photo.id}/transformations",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert len(data) >= 1
    assert data[0]["photo_id"] == photo.id


def test_get_all_photo_transformations_returns_404_for_missing_photo(
    client,
    auth_headers,
) -> None:
    """Reject transformation listing when the target photo does not exist."""

    response = client.get(
        f"{PREFIX}/{MISSING_ENTITY_ID}/transformations",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )


def test_get_photo_transformation_by_id_returns_saved_record(
    client,
    auth_headers,
    seeded_current_user,
    photo_factory,
    transformation_factory,
) -> None:
    """Return one saved transformation by its identifier."""

    photo = photo_factory(owner_id=seeded_current_user.id)
    transformation = transformation_factory(
        photo_id=photo.id,
        user_id=seeded_current_user.id,
        transformation_type=TransformationType.resize,
        transformation_params={"width": 100, "height": 100},
        qr_code_url=QR_CODE_URL,
    )

    response = client.get(
        f"{PREFIX}/transformations/{transformation.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["id"] == transformation.id
    assert data["photo_id"] == photo.id


def test_get_photo_transformation_by_id_returns_404_for_missing_record(
    client,
    auth_headers,
) -> None:
    """Reject transformation lookup when the target record does not exist."""

    response = client.get(
        f"{PREFIX}/transformations/{MISSING_ENTITY_ID}",
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert (
        response.json()["detail"]
        == HTTPStatusMessages.not_found.value
    )
