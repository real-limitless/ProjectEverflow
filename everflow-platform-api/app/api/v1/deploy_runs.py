"""SSH compose-up deploy runs — uses stored deploy keys/nodes/routes when possible."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.deploy import DeployNode, DeployRoute as DeployRouteRow, DeploySshKey
from app.models.project import Project
from app.services.deploy_keys import decrypt_private_key
from app.services.deploy_remote import DeployRoute, execute_compose_up

router = APIRouter(tags=["deploy"])


class DeployRouteBody(BaseModel):
    name: str | None = None
    domain: str = Field(min_length=1, max_length=253)
    service: str = Field(min_length=1, max_length=128)
    port: int = Field(default=80, ge=1, le=65535)
    entrypoint: str = "web"
    url: str | None = None


class DeployRunCreateBody(BaseModel):
    """Preferred: node_id + compose_file (loads key/routes from DB).

    Legacy: pass host/user/private_key_pem for ad-hoc SSH without stored keys.
    """

    node_id: UUID | None = None
    compose_file: str | None = Field(default=None, max_length=512)

    host: str | None = Field(default=None, max_length=253)
    user: str = Field(default="everflow", min_length=1, max_length=64)
    port: int = Field(default=22, ge=1, le=65535)
    private_key_pem: str | None = Field(default=None, min_length=32)
    remote_dir: str = Field(default="/opt/everflow/apps/project", min_length=1, max_length=1024)
    compose_path: str | None = Field(default=None, max_length=512)
    local_workspace_hint: str | None = Field(default=None, max_length=2048)
    routes: list[DeployRouteBody] = Field(default_factory=list)
    dry_run: bool = False


class DeployRunResult(BaseModel):
    ok: bool
    project_id: UUID
    remote_dir: str
    compose_path: str
    routes_path: str
    log_lines: list[str]
    error: str | None = None


def _routes_from_body(body_routes: list[DeployRouteBody]) -> list[DeployRoute]:
    routes: list[DeployRoute] = []
    for r in body_routes:
        try:
            routes.append(
                DeployRoute.from_mapping(
                    {
                        "name": r.name or r.service,
                        "domain": r.domain,
                        "service": r.service,
                        "port": r.port,
                        "entrypoint": r.entrypoint,
                        "url": r.url,
                    }
                )
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    return routes


@router.post(
    "/projects/{project_id}/deploy/runs",
    response_model=DeployRunResult,
    status_code=status.HTTP_200_OK,
)
async def create_deploy_run(
    body: DeployRunCreateBody,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
) -> DeployRunResult:
    """Execute remote docker compose up via SSH (MVP, synchronous)."""

    host = body.host
    user = body.user
    port = body.port
    private_key = (body.private_key_pem or "").strip()
    compose_path = (body.compose_path or body.compose_file or "docker-compose.yml").strip()
    routes = _routes_from_body(body.routes)

    if body.node_id is not None:
        node_res = await session.execute(
            select(DeployNode).where(
                DeployNode.id == body.node_id,
                DeployNode.project_id == project.id,
            )
        )
        node = node_res.scalar_one_or_none()
        if node is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deploy node not found")
        host = node.host
        user = node.ssh_user
        port = node.port

        key_res = await session.execute(
            select(DeploySshKey)
            .where(DeploySshKey.project_id == project.id)
            .order_by(DeploySshKey.created_at.desc())
            .limit(1)
        )
        key = key_res.scalar_one_or_none()
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Generate a deploy SSH key before running a deploy",
            )
        private_key = decrypt_private_key(key.private_key_encrypted)

        if not routes:
            route_res = await session.execute(
                select(DeployRouteRow).where(DeployRouteRow.node_id == node.id)
            )
            for row in route_res.scalars().all():
                routes.append(
                    DeployRoute.from_mapping(
                        {
                            "name": row.service_name,
                            "domain": row.host_header,
                            "service": row.service_name,
                            "port": row.service_port,
                        }
                    )
                )
        if not routes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Add at least one domain→service route before deploying",
            )

    if not host or not private_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide node_id (with stored key) or host + private_key_pem",
        )

    remote_dir = body.remote_dir
    if remote_dir.rstrip("/").endswith("project"):
        remote_dir = f"/opt/everflow/apps/{project.slug or project.id}"

    result = execute_compose_up(
        host=host,
        user=user,
        port=port,
        private_key=private_key,
        local_workspace_hint=body.local_workspace_hint,
        compose_rel_path=compose_path,
        routes=routes,
        remote_dir=remote_dir,
        dry_run=body.dry_run,
    )

    payload: dict[str, Any] = result.to_dict()
    return DeployRunResult(
        ok=bool(payload["ok"]),
        project_id=project.id,
        remote_dir=str(payload["remote_dir"]),
        compose_path=str(payload["compose_path"]),
        routes_path=str(payload["routes_path"]),
        log_lines=list(payload.get("log_lines") or []),
        error=payload.get("error"),
    )
