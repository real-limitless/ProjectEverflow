"""Workflow request/response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowImportBody(BaseModel):
    """POST body: raw n8n export JSON (or wrapper with document)."""

    document: dict[str, Any] | None = None
    # Allow posting the n8n export at the top level via model_extra — handled in route
    name: str | None = Field(default=None, max_length=300)
    active: bool | None = None
    credential_bindings: dict[str, str] | None = None


class WorkflowCreateBody(BaseModel):
    """Create a blank (or optionally documented) workflow."""

    name: str = Field(default="Untitled workflow", min_length=1, max_length=300)
    active: bool = False
    document: dict[str, Any] | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    active: bool | None = None
    n8n_document: dict[str, Any] | None = None
    credential_bindings: dict[str, str] | None = None


class WorkflowGraphNode(BaseModel):
    id: str
    name: str
    type: str
    type_version: float | int | None = None
    position: dict[str, float]
    parameters: dict[str, Any] = Field(default_factory=dict)
    credentials: dict[str, Any] | None = None
    category: str
    supported: bool
    disabled: bool = False
    retry_on_fail: bool = False
    max_tries: int | None = None
    continue_on_fail: bool = False
    notes: str | None = None
    webhook_id: str | None = None


class WorkflowGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    source_name: str
    target_name: str
    connection_type: str
    source_index: int = 0
    target_index: int = 0
    source_handle: str = "main:0"


class WorkflowGraph(BaseModel):
    nodes: list[WorkflowGraphNode]
    edges: list[WorkflowGraphEdge]
    name: str
    settings: dict[str, Any] = Field(default_factory=dict)
    pin_data: dict[str, Any] = Field(default_factory=dict)
    active: bool = False
    report: dict[str, Any] = Field(default_factory=dict)


class WorkflowSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    active: bool
    trigger_summary: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    node_count: int | None = None
    unsupported_count: int | None = None
    credential_requirements_count: int | None = None


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    active: bool
    trigger_summary: str
    settings: dict[str, Any] | None = None
    credential_bindings: dict[str, Any] | None = None
    import_report: dict[str, Any] | None = None
    n8n_document: dict[str, Any]
    graph: WorkflowGraph
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workflow_id: UUID
    project_id: UUID
    status: str
    trigger_type: str
    error_message: str | None = None
    log: list[Any] | None = None
    started_at: datetime
    finished_at: datetime | None = None


class WorkflowExecuteBody(BaseModel):
    trigger: str = "manual"
    """manual | schedule | executeWorkflow"""
    mocks: dict[str, Any] | None = None
    """Test hooks: ftp_files, agent_output, capture_email, openai_api_key, tool_results"""
    credentials: dict[str, dict[str, Any]] | None = None
    """Inline secrets for this run only (not persisted): {openAiApi: {apiKey}, ftp: {...}, ...}"""
    pin_data: dict[str, list[dict[str, Any]]] | None = None
    dry_run: bool = False
    """When true, prefer mocks (capture_email, optional ftp_files) over live I/O."""
    background: bool = False
    """When true, return immediately with status=running and execute async."""


class WorkflowCredentialCreate(BaseModel):
    credential_type: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    credential_type: str
    name: str
    created_at: datetime
    updated_at: datetime


class WorkflowValidateResponse(BaseModel):
    ok: bool
    missing_credentials: list[dict[str, Any]] = Field(default_factory=list)
    unsupported_types: list[str] = Field(default_factory=list)
    triggers: list[dict[str, Any]] = Field(default_factory=list)
    has_schedule: bool = False
    node_count: int = 0
    edge_count: int = 0
    credential_requirements: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowDataTableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    columns: list[Any] | None = Field(default=None, description="Column schema list")


class WorkflowDataTableSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    project_id: UUID
    name: str
    columns: list[Any] | None = None
    row_count: int = 0
    created_at: datetime
    updated_at: datetime


class WorkflowDataTableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: UUID
    project_id: UUID
    name: str
    columns: list[Any] | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    created_at: datetime
    updated_at: datetime


class WorkflowDataTableRowCreate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
