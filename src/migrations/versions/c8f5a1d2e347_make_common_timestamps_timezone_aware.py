"""make common timestamps timezone aware

Revision ID: c8f5a1d2e347
Revises: a0017df77a24
Create Date: 2026-05-24 16:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8f5a1d2e347"
down_revision: Union[str, Sequence[str], None] = "a0017df77a24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    columns = [
        ("password_reset_tokens", "expires_at", False),
        ("password_reset_tokens", "used_at", True),
        ("users", "created_at", False),
        ("users", "updated_at", False),
        ("photos", "created_at", False),
        ("photos", "updated_at", False),
        ("comments", "created_at", False),
        ("comments", "updated_at", False),
        ("photo_ratings", "created_at", False),
        ("photo_ratings", "updated_at", False),
        ("user_sessions", "created_at", False),
        ("user_sessions", "updated_at", False),
        ("photo_transformations", "created_at", False),
    ]

    for table_name, column_name, nullable in columns:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=nullable,
        )


def downgrade() -> None:
    """Downgrade schema."""

    columns = [
        ("photo_transformations", "created_at", False),
        ("user_sessions", "updated_at", False),
        ("user_sessions", "created_at", False),
        ("photo_ratings", "updated_at", False),
        ("photo_ratings", "created_at", False),
        ("comments", "updated_at", False),
        ("comments", "created_at", False),
        ("photos", "updated_at", False),
        ("photos", "created_at", False),
        ("users", "updated_at", False),
        ("users", "created_at", False),
        ("password_reset_tokens", "used_at", True),
        ("password_reset_tokens", "expires_at", False),
    ]

    for table_name, column_name, nullable in columns:
        op.alter_column(
            table_name,
            column_name,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=nullable,
        )
