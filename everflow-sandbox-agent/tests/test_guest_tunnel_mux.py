"""Guest TCP mux protocol: OPEN ack + DATA buffering (Vite HMR handshake)."""

from __future__ import annotations

import asyncio
import struct
import sys
from pathlib import Path

import pytest

# Import mux constants / script from agent
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.guest_tunnel import (  # noqa: E402
    _MAX_FRAME,
    _MSG_CLOSE,
    _MSG_DATA,
    _MSG_OPEN,
    _MUX_SCRIPT,
)


def _pack_open(conn_id: int) -> bytes:
    return struct.pack("!BI", _MSG_OPEN, conn_id)


def _pack_data(conn_id: int, payload: bytes) -> bytes:
    return struct.pack("!BII", _MSG_DATA, conn_id, len(payload)) + payload


def _pack_close(conn_id: int) -> bytes:
    return struct.pack("!BI", _MSG_CLOSE, conn_id)


async def _read_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = await reader.read(n - len(buf))
        if not chunk:
            raise EOFError("stdout closed")
        buf += chunk
    return buf


async def _read_msg(reader: asyncio.StreamReader) -> tuple[int, int, bytes]:
    kind = (await _read_exact(reader, 1))[0]
    if kind == _MSG_DATA:
        conn_id, n = struct.unpack("!II", await _read_exact(reader, 8))
        if n > _MAX_FRAME:
            raise RuntimeError("frame too large")
        payload = await _read_exact(reader, n) if n else b""
        return kind, conn_id, payload
    if kind in (_MSG_OPEN, _MSG_CLOSE):
        (conn_id,) = struct.unpack("!I", await _read_exact(reader, 4))
        return kind, conn_id, b""
    raise RuntimeError(f"bad kind {kind}")


@pytest.mark.asyncio
async def test_mux_open_ack_then_data_delivered() -> None:
    """Guest acks OPEN after dial; DATA reaches the TCP target."""
    received: asyncio.Queue[bytes] = asyncio.Queue()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.read(65536)
            await received.put(data)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handle, host="127.0.0.1", port=0)
    port = int(server.sockets[0].getsockname()[1])

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _MUX_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"EF_PORT": str(port), "PYTHONUNBUFFERED": "1"},
    )
    assert proc.stdin and proc.stdout
    try:
        conn_id = 7
        proc.stdin.write(_pack_open(conn_id))
        await proc.stdin.drain()

        kind, ack_id, _ = await asyncio.wait_for(_read_msg(proc.stdout), timeout=5)
        assert kind == _MSG_OPEN
        assert ack_id == conn_id

        payload = b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        proc.stdin.write(_pack_data(conn_id, payload))
        await proc.stdin.drain()

        got = await asyncio.wait_for(received.get(), timeout=5)
        assert got == payload

        proc.stdin.write(_pack_close(conn_id))
        await proc.stdin.drain()
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_mux_buffers_data_before_open() -> None:
    """DATA before OPEN must be buffered and flushed when the dial succeeds."""
    received: asyncio.Queue[bytes] = asyncio.Queue()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            data = await reader.read(65536)
            await received.put(data)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    probe = await asyncio.start_server(lambda r, w: None, host="127.0.0.1", port=0)
    port = int(probe.sockets[0].getsockname()[1])
    probe.close()
    await probe.wait_closed()

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _MUX_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"EF_PORT": str(port), "PYTHONUNBUFFERED": "1"},
    )
    assert proc.stdin and proc.stdout
    try:
        conn_id = 3
        payload = b"WS-HANDSHAKE"
        # Arrive before OPEN — guest has no sock yet and must buffer
        proc.stdin.write(_pack_data(conn_id, payload))
        await proc.stdin.drain()

        server = await asyncio.start_server(handle, host="127.0.0.1", port=port)

        proc.stdin.write(_pack_open(conn_id))
        await proc.stdin.drain()

        kind, ack_id, _ = await asyncio.wait_for(_read_msg(proc.stdout), timeout=5)
        assert kind == _MSG_OPEN
        assert ack_id == conn_id

        got = await asyncio.wait_for(received.get(), timeout=5)
        assert got == payload

        proc.stdin.write(_pack_close(conn_id))
        await proc.stdin.drain()
        server.close()
        await server.wait_closed()
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


@pytest.mark.asyncio
async def test_mux_open_fail_sends_close() -> None:
    """Failed dial yields CLOSE (no OPEN ack)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        _MUX_SCRIPT,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"EF_PORT": "1", "PYTHONUNBUFFERED": "1"},  # port 1: connection refused
    )
    assert proc.stdin and proc.stdout
    try:
        conn_id = 9
        proc.stdin.write(_pack_open(conn_id))
        await proc.stdin.drain()
        kind, cid, _ = await asyncio.wait_for(_read_msg(proc.stdout), timeout=5)
        assert kind == _MSG_CLOSE
        assert cid == conn_id
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
