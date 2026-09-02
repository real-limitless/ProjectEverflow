"""Teams, seats, room channels, runs, and bot bus.

Revision ID: 017
Revises: 016
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, Sequence[str], None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def upgrade() -> None:
    op.add_column("projects", sa.Column("constitution_md", sa.Text(), nullable=True))

    op.create_table(
        "project_teams",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("mention", sa.String(length=80), nullable=False),
        sa.Column("lane", sa.String(length=32), nullable=False, server_default="line"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("conductor_seat_id", GUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug", name="uq_project_team_slug"),
    )
    op.create_index("ix_project_teams_project_id", "project_teams", ["project_id"])

    op.create_table(
        "project_seats",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("team_id", GUID, nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="bot"),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False, server_default="specialist"),
        sa.Column("lane", sa.String(length=32), nullable=False, server_default="line"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("reports_to_id", GUID, nullable=True),
        sa.Column("owner_user_id", GUID, nullable=True),
        sa.Column("agent_slug", sa.String(length=80), nullable=True),
        sa.Column("is_conductor", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("fired", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("opencode_session_id", sa.String(length=200), nullable=True),
        sa.Column("worktree_path", sa.String(length=400), nullable=True),
        sa.Column("budget_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("permission", sa.JSON(), nullable=True),
        sa.Column("tools", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["project_teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reports_to_id"], ["project_seats.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug", name="uq_project_seat_slug"),
    )
    op.create_index("ix_project_seats_project_id", "project_seats", ["project_id"])
    op.create_index("ix_project_seats_team_id", "project_seats", ["team_id"])
    op.create_index("ix_project_seats_reports_to_id", "project_seats", ["reports_to_id"])
    op.create_index("ix_project_seats_owner_user_id", "project_seats", ["owner_user_id"])

    op.create_table(
        "project_channels",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("team_id", GUID, nullable=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False, server_default="channel"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["project_teams.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "slug", name="uq_project_channel_slug"),
    )
    op.create_index("ix_project_channels_project_id", "project_channels", ["project_id"])

    op.create_table(
        "org_runs",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("channel_id", GUID, nullable=True),
        sa.Column("thread_id", GUID, nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="compiled"),
        sa.Column("compiled_graph", sa.JSON(), nullable=True),
        sa.Column("created_by", GUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["channel_id"], ["project_channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_runs_project_id", "org_runs", ["project_id"])

    op.create_table(
        "org_run_nodes",
        sa.Column("id", GUID, nullable=False),
        sa.Column("run_id", GUID, nullable=False),
        sa.Column("seat_id", GUID, nullable=True),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="waiting"),
        sa.Column("brief", sa.Text(), nullable=False, server_default=""),
        sa.Column("result", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("depends_on", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["org_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seat_id"], ["project_seats.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_run_nodes_run_id", "org_run_nodes", ["run_id"])

    op.create_table(
        "project_channel_messages",
        sa.Column("id", GUID, nullable=False),
        sa.Column("channel_id", GUID, nullable=False),
        sa.Column("thread_id", GUID, nullable=True),
        sa.Column("author_user_id", GUID, nullable=True),
        sa.Column("author_seat_id", GUID, nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=24), nullable=False, server_default="message"),
        sa.Column("mentions", sa.JSON(), nullable=True),
        sa.Column("run_id", GUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["project_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["project_channel_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_seat_id"], ["project_seats.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["org_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_channel_messages_channel_id", "project_channel_messages", ["channel_id"])
    op.create_index("ix_project_channel_messages_thread_id", "project_channel_messages", ["thread_id"])
    op.create_index("ix_project_channel_messages_run_id", "project_channel_messages", ["run_id"])

    op.create_table(
        "org_bus_events",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("run_id", GUID, nullable=True),
        sa.Column("verb", sa.String(length=40), nullable=False),
        sa.Column("from_seat_id", GUID, nullable=True),
        sa.Column("to_seat_id", GUID, nullable=True),
        sa.Column("to_team_id", GUID, nullable=True),
        sa.Column("to_channel_id", GUID, nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["org_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["from_seat_id"], ["project_seats.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_seat_id"], ["project_seats.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_team_id"], ["project_teams.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["to_channel_id"], ["project_channels.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_org_bus_events_project_id", "org_bus_events", ["project_id"])
    op.create_index("ix_org_bus_events_run_id", "org_bus_events", ["run_id"])
    op.create_index("ix_org_bus_events_created_at", "org_bus_events", ["created_at"])

    op.create_table(
        "org_memory_blocks",
        sa.Column("id", GUID, nullable=False),
        sa.Column("project_id", GUID, nullable=False),
        sa.Column("scope", sa.String(length=24), nullable=False),
        sa.Column("scope_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "scope", "scope_id", "name", name="uq_org_memory_block"),
    )
    op.create_index("ix_org_memory_blocks_project_id", "org_memory_blocks", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_org_memory_blocks_project_id", table_name="org_memory_blocks")
    op.drop_table("org_memory_blocks")
    op.drop_index("ix_org_bus_events_created_at", table_name="org_bus_events")
    op.drop_index("ix_org_bus_events_run_id", table_name="org_bus_events")
    op.drop_index("ix_org_bus_events_project_id", table_name="org_bus_events")
    op.drop_table("org_bus_events")
    op.drop_index("ix_project_channel_messages_run_id", table_name="project_channel_messages")
    op.drop_index("ix_project_channel_messages_thread_id", table_name="project_channel_messages")
    op.drop_index("ix_project_channel_messages_channel_id", table_name="project_channel_messages")
    op.drop_table("project_channel_messages")
    op.drop_index("ix_org_run_nodes_run_id", table_name="org_run_nodes")
    op.drop_table("org_run_nodes")
    op.drop_index("ix_org_runs_project_id", table_name="org_runs")
    op.drop_table("org_runs")
    op.drop_index("ix_project_channels_project_id", table_name="project_channels")
    op.drop_table("project_channels")
    op.drop_index("ix_project_seats_owner_user_id", table_name="project_seats")
    op.drop_index("ix_project_seats_reports_to_id", table_name="project_seats")
    op.drop_index("ix_project_seats_team_id", table_name="project_seats")
    op.drop_index("ix_project_seats_project_id", table_name="project_seats")
    op.drop_table("project_seats")
    op.drop_index("ix_project_teams_project_id", table_name="project_teams")
    op.drop_table("project_teams")
    op.drop_column("projects", "constitution_md")
