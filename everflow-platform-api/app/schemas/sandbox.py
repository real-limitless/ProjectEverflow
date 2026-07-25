"""Public sandbox schemas (client-facing via Everflow API)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SandboxStatusRead(BaseModel):
    project_id: UUID
    sandbox_name: str | None
    status: str
    image: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    agent: dict[str, Any] | None = None
    # Present on reconfigure: "bootstrap" (in place) or "recreate" (queued)
    reconfigure_mode: str | None = None


class SandboxExecRequest(BaseModel):
    cmd: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=120, ge=1, le=3600)


class SandboxExecResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class SandboxFsWriteRequest(BaseModel):
    content: str
    encoding: str = "utf-8"


class SandboxFsEntry(BaseModel):
    path: str
    name: str
    is_dir: bool
    size: int | None = None


class DesktopResizeRequest(BaseModel):
    """Match the Desktop panel CSS size to the guest X framebuffer."""

    width: int = Field(ge=640, le=3840)
    height: int = Field(ge=480, le=2160)


class DesktopResizeResponse(BaseModel):
    ok: bool
    width: int
    height: int
    message: str = ""


class BrowserModeRequest(BaseModel):
    mode: str = Field(default="headless", pattern="^(headless|headed|headful|visible)$")
    restart_opencode: bool = True


class BrowserStatusRead(BaseModel):
    sandbox_name: str
    enabled: bool = False
    mode: str = "headless"
    mcp_configured: bool = False
    wrapper_present: bool = False
    browsers_present: bool = False
    desktop_listening: bool = False
    display: str = ":99"
    browsers_path: str = "/opt/everflow-browsers"
    hints: list[str] = Field(default_factory=list)
    playwright_mcp: dict[str, Any] | None = None
    ok: bool | None = None
    desktop_action: dict[str, Any] | None = None
    opencode_restart: dict[str, Any] | None = None
