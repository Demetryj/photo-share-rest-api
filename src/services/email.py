"""Email delivery helpers for user-facing authentication messages.

This module configures the SMTP connection used by ``fastapi-mail`` and exposes
an async helper for sending templated HTML emails.
"""

import logging
from pathlib import Path

from fastapi_mail import (
    ConnectionConfig,
    FastMail,
    MessageSchema,
    MessageType,
)
from fastapi_mail.errors import ConnectionErrors
from pydantic import EmailStr

from src.config.settings import settings

logger = logging.getLogger(__name__)

config = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME="Photo share System",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=Path(__file__).parent / "templates",
)


# Reusable sender for email verification and password reset messages.
async def send_email(
    email: EmailStr,
    username: str,
    host: str,
    token: str,
    subject: str,
    template_name: str,
) -> None:
    """Send a templated HTML email to a user.

    The function builds a ``MessageSchema`` with the provided recipient,
    template context, and subject, then sends it through the configured SMTP
    server. It is used for email confirmation and password reset messages.
    """

    try:
        message = MessageSchema(
            subject=subject,
            recipients=[email],
            template_body={"host": host, "username": username, "token": token},
            subtype=MessageType.html,
        )

        smtp_server = FastMail(config=config)
        await smtp_server.send_message(message=message, template_name=template_name)
    except ConnectionErrors as err:
        logger.exception(err)
