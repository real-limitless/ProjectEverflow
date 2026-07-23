"""Knowledge canvas request/response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

KnowledgeOrigin = Literal["created", "upload", "ocr", "web"]
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


class KnowledgeCanvasCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    content_md: str = ""
    origin: KnowledgeOrigin = "created"
    status: EmbedStatus = "ready"
    mime: str | None = Field(default=None, max_length=120)
    size_label: str | None = Field(default=None, max_length=64)


class KnowledgeCanvasUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    content_md: str | None = None
    origin: KnowledgeOrigin | None = None
    status: EmbedStatus | None = None
    chunks: int | None = None
    mime: str | None = Field(default=None, max_length=120)
    size_label: str | None = Field(default=None, max_length=64)


class KnowledgeCanvasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    content_md: str
    origin: str
    status: str
    chunks: int | None = None
    mime: str | None = None
    size_label: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeCanvasSummary(BaseModel):
    """List view without full markdown body."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    origin: str
    status: str
    chunks: int | None = None
    mime: str | None = None
    size_label: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class WebSearchHit(BaseModel):
    """Mapped SearXNG result for knowledge web search."""

    id: str
    title: str
    url: str
    snippet: str
