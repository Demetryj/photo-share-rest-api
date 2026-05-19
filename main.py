"""FastAPI application entry point for the Photo share REST API."""

import logging

from fastapi import Depends, FastAPI, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.handlers import validation_exception_handler
from src.config.middlewares import setup_cors
from src.database.db import get_db
from src.helpers.create_exception import create_exception
from src.routes import auth, comment, photo, user

app = FastAPI()

logger = logging.getLogger(__name__)

# Register CORS middleware for cross-origin requests.
setup_cors(app)

# Register a validation exception handler to return 400 Bad Request responses.
app.add_exception_handler(
    RequestValidationError, validation_exception_handler
)


app.include_router(auth.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(photo.router, prefix="/api")
app.include_router(comment.router, prefix="/api")


@app.get("/")
def index():
    """Return the base application status message."""

    return {"message": "Photo share REST API Application"}


@app.get("/api/healthchecker")
async def healthchecker(db: AsyncSession = Depends(get_db)):
    """Check that the application can connect to the database."""

    try:
        # Make request
        result = await db.execute(text("SELECT 1 + 1"))
        result = result.fetchone()
        if result is None:
            create_exception(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message="Database is not configured correctly",
            )
        return {"message": "Welcome to FastAPI!"}
    except SQLAlchemyError:
        logger.exception("Healthcheck database query failed")
        create_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Error connecting to the database",
        )
