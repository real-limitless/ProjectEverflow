"""Internal HTTP routes for sandbox-agent."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, status
from fastapi.responses import PlainTextResponse
from starlette.websockets import WebSocketDisconnect

from app.auth import require_agent_token
from app.config import Settings, get_settings
from app.msb import SandboxBackend
from app.opencode_mgr import get_opencode_manager
from app.opencode_proxy import proxy_to_opencode, proxy_to_opencode_guest
from app.guest_tunnel import resolve_dial_target
from app.ports import list_listening_ports
from app.preview_proxy import proxy_http_to_port, proxy_websocket_to_port
from app.schemas import (
    BootstrapRequest,
    ExecRequest,
    ExecResult,
    FsEntry,
    FsWriteRequest,
    HealthResponse,
    ListeningPortInfo,
    OpenCodeEnsureRequest,
    OpenCodeEnsureResponse,
    PortsListResponse,
    SandboxCreateRequest,
    SandboxInfo,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_backend(request: Request) -> SandboxBackend:
    return request.app.state.backend  # type: ignore[no-any-return]


def _to_info(rec) -> SandboxInfo:  # noqa: ANN001
    return SandboxInfo(
        name=rec.name,
        status=rec.status,
        image=rec.image,
        labels=rec.labels,
        harnesses=rec.harnesses,
        workspace_path=rec.workspace_path,
        created_at=rec.created_at,
        error=rec.error,
    )


@router.get("/health", response_model=HealthResponse)
async def health(backend: Annotated[SandboxBackend, Depends(get_backend)]) -> HealthResponse:
    data = await backend.health()
    return HealthResponse(**data)


@router.websocket("/v1/sandboxes/{name}/shell")
async def sandbox_shell_ws(
    websocket: WebSocket,
    name: str,
    token: str = Query(default=""),
    cmd: str | None = Query(default=None),
    cwd: str = Query(default="/workspace"),
) -> None:
    """
    Interactive PTY session (for opencode, bash, etc.).

    Auth: ?token=<SANDBOX_AGENT_TOKEN>
    Frames (JSON): see app/shell_ws.py
    """
    settings = get_settings()
    await websocket.accept()
    if token != settings.sandbox_agent_token:
        await websocket.send_json({"type": "error", "message": "Invalid agent token"})
        await websocket.close(code=4403)
        return

    backend: SandboxBackend = websocket.app.state.backend  # type: ignore[assignment]
    try:
        await backend.shell_session(name, websocket, cmd=cmd, cwd=cwd or "/workspace")
    except KeyError:
        await websocket.send_json({"type": "error", "message": "Sandbox not found"})
    except RuntimeError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.exception("shell_ws failed name=%s", name)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.post(
    "/v1/sandboxes",
    response_model=SandboxInfo,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_agent_token)],
)
async def create_sandbox(
    body: SandboxCreateRequest,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SandboxInfo:
    try:
        rec = await backend.create(
            body.name,
            image=body.image or settings.default_image,
            cpus=body.cpus or settings.default_cpus,
            memory_mib=body.memory_mib or settings.default_memory_mib,
            labels=body.labels,
            harnesses=body.harnesses,
            workspace_host_path=body.workspace_host_path,
            replace=body.replace,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return _to_info(rec)


@router.get(
    "/v1/sandboxes",
    response_model=list[SandboxInfo],
    dependencies=[Depends(require_agent_token)],
)
async def list_sandboxes(
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> list[SandboxInfo]:
    recs = await backend.list()
    return [_to_info(r) for r in recs]


@router.get(
    "/v1/sandboxes/{name}",
    response_model=SandboxInfo,
    dependencies=[Depends(require_agent_token)],
)
async def get_sandbox(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> SandboxInfo:
    rec = await backend.get(name)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found")
    return _to_info(rec)


@router.post(
    "/v1/sandboxes/{name}/start",
    response_model=SandboxInfo,
    dependencies=[Depends(require_agent_token)],
)
async def start_sandbox(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> SandboxInfo:
    try:
        rec = await backend.start(name)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    return _to_info(rec)


@router.post(
    "/v1/sandboxes/{name}/stop",
    response_model=SandboxInfo,
    dependencies=[Depends(require_agent_token)],
)
async def stop_sandbox(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> SandboxInfo:
    try:
        rec = await backend.stop(name)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    return _to_info(rec)


@router.post(
    "/v1/sandboxes/{name}/remove",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_agent_token)],
)
async def remove_sandbox(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> None:
    """Idempotent remove: missing sandbox still returns 204 (recreate-friendly)."""
    try:
        await get_opencode_manager().stop(name)
    except Exception:  # noqa: BLE001
        logger.debug("opencode stop on remove ignored name=%s", name)
    try:
        await backend.remove(name)
    except KeyError:
        # Already gone — success for force recreate paths
        return


@router.post(
    "/v1/sandboxes/{name}/exec",
    response_model=ExecResult,
    dependencies=[Depends(require_agent_token)],
)
async def exec_sandbox(
    name: str,
    body: ExecRequest,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> ExecResult:
    try:
        code, stdout, stderr = await backend.exec(
            name,
            body.cmd,
            body.args,
            cwd=body.cwd,
            env=body.env or None,
            timeout_seconds=body.timeout_seconds,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return ExecResult(exit_code=code, stdout=stdout, stderr=stderr)


@router.post(
    "/v1/sandboxes/{name}/bootstrap",
    response_model=SandboxInfo,
    dependencies=[Depends(require_agent_token)],
)
async def bootstrap_sandbox(
    name: str,
    body: BootstrapRequest,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> SandboxInfo:
    try:
        rec = await backend.bootstrap(name, body.harnesses)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return _to_info(rec)


@router.get(
    "/v1/sandboxes/{name}/fs",
    response_model=list[FsEntry],
    dependencies=[Depends(require_agent_token)],
)
async def list_fs(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
    path: str = ".",
) -> list[FsEntry]:
    try:
        entries = await backend.list_fs(name, path)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found") from None
    except NotADirectoryError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a directory") from None
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return [FsEntry(**e) for e in entries]


@router.get(
    "/v1/sandboxes/{name}/fs/content",
    dependencies=[Depends(require_agent_token)],
)
async def read_fs(
    name: str,
    path: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> PlainTextResponse:
    try:
        data = await backend.read_fs(name, path)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found") from None
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    return PlainTextResponse(text)


@router.put(
    "/v1/sandboxes/{name}/fs/content",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_agent_token)],
)
async def write_fs(
    name: str,
    path: str,
    body: FsWriteRequest,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> None:
    try:
        await backend.write_fs(name, path, body.content.encode(body.encoding))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


async def _require_running_sandbox(
    name: str,
    backend: SandboxBackend,
) -> Any:
    rec = await backend.get(name)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found")
    if rec.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox is not running (status={rec.status})",
        )
    return rec


@router.post(
    "/v1/sandboxes/{name}/opencode/ensure",
    response_model=OpenCodeEnsureResponse,
    dependencies=[Depends(require_agent_token)],
)
async def opencode_ensure(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
    body: OpenCodeEnsureRequest | None = None,
) -> OpenCodeEnsureResponse:
    """Start (or reuse) opencode serve for this sandbox workspace."""
    rec = await _require_running_sandbox(name, backend)
    mgr = get_opencode_manager()
    force = bool(body.force_restart) if body else False
    workspace = rec.workspace_path or ""

    try:
        # Host path available → run OpenCode as host process against workspace
        if workspace and not workspace.startswith("named:") and workspace != "(guest-only)":
            ws_path = Path(workspace)
            if ws_path.is_dir():
                status_dict = await mgr.ensure_host(name, str(ws_path), force_restart=force)
                return OpenCodeEnsureResponse(**status_dict)

        # Guest-only: start inside VM (proxy may be limited)
        status_dict = await mgr.ensure_guest_via_exec(
            name,
            exec_fn=backend.exec,
            workspace_guest="/workspace",
        )
        return OpenCodeEnsureResponse(**status_dict)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None


@router.api_route(
    "/v1/sandboxes/{name}/opencode",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    dependencies=[Depends(require_agent_token)],
)
@router.api_route(
    "/v1/sandboxes/{name}/opencode/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    dependencies=[Depends(require_agent_token)],
)
async def opencode_proxy(
    name: str,
    request: Request,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
    path: str = "",
) -> Response:
    """Reverse-proxy to the sandbox's OpenCode HTTP server (SSE-safe on host mode)."""
    await _require_running_sandbox(name, backend)
    mgr = get_opencode_manager()
    inst = mgr.get(name)

    if not inst:
        # Auto-ensure once if not started
        try:
            await opencode_ensure(name, backend, OpenCodeEnsureRequest())
        except HTTPException:
            raise
        inst = mgr.get(name)

    if inst and inst.mode == "guest":
        # MicroVM: REST via exec; SSE via stream_exec (token streaming)
        stream_fn = getattr(backend, "stream_exec", None)
        return await proxy_to_opencode_guest(
            request,
            exec_fn=backend.exec,
            sandbox_name=name,
            path=path or "",
            port=inst.port or 4096,
            cwd="/workspace",
            stream_exec_fn=stream_fn,
        )

    base = mgr.base_url(name)
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OpenCode is not running for this sandbox. Call /opencode/ensure first. "
                f"(instance={inst.mode if inst else None})"
            ),
        )

    return await proxy_to_opencode(request, base_url=base, path=path or "")


@router.get(
    "/v1/sandboxes/{name}/ports",
    response_model=PortsListResponse,
    dependencies=[Depends(require_agent_token)],
)
async def list_sandbox_ports(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
    probe: bool = Query(default=False, description="Optional HTTP probe for http_likely"),
) -> PortsListResponse:
    """List TCP listen ports inside the sandbox (for Preview dropdown)."""
    await _require_running_sandbox(name, backend)
    try:
        ports = await list_listening_ports(
            backend.exec,
            name,
            cwd="/workspace",
            probe_http=probe,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    except Exception as exc:  # noqa: BLE001
        logger.warning("list ports failed name=%s: %s", name, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Port discovery failed: {exc}",
        ) from exc

    return PortsListResponse(
        sandbox_name=name,
        ports=[ListeningPortInfo(**p.to_dict()) for p in ports],
    )


@router.api_route(
    "/v1/sandboxes/{name}/proxy/{port}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    dependencies=[Depends(require_agent_token)],
)
@router.api_route(
    "/v1/sandboxes/{name}/proxy/{port}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    dependencies=[Depends(require_agent_token)],
)
async def sandbox_port_proxy(
    name: str,
    port: int,
    request: Request,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
    path: str = "",
) -> Response:
    """Reverse-proxy HTTP to a sandbox process (host dial or guest tunnel)."""
    if port < 1 or port > 65535:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid port")
    await _require_running_sandbox(name, backend)
    try:
        dial_host, dial_port, mode = await resolve_dial_target(name, port, backend=backend)
    except Exception as exc:  # noqa: BLE001
        logger.warning("resolve dial target failed name=%s port=%s: %s", name, port, exc)
        dial_host, dial_port, mode = "127.0.0.1", port, "unreachable"

    # Prefer real TCP (host or tunnel). Guest-exec HTTP only if still unreachable.
    return await proxy_http_to_port(
        request,
        port=dial_port,
        path=path or "",
        host=dial_host,
        host_header=f"127.0.0.1:{port}",
        exec_fn=backend.exec if mode == "unreachable" else None,
        sandbox_name=name if mode == "unreachable" else None,
    )


@router.websocket("/v1/sandboxes/{name}/proxy/{port}")
@router.websocket("/v1/sandboxes/{name}/proxy/{port}/{path:path}")
async def sandbox_port_proxy_ws(
    websocket: WebSocket,
    name: str,
    port: int,
    path: str = "",
    token: str = Query(default=""),
) -> None:
    """WebSocket reverse-proxy (host dial or guest TCP tunnel for HMR)."""
    settings = get_settings()
    if token != settings.sandbox_agent_token:
        await websocket.accept()
        await websocket.close(code=4403)
        return
    if port < 1 or port > 65535:
        await websocket.accept()
        await websocket.close(code=4400)
        return

    backend: SandboxBackend = websocket.app.state.backend  # type: ignore[assignment]
    rec = await backend.get(name)
    if rec is None or rec.status != "running":
        await websocket.accept()
        await websocket.close(code=4404)
        return

    query = websocket.url.query
    # Strip our auth token from upstream query
    if query:
        from urllib.parse import parse_qsl, urlencode

        pairs = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k != "token"]
        query = urlencode(pairs)

    try:
        dial_host, dial_port, mode = await resolve_dial_target(name, port, backend=backend)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ws resolve dial failed name=%s port=%s: %s", name, port, exc)
        await websocket.accept()
        await websocket.close(code=1011, reason="tunnel setup failed"[:120])
        return

    if mode == "unreachable":
        await websocket.accept()
        await websocket.close(code=1011, reason="guest port not reachable"[:120])
        return

    await proxy_websocket_to_port(
        websocket,
        port=dial_port,
        path=path or "",
        query=query,
        host=dial_host,
    )
