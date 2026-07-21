"""Add preview_endpoints table for GUID subdomain preview bindings.

Revision ID: 003
Revises: 002
Create Date: 2026-07-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, Sequence[str], None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# CHAR(36) GUID strings — portable across SQLite and PostgreSQL (matches fastapi-users GUID).
GUID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "preview_endpoints",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("sandbox_name", sa.String(length=128), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", GUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "sandbox_name",
            "port",
            name="uq_preview_project_sandbox_port",
        ),
    )
    op.create_index(
        op.f("ix_preview_endpoints_project_id"),
        "preview_endpoints",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_preview_endpoints_sandbox_name"),
        "preview_endpoints",
        ["sandbox_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_preview_endpoints_sandbox_name"), table_name="preview_endpoints")
    op.drop_index(op.f("ix_preview_endpoints_project_id"), table_name="preview_endpoints")
    op.drop_table("preview_endpoints")
