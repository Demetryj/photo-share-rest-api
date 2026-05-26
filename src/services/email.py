"""
Email delivery helpers for user-facing authentication messages.

This module supports two delivery modes:
1. SMTP via ``fastapi-mail`` for local development.
2. Brevo Email API via HTTPS for deployed environments where SMTP ports
   may be blocked by the hosting platform.
"""

import logging
from pathlib import Path

import httpx
from fastapi_mail import (
    ConnectionConfig,
    FastMail,
    MessageSchema,
    MessageType,
)
from fastapi_mail.errors import ConnectionErrors
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import EmailStr

from src.config.settings import EmailProvider, settings

logger = logging.getLogger(__name__)

config = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=True,
    VALIDATE_CERTS=True,
    TEMPLATE_FOLDER=Path(__file__).parent / "templates",
)

template_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "xml"]),
)


async def _send_email_via_smtp(
    email: EmailStr,
    username: str,
    host: str,
    token: str,
    subject: str,
    template_name: str,
) -> None:
    """
    Send an email through the configured SMTP server.

    This path is intended for local development, where the project already uses
    ``fastapi-mail`` and SMTP works as expected.
    """
    message = MessageSchema(
        subject=subject,
        recipients=[email],
        template_body={
            "host": host,
            "username": username,
            "token": token,
        },
        subtype=MessageType.html,
    )

    smtp_server = FastMail(config=config)
    await smtp_server.send_message(
        message=message,
        template_name=template_name,
    )


async def _send_email_via_brevo_api(
    email: EmailStr,
    username: str,
    host: str,
    token: str,
    subject: str,
    template_name: str,
) -> None:
    """
    Send an email through the Brevo transactional email API.

    This path is intended for deployed environments where outbound SMTP ports
    are blocked, but standard HTTPS requests are allowed.
    """
    if not settings.BREVO_API_KEY:
        raise ValueError("BREVO_API_KEY is not configured.")

    # Reuse the existing HTML templates so token-based flows stay unchanged.
    template = template_env.get_template(template_name)
    html_content = template.render(
        host=host,
        username=username,
        token=token,
    )

    payload = {
        "sender": {
            "name": settings.MAIL_FROM_NAME,
            "email": str(settings.MAIL_FROM),
        },
        "to": [
            {
                "email": str(email),
                "name": username,
            }
        ],
        "subject": subject,
        "htmlContent": html_content,
    }

    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
        )

    if response.status_code >= 400:
        logger.error(
            "Brevo API email sending failed. Status: %s, body: %s",
            response.status_code,
            response.text,
        )
        raise ConnectionErrors(
            "Brevo API request failed while sending email."
        )


async def send_email(
    email: EmailStr,
    username: str,
    host: str,
    token: str,
    subject: str,
    template_name: str,
) -> None:
    """
    Send a templated HTML email using the configured provider.

    The same input contract is preserved for both local SMTP sending and
    deployed Brevo API sending, so the rest of the application does not need
    to care which transport is currently active.
    """
    try:
        if settings.EMAIL_PROVIDER == EmailProvider.brevo_api:
            await _send_email_via_brevo_api(
                email=email,
                username=username,
                host=host,
                token=token,
                subject=subject,
                template_name=template_name,
            )
        else:
            await _send_email_via_smtp(
                email=email,
                username=username,
                host=host,
                token=token,
                subject=subject,
                template_name=template_name,
            )
    except (ConnectionErrors, httpx.HTTPError, ValueError) as err:
        logger.exception(err)
