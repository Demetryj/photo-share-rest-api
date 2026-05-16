"""ORM models for photos, tags, and generated transformation links."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.entity.models import Base, LastModifiedMixin

if TYPE_CHECKING:
    from src.entity.user import User


class TransformationType(enum.Enum):
    """Allowed Cloudinary-based operations for transformed photo links."""

    crop = "crop"
    resize = "resize"
    grayscale = "grayscale"
    rotate = "rotate"
    blur = "blur"


class BlurMode(enum.Enum):
    """Allowed blur algorithms for local photo preview transformations."""

    gaussian = "gaussian"
    box = "box"


# Association table for the many-to-many relationship between photos and tags.
photo_tags = Table(
    "photo_tags",
    Base.metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "photo_id",
        Integer,
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        nullable=False,
    ),
    UniqueConstraint("photo_id", "tag_id", name="uq_photo_tag"),
)


class Photo(Base, LastModifiedMixin):
    """User-uploaded original photo stored in Cloudinary.

    Keeps the owner reference, optional description, original image URL,
    Cloudinary public identifier, and relationships to tags and saved
    transformed image links.
    """

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, index=True
    )
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(
        String(300), nullable=True
    )
    image_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True
    )
    public_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )

    owner: Mapped["User"] = relationship("User", backref="photos")
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary=photo_tags, back_populates="photos"
    )
    transformations: Mapped[list["PhotoTransformation"]] = (
        relationship(
            "PhotoTransformation",
            back_populates="photo",
            cascade="all, delete-orphan",
        )
    )


class Tag(Base):
    """Unique tag entity shared across the whole application.

    A single tag can be reused by many photos, and each photo can have
    multiple tags through the ``photo_tags`` association table.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )

    photos: Mapped[list["Photo"]] = relationship(
        "Photo", secondary=photo_tags, back_populates="tags"
    )


class PhotoTransformation(Base):
    """Saved transformed version of an existing photo.

    Stores which photo was transformed, which user created the transformed
    link, what transformation type and parameters were applied, and the
    resulting URL and optional QR code URL.
    """

    __tablename__ = "photo_transformations"

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    photo_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transformation_type: Mapped[TransformationType] = mapped_column(
        Enum(TransformationType, create_type=True), nullable=False
    )
    transformation_params: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    transformed_url: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True
    )
    qr_code_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    photo: Mapped["Photo"] = relationship(
        "Photo", back_populates="transformations"
    )
    user: Mapped["User"] = relationship(
        "User", backref="photo_transformations"
    )
