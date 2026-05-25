import asyncio
import logging
import os
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import Request, Response
from fastapi.testclient import TestClient
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Tell application settings that pytest is running before importing main.
# Route modules create limiter objects at import time, so this must happen first.
os.environ["TESTING"] = "True"

from main import app
from src.database.db import get_db
from src.entity.models import Base
from src.entity.user import Role, User
from src.services.auth import auth_service

logger = logging.getLogger()

# Store the test database next to this conftest.py file so its location does
# not depend on the directory from which pytest is started.
BASE_DIR = Path(__file__).resolve().parent
SQLALCHEMY_DATABASE_URL = (
    f"sqlite+aiosqlite:///{BASE_DIR / 'test.db'}"
)

# Async SQLite engine used only by tests.
# StaticPool keeps the same connection available during the test session.
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Factory for SQLAlchemy async sessions that will be injected into FastAPI.
TestingSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)

# Default user created before tests run. Tests can use it for login/token checks.
test_user = {
    "username": "test_user",
    "email": "test_user@mail.com",
    "password": "1234567890",
}


@pytest.fixture(autouse=True)
def disable_rate_limiter(monkeypatch):
    """Disable FastAPI rate limiting in endpoint tests."""

    async def mock_rate_limiter_call(
        self,
        request: Request,
        response: Response,
    ) -> None:
        return None

    monkeypatch.setattr(
        RateLimiter, "__call__", mock_rate_limiter_call
    )


@pytest.fixture(scope="module", autouse=True)
def init_models_wrap():
    """Recreate the test schema and seed one confirmed admin user."""

    # Recreate all tables and insert a confirmed admin user once per test module.
    async def init_models():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        async with TestingSessionLocal() as session:
            hash_password = auth_service.create_hashed_password(
                test_user["password"]
            )
            current_user = User(
                username=test_user["username"],
                email=test_user["email"],
                password=hash_password,
                confirmed=True,
                role=Role.admin,
            )
            session.add(current_user)
            await session.commit()

    asyncio.run(init_models())


@pytest.fixture(scope="module")
def client():
    # Replace the real application database dependency with the test session.
    async def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        except Exception as err:
            logger.error(err)
            await session.rollback()
            raise
        finally:
            await session.close()

    app.dependency_overrides[get_db] = override_get_db

    yield TestClient(app)

    # Remove test overrides so they do not leak into other test modules.
    app.dependency_overrides.clear()


@pytest.fixture()
def access_token_with_jti() -> tuple[str, str]:
    """Return an access token and its JTI for the default test user."""

    token, jti = auth_service.create_access_token(
        payload={"sub": test_user["email"]}
    )
    return token, jti


@pytest.fixture()
def auth_headers(
    access_token_with_jti: tuple[str, str],
) -> dict[str, str]:
    """Build Authorization headers for authenticated API requests."""

    token, _ = access_token_with_jti
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture()
async def db_session():
    """Yield one async database session for direct repository tests."""

    async with TestingSessionLocal() as session:
        try:
            yield session
        except Exception as err:
            logger.error(err)
            await session.rollback()
            raise


@pytest.fixture()
def user_factory(db_session):
    """Return an async factory that creates and persists test users."""

    # Keep generated usernames and emails unique to avoid uniqueness conflicts
    # when multiple users are created within the same test module.
    counter = 0

    async def _create_user(
        username: str | None = None,
        email: str | None = None,
        password: str = "Qwerty123!",
        role: Role = Role.user,
        confirmed: bool = True,
        blocked: bool = False,
    ) -> User:
        nonlocal counter
        counter += 1

        generated_username = username or f"user_{counter}"
        generated_email = email or f"user_{counter}@mail.com"

        user = User(
            username=generated_username,
            email=generated_email,
            password=auth_service.create_hashed_password(password),
            role=role,
            confirmed=confirmed,
            blocked=blocked,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    return _create_user


# unit/
#     services/
#       test_role_service.py
#     helpers/
#       test_create_exception.py
#   integration/
#     repositories/
#     routes/


#  Найкраще тримати назву тесту в стилі:

# test_<що_тестуємо>_<яка_умова>_<який_результат>

# Або коротший варіант:

# test_<що_робить>_<очікуваний_результат>

# Для твого проєкту підійдуть такі шаблони.

# Для auth_service:

# test_create_hashed_password_returns_hashed_value
# test_verify_password_returns_true_for_valid_password
# test_verify_password_returns_false_for_invalid_password
# test_create_access_token_returns_token_and_jti
# test_create_refresh_token_returns_token
# test_get_token_hash_returns_sha256_hash
# test_get_token_jti_returns_jti_for_valid_token
# test_get_token_exp_returns_exp_for_valid_token
# test_get_email_from_email_token_returns_email
# test_get_email_from_password_reset_token_raises_for_invalid_scope
# Для user_service:

# test_validate_display_name_value_returns_normalized_value
# test_validate_display_name_value_raises_for_empty_string
# test_validate_display_name_value_raises_for_invalid_characters
# test_validate_admin_user_management_action_raises_for_self_update
# test_validate_admin_user_management_action_raises_for_admin_target
# Для photo_service:

# test_normalize_image_tags_returns_normalized_unique_tags
# test_normalize_image_tags_raises_when_tags_exceed_limit
# test_normalize_image_tags_raises_for_duplicate_tags
# test_resolve_photo_owner_id_returns_current_user_id
# test_resolve_photo_owner_id_raises_for_non_admin_target_user
# test_build_transformation_params_returns_resize_params
# test_build_transformation_params_raises_when_resize_params_missing
# Для repository:

# test_create_user_creates_admin_when_first_user
# test_create_user_creates_regular_user_when_users_exist
# test_get_user_by_email_returns_user
# test_update_user_password_updates_hash
# test_create_photo_rating_creates_rating
# test_get_photo_by_id_returns_photo_with_tags
# Для routes:

# test_signup_returns_201_for_valid_payload
# test_signup_returns_409_when_email_exists
# test_signin_returns_access_token_for_valid_credentials
# test_signin_returns_401_for_invalid_password
# test_get_current_user_info_returns_200_for_authenticated_user
# test_get_current_user_info_returns_401_without_token
# test_upload_photo_returns_200_for_valid_file
# test_upload_photo_returns_403_for_forbidden_target_user
# Що важливо:

# назва має одразу показувати сценарій;
# не роби занадто загальні назви типу test_auth або test_user_service;
# краще довша, але зрозуміла назва, ніж коротка й розмита.
