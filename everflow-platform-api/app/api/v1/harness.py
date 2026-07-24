"""Project-scoped OpenCode harness pack (agents, skills, MCP)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.project import Project
from app.services.sandbox import mark_sandbox_missing
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["harness"])


class OpenCodeHarnessPackBody(BaseModel):
    agents: list[dict[str, Any]] | None = None
    skills: list[dict[str, Any]] | None = None
    commands: list[dict[str, Any]] | None = None
    mcp: dict[str, Any] | None = None
    plugin: list[str] | None = None
    marketplace_items: list[dict[str, Any]] | None = None
    remove_agents: list[str] = Field(default_factory=list)
    remove_skills: list[str] = Field(default_factory=list)
    remove_commands: list[str] = Field(default_factory=list)
    remove_plugins: list[str] = Field(default_factory=list)
    remove_marketplace_items: list[dict[str, Any]] = Field(default_factory=list)
    replace_all_agents: bool = False
    replace_all_skills: bool = False
    replace_all_commands: bool = False
    model: str | None = None
    small_model: str | None = None
    default_agent: str | None = None
    manifest: dict[str, Any] | None = None
    agent_meta: dict[str, Any] | None = None


def _require_running_sandbox(project: Project) -> str:
    if not project.sandbox_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has no sandbox yet",
        )
    if project.sandbox_status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox is not running (status={project.sandbox_status})",
        )
    return project.sandbox_name


def _agent_http_error(exc: SandboxAgentError) -> HTTPException:
    code = exc.status_code or status.HTTP_502_BAD_GATEWAY
    if code == 404:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if code == 409:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if code == 400:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if code == 501:
        return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    if code == 503:
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if code >= 500 or code is None:
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/projects/{project_id}/harness/opencode")
async def get_opencode_harness(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Read agents/skills/MCP pack from the project sandbox workspace."""
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        return await client.get_opencode_harness(name)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc


@router.put("/projects/{project_id}/harness/opencode")
async def put_opencode_harness(
    body: OpenCodeHarnessPackBody,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Write/merge agents, skills, and MCP into the project sandbox for OpenCode."""
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        return await client.put_opencode_harness(
            name,
            body.model_dump(exclude_none=True),
        )
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc
