"""Unit tests for Everflow MCP config injection."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.everflow_mcp_inject import (
    MCP_PACKAGE_STAMP_REL,
    agent_mcp_fingerprint,
    build_everflow_mcp_config,
    ensure_everflow_mcp_package,
    merge_opencode_mcp,
    write_everflow_mcp_host,
)


def _write_agent_package(root: Path, marker: str = "# stub\n") -> None:
    for rel in (
        "pyproject.toml",
        "README.md",
        "src/everflow_mcp/__init__.py",
        "src/everflow_mcp/__main__.py",
        "src/everflow_mcp/client.py",
        "src/everflow_mcp/server.py",
    ):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        # server.py carries the content marker so fingerprints change on upgrades
        body = f"{marker}{rel}\n" if rel.endswith("server.py") else marker
        p.write_text(body, encoding="utf-8")


def test_merge_preserves_other_mcp_and_server() -> None:
    existing = {
        "$schema": "https://opencode.ai/config.json",
        "server": {"port": 4096},
        "mcp": {"other": {"type": "remote", "url": "https://example.com"}},
    }
    entry = build_everflow_mcp_config(
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_test",
        project_id="11111111-1111-1111-1111-111111111111",
    )
    merged = merge_opencode_mcp(existing, entry)
    assert merged["server"]["port"] == 4096
    assert "other" in merged["mcp"]
    assert merged["mcp"]["everflow"]["type"] == "local"
    assert merged["mcp"]["everflow"]["command"] == ["python3", "-m", "everflow_mcp"]
    assert merged["mcp"]["everflow"]["environment"]["EVERFLOW_TOKEN"] == "ef_sbox_test"


def test_legacy_binary_name_normalizes_to_module() -> None:
    cfg = build_everflow_mcp_config(
        api_url="http://127.0.0.1:18765",
        token="t",
        project_id="33333333-3333-3333-3333-333333333333",
        command="everflow-mcp",
    )
    assert cfg["command"] == ["python3", "-m", "everflow_mcp"]


def test_write_host_creates_files(tmp_path: Path) -> None:
    status = write_everflow_mcp_host(
        tmp_path,
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_abc",
        project_id="22222222-2222-2222-2222-222222222222",
    )
    assert status["configured"] is True
    assert status["command"] == ["python3", "-m", "everflow_mcp"]
    env = (tmp_path / ".everflow" / "mcp.env").read_text(encoding="utf-8")
    assert "EVERFLOW_TOKEN" in env
    oc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "everflow" in oc["mcp"]
    assert oc["mcp"]["everflow"]["command"] == ["python3", "-m", "everflow_mcp"]


def test_agent_mcp_fingerprint_stable(tmp_path: Path) -> None:
    root = tmp_path / "mcp"
    _write_agent_package(root)
    a = agent_mcp_fingerprint(root)
    b = agent_mcp_fingerprint(root)
    assert a is not None and a == b
    (root / "src/everflow_mcp/server.py").write_text("# changed\n", encoding="utf-8")
    assert agent_mcp_fingerprint(root) != a


@pytest.mark.asyncio
async def test_ensure_package_skips_when_stamp_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "mcp"
    _write_agent_package(root)
    monkeypatch.setattr("app.everflow_mcp_inject.AGENT_MCP_ROOT", root)
    fp = agent_mcp_fingerprint(root)
    assert fp is not None

    async def _read(_backend: object, _name: str, path: str) -> str | None:
        if path == MCP_PACKAGE_STAMP_REL:
            return fp + "\n"
        return None

    monkeypatch.setattr("app.everflow_mcp_inject._guest_read_text", _read)

    backend = AsyncMock()
    backend.exec = AsyncMock(return_value=(0, "0.2.0\n", ""))
    status = await ensure_everflow_mcp_package(backend, "ef-test")
    assert status["installed"] is True
    assert status["source"] == "existing"
    assert status.get("upgraded") is False
    assert backend.exec.await_count == 1


@pytest.mark.asyncio
async def test_ensure_package_vendors_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "mcp"
    _write_agent_package(root)
    monkeypatch.setattr("app.everflow_mcp_inject.AGENT_MCP_ROOT", root)

    writes: list[str] = []

    async def _write(_backend: object, _name: str, path: str, _body: str) -> None:
        writes.append(path)

    async def _read(_backend: object, _name: str, path: str) -> str | None:
        return None

    monkeypatch.setattr("app.everflow_mcp_inject._guest_write_text", _write)
    monkeypatch.setattr("app.everflow_mcp_inject._guest_read_text", _read)

    backend = AsyncMock()
    backend.exec = AsyncMock(
        side_effect=[
            (1, "", "ModuleNotFoundError"),
            (
                0,
                "/usr/local/lib/python3.12/site-packages/everflow_mcp/__init__.py\n0.2.0\n",
                "",
            ),
        ]
    )
    status = await ensure_everflow_mcp_package(backend, "ef-test")
    assert status["installed"] is True
    assert status["source"] == "vendor"
    assert any("vendor/everflow-mcp" in w for w in writes)
    assert any(w == MCP_PACKAGE_STAMP_REL for w in writes)
    assert backend.exec.await_count == 2


@pytest.mark.asyncio
async def test_ensure_package_upgrades_when_importable_but_stamp_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Guest has old prebaked everflow_mcp; agent has newer sources → reinstall."""
    root = tmp_path / "mcp"
    _write_agent_package(root, marker="# new tools\n")
    monkeypatch.setattr("app.everflow_mcp_inject.AGENT_MCP_ROOT", root)

    writes: list[str] = []

    async def _write(_backend: object, _name: str, path: str, body: str) -> None:
        writes.append(path)

    async def _read(_backend: object, _name: str, path: str) -> str | None:
        if path == MCP_PACKAGE_STAMP_REL:
            return "deadbeef_old_stamp\n"
        return None

    monkeypatch.setattr("app.everflow_mcp_inject._guest_write_text", _write)
    monkeypatch.setattr("app.everflow_mcp_inject._guest_read_text", _read)

    backend = AsyncMock()
    backend.exec = AsyncMock(
        side_effect=[
            (0, "0.1.0\n", ""),  # import works but package is stale
            (
                0,
                "/usr/local/lib/python3.12/site-packages/everflow_mcp/__init__.py\n0.2.0\n",
                "",
            ),
        ]
    )
    status = await ensure_everflow_mcp_package(backend, "ef-test")
    assert status["installed"] is True
    assert status["source"] == "upgraded"
    assert status.get("upgraded") is True
    assert any(w == MCP_PACKAGE_STAMP_REL for w in writes)
    install_call = backend.exec.await_args_list[1]
    assert "force-reinstall" in str(install_call)
