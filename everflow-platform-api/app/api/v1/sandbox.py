"""Public project sandbox routes (proxy to internal sandbox-agent)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.project import Project
from app.schemas.sandbox import (
    SandboxExecRequest,
    SandboxExecResult,
    SandboxFsEntry,
    SandboxFsWriteRequest,
    SandboxStatusRead,
)
from app.services.sandbox import (
    destroy_project_sandbox,
    provision_project_sandbox,
    refresh_sandbox_status,
)
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["sandbox"])


def _require_name(project: Project) -> str:
    if not project.sandbox_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has no sandbox yet",
        )
    return project.sandbox_name


def _agent_http_error(exc: SandboxAgentError) -> HTTPException:
    code = exc.status_code or status.HTTP_502_BAD_GATEWAY
    if code == 404:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if code == 409:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if code >= 500 or code is None:
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/projects/{project_id}/sandbox", response_model=SandboxStatusRead)
async def get_sandbox_status(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxStatusRead:
    project = await refresh_sandbox_status(session, project, settings=settings)
    agent_info = None
    if settings.sandbox_enabled and project.sandbox_name:
        try:
            agent_info = await SandboxAgentClient(settings).get_sandbox(project.sandbox_name)
        except SandboxAgentError:
            agent_info = None
    return SandboxStatusRead(
        project_id=project.id,
        sandbox_name=project.sandbox_name,
        status=project.sandbox_status,
        image=project.sandbox_image,
        error=project.sandbox_error,
        created_at=project.sandbox_created_at,
        agent=agent_info,
    )


@router.post("/projects/{project_id}/sandbox/retry", response_model=SandboxStatusRead)
async def retry_sandbox(
    background_tasks: BackgroundTasks,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxStatusRead:
    if not settings.sandbox_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sandbox disabled")

    project.sandbox_status = "pending"
    project.sandbox_error = None
    await session.commit()
    await session.refresh(project)

    background_tasks.add_task(_bg_provision, project.id)

    return SandboxStatusRead(
        project_id=project.id,
        sandbox_name=project.sandbox_name,
        status=project.sandbox_status,
        image=project.sandbox_image,
        error=project.sandbox_error,
        created_at=project.sandbox_created_at,
    )


async def _bg_provision(project_id: UUID) -> None:
    from app.config import get_settings
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as bg_session:
        await provision_project_sandbox(bg_session, project_id, settings=get_settings())


@router.post("/projects/{project_id}/sandbox/start", response_model=SandboxStatusRead)
async def start_sandbox(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxStatusRead:
    name = _require_name(project)
    client = SandboxAgentClient(settings)
    try:
        info = await client.start_sandbox(name)
    except SandboxAgentError as exc:
        raise _agent_http_error(exc) from exc
    project.sandbox_status = str(info.get("status") or "running")
    project.sandbox_error = None
    await session.commit()
    await session.refresh(project)
    return SandboxStatusRead(
        project_id=project.id,
        sandbox_name=project.sandbox_name,
        status=project.sandbox_status,
        image=project.sandbox_image,
        error=project.sandbox_error,
        created_at=project.sandbox_created_at,
        agent=info,
    )


@router.post("/projects/{project_id}/sandbox/stop", response_model=SandboxStatusRead)
async def stop_sandbox(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxStatusRead:
    name = _require_name(project)
    client = SandboxAgentClient(settings)
    try:
        info = await client.stop_sandbox(name)
    except SandboxAgentError as exc:
        raise _agent_http_error(exc) from exc
    project.sandbox_status = str(info.get("status") or "stopped")
    await session.commit()
    await session.refresh(project)
    return SandboxStatusRead(
        project_id=project.id,
        sandbox_name=project.sandbox_name,
        status=project.sandbox_status,
        image=project.sandbox_image,
        error=project.sandbox_error,
        created_at=project.sandbox_created_at,
        agent=info,
    )


@router.post("/projects/{project_id}/sandbox/exec", response_model=SandboxExecResult)
async def exec_in_sandbox(
    body: SandboxExecRequest,
    project: Project = Depends(get_project_for_member),
    settings: Settings = Depends(get_settings),
) -> SandboxExecResult:
    name = _require_name(project)
    if project.sandbox_status not in ("running", "creating"):
        # allow running only for real work
        if project.sandbox_status != "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sandbox is not running (status={project.sandbox_status})",
            )
    client = SandboxAgentClient(settings)
    try:
        result = await client.exec(
            name,
            cmd=body.cmd,
            args=body.args,
            cwd=body.cwd,
            env=body.env or None,
            timeout_seconds=body.timeout_seconds,
        )
    except SandboxAgentError as exc:
        raise _agent_http_error(exc) from exc
    return SandboxExecResult(
        exit_code=int(result.get("exit_code", 1)),
        stdout=str(result.get("stdout", "")),
        stderr=str(result.get("stderr", "")),
    )


@router.get("/projects/{project_id}/sandbox/fs", response_model=list[SandboxFsEntry])
async def list_sandbox_fs(
    path: str = ".",
    project: Project = Depends(get_project_for_member),
    settings: Settings = Depends(get_settings),
) -> list[SandboxFsEntry]:
    name = _require_name(project)
    client = SandboxAgentClient(settings)
    try:
        entries = await client.list_fs(name, path)
    except SandboxAgentError as exc:
        raise _agent_http_error(exc) from exc
    return [SandboxFsEntry(**e) for e in entries]


@router.get("/projects/{project_id}/sandbox/fs/content")
async def read_sandbox_fs(
    path: str,
    project: Project = Depends(get_project_for_member),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    name = _require_name(project)
    client = SandboxAgentClient(settings)
    try:
        text = await client.read_fs(name, path)
    except SandboxAgentError as exc:
        raise _agent_http_error(exc) from exc
    return PlainTextResponse(text)


@router.put("/projects/{project_id}/sandbox/fs/content", status_code=status.HTTP_204_NO_CONTENT)
async def write_sandbox_fs(
    path: str,
    body: SandboxFsWriteRequest,
    project: Project = Depends(get_project_for_member),
    settings: Settings = Depends(get_settings),
) -> None:
    name = _require_name(project)
    client = SandboxAgentClient(settings)
    try:
        await client.write_fs(name, path, body.content)
    except SandboxAgentError as exc:
        raise _agent_http_error(exc) from exc
