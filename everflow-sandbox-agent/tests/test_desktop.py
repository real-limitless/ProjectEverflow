"""Unit tests for guest noVNC desktop ensure."""

from __future__ import annotations

import asyncio

import pytest

from app.desktop import (
    DESKTOP_NOVNC_PORT,
    DESKTOP_SCRIPT,
    DESKTOP_VNC_PORT,
    desktop_listening,
    ensure_guest_desktop,
    ensure_guest_desktop_for_proxy,
    reset_desktop_state_for_tests,
    schedule_ensure_guest_desktop,
)


@pytest.fixture(autouse=True)
def _clean_desktop_state() -> None:
    reset_desktop_state_for_tests()
    yield
    reset_desktop_state_for_tests()


@pytest.mark.asyncio
async def test_desktop_listening_requires_vnc_and_novnc() -> None:
    ports_ok = {DESKTOP_NOVNC_PORT: True, DESKTOP_VNC_PORT: False}

    async def exec_fn(name: str, cmd: str, args: list[str], **kwargs):  # noqa: ANN003
        assert cmd == "python3"
        src = args[1]
        for port, ok in ports_ok.items():
            if f",{port})" in src.replace(" ", ""):
                return (0, "", "") if ok else (1, "", "")
        return 1, "", ""

    assert await desktop_listening(exec_fn, "sb1") is False
    ports_ok[DESKTOP_VNC_PORT] = True
    assert await desktop_listening(exec_fn, "sb1") is True


@pytest.mark.asyncio
async def test_ensure_skips_start_when_stack_healthy() -> None:
    calls: list[str] = []

    async def exec_fn(name: str, cmd: str, args: list[str], **kwargs):  # noqa: ANN003
        calls.append(cmd)
        if cmd == "python3":
            return 0, "", ""
        return 1, "", "should not start"

    assert await ensure_guest_desktop(exec_fn, "sb1") is True
    assert DESKTOP_SCRIPT not in calls


@pytest.mark.asyncio
async def test_ensure_repairs_when_only_novnc_up() -> None:
    """websockify alone must not count as healthy — install + start should run."""
    open_ports = {DESKTOP_NOVNC_PORT}
    started = {"n": 0}

    async def exec_fn(name: str, cmd: str, args: list[str], **kwargs):  # noqa: ANN003
        if cmd == "python3":
            src = args[1]
            if "write_bytes" in src:
                return 0, "installed", ""
            for port in (DESKTOP_NOVNC_PORT, DESKTOP_VNC_PORT):
                # match connect_ex(('127.0.0.1',PORT)
                if f",{port})" in src.replace(" ", ""):
                    return (0, "", "") if port in open_ports else (1, "", "")
            return 1, "", ""
        if cmd == DESKTOP_SCRIPT:
            started["n"] += 1
            open_ports.add(DESKTOP_VNC_PORT)
            return 0, "everflow-desktop: noVNC listening\n", ""
        return 1, "", f"unexpected {cmd}"

    assert await ensure_guest_desktop(exec_fn, "sb1") is True
    assert started["n"] == 1
    assert DESKTOP_VNC_PORT in open_ports


@pytest.mark.asyncio
async def test_ensure_for_proxy_only_on_novnc_port() -> None:
    called = {"n": 0}

    async def exec_fn(name: str, cmd: str, args: list[str], **kwargs):  # noqa: ANN003
        called["n"] += 1
        return 0, "", ""

    await ensure_guest_desktop_for_proxy(exec_fn, "sb1", 5173)
    assert called["n"] == 0
    await ensure_guest_desktop_for_proxy(exec_fn, "sb1", DESKTOP_NOVNC_PORT)
    assert called["n"] >= 1


@pytest.mark.asyncio
async def test_schedule_ensure_runs_background() -> None:
    done = asyncio.Event()

    async def exec_fn(name: str, cmd: str, args: list[str], **kwargs):  # noqa: ANN003
        if cmd == "python3":
            done.set()
            return 0, "", ""
        return 1, "", ""

    schedule_ensure_guest_desktop(exec_fn, "sb1")
    await asyncio.wait_for(done.wait(), timeout=2)
