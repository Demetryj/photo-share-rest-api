"""Unit tests for comment repository helpers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.entity.comment import Comment
from src.repository import comment as comment_repository
from src.schemas.comment import CommentRequestSchema


@pytest.mark.asyncio
async def test_get_total_number_of_comments_on_photo_returns_scalar_count(
    db_session_mock: AsyncMock,
) -> None:
    """Return the total count resolved through db.scalar()."""

    db_session_mock.scalar.return_value = 7

    result = await comment_repository.get_total_number_of_comments_on_photo(
        photo_id=3,
        db=db_session_mock,
    )

    assert result == 7


@pytest.mark.asyncio
async def test_create_comment_to_photo_adds_and_persists_comment(
    db_session_mock: AsyncMock,
) -> None:
    """Create a comment entity and persist it."""

    body = CommentRequestSchema(content="Great shot")

    result = await comment_repository.create_comment_to_photo(
        photo_id=5,
        user_id=9,
        body=body,
        db=db_session_mock,
    )

    assert isinstance(result, Comment)
    assert result.content == "Great shot"
    assert result.photo_id == 5
    assert result.user_id == 9
    db_session_mock.add.assert_called_once_with(result)
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(result)


@pytest.mark.asyncio
async def test_get_all_comments_by_photo_id_returns_scalars_all(
    db_session_mock: AsyncMock,
    scalars_result_factory,
) -> None:
    """Return the list of comments from scalars().all()."""

    comments = [
        Comment(
            id=1, content="one", created_at=datetime.now(timezone.utc)
        ),
        Comment(
            id=2, content="two", created_at=datetime.now(timezone.utc)
        ),
    ]
    db_session_mock.execute.return_value = scalars_result_factory(
        comments
    )

    result = await comment_repository.get_all_comments_by_photo_id(
        photo_id=5,
        limit=10,
        offset=0,
        db=db_session_mock,
    )

    assert result == comments


@pytest.mark.asyncio
async def test_update_photo_comment_returns_none_when_comment_missing(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return None without commit when the comment cannot be found."""

    monkeypatch.setattr(
        "src.repository.comment.get_comment_by_id",
        AsyncMock(return_value=None),
    )

    result = await comment_repository.update_photo_comment(
        comment_id=1,
        user_id=2,
        photo_id=3,
        new_content="updated",
        db=db_session_mock,
    )

    assert result is None
    db_session_mock.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_photo_comment_updates_content_when_comment_exists(
    db_session_mock: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist the new content for the existing comment."""

    comment = Comment(id=1, content="old", photo_id=3, user_id=2)
    monkeypatch.setattr(
        "src.repository.comment.get_comment_by_id",
        AsyncMock(return_value=comment),
    )

    result = await comment_repository.update_photo_comment(
        comment_id=1,
        user_id=2,
        photo_id=3,
        new_content="updated",
        db=db_session_mock,
    )

    assert result is comment
    assert comment.content == "updated"
    db_session_mock.commit.assert_awaited_once()
    db_session_mock.refresh.assert_awaited_once_with(comment)


@pytest.mark.asyncio
async def test_delete_photo_comment_deletes_found_comment(
    db_session_mock: AsyncMock,
    scalar_result_factory,
) -> None:
    """Delete the located comment and return it."""

    comment = Comment(id=4, photo_id=9, user_id=2, content="remove")
    db_session_mock.execute.return_value = scalar_result_factory(
        comment
    )

    result = await comment_repository.delete_photo_comment(
        comment_id=4,
        photo_id=9,
        db=db_session_mock,
    )

    assert result is comment
    db_session_mock.delete.assert_awaited_once_with(comment)
    db_session_mock.commit.assert_awaited_once()
