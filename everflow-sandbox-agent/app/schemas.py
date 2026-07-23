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
    # Everflow MCP bootstrap (platform mints sandbox token and passes these)
    # everflow_api_url: platform URL as seen by the *agent* (for reverse tunnel dial).
    # Guest MCP process uses http://127.0.0.1:<tunnel_port> instead.
    everflow_api_url: str | None = None
    everflow_token: str | None = None
    everflow_project_id: str | None = None
    everflow_mcp_command: str | None = "everflow-mcp"


class ProvidersSecretsRequest(BaseModel):
    """Inject LLM provider API keys into the sandbox (never log values)."""

    # Environment map: OPENAI_API_KEY -> secret, etc.
    env: dict[str, str] = Field(default_factory=dict)
    # Optional OpenCode provider id -> api key (openai, anthropic, openrouter, xai)
    providers: dict[str, str] = Field(default_factory=dict)


class ProvidersSecretsResponse(BaseModel):
    sandbox_name: str
    written: bool
    env_keys: list[str] = Field(default_factory=list)
    opencode_providers: list[str] = Field(default_factory=list)
    path: str | None = None
    error: str | None = None


class OpenCodeEnsureResponse(BaseModel):
    sandbox_name: str
    healthy: bool
    port: int | None = None
    base_url: str | None = None
    version: str | None = None
    mode: str | None = None
    pid: int | None = None
    everflow_mcp: dict[str, Any] | None = None
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


class OpenCodeHarnessPack(BaseModel):
    """Partial pack applied to the sandbox workspace for OpenCode agents/skills/MCP."""

    agents: list[dict[str, Any]] | None = None
    skills: list[dict[str, Any]] | None = None
    mcp: dict[str, Any] | None = None
    remove_agents: list[str] = Field(default_factory=list)
    remove_skills: list[str] = Field(default_factory=list)
    replace_all_agents: bool = False
    replace_all_skills: bool = False
    model: str | None = None
    small_model: str | None = None
    default_agent: str | None = None
    manifest: dict[str, Any] | None = None
    agent_meta: dict[str, Any] | None = None


class OpenCodeHarnessResponse(BaseModel):
    sandbox_name: str
    agents: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    mcp: dict[str, Any] = Field(default_factory=dict)
    manifest: dict[str, Any] = Field(default_factory=dict)
    opencode_json: dict[str, Any] = Field(default_factory=dict)
    written: dict[str, Any] | None = None


class JobCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    command: str = Field(min_length=1, max_length=4000)
    cwd: str | None = Field(default=None, max_length=1024)


class JobUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    command: str | None = Field(default=None, min_length=1, max_length=4000)
    cwd: str | None = Field(default=None, max_length=1024)


class JobInfo(BaseModel):
    id: str
    title: str
    command: str
    cwd: str | None = None
    pid: int | None = None
    status: str
    log_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    exit_code: int | None = None


class JobLogsResponse(BaseModel):
    job_id: str
    status: str | None = None
    tail: int = 200
    content: str = ""
