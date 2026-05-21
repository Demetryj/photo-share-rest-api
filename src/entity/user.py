"""ORM models related to application users and authentication tokens."""

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

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, index=True
    )
    username: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True
    )
    display_name: Mapped[str | None] = mapped_column(
        String(60), nullable=True
    )
    email: Mapped[str] = mapped_column(
        String(150), nullable=False, unique=True
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[Role] = mapped_column(
        "role",
        Enum(Role, create_type=True),
        default=Role.user,
        nullable=False,
    )
    confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    user_sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )


# Separate table for user sessions: one user can sign in from multiple
# devices/browsers, so each session stores its own refresh-token hash,
# current access-token JTI, and optional device information.
class UserSession(Base, LastModifiedMixin):
    """Active authenticated session for one user device or browser.

    A session record represents one sign-in context. It links the owning
    user to the refresh-token hash used to continue that session, the
    currently active access-token JTI used to validate protected requests,
    and optional client/device metadata for identifying where the session
    came from.
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True, index=True
    )
    access_token_jti: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )
    device_info: Mapped[str | None] = mapped_column(
        String(300), nullable=True, default=None
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="user_sessions",
    )


# TODO: додати cleanup для очищення таблиці раз на добу, додати в загальний іпорт та енв поетрі
# Stores password reset JWT hashes and usage state to make reset links one-time.
class PasswordResetToken(Base):
    """One-time password reset token bound to a user and expiration time."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )

    user: Mapped["User"] = relationship(
        "User", backref="password_reset_tokens"
    )
