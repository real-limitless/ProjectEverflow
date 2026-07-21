"""Lifecycle manager for `opencode serve` bound to a sandbox workspace.

Mock mode (and host-path workspaces) run OpenCode as a host subprocess.
Real microVMs start the server inside the guest and proxy via guest curl when
inbound HTTP is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OPENCODE_PORT_BASE = 14100
HEALTH_PATH = "/global/health"
OPENCODE_HOSTNAME = "127.0.0.1"


@dataclass
class OpenCodeInstance:
    sandbox_name: str
    port: int
    workspace: str
    pid: int | None = None
    process: Any | None = field(default=None, repr=False)
    mode: str = "host"  # host | guest
    version: str | None = None
    started_at: float = field(default_factory=time.time)


class OpenCodeManager:
    """Tracks one OpenCode server per sandbox name."""

    def __init__(self) -> None:
        self._instances: dict[str, OpenCodeInstance] = {}
        self._lock = asyncio.Lock()
        self._port_cursor = DEFAULT_OPENCODE_PORT_BASE

    def _next_port(self) -> int:
        # Find a free localhost port starting from the cursor
        for _ in range(200):
            port = self._port_cursor
            self._port_cursor = port + 1 if port < 20000 else DEFAULT_OPENCODE_PORT_BASE
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind((OPENCODE_HOSTNAME, port))
                    return port
                except OSError:
                    continue
        raise RuntimeError("No free port for opencode serve")

    def get(self, name: str) -> OpenCodeInstance | None:
        return self._instances.get(name)

    def base_url(self, name: str) -> str | None:
        """Host-reachable OpenCode URL (only for mode=host)."""
        inst = self._instances.get(name)
        if not inst or inst.mode != "host":
            return None
        return f"http://{OPENCODE_HOSTNAME}:{inst.port}"

    async def stop(self, name: str) -> None:
        async with self._lock:
            inst = self._instances.pop(name, None)
            if not inst:
                return
            await self._kill_instance(inst)

    async def stop_all(self) -> None:
        async with self._lock:
            names = list(self._instances.keys())
            for name in names:
                inst = self._instances.pop(name, None)
                if inst:
                    await self._kill_instance(inst)

    async def _kill_instance(self, inst: OpenCodeInstance) -> None:
        proc = inst.process
        if proc is None:
            return
        # Fake HTTP server
        if hasattr(proc, "shutdown"):
            try:
                proc.shutdown()  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                logger.debug("fake opencode shutdown: %s", exc)
            return
        if isinstance(proc, subprocess.Popen) and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    await asyncio.to_thread(proc.wait, 5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception as exc:  # noqa: BLE001
                logger.warning("opencode stop failed name=%s: %s", inst.sandbox_name, exc)

    def resolve_opencode_bin(self, workspace: str | Path) -> str | None:
        """Return path to a real opencode binary, or None if missing/stub."""
        env_bin = os.environ.get("OPENCODE_BIN")
        candidates: list[Path] = []
        if env_bin:
            candidates.append(Path(env_bin))
        ws = Path(workspace)
        candidates.append(ws / ".everflow" / "bin" / "opencode")
        which = shutil.which("opencode")
        if which:
            candidates.append(Path(which))

        for path in candidates:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")[:500]
            except OSError:
                text = ""
            # Reject Everflow stubs
            if "not fully installed" in text or "mock harness" in text:
                continue
            if os.access(path, os.X_OK):
                return str(path)
        return None

    async def health_check(self, port: int, *, timeout: float = 2.0) -> dict[str, Any] | None:
        url = f"http://{OPENCODE_HOSTNAME}:{port}{HEALTH_PATH}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, dict):
                        return data
        except Exception:  # noqa: BLE001
            return None
        return None

    def attach_host(
        self,
        name: str,
        *,
        port: int,
        workspace: str,
        version: str | None = None,
        process: subprocess.Popen[bytes] | None = None,
    ) -> dict[str, Any]:
        """Register an already-running host OpenCode (tests / external)."""
        inst = OpenCodeInstance(
            sandbox_name=name,
            port=port,
            workspace=workspace,
            pid=process.pid if process else None,
            process=process,
            mode="host",
            version=version,
        )
        self._instances[name] = inst
        return self._status_dict(inst, healthy=True)

    async def ensure_host(
        self,
        name: str,
        workspace: str,
        *,
        force_restart: bool = False,
        allow_fake: bool = True,
    ) -> dict[str, Any]:
        """Ensure opencode serve is running against a host workspace path."""
        async with self._lock:
            existing = self._instances.get(name)
            if existing and not force_restart:
                health = await self.health_check(existing.port)
                alive = True
                if isinstance(existing.process, subprocess.Popen):
                    alive = existing.process.poll() is None
                if health is not None and alive:
                    existing.version = str(health.get("version") or existing.version or "")
                    return self._status_dict(existing, healthy=True)

            if existing:
                await self._kill_instance(existing)
                self._instances.pop(name, None)

            binary = self.resolve_opencode_bin(workspace)
            if not binary:
                if allow_fake and os.environ.get("OPENCODE_ALLOW_FAKE", "true").lower() in (
                    "1",
                    "true",
                    "yes",
                ):
                    return await self._start_fake(name, workspace)
                raise RuntimeError(
                    "OpenCode CLI is not installed in this sandbox. "
                    "Re-run bootstrap (agent-opencode) or set OPENCODE_BIN."
                )

            # Detect stub via --version if possible
            try:
                ver_proc = await asyncio.to_thread(
                    subprocess.run,
                    [binary, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                ver_out = (ver_proc.stdout or ver_proc.stderr or "").strip()
                if "not fully installed" in ver_out or "mock harness" in ver_out:
                    raise RuntimeError(
                        "OpenCode binary is a stub. Install the real CLI in the sandbox."
                    )
            except subprocess.TimeoutExpired:
                pass

            port = self._next_port()
            ws = Path(workspace)
            ws.mkdir(parents=True, exist_ok=True)
            self._write_server_config(ws, port)

            log_path = ws / ".everflow" / "opencode-serve.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_f = open(log_path, "ab", buffering=0)  # noqa: SIM115

            env = os.environ.copy()
            bin_dir = str(ws / ".everflow" / "bin")
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
            env.setdefault("OPENCODE_CLIENT", "everflow")

            cmd = [
                binary,
                "serve",
                "--hostname",
                OPENCODE_HOSTNAME,
                "--port",
                str(port),
            ]
            logger.info("starting opencode serve name=%s port=%s cwd=%s", name, port, ws)
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(ws),
                    env=env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except Exception:
                log_f.close()
                raise

            inst = OpenCodeInstance(
                sandbox_name=name,
                port=port,
                workspace=str(ws),
                pid=proc.pid,
                process=proc,
                mode="host",
            )
            self._instances[name] = inst

            # Wait for health
            deadline = time.time() + 30
            last_err: str | None = None
            while time.time() < deadline:
                if proc.poll() is not None:
                    log_f.close()
                    self._instances.pop(name, None)
                    tail = ""
                    try:
                        tail = log_path.read_text(encoding="utf-8", errors="replace")[-800:]
                    except OSError:
                        pass
                    raise RuntimeError(
                        f"opencode serve exited early (code={proc.returncode}). {tail}"
                    )
                health = await self.health_check(port, timeout=1.0)
                if health is not None:
                    inst.version = str(health.get("version") or "")
                    logger.info(
                        "opencode ready name=%s port=%s version=%s",
                        name,
                        port,
                        inst.version,
                    )
                    return self._status_dict(inst, healthy=True)
                last_err = "waiting for /global/health"
                await asyncio.sleep(0.25)

            await self._kill_instance(inst)
            self._instances.pop(name, None)
            raise RuntimeError(f"opencode serve did not become healthy: {last_err}")

    async def _start_fake(self, name: str, workspace: str) -> dict[str, Any]:
        """Dev/test fallback when real OpenCode CLI is missing."""
        from app.opencode_fake import start_fake_opencode

        server, port, _thread = start_fake_opencode(0)
        # Keep server alive by retaining reference on instance via process=None
        inst = OpenCodeInstance(
            sandbox_name=name,
            port=port,
            workspace=workspace,
            mode="host",
            version="fake-0.0.1",
        )
        # stash server so GC doesn't kill it
        inst.process = server  # type: ignore[assignment]
        self._instances[name] = inst
        logger.warning(
            "OpenCode CLI missing — started fake server for sandbox=%s port=%s",
            name,
            port,
        )
        return self._status_dict(inst, healthy=True)

    def _write_server_config(self, workspace: Path, port: int) -> None:
        """Best-effort opencode.json so serve binds consistently."""
        cfg = workspace / "opencode.json"
        if cfg.exists():
            return
        try:
            cfg.write_text(
                "{\n"
                '  "$schema": "https://opencode.ai/config.json",\n'
                '  "server": {\n'
                f'    "port": {port},\n'
                f'    "hostname": "{OPENCODE_HOSTNAME}"\n'
                "  }\n"
                "}\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.debug("could not write opencode.json: %s", exc)

    def _status_dict(self, inst: OpenCodeInstance, *, healthy: bool) -> dict[str, Any]:
        host_url = (
            f"http://{OPENCODE_HOSTNAME}:{inst.port}" if inst.mode == "host" else None
        )
        return {
            "sandbox_name": inst.sandbox_name,
            "healthy": healthy,
            "port": inst.port,
            "base_url": host_url,
            "version": inst.version,
            "mode": inst.mode,
            "pid": inst.pid,
            "workspace": inst.workspace,
        }

    async def ensure_guest_via_exec(
        self,
        name: str,
        *,
        exec_fn: Any,
        workspace_guest: str = "/workspace",
        port: int = 4096,
    ) -> dict[str, Any]:
        """Start opencode serve inside a guest via backend.exec (best-effort)."""
        async def _guest_health() -> dict[str, Any] | None:
            # Prefer python (always in guest image) over curl
            script = (
                "import json,urllib.request\n"
                f"u='http://127.0.0.1:{port}{HEALTH_PATH}'\n"
                "try:\n"
                "  print(urllib.request.urlopen(u,timeout=3).read().decode())\n"
                "except Exception:\n"
                "  pass\n"
            )
            code, stdout, _ = await exec_fn(
                name,
                "python3",
                ["-c", script],
                cwd=workspace_guest,
                timeout_seconds=15,
            )
            if code != 0 or not (stdout or "").strip().startswith("{"):
                return None
            try:
                import json

                data = json.loads(stdout.strip().splitlines()[-1])
                return data if isinstance(data, dict) else None
            except Exception:  # noqa: BLE001
                return None

        health = await _guest_health()
        if health is not None:
            inst = OpenCodeInstance(
                sandbox_name=name,
                port=port,
                workspace=workspace_guest,
                mode="guest",
                version=str(health.get("version") or ""),
            )
            self._instances[name] = inst
            logger.info("guest opencode already healthy name=%s port=%s", name, port)
            return self._status_dict(inst, healthy=True)

        # Start detached serve (PATH may include .everflow/bin)
        start_cmd = (
            "mkdir -p /workspace/.everflow && "
            "export PATH=\"/workspace/.everflow/bin:$PATH\" && "
            f"(nohup opencode serve --hostname 127.0.0.1 --port {port} "
            f">/workspace/.everflow/opencode-serve.log 2>&1 & echo $!)"
        )
        code, stdout, stderr = await exec_fn(
            name,
            "sh",
            ["-c", start_cmd],
            cwd=workspace_guest,
            timeout_seconds=20,
        )
        if code != 0:
            raise RuntimeError(f"Failed to start opencode in guest: {stderr or stdout}")

        # Poll health inside guest
        deadline = time.time() + 45
        while time.time() < deadline:
            health = await _guest_health()
            if health is not None:
                inst = OpenCodeInstance(
                    sandbox_name=name,
                    port=port,
                    workspace=workspace_guest,
                    mode="guest",
                    version=str(health.get("version") or ""),
                )
                self._instances[name] = inst
                logger.info(
                    "guest opencode ready name=%s port=%s version=%s",
                    name,
                    port,
                    inst.version,
                )
                return self._status_dict(inst, healthy=True)
            await asyncio.sleep(0.75)

        # Surface log tail if possible
        _, log_out, _ = await exec_fn(
            name,
            "sh",
            ["-c", "tail -n 40 /workspace/.everflow/opencode-serve.log 2>/dev/null || true"],
            cwd=workspace_guest,
            timeout_seconds=10,
        )
        raise RuntimeError(
            "opencode serve in guest did not become healthy. "
            f"Log tail: {(log_out or '')[:600]}"
        )


# Process-global manager
_manager = OpenCodeManager()


def get_opencode_manager() -> OpenCodeManager:
    return _manager
