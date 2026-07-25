"""Project-scoped OpenCode reverse proxy (JWT → sandbox-agent → opencode serve)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.project import Project
from app.models.user import User
from app.services.provider_inject import inject_project_provider_secrets
from app.services.sandbox import (
    mark_sandbox_missing,
    refresh_sandbox_status,
    sandbox_not_running_detail,
)
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


async def _require_running_sandbox(
    session: AsyncSession,
    project: Project,
    settings: Settings,
) -> tuple[Project, str]:
    """Refresh agent status first so stale DB ``error`` does not block chat."""
    if not project.sandbox_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has no sandbox yet",
        )
    # TTL skip inside refresh when recently confirmed running (tool/hydrate storms).
    project, _info = await refresh_sandbox_status(session, project, settings=settings)
    if project.sandbox_status != "running":
        detail = sandbox_not_running_detail(project)
        logger.warning(
            "opencode blocked: sandbox not running project=%s name=%s status=%s error=%s",
            project.id,
            project.sandbox_name,
            project.sandbox_status,
            (project.sandbox_error or "")[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )
    return project, project.sandbox_name


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
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Ensure OpenCode server is running inside the project sandbox.

    Also mints a project-scoped sandbox token and registers the Everflow MCP
    server so Chat/OpenCode can create canvases and agents.
    """
    project, name = await _require_running_sandbox(session, project, settings)
    client = SandboxAgentClient(settings)

    mcp_token: str | None = None
    try:
        from app.services.sandbox_tokens import mint_sandbox_token

        _row, mcp_token = await mint_sandbox_token(
            session,
            project_id=project.id,
            user_id=user.id,
            label="opencode-mcp",
            settings=settings,
            revoke_existing=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("sandbox token mint failed project=%s: %s", project.id, exc)

    try:
        # Prefer agent-reachable URL (compose DNS). Guest MCP uses reverse tunnel.
        agent_api = (
            settings.agent_platform_api_url or settings.public_api_url or ""
        ).rstrip("/")
        result = await client.opencode_ensure(
            name,
            force_restart=body.force_restart,
            everflow_api_url=agent_api if mcp_token else None,
            everflow_token=mcp_token,
            everflow_project_id=str(project.id) if mcp_token else None,
            everflow_mcp_command="everflow-mcp",
        )

    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc

    # Product never accepts the internal fake OpenCode server (demo models).
    if isinstance(result, dict):
        ver = str(result.get("version") or "").lower()
        if ver.startswith("fake") or ver == "mock" or result.get("healthy") is False:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    result.get("error")
                    or "OpenCode harness is unavailable. "
                    "Background chat requires a real sandbox harness (fake/demo is disabled)."
                ),
            )

    # Best-effort: inject vault keys into guest + OpenCode auth after ensure
    try:
        inject = await inject_project_provider_secrets(
            session,
            project,
            user_id=user.id,
            settings=settings,
            client=client,
            apply_opencode_auth=True,
        )
        if isinstance(result, dict):
            result = {**result, "provider_inject": inject}
    except Exception as exc:  # noqa: BLE001
        logger.debug("provider inject after opencode ensure: %s", exc)

    if isinstance(result, dict) and mcp_token:
        # Never echo the raw token to the browser
        result = {
            **result,
            "everflow_mcp_ready": bool(
                (result.get("everflow_mcp") or {}).get("configured")
                if isinstance(result.get("everflow_mcp"), dict)
                else False
            ),
        }
        result.pop("everflow_mcp", None)

    return result


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

    project, name = await _require_running_sandbox(session, project, settings)
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
