"""Internal HTTP routes for sandbox-agent."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from app.auth import require_agent_token
from app.config import Settings, get_settings
from app.msb import SandboxBackend
from app.schemas import (
    BootstrapRequest,
    ExecRequest,
    ExecResult,
    FsEntry,
    FsWriteRequest,
    HealthResponse,
    SandboxCreateRequest,
    SandboxInfo,
)

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
