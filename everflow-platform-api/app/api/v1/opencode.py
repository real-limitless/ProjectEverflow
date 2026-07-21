"""Project-scoped OpenCode reverse proxy (JWT → sandbox-agent → opencode serve)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.project import Project
from app.services.sandbox import mark_sandbox_missing
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["opencode"])

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


class OpenCodeEnsureBody(BaseModel):
    force_restart: bool = False


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
    if code == 503:
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if code >= 500 or code is None:
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=code, detail=str(exc))


@router.post("/projects/{project_id}/opencode/ensure")
async def ensure_opencode(
    body: OpenCodeEnsureBody = OpenCodeEnsureBody(),
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Ensure OpenCode server is running inside the project sandbox."""
    name = _require_running_sandbox(project)
    _ = settings  # client uses settings
    client = SandboxAgentClient(settings)
    try:
        return await client.opencode_ensure(name, force_restart=body.force_restart)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc


@router.api_route(
    "/projects/{project_id}/opencode/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_opencode(
    request: Request,
    path: str,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Reverse-proxy to OpenCode in the project sandbox (SSE-safe)."""
    if path == "ensure":
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail="Use POST /opencode/ensure",
        )

    name = _require_running_sandbox(project)
    _ = settings
    body = await request.body()
    fwd_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP and k.lower() != "authorization"
    }
    client = SandboxAgentClient(settings)
    try:
        upstream, http_client = await client.opencode_proxy_stream(
            name,
            method=request.method,
            path=path,
            query=request.url.query or None,
            headers=fwd_headers,
            content=body if body else None,
        )
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc

    media = upstream.headers.get("content-type", "")
    is_stream = "text/event-stream" in media or path.rstrip("/").endswith("event")

    resp_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in HOP_BY_HOP
    }

    async def _close() -> None:
        try:
            await upstream.aclose()
        except Exception:  # noqa: BLE001
            pass
        try:
            await http_client.aclose()
        except Exception:  # noqa: BLE001
            pass

    if is_stream:

        async def stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await _close()

        return StreamingResponse(
            stream(),
            status_code=upstream.status_code,
            headers=resp_headers,
            media_type=media or None,
        )

    try:
        content = await upstream.aread()
    finally:
        await _close()

    clean = {
        k: v
        for k, v in resp_headers.items()
        if k.lower() not in ("content-encoding", "content-length")
    }
    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=clean,
        media_type=media or None,
    )
