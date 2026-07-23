"""Deploy keys, nodes, routes, and compose discovery schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeploySshKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    fingerprint: str
    public_key: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DeploySshKeyGenerateResult(BaseModel):
    id: UUID
    project_id: UUID
    fingerprint: str
    public_key: str
    created_at: datetime


class DeployNodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    ssh_user: str = Field(default="everflow", min_length=1, max_length=128)
    tags: list[str] = Field(default_factory=list)
    status: str = Field(default="unknown", max_length=32)

    @field_validator("name", "host", "ssh_user")
    @classmethod
    def strip_required(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("value is required")
        return s

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, v: list[str]) -> list[str]:
        return [t.strip() for t in v if t and t.strip()]

    @field_validator("status")
    @classmethod
    def normalize_status(cls, v: str) -> str:
        s = (v or "unknown").strip().lower() or "unknown"
        if s not in {"unknown", "online", "offline"}:
            raise ValueError("status must be unknown, online, or offline")
        return s


class DeployNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    host: str
    port: int
    ssh_user: str
    tags: list[str] = Field(default_factory=list)
    status: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DeployRouteCreate(BaseModel):
    host_header: str = Field(min_length=1, max_length=255)
    service_name: str = Field(min_length=1, max_length=200)
    service_port: int = Field(default=80, ge=1, le=65535)
    path_prefix: str = Field(default="/", max_length=512)

    @field_validator("host_header", "service_name")
    @classmethod
    def strip_required(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("value is required")
        return s

    @field_validator("path_prefix")
    @classmethod
    def normalize_prefix(cls, v: str) -> str:
        s = (v or "/").strip() or "/"
        if not s.startswith("/"):
            s = "/" + s
        return s


class DeployRouteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    node_id: UUID
    host_header: str
    service_name: str
    service_port: int
    path_prefix: str
    created_at: datetime
    updated_at: datetime


class ComposeFilesRead(BaseModel):
    files: list[str] = Field(default_factory=list)
    message: str | None = None


class DeployRunStubRequest(BaseModel):
    node_id: UUID
    compose_file: str = Field(min_length=1, max_length=512)
    action: str = Field(default="up", max_length=32)

    @field_validator("compose_file")
    @classmethod
    def strip_compose(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("compose_file is required")
        return s

    @field_validator("action")
    @classmethod
    def normalize_action(cls, v: str) -> str:
        a = (v or "up").strip().lower() or "up"
        if a not in {"up", "down", "validate", "redeploy"}:
            raise ValueError("action must be up, down, validate, or redeploy")
        return a


class DeployRunStubRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    node_id: UUID | None
    compose_file: str | None
    action: str
    status: str
    message: str | None = None
    created_at: datetime
