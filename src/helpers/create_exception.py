from typing import NoReturn

from fastapi import HTTPException, status

from src.config.messages import PhotoTransformationMessage


def create_exception(
    message: PhotoTransformationMessage | str,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> NoReturn:
    """Raise an HTTP exception with the provided status code and message."""

    raise HTTPException(
        status_code=status_code,
        detail=message,
    )
