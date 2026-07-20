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


def kvm_available() -> bool:
    return Path("/dev/kvm").exists()


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
    ) -> SandboxRecord:
        async with self._lock:
            existing = self._sandboxes.get(name)
            if existing and existing.status not in ("destroyed", "error"):
                # Idempotent: return existing running/stopped sandbox
                return existing

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
    ) -> SandboxRecord:
        from microsandbox import Sandbox

        if not kvm_available():
            raise RuntimeError("/dev/kvm is not available on this host")

        ws = Path(workspace_host_path or (self._settings.workspace_path / name))
        ws.mkdir(parents=True, exist_ok=True)

        volumes: dict[str, Any] = {
            "/workspace": {"path": str(ws), "kind": "bind"},
        }

        try:
            sb = await Sandbox.create(
                name,
                image=image,
                cpus=cpus,
                memory=memory_mib,
                labels=labels,
                detached=True,
                replace=True,
                volumes=volumes,
                workdir="/workspace",
            )
            await sb.detach()
        except TypeError:
            # Older/newer SDK volume shape — fall back without volumes
            logger.warning("Sandbox.create volumes kwarg failed; retrying minimal create")
            sb = await Sandbox.create(
                name,
                image=image,
                cpus=cpus,
                memory=memory_mib,
                labels=labels,
                detached=True,
                replace=True,
                workdir="/workspace",
            )
            await sb.detach()

        rec = SandboxRecord(
            name=name,
            status="running",
            image=image,
            labels=dict(labels),
            harnesses=list(harnesses),
            workspace_path=str(ws),
            created_at=datetime.now(timezone.utc),
        )
        self._meta[name] = rec
        if harnesses:
            await self.bootstrap(name, harnesses)
        return rec

    async def get(self, name: str) -> SandboxRecord | None:
        from microsandbox import Sandbox

        try:
            handle = await Sandbox.get(name)
        except Exception:
            return self._meta.get(name)

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

        sb = await Sandbox.start(name, detached=True)
        await sb.detach()
        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        rec.status = "running"
        return rec

    async def stop(self, name: str) -> SandboxRecord:
        from microsandbox import Sandbox

        handle = await Sandbox.get(name)
        if hasattr(handle, "stop"):
            await handle.stop()
        elif hasattr(handle, "connect"):
            sb = await handle.connect()
            await sb.stop()
        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        rec.status = "stopped"
        return rec

    async def remove(self, name: str) -> None:
        from microsandbox import Sandbox

        try:
            handle = await Sandbox.get(name)
            status = getattr(handle, "status", "")
            if callable(status):
                status = status()
            if str(status) == "running":
                await self.stop(name)
        except Exception:
            pass
        await Sandbox.remove(name)
        self._meta.pop(name, None)

    async def _connect(self, name: str) -> Any:
        from microsandbox import Sandbox

        handle = await Sandbox.get(name)
        if hasattr(handle, "connect"):
            return await handle.connect()
        return await Sandbox.start(name)

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
        sb = await self._connect(name)
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

        if timeout_seconds:
            return await asyncio.wait_for(_do(), timeout=timeout_seconds)
        return await _do()

    async def list_fs(self, name: str, path: str) -> list[dict[str, Any]]:
        guest_path = path if path.startswith("/") else f"/workspace/{path.lstrip('/')}"
        code, stdout, stderr = await self.exec(
            name,
            "sh",
            [
                "-c",
                f'ls -la --time-style=long-iso {guest_path!s} 2>/dev/null || ls -la {guest_path!s}',
            ],
        )
        if code != 0:
            raise FileNotFoundError(stderr or path)
        entries: list[dict[str, Any]] = []
        for line in stdout.splitlines()[1:]:
            parts = line.split(maxsplit=7)
            if len(parts) < 8:
                continue
            name_part = parts[7]
            is_dir = parts[0].startswith("d")
            size = int(parts[4]) if parts[4].isdigit() else None
            entries.append(
                {
                    "path": f"{path.rstrip('/')}/{name_part}".lstrip("/"),
                    "name": name_part,
                    "is_dir": is_dir,
                    "size": size,
                }
            )
        return entries

    async def read_fs(self, name: str, path: str) -> bytes:
        sb = await self._connect(name)
        guest_path = path if path.startswith("/") else f"/workspace/{path.lstrip('/')}"
        if hasattr(sb, "fs"):
            data = await sb.fs.read(guest_path)
            return bytes(data)
        code, stdout, stderr = await self.exec(name, "cat", [guest_path])
        if code != 0:
            raise FileNotFoundError(stderr or path)
        return stdout.encode("utf-8")

    async def write_fs(self, name: str, path: str, content: bytes) -> None:
        sb = await self._connect(name)
        guest_path = path if path.startswith("/") else f"/workspace/{path.lstrip('/')}"
        if hasattr(sb, "fs"):
            await sb.fs.write(guest_path, content)
            return
        # fallback: base64 pipe
        import base64

        b64 = base64.b64encode(content).decode("ascii")
        code, _, stderr = await self.exec(
            name,
            "sh",
            ["-c", f'mkdir -p "$(dirname "{guest_path}")" && echo {b64} | base64 -d > "{guest_path}"'],
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


def shlex_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def build_backend(settings: Settings) -> SandboxBackend:
    if settings.resolve_mock():
        logger.warning("Using MockSandboxBackend (SANDBOX_MOCK or microsandbox unavailable)")
        return MockSandboxBackend(settings)
    if not kvm_available():
        logger.warning("/dev/kvm missing — falling back to MockSandboxBackend")
        return MockSandboxBackend(settings)
    try:
        import microsandbox  # noqa: F401
    except ImportError:
        logger.warning("microsandbox not installed — MockSandboxBackend")
        return MockSandboxBackend(settings)
    logger.info("Using MicrosandboxBackend")
    return MicrosandboxBackend(settings)
