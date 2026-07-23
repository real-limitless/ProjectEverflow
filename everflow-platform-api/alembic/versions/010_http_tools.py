"""Add project_http_tools table.

Revision ID: 010
Revises: 009
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, Sequence[str], None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "project_http_tools",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False, server_default="GET"),
        sa.Column("url_template", sa.String(length=2000), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", GUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_http_tools_project_id", "project_http_tools", ["project_id"])
    op.create_index("ix_project_http_tools_created_by", "project_http_tools", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_project_http_tools_created_by", table_name="project_http_tools")
    op.drop_index("ix_project_http_tools_project_id", table_name="project_http_tools")
    op.drop_table("project_http_tools")
