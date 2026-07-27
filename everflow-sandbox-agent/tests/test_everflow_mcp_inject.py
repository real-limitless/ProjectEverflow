"""Unit tests for Everflow MCP config injection."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.everflow_mcp_inject import (
    KNOWLEDGE_POLICY_MARKER,
    MCP_PACKAGE_STAMP_REL,
    PLATFORM_PLAYBOOK_MARKER,
    agent_mcp_fingerprint,
    build_everflow_mcp_config,
    ensure_everflow_mcp_package,
    existing_token_needs_refresh,
    mcp_identity_matches,
    merge_knowledge_policy_markdown,
    merge_opencode_mcp,
    parse_mcp_env,
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
    assert status.get("credentials_written") is True
    assert status.get("reused") is False
    assert status["command"] == ["python3", "-m", "everflow_mcp"]
    env = (tmp_path / ".everflow" / "mcp.env").read_text(encoding="utf-8")
    assert "EVERFLOW_TOKEN" in env
    oc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "everflow" in oc["mcp"]
    assert oc["mcp"]["everflow"]["command"] == ["python3", "-m", "everflow_mcp"]
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert PLATFORM_PLAYBOOK_MARKER in agents
    assert "knowledge_search" in agents
    assert "create_job" in agents
    assert "Tool routing" in agents


def test_parse_mcp_env_and_identity() -> None:
    parsed = parse_mcp_env(
        'EVERFLOW_API_URL="http://127.0.0.1:18765"\n'
        'EVERFLOW_TOKEN="ef_sbox_x"\n'
        'EVERFLOW_PROJECT_ID="22222222-2222-2222-2222-222222222222"\n'
    )
    assert parsed["EVERFLOW_API_URL"] == "http://127.0.0.1:18765"
    assert mcp_identity_matches(
        parsed,
        api_url="http://127.0.0.1:18765/",
        project_id="22222222-2222-2222-2222-222222222222",
    )
    assert not mcp_identity_matches(
        parsed,
        api_url="http://127.0.0.1:18765",
        project_id="33333333-3333-3333-3333-333333333333",
    )


def test_write_host_reuses_identity_without_token_churn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = "22222222-2222-2222-2222-222222222222"
    # Avoid real HTTP probe; treat stored token as still valid.
    monkeypatch.setattr(
        "app.everflow_mcp_inject.probe_sandbox_token_sync",
        lambda **_kw: True,
    )
    first = write_everflow_mcp_host(
        tmp_path,
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_first",
        project_id=pid,
    )
    assert first["credentials_written"] is True
    env1 = (tmp_path / ".everflow" / "mcp.env").read_text(encoding="utf-8")

    second = write_everflow_mcp_host(
        tmp_path,
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_second_unused",
        project_id=pid,
        force_credentials=False,
    )
    assert second["configured"] is True
    assert second["reused"] is True
    assert second["credentials_written"] is False
    env2 = (tmp_path / ".everflow" / "mcp.env").read_text(encoding="utf-8")
    assert env2 == env1
    assert "ef_sbox_first" in env2
    assert "ef_sbox_second_unused" not in env2

    forced = write_everflow_mcp_host(
        tmp_path,
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_forced",
        project_id=pid,
        force_credentials=True,
    )
    assert forced["credentials_written"] is True
    assert forced["reused"] is False
    env3 = (tmp_path / ".everflow" / "mcp.env").read_text(encoding="utf-8")
    assert "ef_sbox_forced" in env3


def test_write_host_rewrites_when_token_probe_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expired/invalid guest token must be replaced on ensure (recovery path)."""
    pid = "22222222-2222-2222-2222-222222222222"
    monkeypatch.setattr(
        "app.everflow_mcp_inject.probe_sandbox_token_sync",
        lambda **_kw: True,
    )
    write_everflow_mcp_host(
        tmp_path,
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_old",
        project_id=pid,
    )
    monkeypatch.setattr(
        "app.everflow_mcp_inject.probe_sandbox_token_sync",
        lambda **_kw: False,  # 401/403
    )
    status = write_everflow_mcp_host(
        tmp_path,
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_new",
        project_id=pid,
        force_credentials=False,
        probe_api_url="http://backend:8000",
    )
    assert status["credentials_written"] is True
    assert status.get("reused") is False
    env = (tmp_path / ".everflow" / "mcp.env").read_text(encoding="utf-8")
    assert "ef_sbox_new" in env
    assert "ef_sbox_old" not in env


def test_existing_token_needs_refresh_only_on_auth_failure() -> None:
    env = {
        "EVERFLOW_API_URL": "http://127.0.0.1:18765",
        "EVERFLOW_TOKEN": "ef_sbox_x",
        "EVERFLOW_PROJECT_ID": "22222222-2222-2222-2222-222222222222",
    }
    pid = "22222222-2222-2222-2222-222222222222"
    assert (
        existing_token_needs_refresh(
            env, api_url="http://127.0.0.1:18765", project_id=pid, probe=False
        )
        is True
    )
    assert (
        existing_token_needs_refresh(
            env, api_url="http://127.0.0.1:18765", project_id=pid, probe=True
        )
        is False
    )
    # Missing token with matching identity → refresh
    no_tok = {**env, "EVERFLOW_TOKEN": ""}
    assert (
        existing_token_needs_refresh(
            no_tok, api_url="http://127.0.0.1:18765", project_id=pid, probe=True
        )
        is True
    )
    # Different project → not a refresh candidate (identity rewrite path)
    assert (
        existing_token_needs_refresh(
            env,
            api_url="http://127.0.0.1:18765",
            project_id="33333333-3333-3333-3333-333333333333",
            probe=False,
        )
        is False
    )


def test_merge_knowledge_policy_idempotent() -> None:
    once = merge_knowledge_policy_markdown("")
    twice = merge_knowledge_policy_markdown(once)
    assert twice.count(PLATFORM_PLAYBOOK_MARKER) == 1
    assert KNOWLEDGE_POLICY_MARKER not in twice
    with_user = merge_knowledge_policy_markdown("# My project\n\nHello.\n")
    assert with_user.startswith("# My project")
    assert PLATFORM_PLAYBOOK_MARKER in with_user
    assert "create_job" in with_user


def test_merge_upgrades_legacy_knowledge_policy_marker() -> None:
    """Old workspaces with knowledge-only block get the full playbook once."""
    legacy = (
        "# My app\n\n"
        f"{KNOWLEDGE_POLICY_MARKER}\n"
        "## Everflow project knowledge\n\n"
        "Old short policy.\n"
    )
    upgraded = merge_knowledge_policy_markdown(legacy)
    assert upgraded.startswith("# My app")
    assert PLATFORM_PLAYBOOK_MARKER in upgraded
    assert upgraded.count(PLATFORM_PLAYBOOK_MARKER) == 1
    assert KNOWLEDGE_POLICY_MARKER not in upgraded
    assert "Old short policy" not in upgraded
    assert "create_job" in upgraded
    # Second merge stays single-block
    again = merge_knowledge_policy_markdown(upgraded)
    assert again.count(PLATFORM_PLAYBOOK_MARKER) == 1


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
