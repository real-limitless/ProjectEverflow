"""Ensure the guest noVNC desktop (port 6080) is running.

Microsandbox boots with ``/init.krun`` as PID 1 and does not keep the OCI
ENTRYPOINT as a long-lived process, so ``sandbox-guest-entrypoint.sh`` never
starts the X11/noVNC stack. Start it via guest exec instead (same pattern as
opencode serve).

Health requires both websockify (:6080) and x11vnc (:5900). A lone websockify
makes noVNC load its UI then show "Failed to connect to server".
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

DESKTOP_NOVNC_PORT = 6080
DESKTOP_VNC_PORT = 5900
DESKTOP_SCRIPT = "/usr/local/bin/everflow-desktop.sh"
_HOST_SCRIPT = Path(__file__).with_name("everflow_desktop.sh")

ExecFn = Callable[..., Awaitable[tuple[int, str, str]]]

_locks: dict[str, asyncio.Lock] = {}
_inflight: dict[str, asyncio.Task[None]] = {}


def _lock_for(name: str) -> asyncio.Lock:
    lock = _locks.get(name)
    if lock is None:
        lock = asyncio.Lock()
        _locks[name] = lock
    return lock


async def _port_open(exec_fn: ExecFn, name: str, port: int) -> bool:
    script = (
        "import socket\n"
        f"s=socket.socket(); s.settimeout(0.5)\n"
        f"r=s.connect_ex(('127.0.0.1',{port})); s.close()\n"
        "raise SystemExit(0 if r==0 else 1)\n"
    )
    try:
        code, _, _ = await exec_fn(
            name,
            "python3",
            ["-c", script],
            cwd="/workspace",
            env=None,
            timeout_seconds=15,
        )
        return code == 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("desktop port probe failed name=%s port=%s: %s", name, port, exc)
        return False


async def desktop_listening(exec_fn: ExecFn, name: str) -> bool:
    """True when VNC and noVNC are both accepting connections in the guest."""
    if not await _port_open(exec_fn, name, DESKTOP_NOVNC_PORT):
        return False
    return await _port_open(exec_fn, name, DESKTOP_VNC_PORT)


async def _install_desktop_script(exec_fn: ExecFn, name: str) -> bool:
    """Overwrite guest script with the agent-bundled copy (heals stale images)."""
    try:
        body = _HOST_SCRIPT.read_bytes()
    except OSError as exc:
        logger.warning("desktop host script missing (%s): %s", _HOST_SCRIPT, exc)
        return False

    b64 = base64.b64encode(body).decode("ascii")
    install = (
        "import base64, pathlib\n"
        f"p=pathlib.Path({DESKTOP_SCRIPT!r})\n"
        f"p.write_bytes(base64.b64decode({b64!r}))\n"
        "p.chmod(0o755)\n"
        "print('installed', p, 'bytes', p.stat().st_size)\n"
    )
    try:
        code, stdout, stderr = await exec_fn(
            name,
            "python3",
            ["-c", install],
            cwd="/workspace",
            env=None,
            timeout_seconds=20,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("desktop script install failed name=%s: %s", name, exc)
        return False
    if code != 0:
        logger.warning(
            "desktop script install exit name=%s code=%s err=%s",
            name,
            code,
            (stderr or stdout or "")[:240],
        )
        return False
    logger.info("desktop script installed name=%s %s", name, (stdout or "").strip())
    return True


async def ensure_guest_desktop(exec_fn: ExecFn, name: str) -> bool:
    """Start/repair the noVNC stack if needed. Returns True if healthy afterwards."""
    async with _lock_for(name):
        if await desktop_listening(exec_fn, name):
            return True

        await _install_desktop_script(exec_fn, name)

        try:
            code, stdout, stderr = await exec_fn(
                name,
                DESKTOP_SCRIPT,
                [],
                cwd="/workspace",
                env=None,
                timeout_seconds=60,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("desktop start exec failed name=%s: %s", name, exc)
            return False

        if code != 0:
            logger.warning(
                "desktop start failed name=%s code=%s out=%s err=%s",
                name,
                code,
                (stdout or "")[:240],
                (stderr or "")[:240],
            )
            # Fall through to poll — stack may still have come up

        for _ in range(20):
            if await desktop_listening(exec_fn, name):
                logger.info(
                    "guest desktop ready name=%s novnc=%s vnc=%s",
                    name,
                    DESKTOP_NOVNC_PORT,
                    DESKTOP_VNC_PORT,
                )
                return True
            await asyncio.sleep(0.25)

        logger.warning(
            "guest desktop not healthy after start name=%s out=%s err=%s",
            name,
            (stdout or "")[:240],
            (stderr or "")[:240],
        )
        return False


def schedule_ensure_guest_desktop(exec_fn: ExecFn, name: str) -> None:
    """Fire-and-forget ensure for create/start (does not block ready)."""
    existing = _inflight.get(name)
    if existing is not None and not existing.done():
        return

    async def _run() -> None:
        try:
            await ensure_guest_desktop(exec_fn, name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("background desktop ensure failed name=%s: %s", name, exc)
        finally:
            if _inflight.get(name) is asyncio.current_task():
                _inflight.pop(name, None)

    _inflight[name] = asyncio.create_task(_run())


async def ensure_guest_desktop_for_proxy(
    exec_fn: ExecFn,
    name: str,
    port: int,
) -> None:
    """Best-effort start/repair before proxying the Desktop panel port."""
    if port != DESKTOP_NOVNC_PORT:
        return
    try:
        ok = await ensure_guest_desktop(exec_fn, name)
        if not ok:
            logger.warning("desktop still down before proxy name=%s", name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("desktop ensure before proxy failed name=%s: %s", name, exc)


def reset_desktop_state_for_tests() -> None:
    """Clear module locks/tasks (unit tests only)."""
    _locks.clear()
    for task in list(_inflight.values()):
        if not task.done():
            task.cancel()
    _inflight.clear()
