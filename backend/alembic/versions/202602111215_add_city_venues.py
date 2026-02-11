"""add city venues table

Revision ID: 202602111215
Revises: 202602111030
Create Date: 2026-02-11 12:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602111215"
down_revision: Union[str, None] = "202602111030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "city_venues",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("venue_name", sa.String(length=240), nullable=False),
        sa.Column("venue_type", sa.String(length=50), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("last_searched", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_events_searched", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cached_events", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("city", "venue_name", name="uq_city_venues_city_name"),
    )
    op.create_index("ix_city_venues_city", "city_venues", ["city"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_city_venues_city", table_name="city_venues")
    op.drop_table("city_venues")
