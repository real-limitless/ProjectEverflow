"""Knowledge canvas / RAG request-response schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

KnowledgeOrigin = Literal["created", "upload", "ocr", "web", "repo", "research"]
EmbedStatus = Literal[
    "ready",
    "uploading",
    "ocr",
    "chunking",
    "embedding",
    "indexed",
    "stale",
    "error",
]
CollectionVisibility = Literal["personal", "team", "agent"]


class KnowledgeCanvasCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    content_md: str = ""
    origin: KnowledgeOrigin = "created"
    status: EmbedStatus = "ready"
    mime: str | None = Field(default=None, max_length=120)
    size_label: str | None = Field(default=None, max_length=64)
    collection_id: UUID | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    repo_path: str | None = Field(default=None, max_length=1024)


class KnowledgeCanvasUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    content_md: str | None = None
    origin: KnowledgeOrigin | None = None
    status: EmbedStatus | None = None
    chunks: int | None = None
    mime: str | None = Field(default=None, max_length=120)
    size_label: str | None = Field(default=None, max_length=64)
    collection_id: UUID | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    repo_path: str | None = Field(default=None, max_length=1024)


class KnowledgeCanvasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    collection_id: UUID | None = None
    name: str
    description: str | None = None
    content_md: str
    origin: str
    status: str
    chunks: int | None = None
    mime: str | None = None
    size_label: str | None = None
    source_url: str | None = None
    content_hash: str | None = None
    etag: str | None = None
    last_fetched_at: datetime | None = None
    repo_path: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeCanvasSummary(BaseModel):
    """List view without full markdown body."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    collection_id: UUID | None = None
    name: str
    description: str | None = None
    origin: str
    status: str
    chunks: int | None = None
    mime: str | None = None
    size_label: str | None = None
    source_url: str | None = None
    content_hash: str | None = None
    last_fetched_at: datetime | None = None
    repo_path: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class WebSearchHit(BaseModel):
    id: str
    title: str
    url: str
    snippet: str
    reader_markdown: str | None = None


class WebReadRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class WebReadResult(BaseModel):
    url: str
    title: str
    markdown: str
    content_type: str = "text/html"


class KnowledgeRetrieveRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    collection_ids: list[UUID] | None = None
    agent_id: UUID | None = None


class KnowledgeRetrieveHit(BaseModel):
    canvas_id: UUID
    canvas_name: str
    chunk_id: UUID
    text: str
    score: float
    source_url: str | None = None
    path: str | None = None
    collection_id: UUID | None = None


class KnowledgeRetrieveResult(BaseModel):
    hits: list[KnowledgeRetrieveHit]


class KnowledgeCollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    visibility: CollectionVisibility = "team"
    owner_user_id: UUID | None = None


class KnowledgeCollectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    visibility: CollectionVisibility | None = None


class KnowledgeCollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    visibility: str
    owner_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AgentCollectionGrantUpsert(BaseModel):
    agent_id: UUID
    can_retrieve: bool = True
    can_write: bool = False


class AgentCollectionGrantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    collection_id: UUID
    can_retrieve: bool
    can_write: bool


class KnowledgeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canvas_id: UUID
    content_md: str
    created_by: UUID | None = None
    label: str | None = None
    created_at: datetime


class KnowledgeLinkCreate(BaseModel):
    from_type: str = Field(min_length=1, max_length=32)
    from_id: str = Field(min_length=1, max_length=64)
    to_type: str = Field(min_length=1, max_length=32)
    to_id: str = Field(min_length=1, max_length=64)
    rel: str = Field(default="derived_from", max_length=32)


class KnowledgeLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    rel: str
    created_at: datetime


class KnowledgeMindMapCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mermaid: str = ""


class KnowledgeMindMapUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    mermaid: str | None = None


class KnowledgeMindMapRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    mermaid: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeEvalQuestionCreate(BaseModel):
    question: str = Field(min_length=1)
    expected_canvas_ids: list[str] | None = None
    expected_notes: str | None = None


class KnowledgeEvalSetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    collection_id: UUID | None = None
    questions: list[KnowledgeEvalQuestionCreate] = Field(default_factory=list)


class KnowledgeEvalQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question: str
    expected_canvas_ids: list[str] | None = None
    expected_notes: str | None = None


class KnowledgeEvalSetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    collection_id: UUID | None = None
    last_score: float | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    questions: list[KnowledgeEvalQuestionRead] = Field(default_factory=list)


class KnowledgeEvalQuestionResult(BaseModel):
    question_id: UUID
    question: str
    hit: bool
    expected_canvas_ids: list[str]
    retrieved_canvas_ids: list[str]
    top_score: float | None = None


class KnowledgeEvalRunResult(BaseModel):
    eval_set_id: UUID
    score: float
    total: int
    hits: int
    results: list[KnowledgeEvalQuestionResult]


class RefreshSourceResult(BaseModel):
    canvas: KnowledgeCanvasRead
    changed: bool
    previous_hash: str | None = None
    new_hash: str | None = None


class RepoIndexRequest(BaseModel):
    paths: list[str] | None = None
    collection_name: str = "Repo docs"


class RepoIndexResult(BaseModel):
    created: int
    updated: int
    skipped: int
    canvas_ids: list[UUID]


class ResearchPromoteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    mode: Literal["thread", "claims"] = "thread"
    source_url: str | None = None
    article_title: str | None = None
    thread: list[dict[str, Any]] = Field(default_factory=list)
    article_markdown: str = ""
