"""Add ai_usage_events for chat token accounting.

Revision ID: 016
Revises: 015
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, Sequence[str], None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=200), nullable=False),
        sa.Column("message_id", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_ai_usage_message_id"),
    )
    op.create_index("ix_ai_usage_events_organization_id", "ai_usage_events", ["organization_id"])
    op.create_index("ix_ai_usage_events_project_id", "ai_usage_events", ["project_id"])
    op.create_index("ix_ai_usage_events_user_id", "ai_usage_events", ["user_id"])
    op.create_index("ix_ai_usage_events_session_id", "ai_usage_events", ["session_id"])
    op.create_index("ix_ai_usage_events_occurred_at", "ai_usage_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_events_occurred_at", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_session_id", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_user_id", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_project_id", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_organization_id", table_name="ai_usage_events")
    op.drop_table("ai_usage_events")
