"""Centralized rate limiter definitions for API routes."""

from pyrate_limiter import (
    Duration,
    InMemoryBucket,
    Limiter,
    Rate,
    RedisBucket,
)

from src.config.settings import settings
from src.services.redis_client import get_sync_redis_client


def make_limiter(rate: Rate, bucket: str) -> Limiter:
    """Create a rate limiter for the current runtime."""

    if settings.testing:
        # Tests import routes before fixtures run. Use an in-memory bucket here
        # so importing the app does not require a Redis connection.
        return Limiter(InMemoryBucket([rate]))

    redis_bucket = RedisBucket.init(
        [rate], get_sync_redis_client(), bucket
    )
    return Limiter(redis_bucket)


# AUTH
# base (to the entire route /auth)
auth_base_limiter = make_limiter(
    Rate(20, Duration.MINUTE), "auth_base"
)

# stricter per route
auth_signup_limiter = make_limiter(
    Rate(5, Duration.MINUTE), "auth_signup"
)
auth_refresh_token_limiter = make_limiter(
    Rate(5, Duration.MINUTE), "auth_refresh_token"
)
auth_confirm_email_limiter = make_limiter(
    Rate(5, Duration.MINUTE), "auth_confirm_email"
)
auth_request_email_limiter = make_limiter(
    Rate(1, Duration.MINUTE * 3), "auth_request_email"
)
auth_reset_password_limiter = make_limiter(
    Rate(1, Duration.MINUTE * 60 * 12), "auth_reset_password"
)

# USER
# users routes - base
user_base_limiter = make_limiter(
    Rate(20, Duration.MINUTE), "user_base"
)

# stricter per route
user_update_profile_limiter = make_limiter(
    Rate(1, Duration.SECOND * 60), "user_update_profile"
)

# PHOTO
# photo routes - base
photo_base_limiter = make_limiter(
    Rate(20, Duration.MINUTE), "photo_base"
)

# stricter per route
photo_upload_limiter = make_limiter(
    Rate(5, Duration.MINUTE), "photo_upload"
)
photo_generate_preview_limiter = make_limiter(
    Rate(5, Duration.MINUTE), "photo_generate_preview"
)
photo_transformation_limiter = make_limiter(
    Rate(5, Duration.MINUTE), "photo_transformation"
)

# COMMENT
# comment routes - base
comment_base_limiter = make_limiter(
    Rate(20, Duration.MINUTE), "comment_base"
)

# PHOTO RATING
# photo rating routes - base
photo_rating_base_limiter = make_limiter(
    Rate(20, Duration.MINUTE), "photo_rating_base"
)
