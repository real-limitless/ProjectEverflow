"""Seed first-party Everflow OpenCode skills + agent into project workspaces.

Applied on OpenCode ensure (alongside AGENTS.md / everflow MCP) so every project
gets platform procedures without marketplace install. Skills are also listed in
the marketplace catalog for discoverability / reinstall.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PLATFORM_DATA = Path(__file__).resolve().parent / "data" / "platform"
PLATFORM_SKILL_IDS = (
    "everflow-knowledge",
    "everflow-jobs",
    "everflow-browser",
)
PLATFORM_AGENT_ID = "everflow"

EVERFLOW_AGENT_PROMPT = """\
You are the **Everflow** platform agent for this project sandbox.

Help the user operate Project Everflow for *this* bound project: Knowledge, Jobs,
browser mode, tests, studio agents, HTTP tools, and workspace coding when needed.

## Priorities

1. Prefer **everflow MCP** tools over inventing UI click-paths or raw platform REST.
2. Project docs/secrets → `knowledge_search` (not MCP resources).
3. Long-running servers → `create_job` + `get_job_logs` (not blocking shell).
4. Browser automation → Playwright MCP + `browser_status` / `browser_set_mode`.
5. App code changes → normal file/edit tools in the workspace.

## Skills

Use OpenCode skills when available: `everflow-knowledge`, `everflow-jobs`,
`everflow-browser` for step-by-step procedures.

## Scope

- Stay on the bound project (`whoami` / `get_project` if unsure).
- You are not operating the Everflow monorepo control plane.
- If a tool fails (sandbox stopped, missing Playwright MCP, empty knowledge),
  explain clearly and suggest the next concrete step.
- Default coding agent is still **build**; you specialize in Everflow platform ops
  while remaining able to edit code when the user asks.
"""


def _read_skill_file(skill_id: str) -> str:
    path = PLATFORM_DATA / "skills" / skill_id / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"platform skill missing: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    return text


def build_platform_seed_pack() -> dict[str, Any]:
    """Harness pack: everflow agent + first-party skills."""
    skills: list[dict[str, Any]] = []
    for sid in PLATFORM_SKILL_IDS:
        skills.append(
            {
                "id": sid,
                "name": sid,
                "content": _read_skill_file(sid),
            }
        )

    agent = {
        "id": PLATFORM_AGENT_ID,
        "name": PLATFORM_AGENT_ID,
        "description": (
            "Project Everflow platform ops — knowledge, jobs, browser mode, "
            "tests, and studio tools for this sandbox project"
        ),
        "mode": "primary",
        "color": "accent",
        "mcpIds": ["everflow"],
        "skillAllow": list(PLATFORM_SKILL_IDS),
        "prompt": EVERFLOW_AGENT_PROMPT.strip() + "\n",
    }

    return {
        "agents": [agent],
        "skills": skills,
        "manifest": {
            "everflow_platform_seed": True,
            "everflow_platform_skills": list(PLATFORM_SKILL_IDS),
            "everflow_platform_agent": PLATFORM_AGENT_ID,
        },
    }


def seed_platform_pack_host(workspace: Path) -> dict[str, Any]:
    """Write platform skills + everflow agent into a host-accessible workspace."""
    from app.opencode_harness import apply_pack_to_workspace

    pack = build_platform_seed_pack()
    try:
        result = apply_pack_to_workspace(
            Path(workspace),
            pack,
            replace_managed_agents=False,
            replace_managed_skills=False,
        )
        written = result.get("written") if isinstance(result.get("written"), dict) else {}
        logger.info(
            "everflow platform seed host agents=%s skills=%s",
            written.get("agents"),
            written.get("skills"),
        )
        return {
            "seeded": True,
            "mode": "host",
            "written_agents": written.get("agents") or [],
            "written_skills": written.get("skills") or [],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("everflow platform seed host failed: %s", exc)
        return {"seeded": False, "mode": "host", "error": str(exc)}


async def seed_platform_pack_guest(backend: Any, sandbox_name: str) -> dict[str, Any]:
    """Write platform skills + everflow agent into the guest workspace."""
    from app.opencode_harness import apply_pack_via_backend

    pack = build_platform_seed_pack()
    try:
        result = await apply_pack_via_backend(
            backend,
            sandbox_name,
            pack,
            replace_managed_agents=False,
            replace_managed_skills=False,
        )
        written = result.get("written") if isinstance(result.get("written"), dict) else {}
        logger.info(
            "everflow platform seed guest name=%s agents=%s skills=%s",
            sandbox_name,
            written.get("agents"),
            written.get("skills"),
        )
        return {
            "seeded": True,
            "mode": "guest",
            "written_agents": written.get("agents") or [],
            "written_skills": written.get("skills") or [],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "everflow platform seed guest failed name=%s: %s", sandbox_name, exc
        )
        return {"seeded": False, "mode": "guest", "error": str(exc)}
