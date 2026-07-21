"""Preview endpoints: mint GUID subdomains + Host-based HTTP/WS proxy edge."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketState

from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session, get_session_factory
from app.models.organization import OrganizationMember
from app.models.preview import PreviewEndpoint
from app.models.project import Project
from app.models.user import User
from app.services.preview_endpoints import (
    get_or_create_endpoint,
    mint_for_endpoint,
    parse_endpoint_id_from_host,
    resolve_endpoint,
)
from app.services.preview_tickets import PreviewTicketError, verify_ticket
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["preview"])

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


class PreviewEndpointCreate(BaseModel):
    port: int = Field(ge=1, le=65535)


class PreviewEndpointRead(BaseModel):
    endpoint_id: str
    port: int
    sandbox_name: str
    url: str
    ticket: str
    expires_at: int


@router.post(
    "/projects/{project_id}/preview/endpoints",
    response_model=PreviewEndpointRead,
)
async def create_preview_endpoint(
    body: PreviewEndpointCreate,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> PreviewEndpointRead:
    """Create or reuse a GUID preview host for a sandbox port; return ticket + URL."""
    if not settings.preview_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Preview disabled")
    if not settings.sandbox_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sandbox disabled")
    try:
        ep = await get_or_create_endpoint(
            session,
            project=project,
            port=body.port,
            user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    payload = mint_for_endpoint(endpoint=ep, user_id=user.id, settings=settings)
    return PreviewEndpointRead(**payload)


@router.get("/projects/{project_id}/sandbox/ports")
async def list_project_sandbox_ports(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
    probe: bool = False,
) -> dict[str, Any]:
    """List listening ports inside the project sandbox (Preview dropdown)."""
    if not settings.sandbox_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Sandbox disabled")
    if not project.sandbox_name:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project has no sandbox")
    if project.sandbox_status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox is not running (status={project.sandbox_status})",
        )
    client = SandboxAgentClient(settings)
    try:
        return await client.list_ports(project.sandbox_name, probe=probe)
    except SandboxAgentError as exc:
        code = exc.status_code or 502
        if code == 404:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sandbox missing on agent") from exc
        raise HTTPException(status_code=code if code < 500 else 502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Host-based preview edge (wrapped around the main FastAPI app)
# ---------------------------------------------------------------------------


def _cookie_name(settings: Settings) -> str:
    return settings.preview_cookie_name


def _extract_ticket(scope: Scope, headers: dict[str, str], settings: Settings) -> str | None:
    # Query ?ticket=
    qs = scope.get("query_string", b"").decode("latin-1")
    if qs:
        from urllib.parse import parse_qs

        params = parse_qs(qs)
        if "ticket" in params and params["ticket"]:
            return params["ticket"][0]
    cookie = headers.get("cookie", "")
    name = _cookie_name(settings)
    if cookie and name:
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith(name + "="):
                return part[len(name) + 1 :]
    return None


async def _user_is_project_member(user_id: UUID, project_id: UUID) -> bool:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project is None:
            return False
        mem = await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == project.organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return mem.scalar_one_or_none() is not None


async def _load_endpoint(endpoint_id: UUID) -> PreviewEndpoint | None:
    factory = get_session_factory()
    async with factory() as session:
        ep = await resolve_endpoint(session, endpoint_id)
        if ep is None:
            return None
        # Touch last_seen
        ep.last_seen_at = datetime.now(timezone.utc)
        await session.commit()
        session.expunge(ep)
        return ep


def _set_cookie_header(settings: Settings, ticket: str) -> str:
    """Host-only cookie on the preview subdomain (not shared with the main app).

    Note: cross-site iframes (UI on localhost:5173 → preview on *.preview.localhost:8000)
    block third-party Set-Cookie under SameSite=Lax. Auth therefore does not rely on
    cookies for subresources — the unguessable endpoint Host is the capability.
    Cookies still help top-level / same-site navigation when the browser accepts them.
    """
    max_age = int(settings.preview_ticket_ttl_seconds)
    parts = [
        f"{settings.preview_cookie_name}={ticket}",
        "Path=/",
        f"Max-Age={max_age}",
        "HttpOnly",
    ]
    if settings.preview_public_scheme == "https":
        # Cross-site iframe-friendly when HTTPS is available (prod).
        parts.extend(["Secure", "SameSite=None", "Partitioned"])
    else:
        parts.append("SameSite=Lax")
    return "; ".join(parts)


async def _authorize_preview(
    scope: Scope,
    headers: dict[str, str],
    endpoint: PreviewEndpoint,
    settings: Settings,
) -> tuple[bool, str | None, int]:
    """Authorize a Host-based preview request.

    Auth model (iframe-safe):
    - The GUID subdomain is an unguessable capability URL (minted only for org members).
    - Optional ticket/cookie, when present, must be valid and match this endpoint.
    - Ticket is NOT required on every subresource: browsers block third-party cookies
      in cross-origin iframes, so Vite assets like /@react-refresh would otherwise 401.

    Returns (ok, ticket_to_echo_as_cookie, status_if_fail).
    """
    raw = _extract_ticket(scope, headers, settings)
    if not raw:
        # Capability URL: knowing the host GUID is sufficient for the preview edge.
        return True, None, 200

    try:
        claims = verify_ticket(raw, settings=settings)
    except PreviewTicketError:
        return False, None, 401
    if claims.endpoint_id != endpoint.id:
        return False, None, 403
    if claims.project_id != endpoint.project_id:
        return False, None, 403
    if claims.port != endpoint.port:
        return False, None, 403
    if not await _user_is_project_member(claims.user_id, claims.project_id):
        return False, None, 403
    return True, raw, 200


async def handle_preview_http(request: Request) -> Response:
    settings = get_settings()
    if not settings.preview_enabled:
        return JSONResponse({"detail": "Preview disabled"}, status_code=503)

    host = request.headers.get("host", "")
    endpoint_id = parse_endpoint_id_from_host(host, settings=settings)
    if endpoint_id is None:
        return JSONResponse({"detail": "Unknown preview host"}, status_code=404)

    endpoint = await _load_endpoint(endpoint_id)
    if endpoint is None:
        return JSONResponse({"detail": "Preview endpoint not found"}, status_code=404)

    headers_map = {k.lower(): v for k, v in request.headers.items()}
    ok, ticket, fail = await _authorize_preview(request.scope, headers_map, endpoint, settings)
    if not ok:
        return JSONResponse({"detail": "Unauthorized preview ticket"}, status_code=fail)

    path = request.url.path.lstrip("/")
    body = await request.body()
    fwd_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in HOP_BY_HOP and k.lower() not in ("authorization", "cookie")
    }
    client = SandboxAgentClient(settings)
    try:
        upstream, http_client = await client.preview_proxy_stream(
            endpoint.sandbox_name,
            port=endpoint.port,
            method=request.method,
            path=path,
            query=request.url.query or None,
            headers=fwd_headers,
            content=body if body else None,
        )
    except SandboxAgentError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code or 502)

    media = upstream.headers.get("content-type", "")
    resp_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in HOP_BY_HOP
        and k.lower()
        not in (
            "x-frame-options",
            "content-security-policy",
            "content-security-policy-report-only",
        )
    }
    if ticket:
        resp_headers["set-cookie"] = _set_cookie_header(settings, ticket)

    async def _close() -> None:
        try:
            await upstream.aclose()
        except Exception:  # noqa: BLE001
            pass
        try:
            await http_client.aclose()
        except Exception:  # noqa: BLE001
            pass

    is_stream = "text/event-stream" in media

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


class PreviewHostMiddleware:
    """Route `*.{preview_base_domain}` HTTP to the preview edge; pass-through otherwise."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            settings = get_settings()
            if settings.preview_enabled:
                headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
                host = headers.get("host", "")
                if parse_endpoint_id_from_host(host, settings=settings) is not None:
                    # Build a minimal Request and return via ASGI Response
                    from starlette.requests import Request as StarletteRequest

                    request = StarletteRequest(scope, receive)
                    response = await handle_preview_http(request)
                    await response(scope, receive, send)
                    return

        if scope["type"] == "websocket":
            settings = get_settings()
            if settings.preview_enabled:
                headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
                host = headers.get("host", "")
                endpoint_id = parse_endpoint_id_from_host(host, settings=settings)
                if endpoint_id is not None:
                    await _handle_preview_websocket(scope, receive, send, endpoint_id, settings)
                    return

        await self.app(scope, receive, send)


async def _handle_preview_websocket(
    scope: Scope,
    receive: Receive,
    send: Send,
    endpoint_id: UUID,
    settings: Settings,
) -> None:
    from starlette.websockets import WebSocket

    websocket = WebSocket(scope, receive, send)
    await websocket.accept()

    endpoint = await _load_endpoint(endpoint_id)
    if endpoint is None:
        await websocket.close(code=4404)
        return

    headers_map = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
    ok, _, fail = await _authorize_preview(scope, headers_map, endpoint, settings)
    if not ok:
        await websocket.close(code=4400 + (fail % 100))
        return

    path = scope.get("path", "/") or "/"
    path = path.lstrip("/")
    query = scope.get("query_string", b"").decode("latin-1")
    # Strip ticket from upstream query
    if query:
        from urllib.parse import parse_qsl, urlencode

        pairs = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k != "ticket"]
        query = urlencode(pairs)

    client = SandboxAgentClient(settings)
    agent_url = client.preview_proxy_ws_url(
        endpoint.sandbox_name,
        port=endpoint.port,
        path=path,
        query=query or None,
    )

    try:
        import websockets
        from websockets.exceptions import ConnectionClosed
    except ImportError:
        await websocket.close(code=1011)
        return

    try:
        upstream = await websockets.connect(agent_url, open_timeout=20, max_size=8 * 1024 * 1024)
    except Exception as exc:  # noqa: BLE001
        logger.warning("preview edge ws agent connect failed: %s", exc)
        await websocket.close(code=1011)
        return

    stop = asyncio.Event()

    async def c2u() -> None:
        try:
            while not stop.is_set():
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("text") is not None:
                    await upstream.send(msg["text"])
                elif msg.get("bytes") is not None:
                    await upstream.send(msg["bytes"])
        except Exception:  # noqa: BLE001
            pass
        finally:
            stop.set()

    async def u2c() -> None:
        try:
            async for message in upstream:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)
        except ConnectionClosed:
            pass
        except Exception:  # noqa: BLE001
            pass
        finally:
            stop.set()

    t1 = asyncio.create_task(c2u())
    t2 = asyncio.create_task(u2c())
    await stop.wait()
    for t in (t1, t2):
        t.cancel()
    try:
        await upstream.close()
    except Exception:
        pass
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
    except Exception:
        pass
