"""Project knowledge canvases, chunks, collections, links, and eval sets."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class KnowledgeCollection(Base):
    """Named knowledge scope: personal, team, or agent-granted."""

    __tablename__ = "knowledge_collections"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # personal | team | agent
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="team")
    owner_user_id: Mapped[UUID | None] = mapped_column(GUID, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="knowledge_collections")
    canvases: Mapped[list["KnowledgeCanvas"]] = relationship(
        "KnowledgeCanvas",
        back_populates="collection",
    )
    agent_grants: Mapped[list["AgentCollectionGrant"]] = relationship(
        "AgentCollectionGrant",
        back_populates="collection",
        cascade="all, delete-orphan",
    )


class AgentCollectionGrant(Base):
    """Which project agents may retrieve/write a collection."""

    __tablename__ = "agent_collection_grants"
    __table_args__ = (
        UniqueConstraint("agent_id", "collection_id", name="uq_agent_collection"),
    )

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("project_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("knowledge_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    can_retrieve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_write: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    collection: Mapped["KnowledgeCollection"] = relationship(
        "KnowledgeCollection",
        back_populates="agent_grants",
    )


class KnowledgeCanvas(Base):
    """Markdown knowledge document scoped to a project (studio Knowledge panel)."""

    __tablename__ = "knowledge_canvases"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection_id: Mapped[UUID | None] = mapped_column(
        GUID,
        ForeignKey("knowledge_collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # created | upload | ocr | web | repo | research
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    # ready | uploading | ocr | chunking | embedding | indexed | stale | error
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    chunks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Living web / repo provenance
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repo_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(GUID, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="knowledge_canvases")
    collection: Mapped["KnowledgeCollection | None"] = relationship(
        "KnowledgeCollection",
        back_populates="canvases",
    )
    chunk_rows: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk",
        back_populates="canvas",
        cascade="all, delete-orphan",
    )
    versions: Mapped[list["KnowledgeCanvasVersion"]] = relationship(
        "KnowledgeCanvasVersion",
        back_populates="canvas",
        cascade="all, delete-orphan",
    )


class KnowledgeChunk(Base):
    """Embedded chunk for retrieval. Embedding stored as JSON float list (SQLite-safe)."""

    __tablename__ = "knowledge_chunks"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    canvas_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("knowledge_canvases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collection_id: Mapped[UUID | None] = mapped_column(GUID, nullable=True, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # path, url, heading, etc.
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    canvas: Mapped["KnowledgeCanvas"] = relationship(
        "KnowledgeCanvas",
        back_populates="chunk_rows",
    )


class KnowledgeCanvasVersion(Base):
    """Snapshot of canvas body for diff / freshness UI."""

    __tablename__ = "knowledge_canvas_versions"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    canvas_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("knowledge_canvases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(GUID, nullable=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    canvas: Mapped["KnowledgeCanvas"] = relationship(
        "KnowledgeCanvas",
        back_populates="versions",
    )


class KnowledgeLink(Base):
    """Explicit graph edge between knowledge entities."""

    __tablename__ = "knowledge_links"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_type: Mapped[str] = mapped_column(String(32), nullable=False)
    from_id: Mapped[str] = mapped_column(String(64), nullable=False)
    to_type: Mapped[str] = mapped_column(String(32), nullable=False)
    to_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # derived_from | cites | maps_to | consumed_by
    rel: Mapped[str] = mapped_column(String(32), nullable=False, default="derived_from")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class KnowledgeMindMap(Base):
    """Persisted Mermaid mind map for the Knowledge panel."""

    __tablename__ = "knowledge_mind_maps"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mermaid: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[UUID | None] = mapped_column(GUID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KnowledgeEvalSet(Base):
    """Golden Q&A set for retrieval recall evaluation."""

    __tablename__ = "knowledge_eval_sets"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    collection_id: Mapped[UUID | None] = mapped_column(GUID, nullable=True)
    last_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    questions: Mapped[list["KnowledgeEvalQuestion"]] = relationship(
        "KnowledgeEvalQuestion",
        back_populates="eval_set",
        cascade="all, delete-orphan",
    )


class KnowledgeEvalQuestion(Base):
    __tablename__ = "knowledge_eval_questions"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    eval_set_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("knowledge_eval_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_canvas_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    expected_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    eval_set: Mapped["KnowledgeEvalSet"] = relationship(
        "KnowledgeEvalSet",
        back_populates="questions",
    )
