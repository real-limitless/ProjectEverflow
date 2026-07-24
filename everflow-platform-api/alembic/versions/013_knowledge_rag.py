"""Knowledge RAG: chunks, collections, versions, links, mind maps, eval.

Revision ID: 013
Revises: 012
Create Date: 2026-07-24

Idempotent: safe to re-run after a partial failure (e.g. SQLite FK ALTER
left knowledge_collections behind while alembic_version stayed at 012).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, Sequence[str], None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _has_table(table):
        return False
    return any(c["name"] == column for c in _inspector().get_columns(table))


def _has_index(table: str, index: str) -> bool:
    if not _has_table(table):
        return False
    return any(i["name"] == index for i in _inspector().get_indexes(table))


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if not _has_index(table, name):
        op.create_index(name, table, columns)


def upgrade() -> None:
    if not _has_table("knowledge_collections"):
        op.create_table(
            "knowledge_collections",
            sa.Column("id", GUID, nullable=False),
            sa.Column("project_id", GUID, nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column(
                "visibility", sa.String(length=32), nullable=False, server_default="team"
            ),
            sa.Column("owner_user_id", GUID, nullable=True),
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
    _create_index_if_missing(
        "ix_knowledge_collections_project_id", "knowledge_collections", ["project_id"]
    )
    _create_index_if_missing(
        "ix_knowledge_collections_owner_user_id",
        "knowledge_collections",
        ["owner_user_id"],
    )

    if not _has_table("agent_collection_grants"):
        op.create_table(
            "agent_collection_grants",
            sa.Column("id", GUID, nullable=False),
            sa.Column("agent_id", GUID, nullable=False),
            sa.Column("collection_id", GUID, nullable=False),
            sa.Column(
                "can_retrieve", sa.Boolean(), nullable=False, server_default=sa.text("1")
            ),
            sa.Column(
                "can_write", sa.Boolean(), nullable=False, server_default=sa.text("0")
            ),
            sa.ForeignKeyConstraint(
                ["agent_id"], ["project_agents.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["collection_id"], ["knowledge_collections.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("agent_id", "collection_id", name="uq_agent_collection"),
        )
    _create_index_if_missing(
        "ix_agent_collection_grants_agent_id", "agent_collection_grants", ["agent_id"]
    )
    _create_index_if_missing(
        "ix_agent_collection_grants_collection_id",
        "agent_collection_grants",
        ["collection_id"],
    )

    # SQLite cannot ALTER ADD CONSTRAINT — use batch mode (copy-and-move).
    canvas_cols = (
        "collection_id",
        "source_url",
        "content_hash",
        "etag",
        "last_fetched_at",
        "repo_path",
    )
    missing_canvas_cols = [c for c in canvas_cols if not _has_column("knowledge_canvases", c)]
    if missing_canvas_cols:
        with op.batch_alter_table("knowledge_canvases") as batch:
            if "collection_id" in missing_canvas_cols:
                batch.add_column(sa.Column("collection_id", GUID, nullable=True))
            if "source_url" in missing_canvas_cols:
                batch.add_column(sa.Column("source_url", sa.String(2048), nullable=True))
            if "content_hash" in missing_canvas_cols:
                batch.add_column(sa.Column("content_hash", sa.String(64), nullable=True))
            if "etag" in missing_canvas_cols:
                batch.add_column(sa.Column("etag", sa.String(255), nullable=True))
            if "last_fetched_at" in missing_canvas_cols:
                batch.add_column(
                    sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True)
                )
            if "repo_path" in missing_canvas_cols:
                batch.add_column(sa.Column("repo_path", sa.String(1024), nullable=True))
            if not _has_index("knowledge_canvases", "ix_knowledge_canvases_collection_id"):
                batch.create_index(
                    "ix_knowledge_canvases_collection_id",
                    ["collection_id"],
                )
            # Always attach FK when we batch-alter; recreate is safe via table rebuild.
            fk_names = {
                fk.get("name") for fk in _inspector().get_foreign_keys("knowledge_canvases")
            }
            if "fk_knowledge_canvases_collection_id" not in fk_names:
                batch.create_foreign_key(
                    "fk_knowledge_canvases_collection_id",
                    "knowledge_collections",
                    ["collection_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
    elif _has_column("knowledge_canvases", "collection_id"):
        # Columns already present from a partial run; ensure index/FK.
        need_index = not _has_index(
            "knowledge_canvases", "ix_knowledge_canvases_collection_id"
        )
        fk_names = {
            fk.get("name") for fk in _inspector().get_foreign_keys("knowledge_canvases")
        }
        need_fk = "fk_knowledge_canvases_collection_id" not in fk_names
        if need_index or need_fk:
            with op.batch_alter_table("knowledge_canvases") as batch:
                if need_index:
                    batch.create_index(
                        "ix_knowledge_canvases_collection_id",
                        ["collection_id"],
                    )
                if need_fk:
                    batch.create_foreign_key(
                        "fk_knowledge_canvases_collection_id",
                        "knowledge_collections",
                        ["collection_id"],
                        ["id"],
                        ondelete="SET NULL",
                    )

    if not _has_table("knowledge_chunks"):
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", GUID, nullable=False),
            sa.Column("project_id", GUID, nullable=False),
            sa.Column("canvas_id", GUID, nullable=False),
            sa.Column("collection_id", GUID, nullable=True),
            sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("embedding", sa.JSON(), nullable=True),
            sa.Column("token_count", sa.Integer(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["canvas_id"], ["knowledge_canvases.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_knowledge_chunks_project_id", "knowledge_chunks", ["project_id"]
    )
    _create_index_if_missing(
        "ix_knowledge_chunks_canvas_id", "knowledge_chunks", ["canvas_id"]
    )
    _create_index_if_missing(
        "ix_knowledge_chunks_collection_id", "knowledge_chunks", ["collection_id"]
    )

    if not _has_table("knowledge_canvas_versions"):
        op.create_table(
            "knowledge_canvas_versions",
            sa.Column("id", GUID, nullable=False),
            sa.Column("canvas_id", GUID, nullable=False),
            sa.Column("content_md", sa.Text(), nullable=False),
            sa.Column("created_by", GUID, nullable=True),
            sa.Column("label", sa.String(120), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["canvas_id"], ["knowledge_canvases.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_knowledge_canvas_versions_canvas_id",
        "knowledge_canvas_versions",
        ["canvas_id"],
    )

    if not _has_table("knowledge_links"):
        op.create_table(
            "knowledge_links",
            sa.Column("id", GUID, nullable=False),
            sa.Column("project_id", GUID, nullable=False),
            sa.Column("from_type", sa.String(32), nullable=False),
            sa.Column("from_id", sa.String(64), nullable=False),
            sa.Column("to_type", sa.String(32), nullable=False),
            sa.Column("to_id", sa.String(64), nullable=False),
            sa.Column(
                "rel", sa.String(32), nullable=False, server_default="derived_from"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_knowledge_links_project_id", "knowledge_links", ["project_id"]
    )

    if not _has_table("knowledge_mind_maps"):
        op.create_table(
            "knowledge_mind_maps",
            sa.Column("id", GUID, nullable=False),
            sa.Column("project_id", GUID, nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("mermaid", sa.Text(), nullable=False, server_default=""),
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
    _create_index_if_missing(
        "ix_knowledge_mind_maps_project_id", "knowledge_mind_maps", ["project_id"]
    )

    if not _has_table("knowledge_eval_sets"):
        op.create_table(
            "knowledge_eval_sets",
            sa.Column("id", GUID, nullable=False),
            sa.Column("project_id", GUID, nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("collection_id", GUID, nullable=True),
            sa.Column("last_score", sa.Float(), nullable=True),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
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
    _create_index_if_missing(
        "ix_knowledge_eval_sets_project_id", "knowledge_eval_sets", ["project_id"]
    )

    if not _has_table("knowledge_eval_questions"):
        op.create_table(
            "knowledge_eval_questions",
            sa.Column("id", GUID, nullable=False),
            sa.Column("eval_set_id", GUID, nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("expected_canvas_ids", sa.JSON(), nullable=True),
            sa.Column("expected_notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["eval_set_id"], ["knowledge_eval_sets.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "ix_knowledge_eval_questions_eval_set_id",
        "knowledge_eval_questions",
        ["eval_set_id"],
    )


def downgrade() -> None:
    if _has_table("knowledge_eval_questions"):
        if _has_index("knowledge_eval_questions", "ix_knowledge_eval_questions_eval_set_id"):
            op.drop_index(
                "ix_knowledge_eval_questions_eval_set_id",
                table_name="knowledge_eval_questions",
            )
        op.drop_table("knowledge_eval_questions")
    if _has_table("knowledge_eval_sets"):
        if _has_index("knowledge_eval_sets", "ix_knowledge_eval_sets_project_id"):
            op.drop_index(
                "ix_knowledge_eval_sets_project_id", table_name="knowledge_eval_sets"
            )
        op.drop_table("knowledge_eval_sets")
    if _has_table("knowledge_mind_maps"):
        if _has_index("knowledge_mind_maps", "ix_knowledge_mind_maps_project_id"):
            op.drop_index(
                "ix_knowledge_mind_maps_project_id", table_name="knowledge_mind_maps"
            )
        op.drop_table("knowledge_mind_maps")
    if _has_table("knowledge_links"):
        if _has_index("knowledge_links", "ix_knowledge_links_project_id"):
            op.drop_index("ix_knowledge_links_project_id", table_name="knowledge_links")
        op.drop_table("knowledge_links")
    if _has_table("knowledge_canvas_versions"):
        if _has_index(
            "knowledge_canvas_versions", "ix_knowledge_canvas_versions_canvas_id"
        ):
            op.drop_index(
                "ix_knowledge_canvas_versions_canvas_id",
                table_name="knowledge_canvas_versions",
            )
        op.drop_table("knowledge_canvas_versions")
    if _has_table("knowledge_chunks"):
        for idx in (
            "ix_knowledge_chunks_collection_id",
            "ix_knowledge_chunks_canvas_id",
            "ix_knowledge_chunks_project_id",
        ):
            if _has_index("knowledge_chunks", idx):
                op.drop_index(idx, table_name="knowledge_chunks")
        op.drop_table("knowledge_chunks")
    if _has_column("knowledge_canvases", "collection_id") or _has_column(
        "knowledge_canvases", "source_url"
    ):
        with op.batch_alter_table("knowledge_canvases") as batch:
            fk_names = {
                fk.get("name") for fk in _inspector().get_foreign_keys("knowledge_canvases")
            }
            if "fk_knowledge_canvases_collection_id" in fk_names:
                batch.drop_constraint(
                    "fk_knowledge_canvases_collection_id", type_="foreignkey"
                )
            if _has_index("knowledge_canvases", "ix_knowledge_canvases_collection_id"):
                batch.drop_index("ix_knowledge_canvases_collection_id")
            for col in (
                "repo_path",
                "last_fetched_at",
                "etag",
                "content_hash",
                "source_url",
                "collection_id",
            ):
                if _has_column("knowledge_canvases", col):
                    batch.drop_column(col)
    if _has_table("agent_collection_grants"):
        for idx in (
            "ix_agent_collection_grants_collection_id",
            "ix_agent_collection_grants_agent_id",
        ):
            if _has_index("agent_collection_grants", idx):
                op.drop_index(idx, table_name="agent_collection_grants")
        op.drop_table("agent_collection_grants")
    if _has_table("knowledge_collections"):
        for idx in (
            "ix_knowledge_collections_owner_user_id",
            "ix_knowledge_collections_project_id",
        ):
            if _has_index("knowledge_collections", idx):
                op.drop_index(idx, table_name="knowledge_collections")
        op.drop_table("knowledge_collections")
