"""Project-scoped HTTP tool CRUD + test/execute."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.http_tool import ProjectHttpTool
from app.models.project import Project
from app.schemas.http_tool import (
    HttpToolCreate,
    HttpToolExecuteRequest,
    HttpToolExecuteResult,
    HttpToolRead,
    HttpToolUpdate,
)
from app.services.http_tools import execute_http_tool

router = APIRouter(tags=["http-tools"])


async def _get_tool_for_project(
    session: AsyncSession,
    project_id: UUID,
    tool_id: UUID,
) -> ProjectHttpTool:
    result = await session.execute(
        select(ProjectHttpTool).where(
            ProjectHttpTool.id == tool_id,
            ProjectHttpTool.project_id == project_id,
        )
    )
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="HTTP tool not found")
    return tool


@router.get(
    "/projects/{project_id}/http-tools",
    response_model=list[HttpToolRead],
)
async def list_http_tools(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[ProjectHttpTool]:
    principal.require_scope("http_tools:read")
    result = await session.execute(
        select(ProjectHttpTool)
        .where(ProjectHttpTool.project_id == project.id)
        .order_by(ProjectHttpTool.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/http-tools",
    response_model=HttpToolRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_http_tool(
    body: HttpToolCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ProjectHttpTool:
    principal.require_scope("http_tools:rw")
    tool = ProjectHttpTool(
        project_id=project.id,
        name=body.name,
        method=body.method,
        url_template=body.url_template,
        enabled=body.enabled,
        created_by=principal.user.id,
    )
    session.add(tool)
    await session.commit()
    await session.refresh(tool)
    return tool


@router.get(
    "/projects/{project_id}/http-tools/{tool_id}",
    response_model=HttpToolRead,
)
async def get_http_tool(
    tool_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ProjectHttpTool:
    principal.require_scope("http_tools:read")
    return await _get_tool_for_project(session, project.id, tool_id)


@router.patch(
    "/projects/{project_id}/http-tools/{tool_id}",
    response_model=HttpToolRead,
)
async def update_http_tool(
    tool_id: UUID,
    body: HttpToolUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ProjectHttpTool:
    principal.require_scope("http_tools:rw")
    tool = await _get_tool_for_project(session, project.id, tool_id)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        tool.name = data["name"]
    if "method" in data and data["method"] is not None:
        tool.method = data["method"]
    if "url_template" in data and data["url_template"] is not None:
        tool.url_template = data["url_template"]
    if "enabled" in data and data["enabled"] is not None:
        tool.enabled = data["enabled"]
    await session.commit()
    await session.refresh(tool)
    return tool


@router.delete(
    "/projects/{project_id}/http-tools/{tool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_http_tool(
    tool_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("http_tools:rw")
    tool = await _get_tool_for_project(session, project.id, tool_id)
    await session.delete(tool)
    await session.commit()


async def _run_tool(
    tool: ProjectHttpTool,
    body: HttpToolExecuteRequest,
    *,
    require_enabled: bool,
) -> HttpToolExecuteResult:
    if require_enabled and not tool.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTTP tool is disabled",
        )
    result = await execute_http_tool(
        method=tool.method,
        url_template=tool.url_template,
        path_params=body.path_params,
        query=body.query,
        headers=body.headers,
        body=body.body,
    )
    return HttpToolExecuteResult(**result)


@router.post(
    "/projects/{project_id}/http-tools/{tool_id}/test",
    response_model=HttpToolExecuteResult,
)
async def test_http_tool(
    tool_id: UUID,
    body: HttpToolExecuteRequest,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> HttpToolExecuteResult:
    """Execute a tool for the Tools panel Test button (allowed even when disabled)."""
    principal.require_scope("http_tools:rw")
    tool = await _get_tool_for_project(session, project.id, tool_id)
    return await _run_tool(tool, body, require_enabled=False)


@router.post(
    "/projects/{project_id}/http-tools/{tool_id}/execute",
    response_model=HttpToolExecuteResult,
)
async def execute_http_tool_route(
    tool_id: UUID,
    body: HttpToolExecuteRequest,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> HttpToolExecuteResult:
    """Execute an enabled tool (MCP / agents)."""
    principal.require_scope("http_tools:rw")
    tool = await _get_tool_for_project(session, project.id, tool_id)
    return await _run_tool(tool, body, require_enabled=True)
