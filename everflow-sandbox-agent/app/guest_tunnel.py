"""Host↔guest TCP tunnels for preview HTTP/WebSocket (Vite HMR).

MicroVM guest loopback is not host-reachable. We open a local TCP port on the
agent host and, for each accepted connection, run an in-guest Python relay over
microsandbox ``exec_stream`` (stdin/stdout length-prefixed frames).

Frame format (both directions)::

    uint32_be length | payload
    length == 0xFFFFFFFF → peer closed
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_EOF = 0xFFFFFFFF
_MAX_FRAME = 8 * 1024 * 1024

# In-guest relay: stdin frames → TCP, TCP → stdout frames
_RELAY_SCRIPT = r"""
import os, select, socket, struct, sys

def read_exact(n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sys.stdin.buffer.read(n - len(buf))
        if not chunk:
            raise EOFError("stdin closed")
        buf += chunk
    return buf

port = int(os.environ["EF_PORT"])
sock = socket.create_connection(("127.0.0.1", port), timeout=15)
sock.setblocking(False)
stdin_fd = sys.stdin.fileno()

try:
    while True:
        r, _, _ = select.select([stdin_fd, sock], [], [], 120.0)
        if not r:
            continue
        if stdin_fd in r:
            hdr = read_exact(4)
            n = struct.unpack("!I", hdr)[0]
            if n == 0xFFFFFFFF:
                break
            if n > 8 * 1024 * 1024:
                raise RuntimeError("frame too large")
            data = read_exact(n)
            view = memoryview(data)
            while view:
                try:
                    sent = sock.send(view)
                    view = view[sent:]
                except BlockingIOError:
                    select.select([], [sock], [], 30.0)
        if sock in r:
            try:
                data = sock.recv(65536)
            except BlockingIOError:
                continue
            if not data:
                sys.stdout.buffer.write(struct.pack("!I", 0xFFFFFFFF))
                sys.stdout.buffer.flush()
                break
            sys.stdout.buffer.write(struct.pack("!I", len(data)))
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
except BrokenPipeError:
    pass
except Exception as exc:
    try:
        sys.stderr.write(f"ef-relay: {exc}\n")
        sys.stderr.flush()
    except Exception:
        pass
finally:
    try:
        sock.close()
    except Exception:
        pass
"""


@dataclass
class _TunnelEntry:
    sandbox_name: str
    guest_port: int
    host_port: int
    server: asyncio.AbstractServer
    created_at: float = field(default_factory=time.time)
    connections: int = 0


class GuestTunnelManager:
    """Lazily allocates local ports that bridge into a guest sandbox port."""

    def __init__(self) -> None:
        self._tunnels: dict[tuple[str, int], _TunnelEntry] = {}
        self._lock = asyncio.Lock()
        self._backend: Any = None

    def bind_backend(self, backend: Any) -> None:
        """Attach the live SandboxBackend (MicrosandboxBackend preferred)."""
        self._backend = backend

    async def close_all(self) -> None:
        async with self._lock:
            for key, entry in list(self._tunnels.items()):
                entry.server.close()
                await entry.server.wait_closed()
                del self._tunnels[key]

    async def ensure_local_port(self, sandbox_name: str, guest_port: int) -> int:
        """Return a host 127.0.0.1 port that tunnels to guest 127.0.0.1:guest_port."""
        if guest_port < 1 or guest_port > 65535:
            raise ValueError(f"invalid guest port: {guest_port}")
        key = (sandbox_name, guest_port)
        async with self._lock:
            existing = self._tunnels.get(key)
            if existing is not None:
                return existing.host_port

            # Bind ephemeral local port
            server = await asyncio.start_server(
                lambda r, w: self._on_client(sandbox_name, guest_port, r, w),
                host="127.0.0.1",
                port=0,
            )
            sockets = server.sockets or []
            if not sockets:
                server.close()
                await server.wait_closed()
                raise RuntimeError("failed to bind tunnel listener")
            host_port = int(sockets[0].getsockname()[1])
            entry = _TunnelEntry(
                sandbox_name=sandbox_name,
                guest_port=guest_port,
                host_port=host_port,
                server=server,
            )
            self._tunnels[key] = entry
            logger.info(
                "guest tunnel listening name=%s guest_port=%s host_port=%s",
                sandbox_name,
                guest_port,
                host_port,
            )
            return host_port

    async def _on_client(
        self,
        sandbox_name: str,
        guest_port: int,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        key = (sandbox_name, guest_port)
        entry = self._tunnels.get(key)
        if entry:
            entry.connections += 1
        peer = writer.get_extra_info("peername")
        logger.debug(
            "guest tunnel accept name=%s guest_port=%s peer=%s",
            sandbox_name,
            guest_port,
            peer,
        )
        try:
            await self._bridge_connection(sandbox_name, guest_port, reader, writer)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "guest tunnel bridge failed name=%s port=%s: %s",
                sandbox_name,
                guest_port,
                exc,
            )
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _bridge_connection(
        self,
        sandbox_name: str,
        guest_port: int,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        backend = self._backend
        if backend is None:
            raise RuntimeError("tunnel manager has no backend")

        # Prefer real microVM stream; MockBackend will raise and callers should host-dial.
        connect = getattr(backend, "open_exec_stream", None)
        if connect is None:
            raise RuntimeError("backend does not support exec_stream tunnels")

        handle, sink = await connect(
            sandbox_name,
            cmd="python3",
            args=["-c", _RELAY_SCRIPT],
            env={"EF_PORT": str(guest_port)},
            cwd="/workspace",
        )

        stop = asyncio.Event()

        async def host_to_guest() -> None:
            try:
                while not stop.is_set():
                    data = await client_reader.read(65536)
                    if not data:
                        try:
                            await sink.write(struct.pack("!I", _EOF))
                        except Exception:
                            pass
                        try:
                            await sink.close()
                        except Exception:
                            pass
                        break
                    if len(data) > _MAX_FRAME:
                        data = data[:_MAX_FRAME]
                    await sink.write(struct.pack("!I", len(data)) + data)
            except Exception as exc:  # noqa: BLE001
                logger.debug("host→guest closed: %s", exc)
            finally:
                stop.set()

        async def guest_to_host() -> None:
            buf = b""
            try:
                async for ev in handle:
                    et = getattr(ev, "event_type", "") or ""
                    data = getattr(ev, "data", None)
                    if et == "stdout" and data:
                        buf += data
                        while len(buf) >= 4:
                            (n,) = struct.unpack("!I", buf[:4])
                            if n == _EOF:
                                buf = buf[4:]
                                stop.set()
                                return
                            if n > _MAX_FRAME:
                                logger.warning("guest frame too large n=%s", n)
                                stop.set()
                                return
                            if len(buf) < 4 + n:
                                break
                            payload = buf[4 : 4 + n]
                            buf = buf[4 + n :]
                            client_writer.write(payload)
                            await client_writer.drain()
                    elif et in ("exited", "error"):
                        break
                    elif et == "stderr" and data:
                        logger.debug(
                            "guest relay stderr name=%s: %s",
                            sandbox_name,
                            data[:300],
                        )
            except Exception as exc:  # noqa: BLE001
                logger.debug("guest→host closed: %s", exc)
            finally:
                stop.set()

        t1 = asyncio.create_task(host_to_guest())
        t2 = asyncio.create_task(guest_to_host())
        await stop.wait()
        for t in (t1, t2):
            t.cancel()
        try:
            await handle.kill()
        except Exception:
            pass
        try:
            await sink.close()
        except Exception:
            pass


_manager: GuestTunnelManager | None = None


def get_tunnel_manager() -> GuestTunnelManager:
    global _manager
    if _manager is None:
        _manager = GuestTunnelManager()
    return _manager


async def can_connect_host(host: str, port: int, *, timeout: float = 0.4) -> bool:
    """True if a TCP connect to host:port succeeds quickly."""
    try:
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=timeout)
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
    """
    Return (host, port, mode) for agent-side dialing.

    mode is ``host`` if loopback already works (mock), else ``tunnel``.
    """
    if await can_connect_host("127.0.0.1", guest_port):
        return "127.0.0.1", guest_port, "host"

    mgr = get_tunnel_manager()
    mgr.bind_backend(backend)
    # open_exec_stream only on MicrosandboxBackend
    if not hasattr(backend, "open_exec_stream"):
        # Fall back — caller may use guest exec HTTP
        return "127.0.0.1", guest_port, "unreachable"

    host_port = await mgr.ensure_local_port(sandbox_name, guest_port)
    return "127.0.0.1", host_port, "tunnel"
