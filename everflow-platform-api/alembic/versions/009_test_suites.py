"""Add test_suites and test_cases tables.

Revision ID: 009
Revises: 008
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, Sequence[str], None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "test_suites",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", GUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_suites_project_id", "test_suites", ["project_id"])
    op.create_index("ix_test_suites_created_by", "test_suites", ["created_by"])

    op.create_table(
        "test_cases",
        sa.Column("id", GUID, nullable=False),
        sa.Column("suite_id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="unit"),
        sa.Column("command", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", GUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["suite_id"], ["test_suites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_cases_suite_id", "test_cases", ["suite_id"])
    op.create_index("ix_test_cases_project_id", "test_cases", ["project_id"])
    op.create_index("ix_test_cases_created_by", "test_cases", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_test_cases_created_by", table_name="test_cases")
    op.drop_index("ix_test_cases_project_id", table_name="test_cases")
    op.drop_index("ix_test_cases_suite_id", table_name="test_cases")
    op.drop_table("test_cases")
    op.drop_index("ix_test_suites_created_by", table_name="test_suites")
    op.drop_index("ix_test_suites_project_id", table_name="test_suites")
    op.drop_table("test_suites")
