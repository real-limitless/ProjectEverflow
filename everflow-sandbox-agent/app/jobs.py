"""Detached background jobs inside a sandbox (nohup + log + metadata)."""

from __future__ import annotations

import json
import logging
import shlex
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.msb import SandboxBackend

logger = logging.getLogger(__name__)

JOBS_DIR_GUEST = "/workspace/.everflow/jobs"
JOBS_DIR_REL = ".everflow/jobs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meta_rel(job_id: str) -> str:
    return f"{JOBS_DIR_REL}/{job_id}.json"


def _log_guest(job_id: str) -> str:
    return f"{JOBS_DIR_GUEST}/{job_id}.log"


def _parse_meta(raw: bytes | str) -> dict[str, Any] | None:
    try:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
        data = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return data


async def _write_meta(backend: SandboxBackend, name: str, meta: dict[str, Any]) -> None:
    job_id = str(meta["id"])
    payload = json.dumps(meta, indent=2, sort_keys=True).encode("utf-8")
    await backend.write_fs(name, _meta_rel(job_id), payload)


async def _read_meta(backend: SandboxBackend, name: str, job_id: str) -> dict[str, Any] | None:
    try:
        raw = await backend.read_fs(name, _meta_rel(job_id))
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("read job meta failed name=%s id=%s: %s", name, job_id, exc)
        return None
    return _parse_meta(raw)


async def _pid_alive(backend: SandboxBackend, name: str, pid: int) -> bool:
    if pid <= 0:
        return False
    code, stdout, _ = await backend.exec(
        name,
        "sh",
        ["-c", f"kill -0 {int(pid)} 2>/dev/null && echo alive || echo dead"],
        cwd="/workspace",
        timeout_seconds=10,
    )
    if code != 0:
        return False
    return "alive" in (stdout or "")


async def _refresh_status(
    backend: SandboxBackend,
    name: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    status = str(meta.get("status") or "unknown")
    if status in ("killed", "exited", "error"):
        return meta
    pid = int(meta.get("pid") or 0)
    if not pid:
        meta = {**meta, "status": "error", "updated_at": _utc_now()}
        try:
            await _write_meta(backend, name, meta)
        except Exception:  # noqa: BLE001
            pass
        return meta
    alive = await _pid_alive(backend, name, pid)
    if alive:
        if status != "running":
            meta = {**meta, "status": "running", "updated_at": _utc_now()}
            try:
                await _write_meta(backend, name, meta)
            except Exception:  # noqa: BLE001
                pass
        return meta
    # Process gone — mark exited (best-effort exit code unknown for nohup)
    meta = {
        **meta,
        "status": "exited",
        "updated_at": _utc_now(),
    }
    try:
        await _write_meta(backend, name, meta)
    except Exception:  # noqa: BLE001
        pass
    return meta


async def start_job(
    backend: SandboxBackend,
    name: str,
    *,
    title: str,
    command: str,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Start a detached job via nohup; persist metadata + log under .everflow/jobs."""
    job_id = str(uuid.uuid4())
    work_cwd = (cwd or "/workspace").strip() or "/workspace"
    log_path = _log_guest(job_id)
    quoted_cmd = shlex.quote(command)
    quoted_cwd = shlex.quote(work_cwd)
    quoted_log = shlex.quote(log_path)

    mkdir_code, _, mkdir_err = await backend.exec(
        name,
        "mkdir",
        ["-p", JOBS_DIR_GUEST],
        cwd="/workspace",
        timeout_seconds=15,
    )
    if mkdir_code != 0:
        raise RuntimeError(mkdir_err or "Failed to create jobs directory")

    # nohup sh -c '<command>' > log 2>&1 & echo $!
    start_script = (
        f"cd {quoted_cwd} && "
        f"nohup sh -c {quoted_cmd} > {quoted_log} 2>&1 & echo $!"
    )
    code, stdout, stderr = await backend.exec(
        name,
        "sh",
        ["-c", start_script],
        cwd="/workspace",
        timeout_seconds=20,
    )
    if code != 0:
        raise RuntimeError(stderr or stdout or "Failed to start job")

    pid_str = (stdout or "").strip().splitlines()[-1].strip() if stdout else ""
    try:
        pid = int(pid_str)
    except ValueError as exc:
        raise RuntimeError(f"Failed to parse job pid from: {stdout!r}") from exc

    meta: dict[str, Any] = {
        "id": job_id,
        "title": title.strip() or command.strip()[:80] or "job",
        "command": command,
        "cwd": work_cwd,
        "pid": pid,
        "status": "running",
        "log_path": log_path,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "exit_code": None,
    }
    await _write_meta(backend, name, meta)
    return meta


async def list_jobs(backend: SandboxBackend, name: str) -> list[dict[str, Any]]:
    """List job metadata, refreshing running/exited status from pid liveness."""
    try:
        entries = await backend.list_fs(name, JOBS_DIR_REL)
    except FileNotFoundError:
        return []
    except Exception as exc:  # noqa: BLE001
        logger.debug("list jobs dir failed name=%s: %s", name, exc)
        return []

    jobs: list[dict[str, Any]] = []
    for entry in entries:
        ent_name = str(entry.get("name") or "")
        if not ent_name.endswith(".json") or entry.get("is_dir"):
            continue
        job_id = ent_name[: -len(".json")]
        meta = await _read_meta(backend, name, job_id)
        if not meta:
            continue
        meta = await _refresh_status(backend, name, meta)
        jobs.append(meta)

    jobs.sort(key=lambda j: str(j.get("created_at") or ""), reverse=True)
    return jobs


async def get_job(backend: SandboxBackend, name: str, job_id: str) -> dict[str, Any] | None:
    meta = await _read_meta(backend, name, job_id)
    if not meta:
        return None
    return await _refresh_status(backend, name, meta)


async def get_job_logs(
    backend: SandboxBackend,
    name: str,
    job_id: str,
    *,
    tail: int = 200,
) -> dict[str, Any]:
    meta = await get_job(backend, name, job_id)
    if meta is None:
        raise KeyError(job_id)
    n = max(1, min(int(tail), 5000))
    log_path = str(meta.get("log_path") or _log_guest(job_id))
    code, stdout, stderr = await backend.exec(
        name,
        "sh",
        ["-c", f"tail -n {n} {shlex.quote(log_path)} 2>/dev/null || true"],
        cwd="/workspace",
        timeout_seconds=15,
    )
    if code != 0 and stderr:
        logger.debug("tail job log failed name=%s id=%s: %s", name, job_id, stderr)
    return {
        "job_id": job_id,
        "status": meta.get("status"),
        "tail": n,
        "content": stdout or "",
    }


async def kill_job(backend: SandboxBackend, name: str, job_id: str) -> dict[str, Any]:
    meta = await get_job(backend, name, job_id)
    if meta is None:
        raise KeyError(job_id)
    status = str(meta.get("status") or "")
    if status in ("killed", "exited", "error"):
        return meta
    pid = int(meta.get("pid") or 0)
    if pid > 0:
        await backend.exec(
            name,
            "sh",
            [
                "-c",
                (
                    f"kill {pid} 2>/dev/null || true; "
                    f"sleep 0.3; "
                    f"kill -0 {pid} 2>/dev/null && kill -9 {pid} 2>/dev/null || true"
                ),
            ],
            cwd="/workspace",
            timeout_seconds=15,
        )
    meta = {
        **meta,
        "status": "killed",
        "updated_at": _utc_now(),
    }
    await _write_meta(backend, name, meta)
    return meta
