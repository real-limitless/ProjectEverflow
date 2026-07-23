"""Sandbox access token schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SandboxTokenCreate(BaseModel):
    label: str | None = Field(default="opencode-mcp", max_length=120)
    scopes: list[str] | None = None
    ttl_seconds: int | None = Field(default=None, ge=60, le=60 * 60 * 24 * 30)
    revoke_existing: bool = False


class SandboxTokenCreated(BaseModel):
    """Returned once on mint — includes the raw token."""

    id: UUID
    project_id: UUID
    user_id: UUID
    prefix: str
    scopes: list[str]
    label: str | None = None
    expires_at: datetime
    token: str


class SandboxTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    user_id: UUID
    prefix: str
    scopes: list[str] | None = None
    label: str | None = None
    expires_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class McpContextRead(BaseModel):
    """Whoami payload for Everflow MCP / sandbox clients."""

    via: str
    user_id: UUID
    user_email: str | None = None
    project_id: UUID
    project_name: str
    project_slug: str
    organization_id: UUID
    sandbox_status: str
    scopes: list[str] = Field(default_factory=list)
