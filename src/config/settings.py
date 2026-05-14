"""
Application settings managed via Pydantic Settings.
Local runs can read values from the project `.env` file, while Docker Compose
can still override them by passing real environment variables into the process.
"""

from pathlib import Path

from pydantic import EmailStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.

    The settings object contains database, JWT, email, Redis, and Cloudinary
    configuration values required by the API.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PSG_DB_USER: str
    PSG_DB_PASSWORD: str
    PSG_DB_NAME: str
    PSG_DB_DOMAIN: str
    PSG_DB_PORT: int

    secret_key: str
    hash_algorithm: str = "HS256"

    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: EmailStr
    MAIL_PORT: int = 2525
    MAIL_SERVER: str = "sandbox.smtp.mailtrap.io"

    REDIS_DOMAIN: str
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # Tests set this flag before importing the app. Rate limiter setup uses it
    # to avoid creating Redis-backed buckets during local pytest runs.
    testing: bool = False

    CLOUDINARY_NAME: str
    CLOUDINARY_API_KEY: int
    CLOUDINARY_API_SECRET: str

    # TODO при деплої Значення має бути True.
    # Встановити відповідне значення в env.
    # Потрібно буде заначити в рідмі, що для локальної розробки False, а для проду True
    COOKIE_SECURE: bool = False

    @computed_field
    @property
    def DB_URL(self) -> str:
        """
        Build the SQLAlchemy async PostgreSQL connection URL.

        :return: PostgreSQL connection URL for ``asyncpg``.
        :rtype: str
        """
        return (
            f"postgresql+asyncpg://{self.PSG_DB_USER}:{self.PSG_DB_PASSWORD}"
            f"@{self.PSG_DB_DOMAIN}:{self.PSG_DB_PORT}/{self.PSG_DB_NAME}"
        )


settings = Settings()
