"""Unit tests for photo rating repository helpers."""

from unittest.mock import AsyncMock

import pytest

from src.entity.photo_rating import PhotoRating
from src.repository import photo_rating as photo_rating_repository


@pytest.mark.asyncio
async def test_get_photo_rating_by_photo_id_and_user_id_returns_scalar_result(
    db_session_mock: AsyncMock,
    scalar_result_factory,
) -> None:
    """Return the rating resolved by scalar_one_or_none()."""

    rating = PhotoRating(photo_id=1, user_id=2, rating=5)
    db_session_mock.execute.return_value = scalar_result_factory(
        rating
    )

    result = await photo_rating_repository.get_photo_rating_by_photo_id_and_user_id(
        photo_id=1,
        user_id=2,
        db=db_session_mock,
    )

    assert result is rating


@pytest.mark.asyncio
async def test_create_photo_rating_adds_and_persists_record(
    db_session_mock: AsyncMock,
) -> None:
    """Create a new rating record and persist it."""

    result = await photo_rating_repository.create_photo_rating(
        photo_id=1,
        user_id=2,
        rating=4,
        db=db_session_mock,
    )

    assert isinstance(result, PhotoRating)
    assert result.photo_id == 1
    assert result.user_id == 2
    assert result.rating == 4
    db_session_mock.add.assert_called_once_with(result)
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_get_all_photo_ratings_returns_scalars_all(
    db_session_mock: AsyncMock,
    scalars_result_factory,
) -> None:
    """Return all ratings from scalars().all()."""

    ratings = [
        PhotoRating(photo_id=1, user_id=2, rating=4),
        PhotoRating(photo_id=1, user_id=3, rating=5),
    ]
    db_session_mock.execute.return_value = scalars_result_factory(
        ratings
    )

    result = await photo_rating_repository.get_all_photo_ratings(
        photo_id=1,
        limit=10,
        offset=0,
        db=db_session_mock,
    )

    assert result == ratings


@pytest.mark.asyncio
async def test_get_total_number_of_ratings_on_photo_returns_scalar_count(
    db_session_mock: AsyncMock,
) -> None:
    """Return the count resolved through db.scalar()."""

    db_session_mock.scalar.return_value = 3

    result = await photo_rating_repository.get_total_number_of_ratings_on_photo(
        photo_id=1,
        db=db_session_mock,
    )

    assert result == 3


@pytest.mark.asyncio
async def test_delete_rating_returns_true_when_row_deleted(
    db_session_mock: AsyncMock,
    delete_result_factory,
) -> None:
    """Return True when the delete query affects one row."""

    db_session_mock.execute.return_value = delete_result_factory(1)

    result = await photo_rating_repository.delete_rating(
        rating_id=7,
        db=db_session_mock,
    )

    assert result is True
    db_session_mock.commit.assert_awaited_once()
