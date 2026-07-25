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
from app.core.principal import Principal, get_principal, get_project_for_principal
from app.schemas.sandbox import (
    BrowserModeRequest,
    BrowserStatusRead,
    DesktopResizeRequest,
    DesktopResizeResponse,
    SandboxExecRequest,
    SandboxExecResult,
    SandboxFsEntry,
    SandboxFsWriteRequest,
    SandboxStatusRead,
)
from app.services.sandbox import (
    MISSING_ON_AGENT,
    mark_sandbox_missing,
    reconfigure_project_sandbox,
    recreate_project_sandbox,
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


def _is_agent_path_missing(exc: SandboxAgentError) -> bool:
    """True when agent 404 means a guest path is missing (not the sandbox itself)."""
    msg = str(exc).lower()
    return "path not found" in msg or "not a directory" in msg


async def _fs_agent_error(
    session: AsyncSession,
    project: Project,
    exc: SandboxAgentError,
) -> HTTPException:
    """Map agent FS errors: missing path → 404; missing sandbox → mark + 409."""
    if exc.status_code == 404 and _is_agent_path_missing(exc):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if exc.status_code == 404:
        await mark_sandbox_missing(session, project)
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=MISSING_ON_AGENT,
        )
    return _agent_http_error(exc)


def _status_read(
    project: Project,
    agent_info: dict | None = None,
    *,
    reconfigure_mode: str | None = None,
) -> SandboxStatusRead:
    return SandboxStatusRead(
        project_id=project.id,
        sandbox_name=project.sandbox_name,
        status=project.sandbox_status,
        image=project.sandbox_image,
        error=project.sandbox_error,
        created_at=project.sandbox_created_at,
        agent=agent_info,
        reconfigure_mode=reconfigure_mode,
    )


@router.get("/projects/{project_id}/sandbox", response_model=SandboxStatusRead)
async def get_sandbox_status(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxStatusRead:
    project, agent_info = await refresh_sandbox_status(session, project, settings=settings)
    return _status_read(project, agent_info)


async def _bg_recreate(project_id: UUID) -> None:
    from app.api.v1.projects import _clone_repos_for_project
    from app.config import get_settings
    from app.db.session import get_session_factory

    settings = get_settings()
    factory = get_session_factory()
    async with factory() as bg_session:
        project = await recreate_project_sandbox(bg_session, project_id, settings=settings)
        if project.sandbox_status == "running":
            # Reset clone status so recreate re-pulls remotes into the new workspace
            repos = list(project.repos or [])
            if repos:
                reset: list[dict] = []
                for r in repos:
                    if not isinstance(r, dict):
                        continue
                    item = dict(r)
                    if item.get("url"):
                        item["clone_status"] = "pending"
                        item["clone_error"] = None
                    reset.append(item)
                project.repos = reset
                await bg_session.commit()
                await bg_session.refresh(project)
                await _clone_repos_for_project(bg_session, project, settings)


@router.post("/projects/{project_id}/sandbox/reconfigure", response_model=SandboxStatusRead)
async def reconfigure_sandbox(
    background_tasks: BackgroundTasks,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxStatusRead:
    """Apply the project's harness list to the sandbox (bootstrap or recreate)."""
    if not settings.sandbox_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sandbox disabled")

    try:
        project, mode = await reconfigure_project_sandbox(
            session, project, settings=settings
        )
    except SandboxAgentError as exc:
        raise _agent_http_error(exc) from exc

    if mode == "recreate":
        project.sandbox_status = "pending"
        project.sandbox_error = None
        if project.repos:
            reset = []
            for r in project.repos:
                if not isinstance(r, dict):
                    continue
                item = dict(r)
                if item.get("url"):
                    item["clone_status"] = "pending"
                    item["clone_error"] = None
                reset.append(item)
            project.repos = reset
        await session.commit()
        await session.refresh(project)
        background_tasks.add_task(_bg_recreate, project.id)
        return _status_read(project, reconfigure_mode="recreate")

    return _status_read(project, reconfigure_mode="bootstrap")


@router.post("/projects/{project_id}/sandbox/retry", response_model=SandboxStatusRead)
@router.post("/projects/{project_id}/sandbox/recreate", response_model=SandboxStatusRead)
async def recreate_sandbox(
    background_tasks: BackgroundTasks,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxStatusRead:
    """Force recreate: remove on agent if present, then provision again."""
    if not settings.sandbox_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sandbox disabled")

    project.sandbox_status = "pending"
    project.sandbox_error = None
    # Mark remotes pending so UI knows clone will re-run
    if project.repos:
        reset = []
        for r in project.repos:
            if not isinstance(r, dict):
                continue
            item = dict(r)
            if item.get("url"):
                item["clone_status"] = "pending"
                item["clone_error"] = None
            reset.append(item)
        project.repos = reset
    await session.commit()
    await session.refresh(project)

    background_tasks.add_task(_bg_recreate, project.id)
    return _status_read(project)


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
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=MISSING_ON_AGENT,
            ) from exc
        raise _agent_http_error(exc) from exc
    project.sandbox_status = str(info.get("status") or "running")
    project.sandbox_error = None
    await session.commit()
    await session.refresh(project)
    return _status_read(project, info)


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
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=MISSING_ON_AGENT,
            ) from exc
        raise _agent_http_error(exc) from exc
    project.sandbox_status = str(info.get("status") or "stopped")
    await session.commit()
    await session.refresh(project)
    return _status_read(project, info)


@router.post("/projects/{project_id}/sandbox/exec", response_model=SandboxExecResult)
async def exec_in_sandbox(
    body: SandboxExecRequest,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SandboxExecResult:
    name = _require_name(project)
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
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=MISSING_ON_AGENT,
            ) from exc
        raise _agent_http_error(exc) from exc
    return SandboxExecResult(
        exit_code=int(result.get("exit_code", 1)),
        stdout=str(result.get("stdout", "")),
        stderr=str(result.get("stderr", "")),
    )


@router.post(
    "/projects/{project_id}/sandbox/desktop/resize",
    response_model=DesktopResizeResponse,
)
async def resize_sandbox_desktop(
    body: DesktopResizeRequest,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> DesktopResizeResponse:
    """Resize the guest noVNC desktop framebuffer to the panel size."""
    name = _require_name(project)
    if project.sandbox_status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox is not running (status={project.sandbox_status})",
        )
    client = SandboxAgentClient(settings)
    try:
        result = await client.resize_desktop(name, width=body.width, height=body.height)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=MISSING_ON_AGENT,
            ) from exc
        raise _agent_http_error(exc) from exc
    return DesktopResizeResponse(
        ok=bool(result.get("ok", False)),
        width=int(result.get("width", body.width)),
        height=int(result.get("height", body.height)),
        message=str(result.get("message", "")),
    )


@router.get(
    "/projects/{project_id}/sandbox/browser/status",
    response_model=BrowserStatusRead,
)
async def get_sandbox_browser_status(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> BrowserStatusRead:
    """Playwright browser harness status (JWT or sandbox token)."""
    principal.require_scope("project:read")
    name = _require_name(project)
    if project.sandbox_status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox is not running (status={project.sandbox_status})",
        )
    client = SandboxAgentClient(settings)
    try:
        result = await client.browser_status(name)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=MISSING_ON_AGENT,
            ) from exc
        raise _agent_http_error(exc) from exc
    return BrowserStatusRead(**result)


@router.post(
    "/projects/{project_id}/sandbox/browser/mode",
    response_model=BrowserStatusRead,
)
async def set_sandbox_browser_mode(
    body: BrowserModeRequest,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> BrowserStatusRead:
    """Switch headless/headed browser mode; headed ensures Desktop (JWT or sandbox token)."""
    principal.require_scope("project:read")
    name = _require_name(project)
    if project.sandbox_status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox is not running (status={project.sandbox_status})",
        )
    client = SandboxAgentClient(settings)
    try:
        result = await client.browser_set_mode(
            name,
            mode=body.mode,
            restart_opencode=body.restart_opencode,
        )
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=MISSING_ON_AGENT,
            ) from exc
        raise _agent_http_error(exc) from exc
    return BrowserStatusRead(**result)


@router.get("/projects/{project_id}/sandbox/fs", response_model=list[SandboxFsEntry])
async def list_sandbox_fs(
    path: str = ".",
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> list[SandboxFsEntry]:
    name = _require_name(project)
    client = SandboxAgentClient(settings)
    try:
        entries = await client.list_fs(name, path)
    except SandboxAgentError as exc:
        raise await _fs_agent_error(session, project, exc) from exc
    return [SandboxFsEntry(**e) for e in entries]


@router.get("/projects/{project_id}/sandbox/fs/content")
async def read_sandbox_fs(
    path: str,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    name = _require_name(project)
    client = SandboxAgentClient(settings)
    try:
        text = await client.read_fs(name, path)
    except SandboxAgentError as exc:
        raise await _fs_agent_error(session, project, exc) from exc
    return PlainTextResponse(text)


@router.put("/projects/{project_id}/sandbox/fs/content", status_code=status.HTTP_204_NO_CONTENT)
async def write_sandbox_fs(
    path: str,
    body: SandboxFsWriteRequest,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> None:
    name = _require_name(project)
    client = SandboxAgentClient(settings)
    try:
        await client.write_fs(name, path, body.content)
    except SandboxAgentError as exc:
        raise await _fs_agent_error(session, project, exc) from exc
