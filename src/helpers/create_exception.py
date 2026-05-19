from typing import NoReturn

from fastapi import HTTPException, status

from src.config.messages import HTTPStatusMessages


def create_exception(
    message: str = HTTPStatusMessages.bad_request.value,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> NoReturn:
    """Raise an HTTP exception with the provided status code and message."""

    raise HTTPException(
        status_code=status_code,
        detail=message,
    )
