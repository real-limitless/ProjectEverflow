"""Unit tests for API reverse-tunnel DATA buffering / OPEN ordering."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api_tunnel import ApiTunnelManager, _ApiTunnel


@dataclass
class _FakeWriter:
    chunks: list[bytes] = field(default_factory=list)
    closed: bool = False

    def write(self, data: bytes) -> None:
        self.chunks.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


@pytest.mark.asyncio
async def test_handle_line_buffers_data_until_open_dial(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATA before dial completes must not be dropped (HTTP client race)."""
    mgr = ApiTunnelManager()
    sink = MagicMock()
    sink.write = AsyncMock()
    tunnel = _ApiTunnel(
        sandbox_name="ef-test",
        listen_port=18765,
        target_host="backend",
        target_port=8000,
        handle=None,
        sink=sink,
    )

    writer = _FakeWriter()
    reader = MagicMock()
    # Keep pump from spinning forever: first read returns empty → exit.
    reader.read = AsyncMock(return_value=b"")

    async def fake_open_connection(host: str, port: int) -> tuple[Any, _FakeWriter]:
        assert host == "backend"
        assert port == 8000
        # Simulate concurrent DATA while dial is "in flight" via pending path.
        return reader, writer

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    # Early DATA before OPEN (should buffer)
    early = b"GET /api/v1/health HTTP/1.1\r\nHost: x\r\n\r\n"
    await mgr._handle_line(
        tunnel,
        f"DATA 1 {base64.b64encode(early).decode('ascii')}",
    )
    assert 1 in tunnel.pending_data
    assert writer.chunks == []

    await mgr._handle_line(tunnel, "OPEN 1")
    # Dial done + pending flushed
    assert tunnel.conns[1] is writer
    assert 1 not in tunnel.pending_data
    assert b"".join(writer.chunks) == early


@pytest.mark.asyncio
async def test_handle_open_awaited_serializes_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """OPEN must be awaited so subsequent DATA sees the writer."""
    mgr = ApiTunnelManager()
    sink = MagicMock()
    sink.write = AsyncMock()
    tunnel = _ApiTunnel(
        sandbox_name="ef-test",
        listen_port=18765,
        target_host="backend",
        target_port=8000,
        handle=None,
        sink=sink,
    )
    writer = _FakeWriter()
    reader = MagicMock()
    # Hang on host→guest pump so it does not CLOSE the conn before DATA arrives.
    hang = asyncio.Event()

    async def _hang_read(_n: int = 65536) -> bytes:
        await hang.wait()
        return b""

    reader.read = _hang_read

    dial_started = asyncio.Event()
    allow_dial = asyncio.Event()

    async def slow_open(host: str, port: int) -> tuple[Any, _FakeWriter]:
        dial_started.set()
        await allow_dial.wait()
        return reader, writer

    monkeypatch.setattr(asyncio, "open_connection", slow_open)

    async def open_then_data() -> None:
        # Sequential path used by reader: await OPEN, then DATA
        open_task = asyncio.create_task(mgr._handle_line(tunnel, "OPEN 7"))
        await dial_started.wait()
        allow_dial.set()
        await open_task
        body = b"hello"
        await mgr._handle_line(
            tunnel,
            f"DATA 7 {base64.b64encode(body).decode('ascii')}",
        )

    await open_then_data()
    assert b"".join(writer.chunks) == b"hello"
    hang.set()
