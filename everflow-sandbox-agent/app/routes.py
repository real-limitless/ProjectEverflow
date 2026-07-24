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
from app.msb import SandboxBackend, is_missing_path_error
from app.opencode_mgr import get_opencode_manager
from app.opencode_proxy import proxy_to_opencode, proxy_to_opencode_guest
from app.guest_tunnel import resolve_dial_target
from app.ports import list_listening_ports
from app.preview_proxy import proxy_http_to_port, proxy_websocket_to_port, ws_requested_subprotocol
from app.opencode_harness import (
    apply_pack_to_workspace,
    apply_pack_via_backend,
    read_pack_from_workspace,
    read_pack_via_backend,
)
from app.jobs import (
    delete_job,
    get_job_logs,
    kill_job,
    list_jobs,
    restart_job,
    start_existing_job,
    start_job,
    update_job,
)
from app.schemas import (
    BootstrapRequest,
    ExecRequest,
    ExecResult,
    FsEntry,
    FsWriteRequest,
    HealthResponse,
    JobCreateRequest,
    JobInfo,
    JobLogsResponse,
    JobUpdateRequest,
    ListeningPortInfo,
    OpenCodeEnsureRequest,
    OpenCodeEnsureResponse,
    OpenCodeHarnessPack,
    OpenCodeHarnessResponse,
    PortsListResponse,
    ProvidersSecretsRequest,
    ProvidersSecretsResponse,
    SandboxCreateRequest,
    SandboxInfo,
)

# Relative paths inside the sandbox workspace (never log secret values)
_PROVIDERS_ENV_PATH = ".everflow/secrets/providers.env"
_PROVIDERS_JSON_PATH = ".everflow/secrets/providers.json"

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


def _job_info(meta: dict[str, Any]) -> JobInfo:
    return JobInfo(
        id=str(meta.get("id") or ""),
        title=str(meta.get("title") or ""),
        command=str(meta.get("command") or ""),
        cwd=meta.get("cwd"),
        pid=int(meta["pid"]) if meta.get("pid") is not None else None,
        status=str(meta.get("status") or "unknown"),
        log_path=meta.get("log_path"),
        created_at=meta.get("created_at"),
        updated_at=meta.get("updated_at"),
        exit_code=meta.get("exit_code"),
    )


@router.post(
    "/v1/sandboxes/{name}/jobs",
    response_model=JobInfo,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_agent_token)],
)
async def create_job(
    name: str,
    body: JobCreateRequest,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> JobInfo:
    await _require_running_sandbox(name, backend)
    try:
        meta = await start_job(
            backend,
            name,
            title=body.title,
            command=body.command,
            cwd=body.cwd,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_info(meta)


@router.get(
    "/v1/sandboxes/{name}/jobs",
    response_model=list[JobInfo],
    dependencies=[Depends(require_agent_token)],
)
async def list_sandbox_jobs(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> list[JobInfo]:
    await _require_running_sandbox(name, backend)
    try:
        jobs = await list_jobs(backend, name)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    return [_job_info(j) for j in jobs]


@router.get(
    "/v1/sandboxes/{name}/jobs/{job_id}/logs",
    response_model=JobLogsResponse,
    dependencies=[Depends(require_agent_token)],
)
async def job_logs(
    name: str,
    job_id: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
    tail: int = Query(default=200, ge=1, le=5000),
) -> JobLogsResponse:
    await _require_running_sandbox(name, backend)
    try:
        data = await get_job_logs(backend, name, job_id, tail=tail)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from None
    return JobLogsResponse(**data)


@router.post(
    "/v1/sandboxes/{name}/jobs/{job_id}/kill",
    response_model=JobInfo,
    dependencies=[Depends(require_agent_token)],
)
async def kill_sandbox_job(
    name: str,
    job_id: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> JobInfo:
    await _require_running_sandbox(name, backend)
    try:
        meta = await kill_job(backend, name, job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_info(meta)


@router.post(
    "/v1/sandboxes/{name}/jobs/{job_id}/stop",
    response_model=JobInfo,
    dependencies=[Depends(require_agent_token)],
)
async def stop_sandbox_job(
    name: str,
    job_id: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> JobInfo:
    """Alias of kill — stop a running background job."""
    return await kill_sandbox_job(name, job_id, backend)


@router.post(
    "/v1/sandboxes/{name}/jobs/{job_id}/start",
    response_model=JobInfo,
    dependencies=[Depends(require_agent_token)],
)
async def start_sandbox_job(
    name: str,
    job_id: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> JobInfo:
    await _require_running_sandbox(name, backend)
    try:
        meta = await start_existing_job(backend, name, job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_info(meta)


@router.post(
    "/v1/sandboxes/{name}/jobs/{job_id}/restart",
    response_model=JobInfo,
    dependencies=[Depends(require_agent_token)],
)
async def restart_sandbox_job(
    name: str,
    job_id: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> JobInfo:
    await _require_running_sandbox(name, backend)
    try:
        meta = await restart_job(backend, name, job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_info(meta)


@router.patch(
    "/v1/sandboxes/{name}/jobs/{job_id}",
    response_model=JobInfo,
    dependencies=[Depends(require_agent_token)],
)
async def patch_sandbox_job(
    name: str,
    job_id: str,
    body: JobUpdateRequest,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> JobInfo:
    await _require_running_sandbox(name, backend)
    if body.title is None and body.command is None and body.cwd is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at least one of title, command, cwd",
        )
    try:
        meta = await update_job(
            backend,
            name,
            job_id,
            title=body.title,
            command=body.command,
            cwd=body.cwd,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_info(meta)


@router.delete(
    "/v1/sandboxes/{name}/jobs/{job_id}",
    response_model=JobInfo,
    dependencies=[Depends(require_agent_token)],
)
async def delete_sandbox_job(
    name: str,
    job_id: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> JobInfo:
    await _require_running_sandbox(name, backend)
    try:
        meta = await delete_job(backend, name, job_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _job_info(meta)


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path not found: {path}",
        ) from None
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except OSError as exc:
        # Belt-and-suspenders: microsandbox FilesystemError may surface as OSError.
        if is_missing_path_error(exc):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Path not found: {path}",
            ) from None
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sandbox filesystem error: {exc}",
        ) from exc
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


def _format_env_file(env: dict[str, str]) -> str:
    lines = [
        "# Managed by Everflow — do not commit. Provider API keys for this sandbox.",
        "# Sourced by knowledge worker / tooling. Values are never logged by the agent.",
    ]
    for key in sorted(env.keys()):
        val = env[key]
        if not key or val is None:
            continue
        # Escape for double-quoted shell assignment
        safe = (
            str(val)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "")
            .replace("\r", "")
        )
        lines.append(f'{key}="{safe}"')
    lines.append("")
    return "\n".join(lines)


@router.post(
    "/v1/sandboxes/{name}/secrets/providers",
    response_model=ProvidersSecretsResponse,
    dependencies=[Depends(require_agent_token)],
)
async def inject_provider_secrets(
    name: str,
    body: ProvidersSecretsRequest,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> ProvidersSecretsResponse:
    """Write provider secrets into the sandbox workspace (env file + JSON).

    Does not log secret values. Optional OpenCode auth is applied by the platform
    via the OpenCode proxy after ensure.
    """
    await _require_running_sandbox(name, backend)

    env = {k: v for k, v in (body.env or {}).items() if k and v}
    # Merge providers map into standard env names when env key missing
    provider_to_env = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "xai": "XAI_API_KEY",
        "custom": "CUSTOM_API_KEY",
    }
    for pid, key in (body.providers or {}).items():
        if not key:
            continue
        env_name = provider_to_env.get(pid.lower())
        if env_name and env_name not in env:
            env[env_name] = key

    if not env and not (body.providers or {}):
        return ProvidersSecretsResponse(
            sandbox_name=name,
            written=False,
            env_keys=[],
            opencode_providers=[],
            path=None,
            error="No secrets provided",
        )

    try:
        import json

        await backend.write_fs(name, _PROVIDERS_ENV_PATH, _format_env_file(env).encode("utf-8"))
        payload = json.dumps({"env": env, "providers": body.providers or {}}, indent=2)
        await backend.write_fs(name, _PROVIDERS_JSON_PATH, payload.encode("utf-8"))
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("inject provider secrets failed name=%s", name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to write provider secrets",
        ) from exc

    logger.info(
        "provider secrets written name=%s env_keys=%s providers=%s",
        name,
        sorted(env.keys()),
        sorted((body.providers or {}).keys()),
    )
    return ProvidersSecretsResponse(
        sandbox_name=name,
        written=True,
        env_keys=sorted(env.keys()),
        opencode_providers=sorted((body.providers or {}).keys()),
        path=_PROVIDERS_ENV_PATH,
    )


@router.post(
    "/v1/sandboxes/{name}/opencode/ensure",
    response_model=OpenCodeEnsureResponse,
    dependencies=[Depends(require_agent_token)],
)
async def opencode_ensure(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
    settings: Annotated[Settings, Depends(get_settings)],
    body: OpenCodeEnsureRequest | None = None,
) -> OpenCodeEnsureResponse:
    """Start (or reuse) opencode serve for this sandbox workspace.

    Always injects Everflow MCP into the workspace used by OpenCode (host path
    and/or guest FS). For real microVMs, starts a reverse tunnel so everflow-mcp
    can reach the platform API via 127.0.0.1 inside the guest.
    """
    from app.api_tunnel import get_api_tunnel_manager
    from app.everflow_mcp_inject import (
        ensure_everflow_mcp_package,
        write_everflow_mcp_guest,
        write_everflow_mcp_host,
    )

    rec = await _require_running_sandbox(name, backend)
    mgr = get_opencode_manager()
    force = bool(body.force_restart) if body else False
    workspace = rec.workspace_path or ""
    mcp_status: dict[str, Any] | None = None
    cfg = settings

    async def _configure_everflow_mcp(*, guest: bool, host_ws: Path | None) -> None:
        nonlocal mcp_status, force
        if not body:
            return
        if not (body.everflow_token and body.everflow_project_id):
            return

        # Agent dials platform via compose DNS (not guest-visible host IPs).
        agent_platform_url = (cfg.platform_api_url or body.everflow_api_url or "").rstrip("/")
        # Prefer non-localhost URL for agent-side dial when body only has localhost.
        if body.everflow_api_url and "localhost" not in body.everflow_api_url and "127.0.0.1" not in body.everflow_api_url:
            agent_platform_url = body.everflow_api_url.rstrip("/")
        elif cfg.platform_api_url:
            agent_platform_url = cfg.platform_api_url.rstrip("/")

        guest_api_url = agent_platform_url
        tunnel_info: dict[str, Any] | None = None
        package_status: dict[str, Any] | None = None

        if guest:
            # Stale guest images often lack everflow_mcp; install from agent bundle.
            package_status = await ensure_everflow_mcp_package(backend, name)
            if not package_status.get("installed"):
                mcp_status = {
                    "configured": False,
                    "error": package_status.get("error") or "everflow_mcp not installed in guest",
                    "package": package_status,
                    "mode": "guest",
                }
                return

        if guest and agent_platform_url:
            async def _kill_guest_port(sandbox_name: str, listen_port: int) -> None:
                await backend.exec(
                    sandbox_name,
                    "sh",
                    [
                        "-c",
                        f"fuser -k {listen_port}/tcp 2>/dev/null || "
                        f"python3 -c \"import os,signal,subprocess; "
                        f"subprocess.run(['sh','-c',"
                        f"'for p in $(ls /proc | grep -E \\\"^[0-9]+$\\\"); do "
                        f"grep -qa {listen_port} /proc/$p/cmdline 2>/dev/null && kill -9 $p; done'],"
                        f"check=False)\" 2>/dev/null || true",
                    ],
                    cwd="/workspace",
                    timeout_seconds=10,
                )

            try:
                tunnel_info = await get_api_tunnel_manager().ensure(
                    name,
                    target_url=agent_platform_url,
                    listen_port=int(cfg.everflow_mcp_tunnel_port),
                    force=True,
                    kill_guest_port=_kill_guest_port,
                )
                if tunnel_info.get("ok") and tunnel_info.get("api_url"):
                    guest_api_url = str(tunnel_info["api_url"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("api tunnel ensure failed name=%s: %s", name, exc)
                tunnel_info = {"ok": False, "error": str(exc)}

        # Host-mode OpenCode runs on agent host — use body URL or agent platform URL.
        host_api_url = (body.everflow_api_url or agent_platform_url).rstrip("/")
        # None / "everflow-mcp" → python3 -m everflow_mcp (PATH-safe) in inject.
        command = body.everflow_mcp_command

        if guest:
            mcp_status = await write_everflow_mcp_guest(
                backend,
                name,
                api_url=guest_api_url,
                token=body.everflow_token,
                project_id=body.everflow_project_id,
                command=command,
            )
        elif host_ws is not None:
            mcp_status = write_everflow_mcp_host(
                host_ws,
                api_url=host_api_url,
                token=body.everflow_token,
                project_id=body.everflow_project_id,
                command=command,
            )
        if mcp_status is not None and tunnel_info is not None:
            mcp_status = {**mcp_status, "tunnel": tunnel_info}
        if mcp_status is not None and package_status is not None:
            mcp_status = {**mcp_status, "package": package_status}
        # Config changed — force OpenCode restart so it reloads MCP servers.
        if mcp_status and mcp_status.get("configured"):
            force = True

    try:
        # Host path available → run OpenCode as host process against workspace
        if workspace and not workspace.startswith("named:") and workspace != "(guest-only)":
            ws_path = Path(workspace)
            if ws_path.is_dir():
                await _configure_everflow_mcp(guest=False, host_ws=ws_path)
                status_dict = await mgr.ensure_host(name, str(ws_path), force_restart=force)
                resp = OpenCodeEnsureResponse(**status_dict)
                resp.everflow_mcp = mcp_status
                return resp

        # Guest-only microVM: write MCP into guest FS + reverse tunnel
        await _configure_everflow_mcp(guest=True, host_ws=_host_workspace_path(rec))
        # Also mirror to host path if present (best-effort)
        host_ws = _host_workspace_path(rec)
        if host_ws is not None and host_ws.is_dir() and body and body.everflow_token:
            try:
                write_everflow_mcp_host(
                    host_ws,
                    api_url=(body.everflow_api_url or cfg.platform_api_url or "").rstrip("/"),
                    token=body.everflow_token,
                    project_id=body.everflow_project_id or "",
                    command=body.everflow_mcp_command,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("host mirror mcp write ignored: %s", exc)

        status_dict = await mgr.ensure_guest_via_exec(
            name,
            exec_fn=backend.exec,
            workspace_guest="/workspace",
            force_restart=force,
        )
        resp = OpenCodeEnsureResponse(**status_dict)
        resp.everflow_mcp = mcp_status
        return resp
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sandbox not found") from None


def _host_workspace_path(rec: Any) -> Path | None:
    """Return a host-accessible workspace Path, or None for guest-only sandboxes."""
    workspace = getattr(rec, "workspace_path", None) or ""
    if not workspace or workspace.startswith("named:") or workspace == "(guest-only)":
        return None
    ws_path = Path(workspace)
    if not ws_path.is_dir():
        return None
    return ws_path


@router.get(
    "/v1/sandboxes/{name}/harness/opencode",
    response_model=OpenCodeHarnessResponse,
    dependencies=[Depends(require_agent_token)],
)
async def get_opencode_harness(
    name: str,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> OpenCodeHarnessResponse:
    """Read OpenCode agents/skills/MCP pack from the sandbox workspace."""
    rec = await _require_running_sandbox(name, backend)
    ws = _host_workspace_path(rec)
    if ws is not None:
        pack = read_pack_from_workspace(ws)
    else:
        # Named volume / guest-only: scan via backend list_fs + read_fs
        pack = await read_pack_via_backend(backend, name)
    return OpenCodeHarnessResponse(
        sandbox_name=name,
        agents=list(pack.get("agents") or []),
        skills=list(pack.get("skills") or []),
        commands=list(pack.get("commands") or []),
        plugins=[str(p) for p in (pack.get("plugins") or [])],
        mcp=dict(pack.get("mcp") or {}),
        manifest=dict(pack.get("manifest") or {}),
        opencode_json=dict(pack.get("opencode_json") or {}),
    )


@router.put(
    "/v1/sandboxes/{name}/harness/opencode",
    response_model=OpenCodeHarnessResponse,
    dependencies=[Depends(require_agent_token)],
)
async def put_opencode_harness(
    name: str,
    body: OpenCodeHarnessPack,
    backend: Annotated[SandboxBackend, Depends(get_backend)],
) -> OpenCodeHarnessResponse:
    """Write/merge OpenCode agents, skills, and MCP into the sandbox workspace."""
    rec = await _require_running_sandbox(name, backend)
    ws = _host_workspace_path(rec)
    # Keep null MCP values (server deletion) — exclude_none would drop them.
    payload = body.model_dump(exclude_none=True)
    if body.mcp is not None:
        payload["mcp"] = body.mcp
    try:
        if ws is not None:
            pack = apply_pack_to_workspace(ws, payload)
        else:
            pack = await apply_pack_via_backend(backend, name, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Guest harness write failed: {exc}",
        ) from exc
    except OSError as exc:
        # Includes microsandbox FilesystemError (ENOENT when parent dirs missing, etc.)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Guest harness write failed: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("put_opencode_harness failed name=%s", name)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Guest harness write failed: {exc}",
        ) from exc
    return OpenCodeHarnessResponse(
        sandbox_name=name,
        agents=list(pack.get("agents") or []),
        skills=list(pack.get("skills") or []),
        commands=list(pack.get("commands") or []),
        plugins=[str(p) for p in (pack.get("plugins") or [])],
        mcp=dict(pack.get("mcp") or {}),
        manifest=dict(pack.get("manifest") or {}),
        opencode_json=dict(pack.get("opencode_json") or {}),
        written=pack.get("written"),
    )


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
    from app.desktop import ensure_guest_desktop_for_proxy

    await ensure_guest_desktop_for_proxy(backend.exec, name, port)
    try:
        dial_host, dial_port, mode = await resolve_dial_target(name, port, backend=backend)
    except Exception as exc:  # noqa: BLE001
        logger.warning("resolve dial target failed name=%s port=%s: %s", name, port, exc)
        dial_host, dial_port, mode = "127.0.0.1", port, "unreachable"

    # Prefer real TCP (host or tunnel). Fall back to guest-exec HTTP when dial fails.
    return await proxy_http_to_port(
        request,
        port=dial_port,
        path=path or "",
        host=dial_host,
        host_header=f"127.0.0.1:{port}",
        guest_port=port,
        exec_fn=backend.exec,
        sandbox_name=name,
    )


@router.websocket("/v1/sandboxes/{name}/proxy/{port}")
@router.websocket("/v1/sandboxes/{name}/proxy/{port}/{path:path}")
async def sandbox_port_proxy_ws(
    websocket: WebSocket,
    name: str,
    port: int,
    path: str = "",
    # Prefer agent_token so Vite HMR can keep using ?token= for its own handshake.
    agent_token: str = Query(default=""),
    token: str = Query(default=""),
) -> None:
    """WebSocket reverse-proxy (host dial or guest TCP tunnel for HMR)."""
    settings = get_settings()
    auth = agent_token or token
    sub = ws_requested_subprotocol(websocket)

    async def _reject(code: int) -> None:
        # Reject without accept so the edge hop fails cleanly (no half-open HMR).
        logger.debug(
            "preview ws reject name=%s port=%s code=%s sub=%s",
            name,
            port,
            code,
            sub,
        )
        try:
            await websocket.close(code=code)
        except Exception:
            pass

    if auth != settings.sandbox_agent_token:
        await _reject(4403)
        return
    if port < 1 or port > 65535:
        await _reject(4400)
        return

    backend: SandboxBackend = websocket.app.state.backend  # type: ignore[assignment]
    rec = await backend.get(name)
    if rec is None or rec.status != "running":
        await _reject(4404)
        return

    from app.desktop import ensure_guest_desktop_for_proxy

    await ensure_guest_desktop_for_proxy(backend.exec, name, port)

    query = websocket.url.query
    # Strip agent auth params only; keep Vite HMR ?token= (and everything else)
    if query:
        from urllib.parse import parse_qsl, urlencode

        agent_secret = settings.sandbox_agent_token
        pairs = []
        for k, v in parse_qsl(query, keep_blank_values=True):
            if k == "agent_token":
                continue
            # Legacy agent auth used token=; strip only if value is the agent secret
            if k == "token" and v == agent_secret:
                continue
            pairs.append((k, v))
        query = urlencode(pairs)

    try:
        dial_host, dial_port, mode = await resolve_dial_target(name, port, backend=backend)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ws resolve dial failed name=%s port=%s: %s", name, port, exc)
        await _reject(1011)
        return

    if mode == "unreachable":
        await _reject(1011)
        return

    await proxy_websocket_to_port(
        websocket,
        port=dial_port,
        path=path or "",
        query=query,
        host=dial_host,
        guest_port=port,
    )
