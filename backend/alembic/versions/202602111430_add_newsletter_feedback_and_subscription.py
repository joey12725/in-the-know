"""add newsletter feedback and subscription flag

Revision ID: 202602111430
Revises: 202602111300
Create Date: 2026-02-11 14:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602111430"
down_revision: Union[str, None] = "202602111300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_subscribed", sa.Boolean(), server_default=sa.text("true"), nullable=False))

    op.create_table(
        "newsletter_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("newsletter_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_reply", sa.Text(), nullable=False),
        sa.Column("rewritten_feedback", sa.Text(), nullable=False),
        sa.Column("feedback_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["newsletter_id"], ["newsletters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_newsletter_feedback_user_created_at", "newsletter_feedback", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_newsletter_feedback_user_created_at", table_name="newsletter_feedback")
    op.drop_table("newsletter_feedback")
    op.drop_column("users", "is_subscribed")
