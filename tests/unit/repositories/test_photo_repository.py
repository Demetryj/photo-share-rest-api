"""Unit tests for photo repository helpers."""

from unittest.mock import AsyncMock

import pytest

from src.entity.models import SortBy
from src.entity.photo import (
    Photo,
    PhotoTransformation,
    SortField,
    Tag,
    TransformationType,
)
from src.repository import photo as photo_repository


@pytest.mark.asyncio
async def test_create_photo_adds_and_persists_record(
    db_session_mock: AsyncMock,
) -> None:
    """Create a photo entity and persist it."""

    tags = [Tag(name="nature")]

    result = await photo_repository.create_photo(
        user_id=4,
        photo_url="https://cdn.example.com/photo.jpg",
        public_id="photo_4",
        description="landscape",
        tags=tags,
        db=db_session_mock,
    )

    assert isinstance(result, Photo)
    assert result.owner_id == 4
    assert result.image_url == "https://cdn.example.com/photo.jpg"
    assert result.tags == tags
    db_session_mock.add.assert_called_once_with(result)
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_get_photos_by_user_id_returns_scalars_all(
    db_session_mock: AsyncMock,
    scalars_result_factory,
) -> None:
    """Return the paginated photos from scalars().all()."""

    photos = [Photo(id=1), Photo(id=2)]
    db_session_mock.execute.return_value = scalars_result_factory(
        photos
    )

    result = await photo_repository.get_photos_by_user_id(
        user_id=5,
        limit=10,
        offset=0,
        db=db_session_mock,
    )

    assert result == photos


def test_build_filtered_photos_stmt_uses_tag_search_for_hash_query() -> (
    None
):
    """Build a statement that filters by tag name for #tag queries."""

    stmt, avg_rating = photo_repository._build_filtered_photos_stmt(
        query="#nature",
    )

    compiled = str(stmt)
    assert "tags.name" in compiled
    assert "lower(tags.name) LIKE lower" in compiled
    assert avg_rating.key == "avg_rating"


@pytest.mark.asyncio
async def test_get_filtered_photos_by_keyword_or_tag_returns_rows(
    db_session_mock: AsyncMock,
    rows_result_factory,
) -> None:
    """Return the row tuples produced by result.all()."""

    photo = Photo(id=1)
    db_session_mock.execute.return_value = rows_result_factory(
        [(photo, 4.5)]
    )

    result = (
        await photo_repository.get_filtered_photos_by_keyword_or_tag(
            db=db_session_mock,
            limit=10,
            offset=0,
            query="mountain",
            sort_field=SortField.rating,
            sort_by=SortBy.desc,
        )
    )

    assert result == [(photo, 4.5)]


@pytest.mark.asyncio
async def test_get_or_create_tag_returns_existing_tag_when_found(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return the existing tag without creating a new one."""

    tag = Tag(id=1, name="nature")
    monkeypatch.setattr(
        "src.repository.photo.get_tag_by_name",
        AsyncMock(return_value=tag),
    )

    result = await photo_repository.get_or_create_tag(
        tag="nature",
        db=db_session_mock,
    )

    assert result is tag
    db_session_mock.add.assert_not_called()
    db_session_mock.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_tag_creates_new_tag_when_missing(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create and flush a new tag when no existing tag is found."""

    monkeypatch.setattr(
        "src.repository.photo.get_tag_by_name",
        AsyncMock(return_value=None),
    )

    result = await photo_repository.get_or_create_tag(
        tag="city",
        db=db_session_mock,
    )

    assert isinstance(result, Tag)
    assert result.name == "city"
    db_session_mock.add.assert_called_once_with(result)
    db_session_mock.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_photo_description_persists_new_value(
    db_session_mock: AsyncMock,
) -> None:
    """Update the in-memory photo description and persist it."""

    photo = Photo(id=3, description="old")

    result = await photo_repository.update_photo_description(
        photo=photo,
        description="new",
        db=db_session_mock,
    )

    assert result is photo
    assert photo.description == "new"
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(photo)


@pytest.mark.asyncio
async def test_create_photo_transformation_adds_and_persists_record(
    db_session_mock: AsyncMock,
) -> None:
    """Create a transformation entity and persist it."""

    result = await photo_repository.create_photo_transformation(
        photo_id=1,
        user_id=2,
        transformation_type=TransformationType.grayscale,
        transformation_params={},
        transformed_url="https://cdn.example.com/transformed.jpg",
        qr_code_url="https://cdn.example.com/qr.png",
        db=db_session_mock,
    )

    assert isinstance(result, PhotoTransformation)
    assert result.photo_id == 1
    assert result.user_id == 2
    db_session_mock.add.assert_called_once_with(result)
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_get_photo_average_rating_returns_zero_for_none_scalar(
    db_session_mock: AsyncMock,
) -> None:
    """Return zero when the aggregate query resolves to None."""

    db_session_mock.scalar.return_value = None

    result = await photo_repository.get_photo_average_rating(
        photo_id=7,
        db=db_session_mock,
    )

    assert result == 0.0
