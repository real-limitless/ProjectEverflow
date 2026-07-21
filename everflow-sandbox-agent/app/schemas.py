"""Request/response models for the internal sandbox-agent API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SandboxCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    image: str | None = None
    cpus: int | None = Field(default=None, ge=1, le=64)
    memory_mib: int | None = Field(default=None, ge=256, le=131072)
    labels: dict[str, str] = Field(default_factory=dict)
    harnesses: list[str] = Field(default_factory=list)
    workspace_host_path: str | None = None
    # When true, replace any existing sandbox with the same name (keep workspace dir).
    replace: bool = False


class ExecRequest(BaseModel):
    cmd: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=120, ge=1, le=3600)


class ExecResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class BootstrapRequest(BaseModel):
    harnesses: list[str] = Field(default_factory=list)


class FsWriteRequest(BaseModel):
    content: str
    encoding: str = "utf-8"


class FsEntry(BaseModel):
    path: str
    name: str
    is_dir: bool
    size: int | None = None


class SandboxInfo(BaseModel):
    name: str
    status: str
    image: str
    labels: dict[str, str] = Field(default_factory=dict)
    harnesses: list[str] = Field(default_factory=list)
    workspace_path: str | None = None
    created_at: datetime | None = None
    error: str | None = None
    metrics: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    kvm: bool
    sdk: str
    mock: bool


class OpenCodeEnsureRequest(BaseModel):
    force_restart: bool = False


class OpenCodeEnsureResponse(BaseModel):
    sandbox_name: str
    healthy: bool
    port: int | None = None
    base_url: str | None = None
    version: str | None = None
    mode: str | None = None
    pid: int | None = None
    workspace: str | None = None
    error: str | None = None


class ListeningPortInfo(BaseModel):
    port: int
    address: str
    protocol: str = "tcp"
    process: str | None = None
    http_likely: bool = False
    label: str = ""


class PortsListResponse(BaseModel):
    sandbox_name: str
    ports: list[ListeningPortInfo] = Field(default_factory=list)
