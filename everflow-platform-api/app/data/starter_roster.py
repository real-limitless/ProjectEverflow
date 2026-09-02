"""Starter company roster: teams, seats, OpenCode agent specs, constitution.

Source of truth for the default org chart (Floor → Product / Eng / DevOps / QA
plus a Services lane). Permissions are deny-by-default; only listed tools are open.
"""

from __future__ import annotations

from typing import Any, Literal

SeatKind = Literal["human", "bot"]
Lane = Literal["line", "services"]

DEFAULT_CONSTITUTION_MD = """# Project constitution

This file is project law. Every seat (human or bot) must read it before acting.

## Purpose

Ship software as a small company: Product briefs, Eng builds and reviews,
DevOps deploys with confirm, QA reports. The channel is the audit log.

## Rules

1. One job per seat. If you need two jobs, make two seats.
2. Deny by default. OpenCode frontmatter lists what is *allowed*.
3. Memory is scoped (seat / team / project / org). No global soup.
4. A bot may message peers on the bus. It may not impersonate them.
5. A bot that can deploy cannot also be the only reviewer.
6. Every bot has an owner human and a kill switch.
7. `ask_human` walks `reports_to`. Never dump approvals to a general channel.
8. Eng.Build owns the worktree. Eng.Review is read-only on the same tree.
9. Floor compiles runs. Floor does not write application code or deploy.
10. Confirm on deploy, merge, and delete.

## Surfaces

- Room — channels, threads, run cards
- Harness — the OpenCode session bound to a seat
- Chart — living org tree; reporting lines are permission lines
"""

# OpenCode tool keys used in seat permission maps.
_READ = {"read": "allow", "glob": "allow", "grep": "allow"}
_NO_WRITE = {"edit": "deny", "bash": "deny"}
_PLAN = {**_READ, **_NO_WRITE, "webfetch": "allow", "websearch": "allow", "task": "deny"}
_BUILD = {
    **_READ,
    "edit": "allow",
    "bash": "allow",
    "todowrite": "allow",
    "lsp": "allow",
    "task": "deny",
}
_REVIEW = {**_READ, "lsp": "allow", "edit": "deny", "bash": "deny", "task": "deny"}
_DEVOPS = {
    **_READ,
    "edit": "deny",
    "bash": "ask",
    "skill": "allow",
    "task": "deny",
}
_QA = {**_READ, "edit": "deny", "bash": "ask", "webfetch": "allow", "task": "deny"}
_SCOUT = {**_READ, **_NO_WRITE, "webfetch": "allow", "task": "deny"}
_DOCS = {**_READ, "edit": "ask", "bash": "deny", "task": "deny"}
_SEC = {**_READ, **_NO_WRITE, "task": "deny"}
_SCRIBE = {"read": "allow", "edit": "deny", "bash": "deny", "task": "deny"}
_FLOOR = {**_READ, **_NO_WRITE, "task": "deny", "webfetch": "deny"}

STARTER_TEAMS: list[dict[str, Any]] = [
    {
        "slug": "eng",
        "name": "Eng",
        "mention": "eng",
        "lane": "line",
        "description": "Build and review. @eng fans out to Eng.Build and Eng.Review.",
    },
    {
        "slug": "services",
        "name": "Services",
        "mention": "services",
        "lane": "services",
        "description": "Shared specialists — Scout, Docs, Sec, Scribe. Not fake reports.",
    },
]

# reports_to is a seat slug. team is a team slug or None (reports to Floor / Board).
STARTER_SEATS: list[dict[str, Any]] = [
    {
        "slug": "you",
        "name": "You / Board",
        "kind": "human",
        "role": "board",
        "lane": "line",
        "team": None,
        "reports_to": None,
        "agent_slug": None,
        "is_conductor": False,
        "worktree_path": None,
        "permission": {},
        "tools": [],
        "prompt": "",
        "description": "Approve deploy/merge. Remove any seat.",
    },
    {
        "slug": "floor",
        "name": "Floor",
        "kind": "bot",
        "role": "conductor",
        "lane": "line",
        "team": None,
        "reports_to": "you",
        "agent_slug": "floor",
        "is_conductor": True,
        "worktree_path": None,
        "permission": _FLOOR,
        "tools": ["read", "grep", "glob"],
        "prompt": (
            "You are Floor, the project conductor. Compile human sentences in the room "
            "into run graphs. Route work on the bus (message, handoff, depend_on, ask_human). "
            "Never edit application code. Never deploy. Never impersonate another seat."
        ),
        "description": "Compiles human sentences into run graphs. Never ships code.",
    },
    {
        "slug": "product",
        "name": "Product",
        "kind": "bot",
        "role": "product",
        "lane": "line",
        "team": None,
        "reports_to": "floor",
        "agent_slug": "product",
        "is_conductor": False,
        "worktree_path": None,
        "permission": _PLAN,
        "tools": ["read", "grep", "webfetch", "websearch"],
        "prompt": (
            "You are Product. Turn channel talk into a brief and an acceptance list. "
            "Other seats must satisfy your acceptance. You may not edit files or write via bash."
        ),
        "description": "Turns channel talk into a brief + acceptance list.",
    },
    {
        "slug": "eng-build",
        "name": "Eng.Build",
        "kind": "bot",
        "role": "build",
        "lane": "line",
        "team": "eng",
        "reports_to": "floor",
        "agent_slug": "eng-build",
        "is_conductor": False,
        "worktree_path": ".everflow/worktrees/eng-build",
        "permission": _BUILD,
        "tools": ["read", "edit", "bash", "grep", "glob", "lsp", "todowrite"],
        "prompt": (
            "You are Eng.Build. Own the project worktree at .everflow/worktrees/eng-build. "
            "Implement against Product's acceptance. Do not deploy to production."
        ),
        "description": "Owns a worktree. Implements against Product acceptance.",
    },
    {
        "slug": "eng-review",
        "name": "Eng.Review",
        "kind": "bot",
        "role": "review",
        "lane": "line",
        "team": "eng",
        "reports_to": "floor",
        "agent_slug": "eng-review",
        "is_conductor": False,
        "worktree_path": ".everflow/worktrees/eng-build",
        "permission": _REVIEW,
        "tools": ["read", "grep", "lsp"],
        "prompt": (
            "You are Eng.Review. Read-only on Eng.Build's worktree. Adversarial pass. "
            "You may block the merge gate. You may not edit files."
        ),
        "description": "Adversarial pass. Can block the gate. No edit.",
    },
    {
        "slug": "devops",
        "name": "DevOps",
        "kind": "bot",
        "role": "devops",
        "lane": "line",
        "team": None,
        "reports_to": "floor",
        "agent_slug": "devops",
        "is_conductor": False,
        "worktree_path": None,
        "permission": _DEVOPS,
        "tools": ["read", "bash", "skill"],
        "prompt": (
            "You are DevOps. Deploy is a skill, not 'run whatever'. Staging deploys require "
            "confirm. Never skip confirm. Never be the only reviewer."
        ),
        "description": "Environments as memory. Deploy is a skill; confirm required.",
    },
    {
        "slug": "qa",
        "name": "QA",
        "kind": "bot",
        "role": "qa",
        "lane": "line",
        "team": None,
        "reports_to": "floor",
        "agent_slug": "qa",
        "is_conductor": False,
        "worktree_path": None,
        "permission": _QA,
        "tools": ["read", "bash", "webfetch"],
        "prompt": (
            "You are QA. Write and run checks against Product acceptance. Post a structured "
            "report. You cannot deploy."
        ),
        "description": "Writes/runs checks against Product acceptance. Cannot deploy.",
    },
    {
        "slug": "scout",
        "name": "Scout",
        "kind": "bot",
        "role": "explore",
        "lane": "services",
        "team": "services",
        "reports_to": "floor",
        "agent_slug": "scout",
        "is_conductor": False,
        "worktree_path": None,
        "permission": _SCOUT,
        "tools": ["read", "grep", "glob", "webfetch"],
        "prompt": "You are Scout. Cheap, fast, disposable context. Explore and report. No edits.",
        "description": "Cheap, fast, disposable context. Floor spawns these.",
    },
    {
        "slug": "docs",
        "name": "Docs",
        "kind": "bot",
        "role": "docs",
        "lane": "services",
        "team": "services",
        "reports_to": "floor",
        "agent_slug": "docs",
        "is_conductor": False,
        "worktree_path": None,
        "permission": _DOCS,
        "tools": ["read", "edit"],
        "prompt": "You are Docs. Update only the files Product pointed at. Nothing else.",
        "description": "Updates the file Product pointed at. Nothing else.",
    },
    {
        "slug": "sec",
        "name": "Sec",
        "kind": "bot",
        "role": "sec",
        "lane": "services",
        "team": "services",
        "reports_to": "floor",
        "agent_slug": "sec",
        "is_conductor": False,
        "worktree_path": None,
        "permission": _SEC,
        "tools": ["read", "grep"],
        "prompt": "You are Sec. Dependency and secret scan. You may block merge. No edits.",
        "description": "Dependency and secret scan. Can block merge.",
    },
    {
        "slug": "scribe",
        "name": "Scribe",
        "kind": "bot",
        "role": "scribe",
        "lane": "services",
        "team": "services",
        "reports_to": "floor",
        "agent_slug": "scribe",
        "is_conductor": False,
        "worktree_path": None,
        "permission": _SCRIBE,
        "tools": ["read"],
        "prompt": "You are Scribe. Turn huddles and runs into the audit note. Always on. No mutating tools.",
        "description": "Turns huddles and runs into the audit note. Always on.",
    },
]

STARTER_CHANNELS: list[dict[str, str]] = [
    {"slug": "ship", "name": "ship", "kind": "channel"},
    {"slug": "general", "name": "general", "kind": "channel"},
]


def seat_by_slug(slug: str) -> dict[str, Any]:
    for row in STARTER_SEATS:
        if row["slug"] == slug:
            return row
    raise KeyError(slug)


def opencode_agent_payload(spec: dict[str, Any]) -> dict[str, Any] | None:
    """Harness-pack agent dict for a bot seat (None for humans)."""
    if spec.get("kind") != "bot" or not spec.get("agent_slug"):
        return None
    mode = "primary"
    if spec.get("role") in ("explore",):
        mode = "subagent"
    return {
        "id": spec["agent_slug"],
        "name": spec["agent_slug"],
        "description": spec.get("description") or "",
        "prompt": spec.get("prompt") or "",
        "mode": mode,
        "permission": dict(spec.get("permission") or {}),
        "managed": True,
        "source": "everflow-roster",
    }


def starter_agent_pack() -> list[dict[str, Any]]:
    agents: list[dict[str, Any]] = []
    for spec in STARTER_SEATS:
        payload = opencode_agent_payload(spec)
        if payload:
            agents.append(payload)
    return agents
