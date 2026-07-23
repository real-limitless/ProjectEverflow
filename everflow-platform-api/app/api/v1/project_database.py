"""Project-scoped database status / tables / read-only query (via sandbox psql)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.project import Project
from app.schemas.database import (
    DatabaseQueryRequest,
    DatabaseQueryResult,
    DatabaseStatusRead,
    DatabaseTableRead,
    DatabaseTablesRead,
)
from app.services import project_database as db_svc
from app.services.sandbox import mark_sandbox_missing
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["database"])


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


async def _handle_missing(
    session: AsyncSession,
    project: Project,
    exc: SandboxAgentError,
) -> HTTPException:
    if exc.status_code == 404:
        await mark_sandbox_missing(session, project)
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sandbox missing on agent; recreate the sandbox",
        )
    return _agent_http_error(exc)


@router.get(
    "/projects/{project_id}/database/status",
    response_model=DatabaseStatusRead,
)
async def database_status(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> DatabaseStatusRead:
    if not project.sandbox_name or project.sandbox_status != "running":
        return DatabaseStatusRead(
            status="no_sandbox",
            message=(
                "Sandbox is not running. Start the sandbox and enable the "
                "db-postgres harness to use the Database panel."
            ),
            harness_installed=False,
            psql_available=False,
        )
    name = project.sandbox_name
    client = SandboxAgentClient(settings)
    try:
        data = await db_svc.get_status(client, name)
    except SandboxAgentError as exc:
        raise await _handle_missing(session, project, exc) from exc
    return DatabaseStatusRead(**data)


@router.get(
    "/projects/{project_id}/database/tables",
    response_model=DatabaseTablesRead,
)
async def database_tables(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> DatabaseTablesRead:
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        data = await db_svc.list_tables(client, name)
    except SandboxAgentError as exc:
        raise await _handle_missing(session, project, exc) from exc
    tables = [DatabaseTableRead(**t) for t in data.get("tables") or []]
    return DatabaseTablesRead(
        tables=tables,
        status=str(data.get("status") or "ready"),
        message=data.get("message"),
    )


@router.post(
    "/projects/{project_id}/database/query",
    response_model=DatabaseQueryResult,
)
async def database_query(
    body: DatabaseQueryRequest,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> DatabaseQueryResult:
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        data = await db_svc.run_query(client, name, body.sql, limit=body.limit)
    except SandboxAgentError as exc:
        raise await _handle_missing(session, project, exc) from exc
    return DatabaseQueryResult(**data)
