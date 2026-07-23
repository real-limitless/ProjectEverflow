"""Add workflows, runs, credentials, and data tables.

Revision ID: 008
Revises: 007
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("n8n_document", sa.JSON(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("trigger_summary", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("credential_bindings", sa.JSON(), nullable=True),
        sa.Column("import_report", sa.JSON(), nullable=True),
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
    op.create_index("ix_workflows_project_id", "workflows", ["project_id"])
    op.create_index("ix_workflows_created_by", "workflows", ["created_by"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", GUID, nullable=False),
        sa.Column("workflow_id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("trigger_type", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_pin", sa.JSON(), nullable=True),
        sa.Column("log", sa.JSON(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("ix_workflow_runs_project_id", "workflow_runs", ["project_id"])

    op.create_table(
        "workflow_credentials",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("credential_type", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_nonce", sa.String(length=64), nullable=False, server_default=""),
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
    op.create_index("ix_workflow_credentials_project_id", "workflow_credentials", ["project_id"])
    op.create_index(
        "ix_workflow_credentials_credential_type", "workflow_credentials", ["credential_type"]
    )
    op.create_index("ix_workflow_credentials_created_by", "workflow_credentials", ["created_by"])

    op.create_table(
        "workflow_data_tables",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=True),
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
    op.create_index("ix_workflow_data_tables_project_id", "workflow_data_tables", ["project_id"])
    op.create_index("ix_workflow_data_tables_name", "workflow_data_tables", ["name"])

    op.create_table(
        "workflow_data_table_rows",
        sa.Column("id", GUID, nullable=False),
        sa.Column("table_id", GUID, nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["table_id"], ["workflow_data_tables.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_data_table_rows_table_id", "workflow_data_table_rows", ["table_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_data_table_rows_table_id", table_name="workflow_data_table_rows")
    op.drop_table("workflow_data_table_rows")
    op.drop_index("ix_workflow_data_tables_name", table_name="workflow_data_tables")
    op.drop_index("ix_workflow_data_tables_project_id", table_name="workflow_data_tables")
    op.drop_table("workflow_data_tables")
    op.drop_index("ix_workflow_credentials_created_by", table_name="workflow_credentials")
    op.drop_index("ix_workflow_credentials_credential_type", table_name="workflow_credentials")
    op.drop_index("ix_workflow_credentials_project_id", table_name="workflow_credentials")
    op.drop_table("workflow_credentials")
    op.drop_index("ix_workflow_runs_project_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index("ix_workflows_created_by", table_name="workflows")
    op.drop_index("ix_workflows_project_id", table_name="workflows")
    op.drop_table("workflows")
