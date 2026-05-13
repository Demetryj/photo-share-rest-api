import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.entity.models import Base, LastModifiedMixin


# Allowed user roles in the system.
class Role(enum.Enum):
    """Available user roles for access control."""

    admin: str = "admin"
    moderator: str = "moderator"
    user: str = "user"


# Application user and related refresh tokens.
class User(Base, LastModifiedMixin):
    """Application user account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    username: Mapped[str] = mapped_column(String(60), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[Role] = mapped_column(
        "role", Enum(Role, create_type=True), default=Role.user, nullable=False
    )
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", backref="user", cascade="all, delete-orphan"
    )

    # Separate table for refresh tokens: one user can sign in from multiple devices,


# so each device/session gets its own refresh token row.
class RefreshToken(Base, LastModifiedMixin):
    """Refresh token issued for a specific user session or device."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    rf_token: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE")
    )


# TODO: додати cleanup для очищення таблиці раз на добу, додати в загальний іпорт та енв поетрі
# Stores password reset JWT hashes and usage state to make reset links one-time.
class PasswordResetToken(Base):
    """One-time password reset token bound to a user and expiration time."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    user: Mapped["User"] = relationship("User", backref="password_reset_tokens")
