"""Project-scoped background jobs (proxy to sandbox-agent detached processes)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.project import Project
from app.services.sandbox import mark_sandbox_missing
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["jobs"])


class JobCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    command: str = Field(min_length=1, max_length=4000)
    cwd: str | None = Field(default=None, max_length=1024)


class JobRead(BaseModel):
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


class JobLogsRead(BaseModel):
    job_id: str
    status: str | None = None
    tail: int = 200
    content: str = ""


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
    if code >= 500 or code is None:
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=code, detail=str(exc))


def _job_read(data: dict[str, Any]) -> JobRead:
    return JobRead(
        id=str(data.get("id") or ""),
        title=str(data.get("title") or ""),
        command=str(data.get("command") or ""),
        cwd=data.get("cwd"),
        pid=int(data["pid"]) if data.get("pid") is not None else None,
        status=str(data.get("status") or "unknown"),
        log_path=data.get("log_path"),
        created_at=data.get("created_at"),
        updated_at=data.get("updated_at"),
        exit_code=data.get("exit_code"),
    )


@router.get("/projects/{project_id}/jobs", response_model=list[JobRead])
async def list_project_jobs(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> list[JobRead]:
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        rows = await client.list_jobs(name)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc
    return [_job_read(r) for r in rows]


@router.post(
    "/projects/{project_id}/jobs",
    response_model=JobRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_job(
    body: JobCreateBody,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> JobRead:
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        data = await client.create_job(
            name,
            title=body.title,
            command=body.command,
            cwd=body.cwd,
        )
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc
    return _job_read(data)


@router.get(
    "/projects/{project_id}/jobs/{job_id}/logs",
    response_model=JobLogsRead,
)
async def get_project_job_logs(
    job_id: str,
    tail: int = Query(default=200, ge=1, le=5000),
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> JobLogsRead:
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        data = await client.get_job_logs(name, job_id, tail=tail)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            # Distinguish sandbox missing vs job missing via body
            detail = str(exc).lower()
            if "sandbox" in detail:
                await mark_sandbox_missing(session, project)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Sandbox missing on agent; recreate the sandbox",
                ) from exc
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
        raise _agent_http_error(exc) from exc
    return JobLogsRead(
        job_id=str(data.get("job_id") or job_id),
        status=data.get("status"),
        tail=int(data.get("tail") or tail),
        content=str(data.get("content") or ""),
    )


@router.post(
    "/projects/{project_id}/jobs/{job_id}/kill",
    response_model=JobRead,
)
async def kill_project_job(
    job_id: str,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> JobRead:
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        data = await client.kill_job(name, job_id)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            detail = str(exc).lower()
            if "sandbox" in detail:
                await mark_sandbox_missing(session, project)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Sandbox missing on agent; recreate the sandbox",
                ) from exc
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
        raise _agent_http_error(exc) from exc
    return _job_read(data)
