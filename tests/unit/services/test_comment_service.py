"""Unit tests for comment service helpers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.entity.comment import Comment
from src.entity.photo import Photo
from src.entity.user import User
from src.services import comment as comment_service


def test_build_comment_response_returns_serialized_comment() -> None:
    """Return a response schema with embedded public author data."""

    author = User(id=7, username="comment_author")
    comment = Comment(
        id=3,
        content="Nice photo",
        photo_id=11,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    result = comment_service.build_comment_response(
        comment=comment,
        user=author,
    )

    assert result.id == comment.id
    assert result.content == comment.content
    assert result.photo_id == comment.photo_id
    assert result.user.id == author.id
    assert result.user.username == author.username


@pytest.mark.asyncio
async def test_get_photo_or_404_returns_photo_when_it_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return the requested photo when the repository finds it."""

    db = AsyncMock(spec=AsyncSession)
    photo = Photo(
        id=5,
        owner_id=1,
        image_url="https://example.com/p.jpg",
        public_id="photo_5",
    )
    repository_mock = AsyncMock(return_value=photo)
    monkeypatch.setattr(
        "src.services.comment.repository_photo.get_photo_by_id",
        repository_mock,
    )

    result = await comment_service.get_photo_or_404(photo_id=5, db=db)

    repository_mock.assert_awaited_once_with(photo_id=5, db=db)
    assert result is photo


@pytest.mark.asyncio
async def test_get_photo_or_404_raises_404_when_photo_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise 404 when the target photo does not exist."""

    db = AsyncMock(spec=AsyncSession)
    repository_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.services.comment.repository_photo.get_photo_by_id",
        repository_mock,
    )

    with pytest.raises(HTTPException) as exc_info:
        await comment_service.get_photo_or_404(photo_id=99, db=db)

    repository_mock.assert_awaited_once_with(photo_id=99, db=db)
    assert exc_info.value.status_code == 404
