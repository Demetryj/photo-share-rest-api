"""Shared fixtures for integration route tests."""

import asyncio
from uuid import uuid4

import pytest

from src.entity.comment import Comment
from src.entity.photo import PhotoTransformation, TransformationType
from src.entity.photo_rating import PhotoRating
from src.entity.user import User
from src.repository import comment as repository_comment
from src.repository import photo as repository_photo
from src.repository import photo_rating as repository_photo_rating
from src.repository import user as repository_user
from src.schemas.comment import CommentRequestSchema
from src.services.auth import auth_service
from tests.conftest import TestingSessionLocal, app, test_user


@pytest.fixture(autouse=True)
def mock_current_user_for_routes():
    """Inject a deterministic authenticated user into every route test.

    These route tests focus on endpoint behavior after authentication has
    already succeeded. We therefore override ``auth_service.get_current_user``
    so tests do not depend on Redis blacklist checks, token/session validation,
    or the full auth flow for each request.
    """

    async def override_get_current_user():
        # Reuse the seeded test user from the shared test database so route
        # handlers still receive a real ORM user object.
        async with TestingSessionLocal() as session:
            return await repository_user.get_user_by_email(
                email=test_user["email"],
                db=session,
            )

    # Replace the FastAPI auth dependency for all tests in this directory.
    app.dependency_overrides[auth_service.get_current_user] = (
        override_get_current_user
    )

    yield

    # Remove the override after each test to avoid leaking mocked auth state.
    app.dependency_overrides.pop(auth_service.get_current_user, None)


@pytest.fixture()
def seeded_current_user():
    """Return the seeded authenticated user from the shared test database."""

    async def _get_user():
        async with TestingSessionLocal() as session:
            return await repository_user.get_user_by_email(
                email=test_user["email"],
                db=session,
            )

    return asyncio.run(_get_user())


@pytest.fixture()
def set_route_current_user():
    """Override the authenticated route user for one test scenario."""

    def _set(current_user: User) -> None:
        async def override_get_current_user() -> User:
            return current_user

        app.dependency_overrides[auth_service.get_current_user] = (
            override_get_current_user
        )

    return _set


@pytest.fixture(scope="module")
def photo_factory():
    """Create persisted photos for integration route tests."""

    async def _create_photo(
        owner_id: int,
        description: str | None = None,
        image_url: str | None = None,
        public_id: str | None = None,
        tags: list[str] | None = None,
    ):
        unique_suffix = uuid4().hex[:8]
        generated_image_url = (
            image_url
            or f"https://example.com/photo_{unique_suffix}.jpg"
        )
        generated_public_id = public_id or f"photo_{unique_suffix}"

        async with TestingSessionLocal() as session:
            tag_records = []
            for tag_name in tags or []:
                tag = await repository_photo.get_or_create_tag(
                    tag=tag_name,
                    db=session,
                )
                tag_records.append(tag)

            return await repository_photo.create_photo(
                user_id=owner_id,
                photo_url=generated_image_url,
                public_id=generated_public_id,
                description=description,
                tags=tag_records,
                db=session,
            )

    return lambda **kwargs: asyncio.run(_create_photo(**kwargs))


@pytest.fixture(scope="module")
def comment_factory():
    """Create persisted comments for integration route tests."""

    async def _create_comment(
        photo_id: int,
        user_id: int,
        content: str,
    ) -> Comment:
        async with TestingSessionLocal() as session:
            return await repository_comment.create_comment_to_photo(
                photo_id=photo_id,
                user_id=user_id,
                body=CommentRequestSchema(content=content),
                db=session,
            )

    return lambda **kwargs: asyncio.run(_create_comment(**kwargs))


@pytest.fixture(scope="module")
def rating_factory():
    """Create persisted ratings for integration route tests."""

    async def _create_rating(
        photo_id: int,
        user_id: int,
        rating: int,
    ) -> PhotoRating:
        async with TestingSessionLocal() as session:
            return await repository_photo_rating.create_photo_rating(
                photo_id=photo_id,
                user_id=user_id,
                rating=rating,
                db=session,
            )

    return lambda **kwargs: asyncio.run(_create_rating(**kwargs))


@pytest.fixture(scope="module")
def transformation_factory():
    """Create persisted photo transformations for integration route tests."""

    async def _create_transformation(
        photo_id: int,
        user_id: int,
        transformation_type: TransformationType,
        transformation_params: dict,
        transformed_url: str | None = None,
        qr_code_url: str | None = None,
    ) -> PhotoTransformation:
        unique_suffix = uuid4().hex[:8]
        generated_transformed_url = (
            transformed_url
            or f"https://example.com/transformed_{unique_suffix}.jpg"
        )

        async with TestingSessionLocal() as session:
            return await repository_photo.create_photo_transformation(
                photo_id=photo_id,
                user_id=user_id,
                transformation_type=transformation_type,
                transformation_params=transformation_params,
                transformed_url=generated_transformed_url,
                qr_code_url=qr_code_url,
                db=session,
            )

    return lambda **kwargs: asyncio.run(
        _create_transformation(**kwargs)
    )
