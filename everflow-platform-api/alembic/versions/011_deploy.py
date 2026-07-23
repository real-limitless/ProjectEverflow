"""Add deploy_nodes, deploy_ssh_keys, deploy_routes, deploy_runs tables.

Revision ID: 011
Revises: 010
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, Sequence[str], None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "deploy_ssh_keys",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("private_key_encrypted", sa.Text(), nullable=False),
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
    op.create_index("ix_deploy_ssh_keys_project_id", "deploy_ssh_keys", ["project_id"])
    op.create_index("ix_deploy_ssh_keys_created_by", "deploy_ssh_keys", ["created_by"])

    op.create_table(
        "deploy_nodes",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("ssh_user", sa.String(length=128), nullable=False, server_default="everflow"),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="unknown"),
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
    op.create_index("ix_deploy_nodes_project_id", "deploy_nodes", ["project_id"])
    op.create_index("ix_deploy_nodes_created_by", "deploy_nodes", ["created_by"])

    op.create_table(
        "deploy_routes",
        sa.Column("id", GUID, nullable=False),
        sa.Column("node_id", GUID, nullable=False),
        sa.Column("host_header", sa.String(length=255), nullable=False),
        sa.Column("service_name", sa.String(length=200), nullable=False),
        sa.Column("service_port", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("path_prefix", sa.String(length=512), nullable=False, server_default="/"),
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
        sa.ForeignKeyConstraint(["node_id"], ["deploy_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deploy_routes_node_id", "deploy_routes", ["node_id"])

    op.create_table(
        "deploy_runs",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("node_id", GUID, nullable=True),
        sa.Column("compose_file", sa.String(length=512), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False, server_default="up"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="stub"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["deploy_nodes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deploy_runs_project_id", "deploy_runs", ["project_id"])
    op.create_index("ix_deploy_runs_node_id", "deploy_runs", ["node_id"])


def downgrade() -> None:
    op.drop_index("ix_deploy_runs_node_id", table_name="deploy_runs")
    op.drop_index("ix_deploy_runs_project_id", table_name="deploy_runs")
    op.drop_table("deploy_runs")
    op.drop_index("ix_deploy_routes_node_id", table_name="deploy_routes")
    op.drop_table("deploy_routes")
    op.drop_index("ix_deploy_nodes_created_by", table_name="deploy_nodes")
    op.drop_index("ix_deploy_nodes_project_id", table_name="deploy_nodes")
    op.drop_table("deploy_nodes")
    op.drop_index("ix_deploy_ssh_keys_created_by", table_name="deploy_ssh_keys")
    op.drop_index("ix_deploy_ssh_keys_project_id", table_name="deploy_ssh_keys")
    op.drop_table("deploy_ssh_keys")
