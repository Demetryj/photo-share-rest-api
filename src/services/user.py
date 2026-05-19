"""Service helpers for user profile and account-related data aggregation."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from src.config.messages import UserValidationMessages
from src.repository import comment as repository_comment
from src.repository import photo as repository_photo

DISPLAY_NAME_PATTERN = re.compile(
    r"^[A-Za-zА-Яа-яІіЇїЄєҐґ]+(?:[ '\-][A-Za-zА-Яа-яІіЇїЄєҐґ]+)*$",
    re.UNICODE,
)


async def get_photos_and_comments_counts(
    user_id: int, db: AsyncSession
):
    """Return aggregated photo and comment counters for the specified user."""

    photos_count = await repository_photo.get_total_number_of_photos(
        user_id=user_id, db=db
    )

    comments_count = (
        await repository_comment.get_total_number_of_comments(
            user_id=user_id, db=db
        )
    )

    return {
        "photos_count": photos_count,
        "comments_count": comments_count,
    }


def validate_display_name_value(value: str | None) -> str | None:
    """Validate and normalize a display name value from profile form data."""

    if value is None:
        return value

    normalized_value = value.strip()

    if not normalized_value:
        raise ValueError(
            UserValidationMessages.display_name_must_not_be_empty.value
        )

    if not DISPLAY_NAME_PATTERN.fullmatch(normalized_value):
        raise ValueError(
            UserValidationMessages.display_name_contains_invalid_characters.value
        )

    return normalized_value
