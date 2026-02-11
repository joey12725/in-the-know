"""add waitlist entries table

Revision ID: 202602111030
Revises: 202602101200
Create Date: 2026-02-11 10:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602111030"
down_revision: Union[str, None] = "202602101200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waitlist_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_waitlist_entries_email", "waitlist_entries", ["email"], unique=False)
    op.create_index("ix_waitlist_entries_city", "waitlist_entries", ["city"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_waitlist_entries_city", table_name="waitlist_entries")
    op.drop_index("ix_waitlist_entries_email", table_name="waitlist_entries")
    op.drop_table("waitlist_entries")
