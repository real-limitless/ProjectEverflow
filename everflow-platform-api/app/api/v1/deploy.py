"""Project-scoped deploy keys, nodes, routes, and compose discovery."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.deploy import DeployNode, DeployRoute, DeployRun, DeploySshKey
from app.models.project import Project
from app.schemas.deploy import (
    ComposeFilesRead,
    DeployNodeCreate,
    DeployNodeRead,
    DeployRouteCreate,
    DeployRouteRead,
    DeployRunStubRead,
    DeployRunStubRequest,
    DeploySshKeyGenerateResult,
    DeploySshKeyRead,
)
from app.services import deploy_keys as keys_svc
from app.services.sandbox import mark_sandbox_missing
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["deploy"])


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


async def _get_node_for_project(
    session: AsyncSession,
    project_id: UUID,
    node_id: UUID,
) -> DeployNode:
    result = await session.execute(
        select(DeployNode).where(
            DeployNode.id == node_id,
            DeployNode.project_id == project_id,
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deploy node not found")
    return node


def _node_read(node: DeployNode) -> DeployNodeRead:
    tags = node.tags if isinstance(node.tags, list) else []
    return DeployNodeRead(
        id=node.id,
        project_id=node.project_id,
        name=node.name,
        host=node.host,
        port=node.port,
        ssh_user=node.ssh_user,
        tags=[str(t) for t in tags],
        status=node.status,
        created_by=node.created_by,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


# --- SSH keys -----------------------------------------------------------------


@router.get(
    "/projects/{project_id}/deploy/keys",
    response_model=list[DeploySshKeyRead],
)
async def list_deploy_keys(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[DeploySshKey]:
    principal.require_scope("deploy:read")
    result = await session.execute(
        select(DeploySshKey)
        .where(DeploySshKey.project_id == project.id)
        .order_by(DeploySshKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/deploy/keys/generate",
    response_model=DeploySshKeyGenerateResult,
    status_code=status.HTTP_201_CREATED,
)
async def generate_deploy_key(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> DeploySshKeyGenerateResult:
    principal.require_scope("deploy:rw")
    name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)
    try:
        material = await keys_svc.generate_ssh_keypair_in_sandbox(
            client, name, settings=settings
        )
    except SandboxAgentError as exc:
        raise await _handle_missing(session, project, exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    encrypted = keys_svc.encrypt_private_key(material["private_key"], settings)
    row = DeploySshKey(
        project_id=project.id,
        fingerprint=material["fingerprint"],
        public_key=material["public_key"],
        private_key_encrypted=encrypted,
        created_by=principal.user.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return DeploySshKeyGenerateResult(
        id=row.id,
        project_id=row.project_id,
        fingerprint=row.fingerprint,
        public_key=row.public_key,
        created_at=row.created_at,
    )


# --- Nodes --------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/deploy/nodes",
    response_model=list[DeployNodeRead],
)
async def list_deploy_nodes(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[DeployNodeRead]:
    principal.require_scope("deploy:read")
    result = await session.execute(
        select(DeployNode)
        .where(DeployNode.project_id == project.id)
        .order_by(DeployNode.updated_at.desc())
    )
    return [_node_read(n) for n in result.scalars().all()]


@router.post(
    "/projects/{project_id}/deploy/nodes",
    response_model=DeployNodeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_deploy_node(
    body: DeployNodeCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> DeployNodeRead:
    principal.require_scope("deploy:rw")
    node = DeployNode(
        project_id=project.id,
        name=body.name,
        host=body.host,
        port=body.port,
        ssh_user=body.ssh_user,
        tags=list(body.tags),
        status=body.status,
        created_by=principal.user.id,
    )
    session.add(node)
    await session.commit()
    await session.refresh(node)
    return _node_read(node)


@router.delete(
    "/projects/{project_id}/deploy/nodes/{node_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_deploy_node(
    node_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("deploy:rw")
    node = await _get_node_for_project(session, project.id, node_id)
    await session.delete(node)
    await session.commit()


# --- Compose discovery --------------------------------------------------------


@router.get(
    "/projects/{project_id}/deploy/compose-files",
    response_model=ComposeFilesRead,
)
async def list_compose_files(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> ComposeFilesRead:
    principal.require_scope("deploy:read")
    if not project.sandbox_name or project.sandbox_status != "running":
        return ComposeFilesRead(
            files=[],
            message="Sandbox is not running; start it to discover compose files.",
        )
    name = project.sandbox_name
    client = SandboxAgentClient(settings)
    try:
        files = await keys_svc.discover_compose_files(client, name)
    except SandboxAgentError as exc:
        raise await _handle_missing(session, project, exc) from exc
    return ComposeFilesRead(files=files)


# --- Routes -------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/deploy/nodes/{node_id}/routes",
    response_model=list[DeployRouteRead],
)
async def list_deploy_routes(
    node_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[DeployRoute]:
    principal.require_scope("deploy:read")
    await _get_node_for_project(session, project.id, node_id)
    result = await session.execute(
        select(DeployRoute)
        .where(DeployRoute.node_id == node_id)
        .order_by(DeployRoute.created_at.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/deploy/nodes/{node_id}/routes",
    response_model=DeployRouteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_deploy_route(
    node_id: UUID,
    body: DeployRouteCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> DeployRoute:
    principal.require_scope("deploy:rw")
    await _get_node_for_project(session, project.id, node_id)
    route = DeployRoute(
        node_id=node_id,
        host_header=body.host_header,
        service_name=body.service_name,
        service_port=body.service_port,
        path_prefix=body.path_prefix,
    )
    session.add(route)
    await session.commit()
    await session.refresh(route)
    return route


@router.delete(
    "/projects/{project_id}/deploy/nodes/{node_id}/routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_deploy_route(
    node_id: UUID,
    route_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("deploy:rw")
    await _get_node_for_project(session, project.id, node_id)
    result = await session.execute(
        select(DeployRoute).where(
            DeployRoute.id == route_id,
            DeployRoute.node_id == node_id,
        )
    )
    route = result.scalar_one_or_none()
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deploy route not found")
    await session.delete(route)
    await session.commit()


# --- Deploy stub --------------------------------------------------------------


@router.post(
    "/projects/{project_id}/deploy/stub",
    response_model=DeployRunStubRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_deploy_run_stub(
    body: DeployRunStubRequest,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> DeployRun:
    """Validate node + compose + routes exist; record stub (SSH not executed yet).

    Live SSH execute lives on POST /deploy/runs (deploy_runs + deploy_remote).
    """
    principal.require_scope("deploy:rw")
    node = await _get_node_for_project(session, project.id, body.node_id)
    if not body.compose_file.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="compose_file is required",
        )

    routes = await session.execute(
        select(DeployRoute).where(DeployRoute.node_id == node.id)
    )
    route_list = list(routes.scalars().all())
    if not route_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add at least one domain→service route before deploying",
        )

    message = "SSH deploy not yet executed"
    run = DeployRun(
        project_id=project.id,
        node_id=node.id,
        compose_file=body.compose_file,
        action=body.action,
        status="stub",
        message=message,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    logger.info(
        "deploy stub project=%s node=%s compose=%s action=%s: %s",
        project.id,
        node.id,
        body.compose_file,
        body.action,
        message,
    )
    return run
