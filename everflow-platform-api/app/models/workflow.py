"""Project-scoped n8n-compatible workflows and run history."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Workflow(Base):
    """n8n-compatible workflow graph stored as full export document + bindings."""

    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Full n8n export body (source of truth for graph semantics)
    n8n_document: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    # Derived: manual | schedule | executeWorkflow | mixed | unknown
    trigger_summary: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    # Map n8n credential id/name → everflow workflow_credential id (string UUID)
    credential_bindings: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
    # Import diagnostics: supported/unsupported types, required creds
    import_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)
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

    project: Mapped["Project"] = relationship("Project", back_populates="workflows")
    runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )


class WorkflowRun(Base):
    """Single execution of a workflow."""

    __tablename__ = "workflow_runs"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # pending | running | success | error | cancelled
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_pin: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Compact step event log for UI (full I/O may live on steps table later)
    log: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True, default=list)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="runs")


class WorkflowCredential(Base):
    """Encrypted secrets for n8n credential types (ftp, smtp, openAiApi, …)."""

    __tablename__ = "workflow_credentials"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # n8n credential type string e.g. openAiApi, ftp, smtp
    credential_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Fernet token of JSON payload (host, user, password, apiKey, headers, …)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    secret_nonce: Mapped[str] = mapped_column(String(64), nullable=False, default="")
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


class WorkflowDataTable(Base):
    """n8n-style named data table scoped to a project."""

    __tablename__ = "workflow_data_tables"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # Column schema list: [{id, displayName, type}, …]
    schema_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True, default=list)
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

    rows: Mapped[list["WorkflowDataTableRow"]] = relationship(
        "WorkflowDataTableRow",
        back_populates="table",
        cascade="all, delete-orphan",
    )


class WorkflowDataTableRow(Base):
    __tablename__ = "workflow_data_table_rows"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    table_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("workflow_data_tables.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    table: Mapped["WorkflowDataTable"] = relationship("WorkflowDataTable", back_populates="rows")
