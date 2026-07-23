"""Unit tests for Everflow MCP config injection."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.everflow_mcp_inject import (
    build_everflow_mcp_config,
    ensure_everflow_mcp_package,
    merge_opencode_mcp,
    write_everflow_mcp_host,
)


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


@pytest.mark.asyncio
async def test_ensure_package_skips_when_importable() -> None:
    backend = AsyncMock()
    backend.exec = AsyncMock(return_value=(0, "ok\n", ""))
    status = await ensure_everflow_mcp_package(backend, "ef-test")
    assert status["installed"] is True
    assert status["source"] == "existing"
    assert backend.exec.await_count == 1


@pytest.mark.asyncio
async def test_ensure_package_vendors_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Minimal agent package tree
    root = tmp_path / "mcp"
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
        p.write_text("# stub\n", encoding="utf-8")
    monkeypatch.setattr("app.everflow_mcp_inject.AGENT_MCP_ROOT", root)

    writes: list[str] = []

    async def _write(_backend: object, _name: str, path: str, _body: str) -> None:
        writes.append(path)

    monkeypatch.setattr("app.everflow_mcp_inject._guest_write_text", _write)

    backend = AsyncMock()
    backend.exec = AsyncMock(
        side_effect=[
            (1, "", "ModuleNotFoundError"),
            (0, "/usr/local/lib/python3.12/site-packages/everflow_mcp/__init__.py\n", ""),
        ]
    )
    status = await ensure_everflow_mcp_package(backend, "ef-test")
    assert status["installed"] is True
    assert status["source"] == "vendor"
    assert any("vendor/everflow-mcp" in w for w in writes)
    assert backend.exec.await_count == 2
