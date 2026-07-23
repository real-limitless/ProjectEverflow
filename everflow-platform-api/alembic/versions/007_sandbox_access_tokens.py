"""Add sandbox_access_tokens for in-sandbox Everflow MCP auth.

Revision ID: 007
Revises: 006
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, Sequence[str], None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "sandbox_access_tokens",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("user_id", GUID, nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=True),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_sandbox_access_tokens_project_id", "sandbox_access_tokens", ["project_id"])
    op.create_index("ix_sandbox_access_tokens_user_id", "sandbox_access_tokens", ["user_id"])
    op.create_index("ix_sandbox_access_tokens_token_hash", "sandbox_access_tokens", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_sandbox_access_tokens_token_hash", table_name="sandbox_access_tokens")
    op.drop_index("ix_sandbox_access_tokens_user_id", table_name="sandbox_access_tokens")
    op.drop_index("ix_sandbox_access_tokens_project_id", table_name="sandbox_access_tokens")
    op.drop_table("sandbox_access_tokens")
