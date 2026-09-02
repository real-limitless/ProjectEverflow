"""Docker-container sandbox backend.

Used when the host advertises ``/dev/kvm`` but cannot create a vCPU (nested
Cloud Agent kernels that BUG in ``alloc_loaded_vmcs``). Boots the same guest
OCI image as microsandbox, via the host Docker engine (socket + CLI).

This is still a real guest (OpenCode, desktop, workspace) — not MockSandboxBackend.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.config import Settings
from app.msb import (
    SandboxBackend,
    SandboxRecord,
    kvm_available,
    normalize_guest_path,
    shlex_quote,
)

logger = logging.getLogger(__name__)

SANDBOX_LABEL = "everflow.sandbox"
SANDBOX_NAME_LABEL = "everflow.sandbox.name"


def parse_image_rewrites(raw: str | None) -> list[tuple[str, str]]:
    """Parse ``src=dst,src2=dst2`` rewrite rules for host-docker image refs."""
    out: list[tuple[str, str]] = []
    for part in (raw or "").split(","):
        item = part.strip()
        if not item or "=" not in item:
            continue
        src, dst = item.split("=", 1)
        src, dst = src.strip(), dst.strip()
        if src and dst:
            out.append((src, dst))
    return out


def rewrite_image_for_host_docker(
    image: str,
    rewrites: list[tuple[str, str]] | None = None,
) -> str:
    """Map compose-DNS image refs to names the host daemon can pull.

    ``registry:5000/everflow/guest:latest`` is reachable from the compose
    network, not from dockerd on the host. Default rewrite is
    ``registry:5000`` → ``127.0.0.1:5000``.
    """
    ref = (image or "").strip()
    rules = list(rewrites or [])
    if not rules:
        rules = [("registry:5000", "127.0.0.1:5000")]
    for src, dst in rules:
        if ref == src or ref.startswith(src + "/"):
            return dst + ref[len(src) :]
    return ref


def docker_cli_available(docker_bin: str = "docker") -> bool:
    return shutil.which(docker_bin) is not None


def docker_socket_available(docker_host: str | None = None) -> bool:
    raw = (docker_host or os.environ.get("DOCKER_HOST") or "unix:///var/run/docker.sock").strip()
    if raw.startswith("unix://"):
        return Path(raw[len("unix://") :]).exists()
    if raw.startswith("tcp://") or raw.startswith("http://") or raw.startswith("https://"):
        return True
    return Path("/var/run/docker.sock").exists()


class _DockerExecSink:
    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    async def write(self, data: bytes) -> None:
        if self._proc.stdin is None:
            raise RuntimeError("exec stdin is closed")
        self._proc.stdin.write(data)
        await self._proc.stdin.drain()

    async def close(self) -> None:
        if self._proc.stdin is None:
            return
        try:
            self._proc.stdin.close()
            await self._proc.stdin.wait_closed()
        except Exception:  # noqa: BLE001
            pass


class _DockerExecHandle:
    """Async-iterable exec stream compatible with guest_tunnel / api_tunnel."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    def __aiter__(self) -> _DockerExecHandle:
        return self

    async def __anext__(self) -> Any:
        if self._proc.stdout is None:
            raise StopAsyncIteration
        chunk = await self._proc.stdout.read(65536)
        if not chunk:
            raise StopAsyncIteration
        return SimpleNamespace(event_type="stdout", data=chunk)

    async def kill(self) -> None:
        try:
            if self._proc.returncode is None:
                self._proc.kill()
            await self._proc.wait()
        except Exception:  # noqa: BLE001
            pass


@dataclass
class _DockerCtx:
    bin: str
    host: str | None
    env: dict[str, str]


class ContainerSandboxBackend(SandboxBackend):
    """Run the Everflow guest image as a sibling Docker container."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._meta: dict[str, SandboxRecord] = {}
        self._bootstrap_tasks: dict[str, asyncio.Task[None]] = {}
        self._bootstrap_gen: dict[str, int] = {}
        docker_bin = getattr(settings, "docker_bin", None) or "docker"
        docker_host = getattr(settings, "docker_host", None) or os.environ.get("DOCKER_HOST")
        env = os.environ.copy()
        if docker_host:
            env["DOCKER_HOST"] = docker_host
        self._docker = _DockerCtx(bin=docker_bin, host=docker_host, env=env)
        self._rewrites = parse_image_rewrites(
            getattr(settings, "container_image_rewrite", None)
        )
        self._network: str | None = getattr(settings, "container_network", None) or None
        self._volume: str | None = getattr(settings, "workspace_docker_volume", None) or None
        self._resolved = False

    async def _ensure_docker_ctx(self) -> None:
        if self._resolved:
            return
        if not docker_cli_available(self._docker.bin):
            raise RuntimeError(
                "docker CLI is not on PATH inside sandbox-agent. "
                "Install docker-cli in the agent image or mount the host docker binary."
            )
        if not docker_socket_available(self._docker.host):
            raise RuntimeError(
                "Docker socket is not available. Mount /var/run/docker.sock into sandbox-agent."
            )
        if not (self._network and self._network.strip()):
            self._network = await self._detect_self_network()
        if not (self._volume and self._volume.strip()):
            self._volume = await self._detect_workspace_volume()
        self._resolved = True
        logger.info(
            "container backend ready network=%s volume=%s docker=%s",
            self._network or "(default)",
            self._volume or "(per-sandbox)",
            self._docker.bin,
        )

    async def _docker_run(
        self,
        args: list[str],
        *,
        timeout: float | None = 60,
        stdin_data: bytes | None = None,
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            self._docker.bin,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
            env=self._docker.env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(stdin_data),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, "", f"docker {' '.join(args[:4])} timed out"
        stdout = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")
        return int(proc.returncode or 0), stdout, stderr

    async def _detect_self_network(self) -> str | None:
        hostname = os.environ.get("HOSTNAME", "").strip()
        if not hostname:
            return None
        code, out, _ = await self._docker_run(
            [
                "inspect",
                "-f",
                "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}",
                hostname,
            ],
            timeout=15,
        )
        if code != 0:
            return None
        names = [n for n in out.split() if n]
        for name in names:
            if name != "bridge":
                return name
        return names[0] if names else None

    async def _detect_workspace_volume(self) -> str | None:
        hostname = os.environ.get("HOSTNAME", "").strip()
        if not hostname:
            return None
        code, out, _ = await self._docker_run(
            [
                "inspect",
                "-f",
                '{{range .Mounts}}{{if eq .Destination "/workspaces"}}{{.Name}}{{end}}{{end}}',
                hostname,
            ],
            timeout=15,
        )
        if code != 0:
            return None
        vol = out.strip()
        return vol or None

    def _container_name(self, name: str) -> str:
        return name

    def _guest_image(self, image: str) -> str:
        return rewrite_image_for_host_docker(image, self._rewrites)

    async def health(self) -> dict[str, Any]:
        from app.kvm_probe import kvm_vcpu_usable

        docker_ok = docker_cli_available(self._docker.bin) and docker_socket_available(
            self._docker.host
        )
        return {
            "status": "ok" if docker_ok else "degraded",
            "kvm": kvm_available(),
            "kvm_usable": kvm_vcpu_usable(),
            "sdk": "container",
            "mock": False,
            "runtime": "container",
        }

    def _cancel_bootstrap(self, name: str) -> None:
        self._bootstrap_gen[name] = self._bootstrap_gen.get(name, 0) + 1
        task = self._bootstrap_tasks.pop(name, None)
        if task is not None and not task.done():
            task.cancel()

    def _schedule_bootstrap(self, name: str, harnesses: list[str]) -> None:
        if not harnesses:
            return
        self._cancel_bootstrap(name)
        gen = self._bootstrap_gen.get(name, 0)

        async def _run() -> None:
            if self._bootstrap_gen.get(name, 0) != gen:
                return
            try:
                await self.bootstrap(name, harnesses)
            except Exception as exc:  # noqa: BLE001
                logger.warning("container bootstrap failed name=%s: %s", name, exc)

        self._bootstrap_tasks[name] = asyncio.create_task(_run())

    async def _pull_image(self, image: str) -> None:
        code, _, err = await self._docker_run(["image", "inspect", image], timeout=20)
        if code == 0:
            return
        logger.info("container backend pulling guest image=%s", image)
        code, out, err = await self._docker_run(["pull", image], timeout=300)
        if code != 0:
            raise RuntimeError(f"docker pull {image} failed: {err or out}")

    async def _rm(self, name: str) -> None:
        await self._docker_run(["rm", "-f", self._container_name(name)], timeout=30)

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
        await self._ensure_docker_ctx()
        guest_image = self._guest_image(image)
        ws = Path(workspace_host_path or (self._settings.workspace_path / name))
        ws.mkdir(parents=True, exist_ok=True)

        self._cancel_bootstrap(name)
        if replace:
            await self._rm(name)
        else:
            existing = await self.get(name)
            if existing and existing.status not in ("destroyed", "error", "exited"):
                return existing

        await self._pull_image(guest_image)

        run_args: list[str] = [
            "run",
            "-d",
            "--name",
            self._container_name(name),
            "--label",
            f"{SANDBOX_LABEL}=1",
            "--label",
            f"{SANDBOX_NAME_LABEL}={name}",
            "--memory",
            f"{max(int(memory_mib), 256)}m",
            "--cpus",
            str(max(float(cpus), 0.5)),
            "--shm-size",
            "1g",
            "--security-opt",
            "seccomp=unconfined",
            "--init",
            "--restart",
            "no",
        ]
        for key, value in labels.items():
            run_args.extend(["--label", f"everflow.user.{key}={value}"])
        if self._network:
            run_args.extend(["--network", self._network])

        volume = self._volume
        used_workspace = str(ws)
        if volume:
            run_args.extend(["--mount", f"type=volume,src={volume},dst=/workspaces"])
        else:
            vol_name = f"ef-ws-{name}"[:120]
            run_args.extend(["--mount", f"type=volume,src={vol_name},dst=/workspaces"])
            used_workspace = f"named:{vol_name}"

        # Guest tools expect /workspace. Share the agent volume and symlink.
        safe_name = name.replace("'", "")
        boot = (
            f"rm -rf /workspace && ln -sfn /workspaces/{safe_name} /workspace "
            "&& mkdir -p /workspace "
            "&& exec /usr/local/bin/sandbox-guest-entrypoint.sh sleep infinity"
        )
        run_args.extend(
            [
                "--entrypoint",
                "/bin/bash",
                guest_image,
                "-lc",
                boot,
            ]
        )

        code, out, err = await self._docker_run(run_args, timeout=120)
        if code != 0:
            await self._rm(name)
            raise RuntimeError(f"Failed to start container sandbox {name}: {err or out}")

        rec = SandboxRecord(
            name=name,
            status="running",
            image=guest_image,
            labels=dict(labels),
            harnesses=list(harnesses),
            workspace_path=used_workspace,
            created_at=datetime.now(timezone.utc),
        )
        self._meta[name] = rec
        from app.desktop import schedule_ensure_guest_desktop

        schedule_ensure_guest_desktop(self.exec, name)
        if harnesses:
            self._schedule_bootstrap(name, list(harnesses))
        logger.info(
            "container sandbox created name=%s image=%s network=%s volume=%s",
            name,
            guest_image,
            self._network,
            volume,
        )
        return rec

    async def _inspect_status(self, name: str) -> str | None:
        code, out, _ = await self._docker_run(
            [
                "inspect",
                "-f",
                "{{.State.Status}}",
                self._container_name(name),
            ],
            timeout=15,
        )
        if code != 0:
            return None
        return (out or "").strip() or None

    async def get(self, name: str) -> SandboxRecord | None:
        status = await self._inspect_status(name)
        meta = self._meta.get(name)
        if status is None:
            if meta is None:
                return None
            meta.status = "error"
            meta.error = meta.error or "Sandbox container not found"
            return meta
        mapped = "running" if status == "running" else status
        if status == "exited":
            mapped = "stopped"
        rec = SandboxRecord(
            name=name,
            status=mapped,
            image=meta.image if meta else self._settings.default_image,
            labels=meta.labels if meta else {},
            harnesses=meta.harnesses if meta else [],
            workspace_path=meta.workspace_path if meta else str(self._settings.workspace_path / name),
            created_at=meta.created_at if meta else None,
            error=None if mapped == "running" else (meta.error if meta else None),
        )
        self._meta[name] = rec
        return rec

    async def list(self) -> list[SandboxRecord]:
        code, out, _ = await self._docker_run(
            [
                "ps",
                "-a",
                "--filter",
                f"label={SANDBOX_LABEL}=1",
                "--format",
                "{{.Label \"" + SANDBOX_NAME_LABEL + "\"}}",
            ],
            timeout=20,
        )
        names: list[str] = []
        if code == 0:
            names = [line.strip() for line in out.splitlines() if line.strip()]
        if not names:
            names = list(self._meta.keys())
        recs: list[SandboxRecord] = []
        for name in names:
            rec = await self.get(name)
            if rec:
                recs.append(rec)
        return recs

    async def start(self, name: str) -> SandboxRecord:
        code, out, err = await self._docker_run(["start", self._container_name(name)], timeout=30)
        if code != 0:
            raise KeyError(name) if "No such container" in (err + out) else RuntimeError(err or out)
        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        rec.status = "running"
        from app.desktop import schedule_ensure_guest_desktop

        schedule_ensure_guest_desktop(self.exec, name)
        return rec

    async def stop(self, name: str) -> SandboxRecord:
        code, out, err = await self._docker_run(["stop", self._container_name(name)], timeout=40)
        if code != 0:
            raise KeyError(name) if "No such container" in (err + out) else RuntimeError(err or out)
        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        rec.status = "stopped"
        return rec

    async def remove(self, name: str) -> None:
        self._cancel_bootstrap(name)
        await self._rm(name)
        self._meta.pop(name, None)

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
        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        if rec.status != "running":
            raise RuntimeError(f"Sandbox {name} is not running (status={rec.status})")
        docker_args = ["exec"]
        if cwd:
            docker_args.extend(["-w", cwd])
        if env:
            for key, value in env.items():
                docker_args.extend(["-e", f"{key}={value}"])
        docker_args.extend([self._container_name(name), cmd, *args])
        return await self._docker_run(docker_args, timeout=timeout_seconds)

    async def open_exec_stream(
        self,
        name: str,
        *,
        cmd: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,  # noqa: ARG002 — docker exec has no idle timeout
    ) -> tuple[Any, Any]:
        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        if rec.status != "running":
            raise RuntimeError(f"Sandbox {name} is not running (status={rec.status})")
        docker_args = [self._docker.bin, "exec", "-i"]
        if cwd:
            docker_args.extend(["-w", cwd])
        if env:
            for key, value in env.items():
                docker_args.extend(["-e", f"{key}={value}"])
        docker_args.extend([self._container_name(name), cmd, *(args or [])])
        proc = await asyncio.create_subprocess_exec(
            *docker_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=self._docker.env,
        )
        return _DockerExecHandle(proc), _DockerExecSink(proc)

    async def stream_exec(
        self,
        name: str,
        cmd: str,
        args: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ):
        handle, sink = await self.open_exec_stream(
            name, cmd=cmd, args=args, cwd=cwd, env=env
        )
        try:
            async for event in handle:
                data = getattr(event, "data", None)
                if data:
                    yield bytes(data)
        finally:
            try:
                await sink.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                await handle.kill()
            except Exception:  # noqa: BLE001
                pass

    async def list_fs(self, name: str, path: str) -> list[dict[str, Any]]:
        from app.msb import guest_entry_relpath

        guest_path = normalize_guest_path(path)
        q = shlex_quote(guest_path)
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
        guest_path = normalize_guest_path(path, allow_tmp=True)
        code, stdout, stderr = await self.exec(name, "cat", [guest_path])
        if code != 0:
            raise FileNotFoundError(stderr or path)
        return stdout.encode("utf-8")

    async def write_fs(self, name: str, path: str, content: bytes) -> None:
        import base64
        from pathlib import PurePosixPath

        guest_path = normalize_guest_path(path, allow_tmp=True)
        parent = str(PurePosixPath(guest_path).parent)
        if parent not in ("", ".", "/"):
            code, _, stderr = await self.exec(name, "mkdir", ["-p", parent], timeout_seconds=30)
            if code != 0:
                raise RuntimeError(stderr or f"mkdir -p failed for {parent}")
        b64 = base64.b64encode(content).decode("ascii")
        q = shlex_quote(guest_path)
        code, _, stderr = await self.exec(
            name,
            "sh",
            ["-c", f"echo {b64} | base64 -d > {q}"],
            timeout_seconds=120,
        )
        if code != 0:
            raise RuntimeError(stderr or "write failed")

    async def bootstrap(self, name: str, harnesses: list[str]) -> SandboxRecord:
        from pathlib import Path as P

        bootstrap_dir = P(__file__).resolve().parent / "bootstrap"
        script_path = bootstrap_dir / "install_harnesses.sh"
        if script_path.exists():
            script = script_path.read_text(encoding="utf-8")
            await self.write_fs(name, "/tmp/install_harnesses.sh", script.encode("utf-8"))
            for companion in bootstrap_dir.glob("install_*.sh"):
                if companion.name == "install_harnesses.sh":
                    continue
                await self.write_fs(
                    name,
                    f"/tmp/{companion.name}",
                    companion.read_text(encoding="utf-8").encode("utf-8"),
                )
            code, stdout, stderr = await self.exec(
                name,
                "sh",
                ["/tmp/install_harnesses.sh", *harnesses],
                timeout_seconds=600,
            )
            if code != 0:
                raise RuntimeError(f"bootstrap failed: {stderr or stdout}")
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
        from app.shell_ws import run_docker_exec_shell

        rec = await self.get(name)
        if rec is None:
            raise KeyError(name)
        if rec.status != "running":
            raise RuntimeError(f"Sandbox {name} is not running")
        await run_docker_exec_shell(
            self._docker.bin,
            self._container_name(name),
            websocket,
            cmd=cmd,
            cwd=cwd or "/workspace",
            env=self._docker.env,
        )
