"""add dating preference to users

Revision ID: 202602111300
Revises: 202602111215
Create Date: 2026-02-11 13:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "202602111300"
down_revision: Union[str, None] = "202602111215"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("dating_preference", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "dating_preference")
