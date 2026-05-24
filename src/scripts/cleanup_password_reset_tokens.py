"""Delete old password reset tokens from the database."""

import asyncio
import logging

from src.database.db import sessionmanager
from src.repository.auth import delete_old_password_reset_tokens

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RETENTION_DAYS = 0


async def main() -> None:
    """Run cleanup for old password reset tokens."""

    async with sessionmanager.get_session() as db:
        deleted_count = await delete_old_password_reset_tokens(
            older_than_days=RETENTION_DAYS,
            db=db,
        )

        logger.info(
            "Deleted %s old password reset token records.",
            deleted_count,
        )


if __name__ == "__main__":
    asyncio.run(main())
