"""initial schema

Revision ID: 202602101200
Revises:
Create Date: 2026-02-10 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "202602101200"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("address", sa.String(length=300), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("concision_pref", sa.String(length=20), nullable=False),
        sa.Column("event_radius_miles", sa.Integer(), nullable=False),
        sa.Column("personality_type", sa.String(length=10), nullable=True),
        sa.Column("onboarding_token", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("onboarding_token"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index("ix_users_city", "users", ["city"], unique=False)
    op.create_index("ix_users_onboarding_token", "users", ["onboarding_token"], unique=False)

    op.create_table(
        "hobby_tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_name", sa.String(length=100), nullable=False),
        sa.Column("search_prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tag_name"),
    )
    op.create_index("ix_hobby_tags_tag_name", "hobby_tags", ["tag_name"], unique=False)

    op.create_table(
        "user_hobbies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("parsed_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "user_goals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("goal_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "hobby_city_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hobby_tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        sa.Column("last_searched", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cached_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["hobby_tag_id"], ["hobby_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hobby_city_pairs_city", "hobby_city_pairs", ["city"], unique=False)

    op.create_table(
        "oauth_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oauth_tokens_provider", "oauth_tokens", ["provider"], unique=False)

    op.create_table(
        "newsletters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("events_included", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "onboarding_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "step_name", name="uq_onboarding_steps_user_step"),
    )


def downgrade() -> None:
    op.drop_table("onboarding_steps")
    op.drop_table("newsletters")
    op.drop_index("ix_oauth_tokens_provider", table_name="oauth_tokens")
    op.drop_table("oauth_tokens")
    op.drop_index("ix_hobby_city_pairs_city", table_name="hobby_city_pairs")
    op.drop_table("hobby_city_pairs")
    op.drop_table("user_goals")
    op.drop_table("user_hobbies")
    op.drop_index("ix_hobby_tags_tag_name", table_name="hobby_tags")
    op.drop_table("hobby_tags")
    op.drop_index("ix_users_onboarding_token", table_name="users")
    op.drop_index("ix_users_city", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
