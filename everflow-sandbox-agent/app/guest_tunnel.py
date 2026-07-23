"""Host↔guest TCP tunnels for preview HTTP/WebSocket (Vite HMR).

Strategy: **one long-lived multiplexed exec_stream per (sandbox, guest_port)**.

Vite fans out many parallel GETs + a WebSocket. Spawning one microsandbox
``exec_stream`` per request races and yields intermittent 502s / failed HMR.

Protocol (both directions over a single stream)::

    OPEN  | conn_id:u32
    DATA  | conn_id:u32 | length:u32 | payload
    CLOSE | conn_id:u32

Host→guest OPEN asks the guest to dial the app port. Guest→host OPEN is an
ack that the dial succeeded (host must wait for it before sending DATA).
Guest buffers early DATA until the dial completes so WebSocket handshakes
are not dropped.

On the agent host we listen on 127.0.0.1:ephemeral; each accepted TCP client
gets a conn_id and is framed over the shared guest stream. The guest dials
127.0.0.1:{guest_port} per OPEN and pipes bytes.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MSG_OPEN = 1
_MSG_DATA = 2
_MSG_CLOSE = 3
_MAX_FRAME = 4 * 1024 * 1024
_OPEN_ACK_TIMEOUT_S = 20.0

# Guest-side multiplexer (single process, many local TCP conns)
_MUX_SCRIPT = r"""
import os, socket, struct, sys, threading
from collections import defaultdict

MSG_OPEN, MSG_DATA, MSG_CLOSE = 1, 2, 3
MAX = 4 * 1024 * 1024
port = int(os.environ["EF_PORT"])
socks = {}
pending = defaultdict(bytearray)
lock = threading.Lock()
stdout_lock = threading.Lock()

def read_exact(n):
    buf = b""
    while len(buf) < n:
        chunk = sys.stdin.buffer.read(n - len(buf))
        if not chunk:
            raise EOFError("stdin closed")
        buf += chunk
    return buf

def write_msg(kind, conn_id, payload=b""):
    with stdout_lock:
        if kind == MSG_DATA:
            sys.stdout.buffer.write(struct.pack("!BII", kind, conn_id, len(payload)))
            if payload:
                sys.stdout.buffer.write(payload)
        else:
            sys.stdout.buffer.write(struct.pack("!BI", kind, conn_id))
        sys.stdout.buffer.flush()

def flush_pending(conn_id, sock):
    with lock:
        buf = pending.pop(conn_id, None)
    if not buf:
        return True
    try:
        sock.sendall(bytes(buf))
        return True
    except Exception:
        return False

def reader_loop(conn_id, sock):
    try:
        while True:
            data = sock.recv(65536)
            if not data:
                break
            write_msg(MSG_DATA, conn_id, data)
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
        with lock:
            socks.pop(conn_id, None)
            pending.pop(conn_id, None)
        try:
            write_msg(MSG_CLOSE, conn_id)
        except Exception:
            pass

try:
    while True:
        hdr = read_exact(1)
        kind = hdr[0]
        if kind == MSG_OPEN:
            conn_id = struct.unpack("!I", read_exact(4))[0]
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=15)
            except Exception as e:
                sys.stderr.write("open fail %s: %s\n" % (conn_id, e))
                sys.stderr.flush()
                with lock:
                    pending.pop(conn_id, None)
                write_msg(MSG_CLOSE, conn_id)
                continue
            with lock:
                socks[conn_id] = sock
            if not flush_pending(conn_id, sock):
                try:
                    sock.close()
                except Exception:
                    pass
                with lock:
                    socks.pop(conn_id, None)
                write_msg(MSG_CLOSE, conn_id)
                continue
            # Ack dial success so host can safely send the WS/HTTP request body
            write_msg(MSG_OPEN, conn_id)
            t = threading.Thread(target=reader_loop, args=(conn_id, sock), daemon=True)
            t.start()
        elif kind == MSG_DATA:
            conn_id, n = struct.unpack("!II", read_exact(8))
            if n > MAX:
                raise RuntimeError("frame too large")
            data = read_exact(n) if n else b""
            if not data:
                continue
            with lock:
                sock = socks.get(conn_id)
                if sock is None:
                    # Dial still in progress (or OPEN not yet seen) — buffer
                    pending[conn_id].extend(data)
                    if len(pending[conn_id]) > MAX:
                        pending.pop(conn_id, None)
                        write_msg(MSG_CLOSE, conn_id)
                    continue
            try:
                sock.sendall(data)
            except Exception:
                try:
                    sock.close()
                except Exception:
                    pass
                with lock:
                    socks.pop(conn_id, None)
                    pending.pop(conn_id, None)
                write_msg(MSG_CLOSE, conn_id)
        elif kind == MSG_CLOSE:
            conn_id = struct.unpack("!I", read_exact(4))[0]
            with lock:
                sock = socks.pop(conn_id, None)
                pending.pop(conn_id, None)
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        else:
            raise RuntimeError("bad kind %s" % kind)
except EOFError:
    pass
except Exception as e:
    sys.stderr.write("mux: %s\n" % e)
    sys.stderr.flush()
finally:
    with lock:
        items = list(socks.items())
        socks.clear()
        pending.clear()
    for _, sock in items:
        try:
            sock.close()
        except Exception:
            pass
"""


@dataclass
class _Conn:
    conn_id: int
    writer: asyncio.StreamWriter
    queue: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    open_ack: asyncio.Event = field(default_factory=asyncio.Event)
    closed: bool = False


@dataclass
class _MuxTunnel:
    sandbox_name: str
    guest_port: int
    host_port: int
    server: asyncio.AbstractServer
    handle: Any
    sink: Any
    created_at: float = field(default_factory=time.time)
    next_id: int = 1
    conns: dict[int, _Conn] = field(default_factory=dict)
    write_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    alive: bool = True
    reader_task: asyncio.Task | None = None


class GuestTunnelManager:
    def __init__(self) -> None:
        self._tunnels: dict[tuple[str, int], _MuxTunnel] = {}
        self._lock = asyncio.Lock()
        self._backend: Any = None

    def bind_backend(self, backend: Any) -> None:
        self._backend = backend

    async def close_all(self) -> None:
        async with self._lock:
            keys = list(self._tunnels.keys())
        for key in keys:
            await self._teardown(key)

    async def ensure_local_port(self, sandbox_name: str, guest_port: int) -> int:
        if guest_port < 1 or guest_port > 65535:
            raise ValueError(f"invalid guest port: {guest_port}")
        key = (sandbox_name, guest_port)
        async with self._lock:
            existing = self._tunnels.get(key)
            if existing is not None and existing.alive:
                return existing.host_port
            if existing is not None:
                # stale
                self._tunnels.pop(key, None)

        tunnel = await self._start_mux(sandbox_name, guest_port)
        async with self._lock:
            self._tunnels[key] = tunnel
        return tunnel.host_port

    async def _start_mux(self, sandbox_name: str, guest_port: int) -> _MuxTunnel:
        backend = self._backend
        if backend is None or not hasattr(backend, "open_exec_stream"):
            raise RuntimeError("backend does not support exec_stream tunnels")

        handle, sink = await backend.open_exec_stream(
            sandbox_name,
            cmd="python3",
            args=["-c", _MUX_SCRIPT],
            env={"EF_PORT": str(guest_port), "PYTHONUNBUFFERED": "1"},
            cwd="/workspace",
        )

        # Placeholder host_port until server starts
        tunnel = _MuxTunnel(
            sandbox_name=sandbox_name,
            guest_port=guest_port,
            host_port=0,
            server=None,  # type: ignore[arg-type]
            handle=handle,
            sink=sink,
        )

        async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await self._handle_client(tunnel, reader, writer)

        server = await asyncio.start_server(on_client, host="127.0.0.1", port=0)
        socks = server.sockets or []
        if not socks:
            server.close()
            await server.wait_closed()
            try:
                await handle.kill()
            except Exception:
                pass
            raise RuntimeError("failed to bind mux listener")
        tunnel.server = server
        tunnel.host_port = int(socks[0].getsockname()[1])
        tunnel.reader_task = asyncio.create_task(self._guest_reader_loop(tunnel))
        logger.info(
            "guest mux tunnel up name=%s guest_port=%s host_port=%s",
            sandbox_name,
            guest_port,
            tunnel.host_port,
        )
        return tunnel

    async def _teardown(self, key: tuple[str, int]) -> None:
        async with self._lock:
            tunnel = self._tunnels.pop(key, None)
        if tunnel is None:
            return
        tunnel.alive = False
        for conn in list(tunnel.conns.values()):
            try:
                await conn.queue.put(None)
            except Exception:
                pass
            try:
                conn.writer.close()
            except Exception:
                pass
        try:
            tunnel.server.close()
            await tunnel.server.wait_closed()
        except Exception:
            pass
        if tunnel.reader_task:
            tunnel.reader_task.cancel()
        try:
            await tunnel.handle.kill()
        except Exception:
            pass
        try:
            await tunnel.sink.close()
        except Exception:
            pass

    async def _send(self, tunnel: _MuxTunnel, data: bytes) -> None:
        async with tunnel.write_lock:
            if not tunnel.alive:
                raise RuntimeError("tunnel dead")
            await tunnel.sink.write(data)

    async def _handle_client(
        self,
        tunnel: _MuxTunnel,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if not tunnel.alive:
            writer.close()
            return
        conn_id = tunnel.next_id
        tunnel.next_id += 1
        conn = _Conn(conn_id=conn_id, writer=writer)
        tunnel.conns[conn_id] = conn
        peer = writer.get_extra_info("peername")
        logger.debug(
            "mux accept name=%s guest=%s conn=%s peer=%s",
            tunnel.sandbox_name,
            tunnel.guest_port,
            conn_id,
            peer,
        )
        try:
            await self._send(tunnel, struct.pack("!BI", _MSG_OPEN, conn_id))
            # Wait for guest dial ack before pumping request bytes (WS handshake).
            try:
                await asyncio.wait_for(conn.open_ack.wait(), timeout=_OPEN_ACK_TIMEOUT_S)
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f"guest dial ack timeout conn={conn_id} port={tunnel.guest_port}"
                ) from exc
            if conn.closed or not tunnel.alive:
                raise RuntimeError(
                    f"guest dial failed conn={conn_id} port={tunnel.guest_port}"
                )

            async def host_to_guest() -> None:
                try:
                    while tunnel.alive:
                        data = await reader.read(65536)
                        if not data:
                            break
                        offset = 0
                        while offset < len(data):
                            chunk = data[offset : offset + _MAX_FRAME]
                            offset += len(chunk)
                            await self._send(
                                tunnel,
                                struct.pack("!BII", _MSG_DATA, conn_id, len(chunk)) + chunk,
                            )
                finally:
                    try:
                        await self._send(tunnel, struct.pack("!BI", _MSG_CLOSE, conn_id))
                    except Exception:
                        pass

            async def guest_to_host() -> None:
                try:
                    while True:
                        item = await conn.queue.get()
                        if item is None:
                            break
                        writer.write(item)
                        await writer.drain()
                except Exception:
                    pass

            t1 = asyncio.create_task(host_to_guest())
            t2 = asyncio.create_task(guest_to_host())
            done, pending = await asyncio.wait(
                {t1, t2}, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
            await asyncio.gather(t1, t2, return_exceptions=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mux client failed name=%s port=%s conn=%s: %s",
                tunnel.sandbox_name,
                tunnel.guest_port,
                conn_id,
                exc,
            )
        finally:
            tunnel.conns.pop(conn_id, None)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _guest_reader_loop(self, tunnel: _MuxTunnel) -> None:
        buf = b""
        try:
            async for ev in tunnel.handle:
                et = getattr(ev, "event_type", "") or ""
                data = getattr(ev, "data", None)
                if et == "stdout" and data:
                    buf += data
                    while True:
                        if len(buf) < 1:
                            break
                        kind = buf[0]
                        if kind == _MSG_DATA:
                            if len(buf) < 9:
                                break
                            conn_id, n = struct.unpack("!II", buf[1:9])
                            if n > _MAX_FRAME:
                                logger.warning("mux frame too large n=%s", n)
                                tunnel.alive = False
                                return
                            if len(buf) < 9 + n:
                                break
                            payload = buf[9 : 9 + n]
                            buf = buf[9 + n :]
                            conn = tunnel.conns.get(conn_id)
                            if conn is not None:
                                await conn.queue.put(payload)
                        elif kind in (_MSG_OPEN, _MSG_CLOSE):
                            if len(buf) < 5:
                                break
                            (conn_id,) = struct.unpack("!I", buf[1:5])
                            buf = buf[5:]
                            conn = tunnel.conns.get(conn_id)
                            if kind == _MSG_OPEN:
                                # Guest dial succeeded — unblock host→guest pump
                                if conn is not None:
                                    conn.open_ack.set()
                            elif kind == _MSG_CLOSE:
                                if conn is not None:
                                    conn.closed = True
                                    conn.open_ack.set()
                                    await conn.queue.put(None)
                        else:
                            logger.warning("mux bad kind=%s", kind)
                            tunnel.alive = False
                            return
                elif et == "stderr" and data:
                    logger.debug(
                        "mux stderr name=%s: %s",
                        tunnel.sandbox_name,
                        data[:400],
                    )
                elif et in ("exited", "error"):
                    logger.warning(
                        "mux guest stream ended name=%s port=%s et=%s code=%s",
                        tunnel.sandbox_name,
                        tunnel.guest_port,
                        et,
                        getattr(ev, "code", None),
                    )
                    break
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "mux reader failed name=%s port=%s: %s",
                tunnel.sandbox_name,
                tunnel.guest_port,
                exc,
            )
        finally:
            tunnel.alive = False
            for conn in list(tunnel.conns.values()):
                conn.closed = True
                conn.open_ack.set()
                try:
                    await conn.queue.put(None)
                except Exception:
                    pass
            # Drop from registry so next request recreates
            key = (tunnel.sandbox_name, tunnel.guest_port)
            async with self._lock:
                if self._tunnels.get(key) is tunnel:
                    self._tunnels.pop(key, None)


_manager: GuestTunnelManager | None = None


def get_tunnel_manager() -> GuestTunnelManager:
    global _manager
    if _manager is None:
        _manager = GuestTunnelManager()
    return _manager


async def can_connect_host(host: str, port: int, *, timeout: float = 0.35) -> bool:
    try:
        conn = asyncio.open_connection(host, port)
        _reader, writer = await asyncio.wait_for(conn, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def resolve_dial_target(
    sandbox_name: str,
    guest_port: int,
    *,
    backend: Any,
) -> tuple[str, int, str]:
    """Return (host, port, mode) for agent-side dialing."""
    if await can_connect_host("127.0.0.1", guest_port):
        return "127.0.0.1", guest_port, "host"

    mgr = get_tunnel_manager()
    mgr.bind_backend(backend)
    if not hasattr(backend, "open_exec_stream"):
        return "127.0.0.1", guest_port, "unreachable"

    host_port = await mgr.ensure_local_port(sandbox_name, guest_port)
    return "127.0.0.1", host_port, "tunnel"
