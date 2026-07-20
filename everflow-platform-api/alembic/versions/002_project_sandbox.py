"""Add project sandbox lifecycle columns.

Revision ID: 002
Revises: 001
Create Date: 2026-07-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("sandbox_name", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column(
                "sandbox_status",
                sa.String(length=32),
                nullable=False,
                server_default="pending",
            )
        )
        batch.add_column(sa.Column("sandbox_image", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("sandbox_error", sa.Text(), nullable=True))
        batch.add_column(sa.Column("sandbox_created_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_projects_sandbox_name"), "projects", ["sandbox_name"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_sandbox_name"), table_name="projects")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("sandbox_created_at")
        batch.drop_column("sandbox_error")
        batch.drop_column("sandbox_image")
        batch.drop_column("sandbox_status")
        batch.drop_column("sandbox_name")
