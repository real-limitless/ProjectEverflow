"""Microsandbox backend abstraction: real SDK or in-memory mock."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)

# Prefer named volumes in nested Docker+KVM; bind and guest-only are fallbacks.
VOLUME_STRATEGY_ORDER: tuple[str, ...] = ("named-volume", "bind", "no-volumes")
# Process-local: last strategy that successfully booted a sandbox (speeds later creates).
_last_volume_strategy: str | None = None


def volume_attempt_order(strategy: str | None, *, last_success: str | None = None) -> list[str]:
    """Resolve which mount strategies to try, and in what order."""
    raw = (strategy or "auto").strip().lower()
    if raw in VOLUME_STRATEGY_ORDER:
        return [raw]
    # auto (or unknown → auto)
    order = list(VOLUME_STRATEGY_ORDER)
    cached = last_success if last_success in VOLUME_STRATEGY_ORDER else _last_volume_strategy
    if cached and cached in order:
        order.remove(cached)
        order.insert(0, cached)
    return order


def remember_volume_strategy(label: str) -> None:
    global _last_volume_strategy
    if label in VOLUME_STRATEGY_ORDER:
        _last_volume_strategy = label


WORKSPACE_GUEST = "/workspace"


def normalize_guest_path(path: str | None, *, allow_tmp: bool = False) -> str:
    """Map a request path to an absolute path inside the guest workspace.

    Relative paths (including ``.`` / ``./``) resolve under ``/workspace``.
    Absolute paths must stay under ``/workspace``, or under ``/tmp`` when
    ``allow_tmp`` is true (bootstrap scripts).
    """
    raw = (path or ".").strip() or "."
    if raw in (".", "./"):
        return WORKSPACE_GUEST
    while raw.startswith("./"):
        raw = raw[2:]
        if not raw:
            return WORKSPACE_GUEST

    if raw.startswith("/"):
        if raw == WORKSPACE_GUEST or raw.startswith(WORKSPACE_GUEST + "/"):
            # Collapse /workspace and /workspace/
            cleaned = raw.rstrip("/") or WORKSPACE_GUEST
            return cleaned if cleaned.startswith(WORKSPACE_GUEST) else WORKSPACE_GUEST
        if allow_tmp and (raw == "/tmp" or raw.startswith("/tmp/")):
            return raw
        raise PermissionError(f"path escapes workspace: {path}")

    cleaned = raw.lstrip("/")
    if cleaned.startswith("workspace/"):
        cleaned = cleaned[len("workspace/") :]
    parts: list[str] = []
    for part in cleaned.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise PermissionError("path escapes workspace")
            parts.pop()
            continue
        parts.append(part)
    if not parts:
        return WORKSPACE_GUEST
    return f"{WORKSPACE_GUEST}/{'/'.join(parts)}"


def guest_entry_relpath(guest_dir: str, entry_name: str) -> str:
    """Workspace-relative path for a directory listing entry (no leading ./)."""
    base = guest_dir.rstrip("/") or WORKSPACE_GUEST
    if base == WORKSPACE_GUEST:
        parent_rel = ""
    elif base.startswith(WORKSPACE_GUEST + "/"):
        parent_rel = base[len(WORKSPACE_GUEST) + 1 :]
    else:
        parent_rel = base.lstrip("/")
    if not parent_rel:
        return entry_name
    return f"{parent_rel}/{entry_name}"


@dataclass
class SandboxRecord:
    name: str
    status: str
    image: str
    labels: dict[str, str] = field(default_factory=dict)
    harnesses: list[str] = field(default_factory=list)
    workspace_path: str | None = None
    created_at: datetime | None = None
    error: str | None = None


class SandboxBackend(ABC):
    @abstractmethod
    async def health(self) -> dict[str, Any]: ...

    @abstractmethod
    async def create(
        self,
        name: str,
        *,
        image: str,
        cpus: int,
        memory_mib: int,
        labels: dict[str, str],
        harnesses: list[str],
        workspace_host_path: str | None,
        replace: bool = False,
    ) -> SandboxRecord: ...

    @abstractmethod
    async def get(self, name: str) -> SandboxRecord | None: ...

    @abstractmethod
    async def list(self) -> list[SandboxRecord]: ...

    @abstractmethod
    async def start(self, name: str) -> SandboxRecord: ...

    @abstractmethod
    async def stop(self, name: str) -> SandboxRecord: ...

    @abstractmethod
    async def remove(self, name: str) -> None: ...

    @abstractmethod
    async def exec(
        self,
        name: str,
        cmd: str,
        args: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = 120,
    ) -> tuple[int, str, str]: ...

    @abstractmethod
    async def list_fs(self, name: str, path: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def read_fs(self, name: str, path: str) -> bytes: ...

    @abstractmethod
    async def write_fs(self, name: str, path: str, content: bytes) -> None: ...

    @abstractmethod
    async def bootstrap(self, name: str, harnesses: list[str]) -> SandboxRecord: ...

    async def shell_session(
        self,
        name: str,
        websocket: Any,
        *,
        cmd: str | None = None,
        cwd: str = "/workspace",
    ) -> None:
        """Interactive PTY over WebSocket. Override in backends."""
        raise NotImplementedError("Interactive shell not supported on this backend")


def kvm_available() -> bool:
    return Path("/dev/kvm").exists()


def _is_sandbox_not_found(exc: BaseException) -> bool:
    """True if microsandbox (or wrapper) reports the named sandbox is missing."""
    name = type(exc).__name__
    if name in ("SandboxNotFoundError", "NotFoundError"):
        return True
    msg = str(exc).lower()
    return "not found" in msg or "does not exist" in msg


class MockSandboxBackend(SandboxBackend):
    """In-memory sandboxes backed by host workspace directories (no KVM)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sandboxes: dict[str, SandboxRecord] = {}
        self._lock = asyncio.Lock()

    def _workspace(self, name: str, explicit: str | None) -> Path:
        if explicit:
            path = Path(explicit)
        else:
            path = self._settings.workspace_path / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "kvm": kvm_available(),
            "sdk": "mock",
            "mock": True,
        }

    async def create(
        self,
        name: str,
        *,
        image: str,
        cpus: int,
        memory_mib: int,
        labels: dict[str, str],
        harnesses: list[str],
        workspace_host_path: str | None,
        replace: bool = False,
    ) -> SandboxRecord:
        async with self._lock:
            existing = self._sandboxes.get(name)
            if existing and existing.status not in ("destroyed", "error"):
                if not replace:
                    # Idempotent: return existing running/stopped sandbox
                    return existing
                # Force recreate: drop registry entry; keep workspace files
                self._sandboxes.pop(name, None)

            ws = self._workspace(name, workspace_host_path)
            readme = ws / "README.md"
            if not readme.exists():
                readme.write_text(
                    f"# {name}\n\nEverflow project workspace (mock sandbox).\n",
                    encoding="utf-8",
                )

            rec = SandboxRecord(
                name=name,
                status="running",
                image=image,
                labels=dict(labels),
                harnesses=list(harnesses),
                workspace_path=str(ws),
                created_at=datetime.now(timezone.utc),
            )
            if harnesses:
                await self._mock_bootstrap(ws, harnesses)
            self._sandboxes[name] = rec
            logger.info("mock sandbox created name=%s workspace=%s", name, ws)
            return rec

    async def _mock_bootstrap(self, ws: Path, harnesses: list[str]) -> None:
        bin_dir = ws / ".everflow" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        for h in harnesses:
            if h in ("agent-claude-code", "claude-code"):
                stub = bin_dir / "claude"
                stub.write_text(
                    "#!/bin/sh\necho 'claude (mock harness) — configure API key to use real CLI'\n",
                    encoding="utf-8",
                )
                stub.chmod(0o755)
            if h in ("agent-opencode", "opencode"):
                stub = bin_dir / "opencode"
                stub.write_text(
                    "#!/bin/sh\necho 'opencode (mock harness) — configure API key to use real CLI'\n",
                    encoding="utf-8",
                )
                stub.chmod(0o755)
        marker = ws / ".everflow" / "bootstrapped"
        marker.write_text(",".join(harnesses) + "\n", encoding="utf-8")

    async def get(self, name: str) -> SandboxRecord | None:
        return self._sandboxes.get(name)

    async def list(self) -> list[SandboxRecord]:
        return list(self._sandboxes.values())

    async def start(self, name: str) -> SandboxRecord:
        rec = self._require(name)
        rec.status = "running"
        rec.error = None
        return rec

    async def stop(self, name: str) -> SandboxRecord:
        rec = self._require(name)
        rec.status = "stopped"
        return rec

    async def remove(self, name: str) -> None:
        async with self._lock:
            rec = self._sandboxes.pop(name, None)
            if rec and rec.workspace_path:
                # Keep workspace data; only drop registry entry
                pass

    async def exec(
        self,
        name: str,
        cmd: str,
        args: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = 120,
    ) -> tuple[int, str, str]:
        rec = self._require(name)
        if rec.status != "running":
            raise RuntimeError(f"Sandbox {name} is not running (status={rec.status})")
        workdir = cwd or rec.workspace_path or str(self._settings.workspace_path / name)
        full_env = os.environ.copy()
        if rec.workspace_path:
            bin_dir = str(Path(rec.workspace_path) / ".everflow" / "bin")
            full_env["PATH"] = bin_dir + os.pathsep + full_env.get("PATH", "")
        if env:
            full_env.update(env)

        def _run() -> tuple[int, str, str]:
            try:
                proc = subprocess.run(
                    [cmd, *args],
                    cwd=workdir,
                    env=full_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                return proc.returncode, proc.stdout, proc.stderr
            except FileNotFoundError as exc:
                return 127, "", str(exc)
            except subprocess.TimeoutExpired:
                return 124, "", "exec timed out"

        return await asyncio.to_thread(_run)

    def _ws_path(self, name: str, path: str) -> Path:
        rec = self._require(name)
        root = Path(rec.workspace_path or (self._settings.workspace_path / name))
        # Prevent path escape
        rel = path.lstrip("/")
        if rel.startswith("workspace/"):
            rel = rel[len("workspace/") :]
        target = (root / rel).resolve()
        if not str(target).startswith(str(root.resolve())):
            raise PermissionError("path escapes workspace")
        return target

    async def list_fs(self, name: str, path: str) -> list[dict[str, Any]]:
        target = self._ws_path(name, path or ".")
        if not target.exists():
            raise FileNotFoundError(path)
        if not target.is_dir():
            raise NotADirectoryError(path)
        entries: list[dict[str, Any]] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            entries.append(
                {
                    "path": str(child.relative_to(Path(self._require(name).workspace_path or child))),
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return entries

    async def read_fs(self, name: str, path: str) -> bytes:
        target = self._ws_path(name, path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return target.read_bytes()

    async def write_fs(self, name: str, path: str, content: bytes) -> None:
        target = self._ws_path(name, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    async def bootstrap(self, name: str, harnesses: list[str]) -> SandboxRecord:
        rec = self._require(name)
        ws = Path(rec.workspace_path or self._settings.workspace_path / name)
        await self._mock_bootstrap(ws, harnesses)
        rec.harnesses = list(dict.fromkeys([*rec.harnesses, *harnesses]))
        return rec

    async def shell_session(
        self,
        name: str,
        websocket: Any,
        *,
        cmd: str | None = None,
        cwd: str = "/workspace",
    ) -> None:
        from app.shell_ws import run_mock_shell

        rec = self._require(name)
        if rec.status != "running":
            raise RuntimeError(f"Sandbox {name} is not running")
        ws = rec.workspace_path or str(self._settings.workspace_path / name)
        # cwd relative to workspace when mock
        work = ws
        if cwd and cwd not in (".", "/workspace", "/workspace/"):
            # best-effort map /workspace/... → host path
            rel = cwd[len("/workspace") :].lstrip("/") if cwd.startswith("/workspace") else cwd
            candidate = Path(ws) / rel
            if candidate.is_dir():
                work = str(candidate)
        await run_mock_shell(work, websocket, cmd=cmd)

    def _require(self, name: str) -> SandboxRecord:
        rec = self._sandboxes.get(name)
        if rec is None:
            raise KeyError(name)
        return rec


class MicrosandboxBackend(SandboxBackend):
    """Real microsandbox SDK backend (requires KVM + microsandbox package)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._meta: dict[str, SandboxRecord] = {}
        # name -> in-flight harness install (cancelled on remove/replace)
        self._bootstrap_tasks: dict[str, asyncio.Task[None]] = {}
        self._bootstrap_gen: dict[str, int] = {}

    async def health(self) -> dict[str, Any]:
        try:
            import microsandbox  # noqa: F401

            sdk = "microsandbox"
        except ImportError:
            sdk = "missing"
        return {
            "status": "ok" if kvm_available() and sdk == "microsandbox" else "degraded",
            "kvm": kvm_available(),
            "sdk": sdk,
            "mock": False,
        }

    def _cancel_bootstrap(self, name: str) -> None:
        """Cancel any in-flight background harness install for this sandbox."""
        self._bootstrap_gen[name] = self._bootstrap_gen.get(name, 0) + 1
        task = self._bootstrap_tasks.pop(name, None)
        if task is not None and not task.done():
            task.cancel()
            logger.debug("cancelled in-flight bootstrap name=%s", name)

    def _schedule_bootstrap(self, name: str, harnesses: list[str]) -> None:
        """Install harnesses after create returns (does not block ready)."""
        if not harnesses:
            return
        self._cancel_bootstrap(name)
        gen = self._bootstrap_gen.get(name, 0)

        async def _run() -> None:
            if self._bootstrap_gen.get(name, 0) != gen:
                return
            try:
                await self.bootstrap(name, harnesses)
                if self._bootstrap_gen.get(name, 0) != gen:
                    return
                rec = self._meta.get(name)
                if rec is not None:
                    rec.harnesses = list(dict.fromkeys([*rec.harnesses, *harnesses]))
                    if rec.error and rec.error.startswith("bootstrap failed:"):
                        rec.error = None
                logger.info("background bootstrap finished name=%s harnesses=%s", name, harnesses)
            except asyncio.CancelledError:
                logger.info("background bootstrap cancelled name=%s", name)
                raise
            except Exception as exc:
                if self._bootstrap_gen.get(name, 0) != gen:
                    return
                logger.exception(
                    "background bootstrap failed name=%s (sandbox still running): %s",
                    name,
                    exc,
                )
                rec = self._meta.get(name)
                if rec is not None:
                    rec.error = f"bootstrap failed: {exc}"[:500]
            finally:
                if self._bootstrap_tasks.get(name) is asyncio.current_task():
                    self._bootstrap_tasks.pop(name, None)

        self._bootstrap_tasks[name] = asyncio.create_task(_run(), name=f"bootstrap:{name}")

    async def _force_cleanup(self, name: str) -> None:
        """Best-effort stop+remove so create/replace is clean."""
        try:
            await self.remove(name)
        except Exception as exc:
            logger.debug("cleanup before create name=%s: %s", name, exc)

    async def _build_volume_attempts(
        self,
        name: str,
        ws: Path,
    ) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
        """Build ordered mount strategies to try; only prep strategies we will attempt."""
        from microsandbox import Volume

        vol_name = f"ef-ws-{name}"[:120]
        errors: list[str] = []
        order = volume_attempt_order(self._settings.volume_strategy)
        attempts: list[tuple[str, dict[str, Any]]] = []

        for label in order:
            if label == "named-volume":
                try:
                    try:
                        await Volume.create(vol_name, kind="dir")
                    except Exception:
                        pass  # already exists
                    attempts.append(
                        (
                            "named-volume",
                            {
                                "volumes": {"/workspace": Volume.named(vol_name)},
                                "workdir": "/workspace",
                            },
                        )
                    )
                except Exception as exc:
                    errors.append(f"named-volume-prep: {exc}")
            elif label == "bind":
                attempts.append(
                    (
                        "bind",
                        {
                            "volumes": {"/workspace": Volume.bind(str(ws))},
                            "workdir": "/workspace",
                        },
                    )
                )
            elif label == "no-volumes":
                attempts.append(("no-volumes", {"workdir": "/root"}))

        return attempts, errors

    async def create(
        self,
        name: str,
        *,
        image: str,
        cpus: int,
        memory_mib: int,
        labels: dict[str, str],
        harnesses: list[str],
        workspace_host_path: str | None,
        replace: bool = False,
    ) -> SandboxRecord:
        from microsandbox import Sandbox

        if not kvm_available():
            raise RuntimeError("/dev/kvm is not available on this host")

        ws = Path(workspace_host_path or (self._settings.workspace_path / name))
        ws.mkdir(parents=True, exist_ok=True)

        # Drop any previous bootstrap for this name before teardown/recreate
        self._cancel_bootstrap(name)

        if replace:
            await self._force_cleanup(name)

        # Nested Docker+KVM often rejects bind mounts; try preferred/cached strategy first.
        vol_name = f"ef-ws-{name}"[:120]
        attempts, errors = await self._build_volume_attempts(name, ws)
        sb = None
        used_workspace = str(ws)
        won_label: str | None = None

        for label, extra in attempts:
            try:
                logger.info("Sandbox.create attempt=%s name=%s image=%s", label, name, image)
                sb = await Sandbox.create(
                    name,
                    image=image,
                    cpus=cpus,
                    memory=memory_mib,
                    labels=labels,
                    detached=True,
                    replace=True,
                    **extra,
                )
                await sb.detach()
                logger.info("Sandbox.create succeeded attempt=%s name=%s", label, name)
                won_label = label
                remember_volume_strategy(label)
                if label == "named-volume":
                    used_workspace = f"named:{vol_name}"
                elif label == "no-volumes":
                    used_workspace = "(guest-only)"
                break
            except Exception as exc:
                msg = f"{label}: {exc}"
                errors.append(msg)
                logger.warning("Sandbox.create failed attempt=%s name=%s: %s", label, name, exc)
                await self._force_cleanup(name)
                sb = None

        if sb is None:
            detail = " | ".join(errors) if errors else "unknown error"
            raise RuntimeError(
                "Failed to boot microVM sandbox. "
                f"Attempts: {detail}. "
                "If running in Docker/Podman, ensure privileged + /dev/kvm and nested virt; "
                "or set SANDBOX_MOCK=true for local mock sandboxes."
            )

        # Ready as soon as the microVM is up. Harness install runs in the background.
        rec = SandboxRecord(
            name=name,
            status="running",
            image=image,
            labels=dict(labels),
            harnesses=list(harnesses),
            workspace_path=used_workspace,
            created_at=datetime.now(timezone.utc),
        )
        self._meta[name] = rec
        if harnesses:
            self._schedule_bootstrap(name, list(harnesses))
            logger.info(
                "Sandbox.create ready name=%s strategy=%s harnesses deferred=%s",
                name,
                won_label,
                harnesses,
            )
        else:
            logger.info("Sandbox.create ready name=%s strategy=%s", name, won_label)
        return rec

    async def get(self, name: str) -> SandboxRecord | None:
        from microsandbox import Sandbox

        try:
            handle = await Sandbox.get(name)
        except Exception:
            # Do not return stale in-memory "running" if the VM is gone
            meta = self._meta.get(name)
            if meta is not None:
                meta.status = "error"
                meta.error = meta.error or "Sandbox not found on microsandbox runtime"
            return meta

        meta = self._meta.get(name)
        status = getattr(handle, "status", None) or (meta.status if meta else "unknown")
        if callable(status):
            status = status()
        rec = SandboxRecord(
            name=name,
            status=str(status),
            image=meta.image if meta else self._settings.default_image,
            labels=meta.labels if meta else {},
            harnesses=meta.harnesses if meta else [],
            workspace_path=meta.workspace_path if meta else None,
            created_at=meta.created_at if meta else None,
            error=meta.error if meta else None,
        )
        self._meta[name] = rec
        return rec

    async def list(self) -> list[SandboxRecord]:
        from microsandbox import Sandbox

        try:
            handles = await Sandbox.list()
        except Exception:
            return list(self._meta.values())

        out: list[SandboxRecord] = []
        for h in handles:
            name = getattr(h, "name", None)
            if callable(name):
                name = name()
            name = str(name)
            rec = await self.get(name)
            if rec:
                out.append(rec)
        return out

    async def start(self, name: str) -> SandboxRecord:
        from microsandbox import Sandbox

        try:
            sb = await Sandbox.start(name, detached=True)
            await sb.detach()
        except Exception as exc:
            if _is_sandbox_not_found(exc):
                raise KeyError(name) from exc
            raise
        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        rec.status = "running"
        return rec

    async def stop(self, name: str) -> SandboxRecord:
        from microsandbox import Sandbox

        try:
            handle = await Sandbox.get(name)
        except Exception as exc:
            if _is_sandbox_not_found(exc):
                raise KeyError(name) from exc
            raise
        try:
            if hasattr(handle, "stop"):
                await handle.stop()
            elif hasattr(handle, "connect"):
                sb = await handle.connect()
                await sb.stop()
        except Exception as exc:
            if _is_sandbox_not_found(exc):
                raise KeyError(name) from exc
            raise
        rec = await self.get(name)
        if rec is None:
            # Already gone after stop — treat as stopped missing
            raise KeyError(name)
        rec.status = "stopped"
        return rec

    async def remove(self, name: str) -> None:
        """Idempotent: missing sandbox is success (supports recreate after agent wipe)."""
        from microsandbox import Sandbox

        self._cancel_bootstrap(name)

        try:
            handle = await Sandbox.get(name)
            status = getattr(handle, "status", "")
            if callable(status):
                status = status()
            if str(status) == "running":
                try:
                    await self.stop(name)
                except KeyError:
                    pass
        except Exception as exc:
            if _is_sandbox_not_found(exc):
                self._meta.pop(name, None)
                return
            # get failed for other reasons — still try remove
            logger.warning("Sandbox.get before remove failed for %s: %s", name, exc)

        try:
            await Sandbox.remove(name)
        except Exception as exc:
            if _is_sandbox_not_found(exc):
                self._meta.pop(name, None)
                return
            raise
        self._meta.pop(name, None)

    async def _connect(self, name: str) -> Any:
        from microsandbox import Sandbox

        try:
            handle = await Sandbox.get(name)
        except Exception as exc:
            if _is_sandbox_not_found(exc):
                raise KeyError(name) from exc
            raise
        if hasattr(handle, "connect"):
            return await handle.connect()
        try:
            return await Sandbox.start(name)
        except Exception as exc:
            if _is_sandbox_not_found(exc):
                raise KeyError(name) from exc
            raise

    async def exec(
        self,
        name: str,
        cmd: str,
        args: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = 120,
    ) -> tuple[int, str, str]:
        try:
            sb = await self._connect(name)
        except KeyError:
            raise
        kwargs: dict[str, Any] = {}
        if cwd:
            kwargs["cwd"] = cwd
        if env:
            kwargs["env"] = env

        async def _do() -> tuple[int, str, str]:
            out = await sb.exec(cmd, args, **kwargs)
            stdout = getattr(out, "stdout_text", None)
            if stdout is None:
                stdout = getattr(out, "stdout", lambda: "")()
                if callable(stdout):
                    stdout = stdout()
            stderr = getattr(out, "stderr_text", None)
            if stderr is None:
                stderr = getattr(out, "stderr", lambda: "")()
                if callable(stderr):
                    stderr = stderr()
            code = getattr(out, "exit_code", None)
            if code is None:
                code = getattr(out, "returncode", 0)
            return int(code or 0), str(stdout or ""), str(stderr or "")

        try:
            if timeout_seconds:
                return await asyncio.wait_for(_do(), timeout=timeout_seconds)
            return await _do()
        except Exception as exc:
            if _is_sandbox_not_found(exc):
                raise KeyError(name) from exc
            raise

    async def list_fs(self, name: str, path: str) -> list[dict[str, Any]]:
        """List one directory under the guest workspace (relative paths, no . / ..)."""
        guest_path = normalize_guest_path(path)
        q = shlex_quote(guest_path)
        # Prefer GNU find -printf; fall back to ls -1A (never emits . / ..).
        script = (
            f"if [ ! -e {q} ]; then exit 2; fi; "
            f"if [ ! -d {q} ]; then exit 3; fi; "
            f'if find {q} -maxdepth 1 -mindepth 1 -printf "%y\\t%s\\t%f\\n" 2>/dev/null; then '
            f":; "
            f"else "
            f"ls -1A {q} | while IFS= read -r n; do "
            f'[ -z "$n" ] && continue; '
            f'p={q}/"$n"; '
            f'if [ -d "$p" ]; then t=d; else t=f; fi; '
            f's=$(stat -c %s "$p" 2>/dev/null || wc -c <"$p" 2>/dev/null || echo 0); '
            f'printf "%s\\t%s\\t%s\\n" "$t" "$s" "$n"; '
            f"done; "
            f"fi"
        )
        code, stdout, stderr = await self.exec(name, "sh", ["-c", script])
        if code == 2:
            raise FileNotFoundError(path)
        if code == 3:
            raise NotADirectoryError(path)
        if code != 0:
            raise FileNotFoundError(stderr or path)

        entries: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            line = line.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            ftype, size_s, name_part = parts
            if not name_part or name_part in (".", ".."):
                continue
            is_dir = ftype.startswith("d")
            size: int | None
            try:
                size = int(str(size_s).strip()) if not is_dir else None
            except ValueError:
                size = None
            entries.append(
                {
                    "path": guest_entry_relpath(guest_path, name_part),
                    "name": name_part,
                    "is_dir": is_dir,
                    "size": size,
                }
            )
        return entries

    async def read_fs(self, name: str, path: str) -> bytes:
        sb = await self._connect(name)
        guest_path = normalize_guest_path(path, allow_tmp=True)
        if hasattr(sb, "fs"):
            data = await sb.fs.read(guest_path)
            return bytes(data)
        code, stdout, stderr = await self.exec(name, "cat", [guest_path])
        if code != 0:
            raise FileNotFoundError(stderr or path)
        return stdout.encode("utf-8")

    async def write_fs(self, name: str, path: str, content: bytes) -> None:
        sb = await self._connect(name)
        guest_path = normalize_guest_path(path, allow_tmp=True)
        if hasattr(sb, "fs"):
            await sb.fs.write(guest_path, content)
            return
        # fallback: base64 pipe
        import base64

        b64 = base64.b64encode(content).decode("ascii")
        q = shlex_quote(guest_path)
        code, _, stderr = await self.exec(
            name,
            "sh",
            ["-c", f"mkdir -p \"$(dirname {q})\" && echo {b64} | base64 -d > {q}"],
        )
        if code != 0:
            raise RuntimeError(stderr or "write failed")

    async def bootstrap(self, name: str, harnesses: list[str]) -> SandboxRecord:
        script_path = Path(__file__).resolve().parent / "bootstrap" / "install_harnesses.sh"
        if script_path.exists():
            script = script_path.read_text(encoding="utf-8")
            await self.write_fs(name, "/tmp/install_harnesses.sh", script.encode("utf-8"))
            args = " ".join(shlex_quote(h) for h in harnesses)
            code, stdout, stderr = await self.exec(
                name,
                "sh",
                ["/tmp/install_harnesses.sh", *harnesses],
                timeout_seconds=600,
            )
            if code != 0:
                logger.error("bootstrap failed: %s %s", stdout, stderr)
                raise RuntimeError(f"bootstrap failed: {stderr or stdout}")
        else:
            # Minimal markers when script missing
            for h in harnesses:
                await self.exec(
                    name,
                    "sh",
                    ["-c", f"mkdir -p /workspace/.everflow && echo {h} >> /workspace/.everflow/bootstrapped"],
                )

        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        rec.harnesses = list(dict.fromkeys([*rec.harnesses, *harnesses]))
        self._meta[name] = rec
        return rec

    async def shell_session(
        self,
        name: str,
        websocket: Any,
        *,
        cmd: str | None = None,
        cwd: str = "/workspace",
    ) -> None:
        from app.shell_ws import run_microsandbox_shell

        sb = await self._connect(name)
        workdir = cwd or "/workspace"
        await run_microsandbox_shell(sb, websocket, cmd=cmd, cwd=workdir)


def shlex_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def build_backend(settings: Settings) -> SandboxBackend:
    """
    Prefer real microsandbox. Mock only when SANDBOX_MOCK is explicitly true.

    If SANDBOX_MOCK is false/unset and KVM/SDK is missing, raise so deploy fails
    loudly instead of silently giving fake sandboxes.
    """
    if settings.sandbox_mock is True:
        logger.warning("SANDBOX_MOCK=true — using MockSandboxBackend (NOT for product)")
        return MockSandboxBackend(settings)

    if not kvm_available():
        raise RuntimeError(
            "/dev/kvm is not available. Real microVMs require KVM. "
            "Pass --device /dev/kvm and privileged, or set SANDBOX_MOCK=true only for CI."
        )
    try:
        import microsandbox  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "microsandbox Python package is not installed. "
            "Use deploy/sandbox-agent.Dockerfile based on ghcr.io/superradcompany/microsandbox."
        ) from exc

    # Prefer official runtime binary when present
    import shutil

    msb = shutil.which("msb")
    logger.info(
        "Using MicrosandboxBackend (real microVMs) kvm=yes msb=%s",
        msb or "(sdk-embedded)",
    )
    return MicrosandboxBackend(settings)
