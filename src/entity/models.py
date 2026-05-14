"""Shared SQLAlchemy declarative base and common model mixins."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# SQLAlchemy base class for declarative models..
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""

    pass


# Shared timestamp fields for models that need creation and update tracking.
class LastModifiedMixin:
    """Mixin that adds creation and update timestamps to a model."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now()
    )
