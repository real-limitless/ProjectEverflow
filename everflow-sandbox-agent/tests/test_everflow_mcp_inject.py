"""Unit tests for Everflow MCP config injection."""

import json
from pathlib import Path

from app.everflow_mcp_inject import (
    build_everflow_mcp_config,
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
    assert merged["mcp"]["everflow"]["command"] == ["everflow-mcp"]
    assert merged["mcp"]["everflow"]["environment"]["EVERFLOW_TOKEN"] == "ef_sbox_test"


def test_write_host_creates_files(tmp_path: Path) -> None:
    status = write_everflow_mcp_host(
        tmp_path,
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_abc",
        project_id="22222222-2222-2222-2222-222222222222",
    )
    assert status["configured"] is True
    env = (tmp_path / ".everflow" / "mcp.env").read_text(encoding="utf-8")
    assert "EVERFLOW_TOKEN" in env
    oc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "everflow" in oc["mcp"]
