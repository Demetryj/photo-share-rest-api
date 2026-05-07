"""FastAPI application entry point for the Photo share REST API."""

import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.handlers import validation_exception_handler
from src.config.middlewares import setup_cors
from src.database.db import get_db

app = FastAPI()

logger = logging.getLogger(__name__)

# Register CORS middleware for cross-origin requests.
setup_cors(app)

# Register a validation exception handler to return 400 Bad Request responses.
app.add_exception_handler(RequestValidationError, validation_exception_handler)


@app.get("/")
def index():
    """Return a basic application status message.

    :return: Application welcome message.
    :rtype: dict[str, str]
    """

    return {"message": "Photo share REST API Application"}


@app.get("/api/healthchecker")
async def healthchecker(db: AsyncSession = Depends(get_db)):
    """Check database connectivity.

    :param db: SQLAlchemy asynchronous database session.
    :type db: AsyncSession
    :raises HTTPException: Raises ``500 Internal Server Error`` when the
        database check fails.
    :return: Health check success message.
    :rtype: dict[str, str]
    """

    try:
        # Make request
        result = await db.execute(text("SELECT 1 + 1"))
        result = result.fetchone()
        if result is None:
            raise HTTPException(
                status_code=500, detail="Database is not configured correctly"
            )
        return {"message": "Welcome to FastAPI!"}
    except SQLAlchemyError:
        logger.exception("Healthcheck database query failed")
        raise HTTPException(status_code=500, detail="Error connecting to the database")
