"""SQLAlchemy model for photo comments."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.entity.models import Base, LastModifiedMixin

if TYPE_CHECKING:
    from src.entity.photo import Photo
    from src.entity.user import User


class Comment(Base, LastModifiedMixin):
    """Persisted user comment linked to a photo."""

    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    content: Mapped[str] = mapped_column(String(300), nullable=False)
    photo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "photos.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship("User", backref="comments")
    photo: Mapped["Photo"] = relationship("Photo", backref="comments")
