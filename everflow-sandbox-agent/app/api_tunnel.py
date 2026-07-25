"""Reverse TCP tunnel: guest 127.0.0.1:port → agent → platform API.

Uses a **line-based** protocol (not raw binary) so microsandbox exec_stream
delivers stdout promptly (binary frames were stuck until buffer fill).

Guest → agent (stdout lines):
  OPEN <conn_id>
  DATA <conn_id> <base64>
  CLOSE <conn_id>

Agent → guest (stdin lines):
  DATA <conn_id> <base64>
  CLOSE <conn_id>
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_REVERSE_MUX_SCRIPT = r"""
import base64, os, socket, sys, threading
from socketserver import ThreadingTCPServer, BaseRequestHandler

listen_port = int(os.environ["EF_LISTEN_PORT"])
socks = {}
lock = threading.Lock()
stdout_lock = threading.Lock()
next_id = 1

def emit(line: str) -> None:
    with stdout_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

class H(BaseRequestHandler):
    def handle(self):
        global next_id
        sock = self.request
        with lock:
            conn_id = next_id
            next_id += 1
            socks[conn_id] = sock
        try:
            emit("OPEN %d" % conn_id)
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
            with lock:
                socks.pop(conn_id, None)
            return
        try:
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                emit("DATA %d %s" % (conn_id, base64.b64encode(data).decode("ascii")))
        except Exception:
            pass
        finally:
            try:
                sock.close()
            except Exception:
                pass
            with lock:
                socks.pop(conn_id, None)
            try:
                emit("CLOSE %d" % conn_id)
            except Exception:
                pass

def stdin_loop():
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 2)
            kind = parts[0]
            if kind == "DATA" and len(parts) == 3:
                conn_id = int(parts[1])
                payload = base64.b64decode(parts[2].encode("ascii"))
                with lock:
                    sock = socks.get(conn_id)
                if sock is not None and payload:
                    try:
                        sock.sendall(payload)
                    except Exception:
                        try:
                            sock.close()
                        except Exception:
                            pass
                        with lock:
                            socks.pop(conn_id, None)
            elif kind == "CLOSE" and len(parts) >= 2:
                conn_id = int(parts[1])
                with lock:
                    sock = socks.pop(conn_id, None)
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
    except Exception as e:
        sys.stderr.write("api-mux stdin: %s\n" % e)
        sys.stderr.flush()
    finally:
        with lock:
            items = list(socks.items())
            socks.clear()
        for _, sock in items:
            try:
                sock.close()
            except Exception:
                pass

t = threading.Thread(target=stdin_loop, daemon=True)
t.start()
ThreadingTCPServer.allow_reuse_address = True
srv = ThreadingTCPServer(("127.0.0.1", listen_port), H)
sys.stderr.write("api-tunnel listening 127.0.0.1:%s\n" % listen_port)
sys.stderr.flush()
try:
    srv.serve_forever()
except Exception as e:
    sys.stderr.write("api-tunnel serve: %s\n" % e)
    sys.stderr.flush()
"""


@dataclass
class _ApiTunnel:
    sandbox_name: str
    listen_port: int
    target_host: str
    target_port: int
    handle: Any
    sink: Any
    created_at: float = field(default_factory=time.time)
    conns: dict[int, asyncio.StreamWriter] = field(default_factory=dict)
    # DATA frames that arrive before OPEN dial finishes (HTTP clients send immediately)
    pending_data: dict[int, list[bytes]] = field(default_factory=dict)
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    alive: bool = True
    listener_ready: asyncio.Event = field(default_factory=asyncio.Event)
    reader_task: asyncio.Task | None = None


class ApiTunnelManager:
    def __init__(self) -> None:
        self._tunnels: dict[str, _ApiTunnel] = {}
        self._lock = asyncio.Lock()
        self._backend: Any = None

    def bind_backend(self, backend: Any) -> None:
        self._backend = backend

    async def close_all(self) -> None:
        async with self._lock:
            names = list(self._tunnels.keys())
        for name in names:
            await self._teardown(name)

    async def ensure(
        self,
        sandbox_name: str,
        *,
        target_url: str,
        listen_port: int = 18765,
        force: bool = False,
        kill_guest_port: Any | None = None,
    ) -> dict[str, Any]:
        host, port = _parse_host_port(target_url)
        async with self._lock:
            existing = self._tunnels.get(sandbox_name)
            if (
                not force
                and existing is not None
                and existing.alive
                and existing.target_host == host
                and existing.target_port == port
                and existing.listen_port == listen_port
            ):
                return {
                    "ok": True,
                    "listen_port": existing.listen_port,
                    "target": f"{host}:{port}",
                    "api_url": f"http://127.0.0.1:{existing.listen_port}",
                }
            if existing is not None:
                self._tunnels.pop(sandbox_name, None)
                stale = existing
            else:
                stale = None

        if stale is not None:
            await self._close_tunnel(stale)

        if kill_guest_port is not None:
            try:
                await kill_guest_port(sandbox_name, listen_port)
            except Exception as exc:  # noqa: BLE001
                logger.debug("kill guest api tunnel port: %s", exc)

        try:
            tunnel = await self._start(sandbox_name, host, port, listen_port)
        except Exception as exc:  # noqa: BLE001
            logger.warning("api tunnel start failed name=%s: %s", sandbox_name, exc)
            return {
                "ok": False,
                "error": str(exc),
                "listen_port": listen_port,
                "target": f"{host}:{port}",
            }

        async with self._lock:
            self._tunnels[sandbox_name] = tunnel

        # Wait for guest mux to report listen (stderr), else brief settle delay.
        try:
            await asyncio.wait_for(tunnel.listener_ready.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            await asyncio.sleep(0.5)
            logger.warning(
                "api tunnel listen ack timed out name=%s (continuing; may race)",
                sandbox_name,
            )
        return {
            "ok": True,
            "listen_port": listen_port,
            "target": f"{host}:{port}",
            "api_url": f"http://127.0.0.1:{listen_port}",
        }

    async def _start(
        self,
        sandbox_name: str,
        target_host: str,
        target_port: int,
        listen_port: int,
    ) -> _ApiTunnel:
        backend = self._backend
        if backend is None or not hasattr(backend, "open_exec_stream"):
            raise RuntimeError("backend does not support exec_stream tunnels")

        handle, sink = await backend.open_exec_stream(
            sandbox_name,
            cmd="python3",
            args=["-c", _REVERSE_MUX_SCRIPT],
            env={
                "EF_LISTEN_PORT": str(listen_port),
                "PYTHONUNBUFFERED": "1",
            },
            cwd="/workspace",
        )
        tunnel = _ApiTunnel(
            sandbox_name=sandbox_name,
            listen_port=listen_port,
            target_host=target_host,
            target_port=target_port,
            handle=handle,
            sink=sink,
        )
        tunnel.reader_task = asyncio.create_task(self._reader_loop(tunnel))
        logger.info(
            "api tunnel up name=%s listen=%s target=%s:%s",
            sandbox_name,
            listen_port,
            target_host,
            target_port,
        )
        return tunnel

    async def _reader_loop(self, tunnel: _ApiTunnel) -> None:
        buf = ""
        try:
            async for ev in tunnel.handle:
                et = getattr(ev, "event_type", "") or ""
                data = getattr(ev, "data", None)
                if et == "stdout" and data:
                    if isinstance(data, bytes):
                        text = data.decode("utf-8", errors="replace")
                    else:
                        text = str(data)
                    buf += text
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        await self._handle_line(tunnel, line)
                elif et == "stderr" and data:
                    msg = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
                    logger.info("api tunnel stderr name=%s: %s", tunnel.sandbox_name, msg[:400])
                    if "api-tunnel listening" in msg:
                        tunnel.listener_ready.set()
                elif et in ("exited", "error"):
                    logger.warning(
                        "api tunnel stream ended name=%s et=%s",
                        tunnel.sandbox_name,
                        et,
                    )
                    break
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("api tunnel reader failed name=%s: %s", tunnel.sandbox_name, exc)
        finally:
            tunnel.alive = False
            tunnel.pending_data.clear()
            for cid in list(tunnel.conns.keys()):
                await self._close_conn(tunnel, cid)
            async with self._lock:
                if self._tunnels.get(tunnel.sandbox_name) is tunnel:
                    self._tunnels.pop(tunnel.sandbox_name, None)
            logger.warning(
                "api tunnel removed name=%s — re-run opencode/ensure to restore Everflow MCP API access",
                tunnel.sandbox_name,
            )

    async def _handle_line(self, tunnel: _ApiTunnel, line: str) -> None:
        parts = line.split(" ", 2)
        kind = parts[0]
        if kind == "OPEN" and len(parts) >= 2:
            conn_id = int(parts[1])
            # Await dial so early HTTP DATA is not dropped (create_task raced).
            await self._handle_open(tunnel, conn_id)
        elif kind == "DATA" and len(parts) == 3:
            conn_id = int(parts[1])
            payload = base64.b64decode(parts[2].encode("ascii"))
            if not payload:
                return
            writer = tunnel.conns.get(conn_id)
            if writer is not None:
                try:
                    writer.write(payload)
                    await writer.drain()
                except Exception:  # noqa: BLE001
                    await self._close_conn(tunnel, conn_id)
            else:
                # Buffer until OPEN dial finishes (belt-and-suspenders).
                tunnel.pending_data.setdefault(conn_id, []).append(payload)
        elif kind == "CLOSE" and len(parts) >= 2:
            conn_id = int(parts[1])
            await self._close_conn(tunnel, conn_id)

    async def _handle_open(self, tunnel: _ApiTunnel, conn_id: int) -> None:
        logger.info(
            "api tunnel OPEN name=%s conn=%s -> %s:%s",
            tunnel.sandbox_name,
            conn_id,
            tunnel.target_host,
            tunnel.target_port,
        )
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(tunnel.target_host, tunnel.target_port),
                timeout=15,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "api tunnel dial fail name=%s %s:%s: %s",
                tunnel.sandbox_name,
                tunnel.target_host,
                tunnel.target_port,
                exc,
            )
            tunnel.pending_data.pop(conn_id, None)
            try:
                await self._send_line(tunnel, f"CLOSE {conn_id}")
            except Exception:  # noqa: BLE001
                pass
            return

        tunnel.conns[conn_id] = writer
        # Flush any DATA that arrived while dial was in progress.
        pending = tunnel.pending_data.pop(conn_id, [])
        if pending:
            try:
                for chunk in pending:
                    writer.write(chunk)
                await writer.drain()
            except Exception:  # noqa: BLE001
                await self._close_conn(tunnel, conn_id)
                return

        async def pump_host_to_guest() -> None:
            try:
                while tunnel.alive:
                    data = await _reader.read(65536)
                    if not data:
                        break
                    b64 = base64.b64encode(data).decode("ascii")
                    await self._send_line(tunnel, f"DATA {conn_id} {b64}")
            except Exception:  # noqa: BLE001
                pass
            finally:
                try:
                    await self._send_line(tunnel, f"CLOSE {conn_id}")
                except Exception:  # noqa: BLE001
                    pass
                await self._close_conn(tunnel, conn_id)

        asyncio.create_task(pump_host_to_guest())

    async def _close_conn(self, tunnel: _ApiTunnel, conn_id: int) -> None:
        tunnel.pending_data.pop(conn_id, None)
        writer = tunnel.conns.pop(conn_id, None)
        if writer is None:
            return
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass

    async def _send_line(self, tunnel: _ApiTunnel, line: str) -> None:
        async with tunnel.write_lock:
            if not tunnel.alive:
                raise RuntimeError("tunnel dead")
            await tunnel.sink.write((line + "\n").encode("utf-8"))

    async def _teardown(self, sandbox_name: str) -> None:
        async with self._lock:
            tunnel = self._tunnels.pop(sandbox_name, None)
        if tunnel is not None:
            await self._close_tunnel(tunnel)

    async def _close_tunnel(self, tunnel: _ApiTunnel) -> None:
        tunnel.alive = False
        if tunnel.reader_task is not None:
            tunnel.reader_task.cancel()
            try:
                await tunnel.reader_task
            except Exception:  # noqa: BLE001
                pass
        for cid in list(tunnel.conns.keys()):
            await self._close_conn(tunnel, cid)
        try:
            await tunnel.handle.kill()
        except Exception:  # noqa: BLE001
            pass
        try:
            await tunnel.sink.close()
        except Exception:  # noqa: BLE001
            pass


_manager = ApiTunnelManager()


def get_api_tunnel_manager() -> ApiTunnelManager:
    return _manager


def _parse_host_port(url: str) -> tuple[str, int]:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("empty target url")
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return host, port
