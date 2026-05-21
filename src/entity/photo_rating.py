"""ORM model for user photo ratings."""

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.entity.models import Base, LastModifiedMixin

if TYPE_CHECKING:
    from src.entity.photo import Photo
    from src.entity.user import User


class PhotoRating(Base, LastModifiedMixin):
    """Single user-provided rating for a photo.

    Each record stores one user's score for one photo. The same user can rate
    the same photo only once, and the rating value is expected to stay within
    the allowed 1-to-5 range.
    """

    __tablename__ = "photo_ratings"
    __table_args__ = (
        UniqueConstraint(
            "photo_id",
            "user_id",
            name="uq_photo_ratings_photo_id_user_id",
        ),
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_photo_ratings_rating_1_5",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    photo: Mapped["Photo"] = relationship(
        "Photo",
        back_populates="ratings",
    )
    user: Mapped["User"] = relationship(
        "User",
        backref="photo_ratings",
    )
