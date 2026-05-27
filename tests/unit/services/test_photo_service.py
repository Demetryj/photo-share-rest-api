"""Unit tests for photo service helpers."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.photo import BlurMode, Photo, Tag, TransformationType
from src.entity.user import Role, User
from src.schemas.photo import PhotoTransformationRequestSchema
from src.services import photo as photo_service


def test_normalize_image_tags_returns_normalized_unique_tags() -> (
    None
):
    """Normalize tags by trimming, lowering, and removing empty values."""

    result = photo_service.normalize_image_tags(
        [" Nature ", "CITY", "", "porTrait "]
    )

    assert result == ["nature", "city", "portrait"]


def test_normalize_image_tags_raises_when_tags_exceed_limit() -> None:
    """Raise ValueError when more than the allowed number of tags is provided."""

    with pytest.raises(ValueError):
        photo_service.normalize_image_tags(
            ["a", "b", "c", "d", "e", "f"]
        )


def test_normalize_image_tags_raises_for_duplicate_tags() -> None:
    """Raise ValueError when normalized tags are not unique."""

    with pytest.raises(ValueError):
        photo_service.normalize_image_tags(["Nature", "nature"])


@pytest.mark.asyncio
async def test_prepare_photo_tags_returns_resolved_tags_and_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve normalized tags and return both ORM tags and response schemas."""

    db = AsyncMock(spec=AsyncSession)

    async def fake_get_or_create_tag(
        tag: str, db: AsyncSession
    ) -> Tag:
        return Tag(id=len(tag), name=tag)

    monkeypatch.setattr(
        "src.services.photo.repository_photo.get_or_create_tag",
        fake_get_or_create_tag,
    )

    tag_list, tags_for_resp = await photo_service.prepare_photo_tags(
        tags=[" Nature ", "CITY"],
        db=db,
    )

    assert [tag.name for tag in tag_list] == ["nature", "city"]
    assert [tag.id for tag in tags_for_resp] == [6, 4]
    assert [tag.name for tag in tags_for_resp] == ["nature", "city"]


@pytest.mark.asyncio
async def test_resolve_photo_owner_id_returns_current_user_id_by_default() -> (
    None
):
    """Return the current user's id when no target user id is provided."""

    current_user = User(id=10, role=Role.user)

    owner_id = await photo_service.resolve_photo_owner_id(
        current_user=current_user,
        db=AsyncMock(spec=AsyncSession),
    )

    assert owner_id == current_user.id


@pytest.mark.asyncio
async def test_resolve_photo_owner_id_raises_403_for_non_admin_target_user() -> (
    None
):
    """Raise 403 when a non-admin tries to upload a photo for another user."""

    current_user = User(id=10, role=Role.user)

    with pytest.raises(HTTPException) as exc_info:
        await photo_service.resolve_photo_owner_id(
            current_user=current_user,
            db=AsyncMock(spec=AsyncSession),
            target_user_id=77,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_resolve_photo_owner_id_raises_404_when_target_user_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 404 when the admin-selected target user does not exist."""

    current_user = User(id=1, role=Role.admin)
    repository_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.services.photo.repository_user.get_user_by_id",
        repository_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await photo_service.resolve_photo_owner_id(
            current_user=current_user,
            db=AsyncMock(spec=AsyncSession),
            target_user_id=22,
        )

    assert exc_info.value.status_code == 404


def test_build_transformation_params_returns_resize_params() -> None:
    """Build normalized parameters for a resize transformation."""

    body = PhotoTransformationRequestSchema(
        transformation_type=TransformationType.resize,
        width=800,
        height=600,
    )

    result = photo_service.build_transformation_params(body)

    assert result == {"width": 800, "height": 600}


def test_build_transformation_params_returns_blur_params() -> None:
    """Build normalized parameters for a blur transformation."""

    body = PhotoTransformationRequestSchema(
        transformation_type=TransformationType.blur,
        blur_mode=BlurMode.box,
        blur_radius=3,
    )

    result = photo_service.build_transformation_params(body)

    assert result == {
        "blur_mode": BlurMode.box,
        "blur_radius": 3,
    }


def test_build_transformation_params_raises_when_resize_params_missing() -> (
    None
):
    """Raise 400 when resize is requested without both dimensions."""

    body = PhotoTransformationRequestSchema(
        transformation_type=TransformationType.resize,
        width=800,
    )

    with pytest.raises(HTTPException) as exc_info:
        photo_service.build_transformation_params(body)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_download_original_photo_raises_502_for_http_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 502 when the original image cannot be downloaded."""

    photo = Photo(
        id=2,
        owner_id=1,
        image_url="https://example.com/photo.jpg",
        public_id="photo_2",
    )

    class FailingAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            raise photo_service.httpx.RequestError(
                "network failure",
                request=photo_service.httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "src.services.photo.httpx.AsyncClient",
        lambda timeout: FailingAsyncClient(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await photo_service.download_original_photo(photo)

    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_build_preview_response_raises_422_for_invalid_image_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 422 when the downloaded original bytes are not a valid image."""

    photo = Photo(
        id=4,
        owner_id=1,
        image_url="https://example.com/photo.jpg",
        public_id="photo_4",
    )
    monkeypatch.setattr(
        "src.services.photo.download_original_photo",
        AsyncMock(return_value=b"not-an-image"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await photo_service.build_preview_response(
            photo=photo,
            transformation_type=TransformationType.grayscale,
            params={},
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_build_preview_response_returns_streaming_response_for_valid_image_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return a JPEG streaming response when preview generation succeeds."""

    photo = Photo(
        id=8,
        owner_id=1,
        image_url="https://example.com/photo.jpg",
        public_id="photo_8",
    )
    valid_image_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc`\xf8\xcf\x00\x00\x02\x02\x01"
        b"\x00{\t\x81x\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    monkeypatch.setattr(
        "src.services.photo.download_original_photo",
        AsyncMock(return_value=valid_image_bytes),
    )

    result = await photo_service.build_preview_response(
        photo=photo,
        transformation_type=TransformationType.grayscale,
        params={},
    )

    assert isinstance(result, StreamingResponse)
    assert result.media_type == photo_service.PREVIEW_MEDIA_TYPE
