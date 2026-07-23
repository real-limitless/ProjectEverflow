"""Add knowledge_canvases and project_agents tables.

Revision ID: 006
Revises: 005
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, Sequence[str], None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "knowledge_canvases",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("origin", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("chunks", sa.Integer(), nullable=True),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("size_label", sa.String(length=64), nullable=True),
        sa.Column("created_by", GUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_canvases_project_id", "knowledge_canvases", ["project_id"])
    op.create_index("ix_knowledge_canvases_created_by", "knowledge_canvases", ["created_by"])

    op.create_table(
        "project_agents",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False, server_default="general"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("tools", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", GUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_agents_project_id", "project_agents", ["project_id"])
    op.create_index("ix_project_agents_created_by", "project_agents", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_project_agents_created_by", table_name="project_agents")
    op.drop_index("ix_project_agents_project_id", table_name="project_agents")
    op.drop_table("project_agents")
    op.drop_index("ix_knowledge_canvases_created_by", table_name="knowledge_canvases")
    op.drop_index("ix_knowledge_canvases_project_id", table_name="knowledge_canvases")
    op.drop_table("knowledge_canvases")
