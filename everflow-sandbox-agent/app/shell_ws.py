"""Interactive PTY shell over WebSocket for a sandbox."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shlex
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

# SIGWINCH on Linux — TUIs re-read TIOCGWINSZ after this signal.
_SIGWINCH = 28


async def _safe_send(ws: WebSocket, payload: dict[str, Any]) -> bool:
    if ws.client_state != WebSocketState.CONNECTED:
        return False
    try:
        await ws.send_text(json.dumps(payload))
        return True
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode_input(msg: dict[str, Any]) -> bytes:
    raw = msg.get("data", "")
    if msg.get("encoding") == "base64" or (
        isinstance(raw, str) and msg.get("b64") is True
    ):
        return base64.b64decode(raw)
    if isinstance(raw, str):
        return raw.encode("utf-8", errors="replace")
    return bytes(raw)


def _clamp_size(cols: int, rows: int) -> tuple[int, int]:
    return max(2, min(int(cols), 500)), max(1, min(int(rows), 200))


def _stty_prefix(cols: int, rows: int) -> str:
    """Set PTY winsize inside the guest before exec'ing the real command.

    microsandbox ExecHandle has no resize API; many TUIs (opencode, etc.) read
    TIOCGWINSZ rather than $COLUMNS/$LINES, so stty is required for full width.
    """
    c, r = _clamp_size(cols, rows)
    return f"stty cols {c} rows {r} 2>/dev/null; export COLUMNS={c} LINES={r}; "


async def _wait_initial_size(websocket: WebSocket) -> tuple[int, int, bytes | None]:
    """Wait for client resize/hello so the process starts at panel dimensions.

    Collects size frames for a short settle window after the first good
    measurement (FitAddon often reports 80×24 on the first paint, then the
    real panel size on the next rAF). Returns (cols, rows, buffered input).
    """
    cols, rows = 160, 40
    buffered: bytes | None = None
    got_size = False
    loop = asyncio.get_running_loop()
    # Hard cap so a broken client cannot block forever
    hard_deadline = loop.time() + 3.0
    # After first usable size, keep listening briefly for a larger fit
    settle_deadline: float | None = None

    while True:
        now = loop.time()
        if settle_deadline is not None and now >= settle_deadline:
            break
        remaining = (settle_deadline if settle_deadline is not None else hard_deadline) - now
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        except WebSocketDisconnect:
            raise
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            buffered = raw.encode("utf-8", errors="replace")
            break
        mtype = msg.get("type")
        if mtype in ("resize", "hello", "start"):
            try:
                c, r = _clamp_size(
                    int(msg.get("cols") or cols),
                    int(msg.get("rows") or rows),
                )
            except (TypeError, ValueError):
                continue
            # Keep the largest footprint seen (panel growing after dock layout)
            if not got_size or c * r >= cols * rows:
                cols, rows = c, r
            got_size = True
            if cols >= 40 and rows >= 8 and settle_deadline is None:
                # Allow extra frames for FitAddon / ResizeObserver to catch up
                settle_deadline = loop.time() + 0.25
            continue
        if mtype == "input":
            buffered = _decode_input(msg)
            break
        # Ignore pings / unknown while waiting for size
    return cols, rows, buffered

def _event_kind(event: Any) -> str:
    et = getattr(event, "event_type", None) or getattr(event, "kind", None)
    if et:
        return str(et).lower()
    name = type(event).__name__.lower()
    if "stdout" in name:
        return "stdout"
    if "stderr" in name:
        return "stderr"
    if "exit" in name:
        return "exited"
    if "start" in name:
        return "started"
    if "fail" in name:
        return "failed"
    return name


async def run_microsandbox_shell(
    sb: Any,
    websocket: WebSocket,
    *,
    cmd: str | None = None,
    cwd: str = "/workspace",
) -> None:
    """Stream an interactive TTY session using microsandbox exec_stream."""
    from microsandbox import Stdin

    # Ask client for size first; process must start at correct winsize (no live
    # PTY resize API in current microsandbox SDK).
    await _safe_send(websocket, {"type": "ready", "mode": "pty", "need_size": True})
    try:
        cols, rows, buffered_input = await _wait_initial_size(websocket)
    except WebSocketDisconnect:
        return

    env = {
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
        "COLUMNS": str(cols),
        "LINES": str(rows),
    }

    prefix = _stty_prefix(cols, rows)

    # Always wrap with stty so TIOCGWINSZ matches the browser panel.
    candidates: list[tuple[str, list[str]]] = []
    if cmd and cmd.strip():
        # Run user command under shell so PATH works; stty then exec.
        inner = cmd.strip()
        candidates.append(("sh", ["-c", prefix + f"exec {inner}"]))
        # Fallback without exec if command is a shell script line
        candidates.append(("sh", ["-c", prefix + inner]))
    else:
        candidates.extend(
            [
                ("bash", ["-c", prefix + "exec bash -il"]),
                ("bash", ["-c", prefix + "exec bash -i"]),
                ("sh", ["-c", prefix + "exec sh -i"]),
                ("sh", ["-c", prefix + "exec sh"]),
            ]
        )

    last_err: Exception | None = None
    handle = None
    for exe, args in candidates:
        try:
            handle = await sb.exec_stream(
                exe,
                args,
                cwd=cwd,
                env=env,
                stdin=Stdin.pipe(),
                tty=True,
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning("exec_stream failed cmd=%s args=%s: %s", exe, args, exc)
            handle = None

    if handle is None:
        await _safe_send(
            websocket,
            {
                "type": "error",
                "message": f"Could not start shell: {last_err}",
            },
        )
        return

    stdin = None
    try:
        stdin = handle.take_stdin()
    except Exception as exc:  # noqa: BLE001
        logger.warning("take_stdin failed: %s", exc)

    if buffered_input and stdin is not None:
        try:
            await stdin.write(buffered_input)
        except Exception:
            pass

    stop = asyncio.Event()
    size: dict[str, Any] = {"cols": cols, "rows": rows, "pid": None}
    resize_lock = asyncio.Lock()
    await _safe_send(
        websocket,
        {"type": "started", "cols": cols, "rows": rows, "mode": "pty"},
    )

    async def guest_set_winsize(c: int, r: int) -> None:
        """Best-effort: set guest PTY size and notify process (SIGWINCH)."""
        c, r = _clamp_size(c, r)
        pid = size.get("pid")
        # Prefer targeting the process tty via /proc; also try handle.signal.
        scripts = []
        if pid:
            scripts.append(
                f"stty -F /proc/{int(pid)}/fd/0 cols {c} rows {r} 2>/dev/null; "
                f"kill -WINCH {int(pid)} 2>/dev/null || true"
            )
            # Child of the wrapper sh may be the actual TUI
            scripts.append(
                f"for p in $(ls /proc/{int(pid)}/task 2>/dev/null); do true; done; "
                f"pkill -P {int(pid)} -WINCH 2>/dev/null; "
                f"for cpid in $(pgrep -P {int(pid)} 2>/dev/null); do "
                f"  stty -F /proc/$cpid/fd/0 cols {c} rows {r} 2>/dev/null; "
                f"  kill -WINCH $cpid 2>/dev/null; "
                f"done"
            )
        for script in scripts:
            try:
                await sb.exec("sh", ["-c", script], cwd=cwd, timeout=2.0)
            except TypeError:
                try:
                    await sb.exec("sh", ["-c", script], cwd=cwd)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("guest stty failed: %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.debug("guest stty failed: %s", exc)
        try:
            if hasattr(handle, "signal"):
                await handle.signal(_SIGWINCH)
        except Exception:
            pass
        # If we still have stdin and a shell (not a full-screen TUI), stty may help
        # when run on the same tty — silent best-effort only for shells.
        if stdin is not None and not (cmd and cmd.strip()):
            try:
                # Don't inject stty into interactive TUI stdin (corrupts input).
                pass
            except Exception:
                pass

    async def apply_resize(new_cols: int, new_rows: int) -> None:
        new_cols, new_rows = _clamp_size(new_cols, new_rows)
        if new_cols == size["cols"] and new_rows == size["rows"]:
            return
        size["cols"], size["rows"] = new_cols, new_rows
        async with resize_lock:
            # SDK methods if they appear in future releases
            for meth_name in ("resize", "set_size", "set_window_size", "window_size"):
                meth = getattr(handle, meth_name, None)
                if callable(meth):
                    try:
                        res = meth(new_cols, new_rows)
                        if asyncio.iscoroutine(res):
                            await res
                        return
                    except TypeError:
                        try:
                            res = meth(new_rows, new_cols)
                            if asyncio.iscoroutine(res):
                                await res
                            return
                        except Exception:
                            pass
                    except Exception:
                        pass
            await guest_set_winsize(new_cols, new_rows)

    async def pump_out() -> None:
        try:
            async for event in handle:
                et = _event_kind(event)
                if et == "started":
                    pid = getattr(event, "pid", None)
                    if pid is not None:
                        size["pid"] = int(pid)
                        # Re-apply winsize now that we know the pid (PTY may have
                        # been created at default 80x24 by the runtime).
                        try:
                            await guest_set_winsize(int(size["cols"]), int(size["rows"]))
                        except Exception as exc:  # noqa: BLE001
                            logger.debug("post-start resize failed: %s", exc)
                    continue
                if et in ("stdout", "stderr"):
                    data = getattr(event, "data", None) or b""
                    if data:
                        if not await _safe_send(
                            websocket,
                            {
                                "type": "output",
                                "encoding": "base64",
                                "data": _b64(bytes(data)),
                            },
                        ):
                            break
                elif et == "exited":
                    code = getattr(event, "code", None)
                    await _safe_send(websocket, {"type": "exit", "code": code})
                    break
                elif et in ("failed", "stdin_error"):
                    msg = getattr(event, "data", b"") or b"stream failed"
                    if isinstance(msg, bytes):
                        msg = msg.decode("utf-8", errors="replace")
                    await _safe_send(websocket, {"type": "error", "message": str(msg)})
                    break
        except Exception as exc:  # noqa: BLE001
            logger.exception("shell pump_out error: %s", exc)
            await _safe_send(websocket, {"type": "error", "message": str(exc)})
        finally:
            stop.set()

    async def pump_in() -> None:
        try:
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except WebSocketDisconnect:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    if stdin is not None:
                        await stdin.write(raw.encode("utf-8", errors="replace"))
                    continue
                mtype = msg.get("type")
                if mtype == "input":
                    if stdin is not None:
                        await stdin.write(_decode_input(msg))
                elif mtype in ("resize", "hello"):
                    try:
                        await apply_resize(
                            int(msg.get("cols") or size["cols"]),
                            int(msg.get("rows") or size["rows"]),
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("resize failed: %s", exc)
                elif mtype == "signal":
                    sig = msg.get("sig", "INT")
                    try:
                        if hasattr(handle, "signal"):
                            n = 2 if str(sig).upper() in ("INT", "SIGINT", "2") else 15
                            await handle.signal(n)
                        elif str(sig).upper() in ("INT", "SIGINT") and stdin is not None:
                            await stdin.write(b"\x03")
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("signal failed: %s", exc)
                elif mtype == "ping":
                    await _safe_send(websocket, {"type": "pong"})
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.exception("shell pump_in error: %s", exc)
        finally:
            stop.set()

    out_task = asyncio.create_task(pump_out())
    in_task = asyncio.create_task(pump_in())
    try:
        await stop.wait()
    finally:
        out_task.cancel()
        in_task.cancel()
        for t in (out_task, in_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
        try:
            if hasattr(handle, "kill"):
                await handle.kill()
        except Exception:
            pass
        try:
            if stdin is not None and hasattr(stdin, "close"):
                await stdin.close()
        except Exception:
            pass


async def run_mock_shell(
    workspace: str,
    websocket: WebSocket,
    *,
    cmd: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> None:
    """Interactive local shell for MockSandboxBackend (PTY when available)."""
    import fcntl
    import pty
    import struct
    import termios

    await _safe_send(websocket, {"type": "ready", "mode": "mock-pty", "need_size": True})

    cols, rows = 160, 40
    try:
        cols, rows, _ = await _wait_initial_size(websocket)
    except WebSocketDisconnect:
        return

    master, slave = pty.openpty()
    # Set PTY winsize before the child starts so TIOCGWINSZ is correct.
    try:
        fcntl.ioctl(
            master,
            termios.TIOCSWINSZ,
            struct.pack("HHHH", rows, cols, 0, 0),
        )
    except Exception:
        pass

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = str(cols)
    env["LINES"] = str(rows)
    env["HOME"] = workspace
    if env_extra:
        env.update(env_extra)
    # Prefixed PATH for harness stubs
    bin_dir = os.path.join(workspace, ".everflow", "bin")
    if os.path.isdir(bin_dir):
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")

    if cmd and cmd.strip():
        argv = ["bash", "-lc", cmd.strip()]
    else:
        argv = ["bash", "-il"] if os.path.exists("/bin/bash") else ["sh", "-i"]

    pid = os.fork()
    if pid == 0:
        os.close(master)
        os.setsid()
        os.dup2(slave, 0)
        os.dup2(slave, 1)
        os.dup2(slave, 2)
        if slave > 2:
            os.close(slave)
        os.chdir(workspace)
        os.execvpe(argv[0], argv, env)

    os.close(slave)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    await _safe_send(
        websocket,
        {"type": "started", "cols": cols, "rows": rows, "mode": "mock-pty"},
    )

    async def pump_out() -> None:
        try:
            while not stop.is_set():
                try:
                    data = await loop.run_in_executor(None, lambda: os.read(master, 4096))
                except OSError:
                    break
                if not data:
                    break
                if not await _safe_send(
                    websocket,
                    {"type": "output", "encoding": "base64", "data": _b64(data)},
                ):
                    break
        finally:
            stop.set()

    async def pump_in() -> None:
        try:
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except WebSocketDisconnect:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await loop.run_in_executor(None, lambda: os.write(master, raw.encode()))
                    continue
                mtype = msg.get("type")
                if mtype == "input":
                    data = _decode_input(msg)
                    await loop.run_in_executor(None, lambda d=data: os.write(master, d))
                elif mtype in ("resize", "hello"):
                    c = int(msg.get("cols") or 80)
                    r = int(msg.get("rows") or 24)
                    try:
                        fcntl.ioctl(
                            master,
                            termios.TIOCSWINSZ,
                            struct.pack("HHHH", r, c, 0, 0),
                        )
                        os.kill(pid, _SIGWINCH)
                    except Exception:
                        pass
                elif mtype == "signal":
                    sig = str(msg.get("sig", "INT")).upper()
                    import signal as signal_mod

                    s = signal_mod.SIGINT if "INT" in sig else signal_mod.SIGTERM
                    try:
                        os.kill(pid, s)
                    except ProcessLookupError:
                        pass
                elif mtype == "ping":
                    await _safe_send(websocket, {"type": "pong"})
        except WebSocketDisconnect:
            pass
        finally:
            stop.set()

    out_task = asyncio.create_task(pump_out())
    in_task = asyncio.create_task(pump_in())
    try:
        await stop.wait()
    finally:
        out_task.cancel()
        in_task.cancel()
        try:
            os.close(master)
        except OSError:
            pass
        try:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        except Exception:
            pass
        await _safe_send(websocket, {"type": "exit", "code": 0})


async def run_docker_exec_shell(
    docker_bin: str,
    container: str,
    websocket: WebSocket,
    *,
    cmd: str | None = None,
    cwd: str = "/workspace",
    env: dict[str, str] | None = None,
) -> None:
    """Interactive shell via ``docker exec -i`` + guest PTY (container backend)."""
    await _safe_send(websocket, {"type": "ready", "mode": "docker-pty", "need_size": True})
    try:
        cols, rows, buffered_input = await _wait_initial_size(websocket)
    except WebSocketDisconnect:
        return

    inner = (cmd or "").strip() or "bash -il"
    prefix = _stty_prefix(cols, rows)
    guest = (
        "import os, pty, sys\n"
        f"os.chdir({cwd!r})\n"
        f"os.environ['TERM']='xterm-256color'\n"
        f"os.environ['COLUMNS']={str(cols)!r}\n"
        f"os.environ['LINES']={str(rows)!r}\n"
        f"pty.spawn(['/bin/bash','-lc',{prefix + 'exec ' + inner!r}])\n"
    )
    argv = [
        docker_bin,
        "exec",
        "-i",
        "-w",
        cwd,
        "-e",
        "TERM=xterm-256color",
        "-e",
        f"COLUMNS={cols}",
        "-e",
        f"LINES={rows}",
        container,
        "python3",
        "-c",
        guest,
    ]
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    assert proc.stdin is not None and proc.stdout is not None
    stop = asyncio.Event()
    await _safe_send(
        websocket,
        {"type": "started", "cols": cols, "rows": rows, "mode": "docker-pty"},
    )
    if buffered_input:
        proc.stdin.write(buffered_input)
        await proc.stdin.drain()

    async def pump_out() -> None:
        try:
            while not stop.is_set():
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                if not await _safe_send(
                    websocket,
                    {"type": "output", "encoding": "base64", "data": _b64(chunk)},
                ):
                    break
        finally:
            stop.set()

    async def pump_in() -> None:
        try:
            while not stop.is_set():
                try:
                    raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                except WebSocketDisconnect:
                    break
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    proc.stdin.write(raw.encode())
                    await proc.stdin.drain()
                    continue
                mtype = msg.get("type")
                if mtype == "input":
                    proc.stdin.write(_decode_input(msg))
                    await proc.stdin.drain()
                elif mtype == "ping":
                    await _safe_send(websocket, {"type": "pong"})
                elif mtype == "signal":
                    # Best-effort: Ctrl-C / terminate the exec.
                    sig = str(msg.get("sig", "INT")).upper()
                    if "INT" in sig:
                        proc.stdin.write(b"\x03")
                        await proc.stdin.drain()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            stop.set()

    out_task = asyncio.create_task(pump_out())
    in_task = asyncio.create_task(pump_in())
    try:
        await stop.wait()
    finally:
        out_task.cancel()
        in_task.cancel()
        try:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
        except Exception:
            pass
        await _safe_send(websocket, {"type": "exit", "code": int(proc.returncode or 0)})
