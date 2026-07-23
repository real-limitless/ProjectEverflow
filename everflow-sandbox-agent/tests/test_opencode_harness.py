"""Unit tests for OpenCode harness pack read/write (no OpenCode process required)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.opencode_harness import (
    apply_pack_to_workspace,
    apply_pack_via_backend,
    is_valid_slug,
    merge_opencode_json,
    parse_agent_markdown,
    read_pack_from_workspace,
    read_pack_via_backend,
    render_agent_markdown,
    render_skill_markdown,
)


class _FakeGuestBackend:
    """In-memory path tree emulating backend list_fs/read_fs/write_fs/exec."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _p(self, path: str) -> Path:
        p = path.lstrip("/")
        if p.startswith("workspace/"):
            p = p[len("workspace/") :]
        return self.root / p

    async def list_fs(self, name: str, path: str) -> list[dict]:
        t = self._p(path)
        if not t.exists():
            raise FileNotFoundError(path)
        out: list[dict] = []
        for c in sorted(t.iterdir()):
            out.append(
                {
                    "name": c.name,
                    "is_dir": c.is_dir(),
                    "path": str(c.relative_to(self.root)),
                    "size": c.stat().st_size if c.is_file() else None,
                }
            )
        return out

    async def read_fs(self, name: str, path: str) -> bytes:
        t = self._p(path)
        if not t.is_file():
            raise FileNotFoundError(path)
        return t.read_bytes()

    async def write_fs(self, name: str, path: str, content: bytes) -> None:
        t = self._p(path)
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_bytes(content)

    async def exec(self, name: str, cmd: str, args: list[str], **kwargs):  # noqa: ANN003
        import shutil

        if cmd == "rm" and args and args[0] == "-rf":
            t = self._p(args[1])
            if t.is_dir():
                shutil.rmtree(t)
            elif t.exists():
                t.unlink()
            return 0, "", ""
        return 1, "", "unknown"


def test_slug_validation() -> None:
    assert is_valid_slug("code-reviewer")
    assert is_valid_slug("build")
    assert not is_valid_slug("Code_Reviewer")
    assert not is_valid_slug("-bad")
    assert not is_valid_slug("bad--name")


def test_agent_markdown_roundtrip() -> None:
    agent = {
        "id": "code-reviewer",
        "description": "Reviews code for security",
        "mode": "subagent",
        "model": "anthropic/claude-sonnet-4",
        "prompt": "You are a careful code reviewer.\nFocus on security.",
        "permission": {"edit": "deny", "bash": "ask"},
        "modelsPreferred": ["anthropic/claude-sonnet-4", "openai/gpt-4.1"],
        "mcpIds": ["github"],
        "skillAllow": ["review-pr"],
    }
    md = render_agent_markdown(agent)
    assert md.startswith("---")
    assert "mode: subagent" in md
    assert "model: anthropic/claude-sonnet-4" in md
    parsed = parse_agent_markdown(md, slug="code-reviewer")
    assert parsed["id"] == "code-reviewer"
    assert parsed["mode"] == "subagent"
    assert parsed["model"] == "anthropic/claude-sonnet-4"
    assert "security" in parsed["prompt"].lower() or "reviewer" in parsed["prompt"].lower()
    assert parsed.get("permission", {}).get("edit") == "deny"
    assert parsed.get("modelsPreferred") == ["anthropic/claude-sonnet-4", "openai/gpt-4.1"]
    assert parsed.get("mcpIds") == ["github"]


def test_merge_opencode_json_preserves_server() -> None:
    existing = {
        "$schema": "https://opencode.ai/config.json",
        "server": {"port": 14100, "hostname": "127.0.0.1"},
        "mcp": {"old": {"type": "remote", "url": "https://example.com", "enabled": True}},
    }
    merged = merge_opencode_json(
        existing,
        mcp={
            "github": {"type": "remote", "url": "https://mcp.github.com", "enabled": True},
            "old": {"enabled": False},
        },
    )
    assert merged["server"]["port"] == 14100
    assert merged["mcp"]["github"]["url"] == "https://mcp.github.com"
    assert merged["mcp"]["old"]["enabled"] is False
    assert merged["mcp"]["old"]["url"] == "https://example.com"


def test_apply_and_read_pack(tmp_path: Path) -> None:
    # Seed server block like opencode_mgr would
    (tmp_path / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "server": {"port": 14101, "hostname": "127.0.0.1"},
            }
        ),
        encoding="utf-8",
    )

    result = apply_pack_to_workspace(
        tmp_path,
        {
            "agents": [
                {
                    "id": "docs-writer",
                    "description": "Writes docs",
                    "mode": "subagent",
                    "model": "openai/gpt-4.1",
                    "prompt": "Write clear documentation.",
                    "permission": {"bash": "deny"},
                }
            ],
            "skills": [
                {
                    "id": "git-release",
                    "description": "Prepare releases",
                    "body": "## Steps\n- draft notes\n",
                }
            ],
            "mcp": {
                "github": {
                    "type": "remote",
                    "url": "https://api.githubcopilot.com/mcp/",
                    "enabled": True,
                }
            },
        },
    )

    assert "docs-writer" in result["written"]["agents"]
    assert "git-release" in result["written"]["skills"]

    agent_path = tmp_path / ".opencode" / "agents" / "docs-writer.md"
    assert agent_path.is_file()
    skill_path = tmp_path / ".opencode" / "skills" / "git-release" / "SKILL.md"
    assert skill_path.is_file()

    oc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert oc["server"]["port"] == 14101
    assert oc["mcp"]["github"]["enabled"] is True

    pack = read_pack_from_workspace(tmp_path)
    assert len(pack["agents"]) == 1
    assert pack["agents"][0]["id"] == "docs-writer"
    assert pack["skills"][0]["id"] == "git-release"
    assert "github" in pack["mcp"]
    assert "docs-writer" in pack["manifest"]["managed_agents"]


def test_remove_agent(tmp_path: Path) -> None:
    apply_pack_to_workspace(
        tmp_path,
        {
            "agents": [
                {
                    "id": "tmp-agent",
                    "description": "temp",
                    "mode": "all",
                    "prompt": "hi",
                }
            ]
        },
    )
    assert (tmp_path / ".opencode" / "agents" / "tmp-agent.md").is_file()
    apply_pack_to_workspace(tmp_path, {"remove_agents": ["tmp-agent"]})
    assert not (tmp_path / ".opencode" / "agents" / "tmp-agent.md").is_file()


def test_invalid_agent_slug_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        apply_pack_to_workspace(
            tmp_path,
            {"agents": [{"id": "Bad Name", "description": "x", "prompt": "y"}]},
        )


def test_skill_render_has_frontmatter() -> None:
    md = render_skill_markdown(
        {"id": "fix", "description": "Diagnose bugs", "body": "Find the root cause."}
    )
    assert "name: fix" in md
    assert "Diagnose bugs" in md
    assert "Find the root cause." in md


def test_guest_backend_apply_and_read(tmp_path: Path) -> None:
    """Named-volume / guest-only sandboxes use backend FS instead of host Path."""
    import asyncio

    (tmp_path / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "server": {"port": 14102, "hostname": "127.0.0.1"},
            }
        ),
        encoding="utf-8",
    )
    backend = _FakeGuestBackend(tmp_path)

    async def _run() -> None:
        result = await apply_pack_via_backend(
            backend,
            "sb-guest",
            {
                "agents": [
                    {
                        "id": "security-reviewer",
                        "description": "Security review",
                        "mode": "subagent",
                        "prompt": "Review for security issues.",
                    }
                ],
                "skills": [
                    {
                        "id": "pr-review",
                        "description": "PR review",
                        "body": "Check the diff.",
                    }
                ],
                "mcp": {
                    "github": {
                        "type": "remote",
                        "url": "https://example.com/mcp",
                        "enabled": True,
                    }
                },
            },
        )
        assert "security-reviewer" in result["written"]["agents"]
        assert "pr-review" in result["written"]["skills"]
        assert (tmp_path / ".opencode" / "agents" / "security-reviewer.md").is_file()

        pack = await read_pack_via_backend(backend, "sb-guest")
        assert any(a["id"] == "security-reviewer" for a in pack["agents"])
        assert any(s["id"] == "pr-review" for s in pack["skills"])
        assert pack["mcp"]["github"]["enabled"] is True
        # Server block preserved when merging MCP
        oc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
        assert oc["server"]["port"] == 14102

    asyncio.run(_run())
