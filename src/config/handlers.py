"""Application exception handlers."""

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """Return a normalized response for request validation errors.

    :param request: Incoming request that failed validation.
    :type request: Request
    :param exc: Validation exception raised by FastAPI.
    :type exc: RequestValidationError
    :return: JSON response with validation details.
    :rtype: JSONResponse
    """
    return JSONResponse(
        status_code=400,
        content={
            # Pydantic validation details may include non-JSON-serializable
            # objects such as ValueError instances. Normalize them before
            # building the JSON response.
            "detail": jsonable_encoder(exc.errors()),
            "message": "Bad Request",
        },
    )
