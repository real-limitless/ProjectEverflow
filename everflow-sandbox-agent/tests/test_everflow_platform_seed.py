"""Tests for first-party Everflow platform skill/agent seed pack."""

from pathlib import Path

from app.everflow_mcp_inject import write_everflow_mcp_host
from app.everflow_platform_seed import (
    PLATFORM_AGENT_ID,
    PLATFORM_SKILL_IDS,
    build_platform_seed_pack,
    seed_platform_pack_host,
)


def test_build_platform_seed_pack_has_agent_and_skills() -> None:
    pack = build_platform_seed_pack()
    assert pack["agents"][0]["id"] == PLATFORM_AGENT_ID
    assert pack["agents"][0]["mode"] == "primary"
    assert "knowledge_search" in pack["agents"][0]["prompt"]
    skill_ids = {s["id"] for s in pack["skills"]}
    assert skill_ids == set(PLATFORM_SKILL_IDS)
    for skill in pack["skills"]:
        assert "---" in skill["content"]
        assert skill["id"] in skill["content"] or "name:" in skill["content"]


def test_seed_platform_pack_host_writes_files(tmp_path: Path) -> None:
    status = seed_platform_pack_host(tmp_path)
    assert status["seeded"] is True
    assert PLATFORM_AGENT_ID in (status.get("written_agents") or [])
    agent_md = tmp_path / ".opencode" / "agents" / f"{PLATFORM_AGENT_ID}.md"
    assert agent_md.is_file()
    text = agent_md.read_text(encoding="utf-8")
    assert "mode: primary" in text
    assert "Everflow" in text
    for sid in PLATFORM_SKILL_IDS:
        skill_path = tmp_path / ".opencode" / "skills" / sid / "SKILL.md"
        assert skill_path.is_file(), sid
        assert skill_path.read_text(encoding="utf-8").strip()


def test_write_everflow_mcp_host_seeds_platform(tmp_path: Path) -> None:
    status = write_everflow_mcp_host(
        tmp_path,
        api_url="http://127.0.0.1:18765",
        token="ef_sbox_test",
        project_id="22222222-2222-2222-2222-222222222222",
    )
    assert status["configured"] is True
    seed = status.get("platform_seed") or {}
    assert seed.get("seeded") is True
    assert (tmp_path / ".opencode" / "agents" / "everflow.md").is_file()
    assert (tmp_path / ".opencode" / "skills" / "everflow-jobs" / "SKILL.md").is_file()
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "everflow-knowledge" in agents
    assert "everflow" in agents.lower()
