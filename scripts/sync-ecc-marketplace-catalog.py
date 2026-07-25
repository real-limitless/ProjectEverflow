#!/usr/bin/env python3
"""Sync Everflow marketplace catalog from affaan-m/ECC + curated plugins/tools.

Writes identical JSON to:
  - everflow-platform-ui/src/data/marketplace/catalog.json
  - everflow-platform-api/app/data/marketplace_catalog.json

Usage:
  python scripts/sync-ecc-marketplace-catalog.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_OUT = ROOT / "everflow-platform-ui" / "src" / "data" / "marketplace" / "catalog.json"
API_OUT = ROOT / "everflow-platform-api" / "app" / "data" / "marketplace_catalog.json"

ECC_API = "https://api.github.com/repos/affaan-m/ECC/contents"
ECC_RAW = "https://raw.githubusercontent.com/affaan-m/ECC/main"
# Bundled under everflow-platform-api/app/data/marketplace_skills/
GRAPHIFY_SKILL_FILE = "graphify/SKILL.md"
EVERFLOW_SKILL_FILES = {
    "everflow-knowledge": "everflow-knowledge/SKILL.md",
    "everflow-jobs": "everflow-jobs/SKILL.md",
    "everflow-browser": "everflow-browser/SKILL.md",
}

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def fetch_json(url: str) -> object:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "everflow-catalog-sync"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "everflow-catalog-sync"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def parse_frontmatter_description(text: str) -> str:
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        return ""
    end = raw.find("\n---", 3)
    if end < 0:
        return ""
    for line in raw[3:end].strip("\n").splitlines():
        m = re.match(r"^description:\s*(.*)$", line)
        if not m:
            continue
        val = m.group(1).strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            try:
                return json.loads(val.replace("'", '"') if val.startswith("'") else val)
            except json.JSONDecodeError:
                return val[1:-1]
        return val
    return ""


def to_slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:64]


def list_dir(path: str) -> list[dict]:
    data = fetch_json(f"{ECC_API}/{path}")
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected response for {path}")
    return data


def build_skills(*, with_descriptions: bool = False) -> list[dict]:
    entries = list_dir("skills")
    out: list[dict] = []
    for entry in entries:
        if entry.get("type") != "dir":
            continue
        name = str(entry.get("name") or "")
        slug = to_slug(name)
        if not SLUG_RE.match(slug):
            continue
        content_url = f"{ECC_RAW}/skills/{name}/SKILL.md"
        description = f"ECC skill: {name}"
        if with_descriptions:
            try:
                description = parse_frontmatter_description(fetch_text(content_url)) or description
            except urllib.error.HTTPError:
                pass
        out.append(
            {
                "id": slug,
                "kind": "skill",
                "name": name.replace("-", " ").title() if "-" in name else name,
                "description": description,
                "origin": "ecc",
                "source": "https://github.com/affaan-m/ECC",
                "contentUrl": content_url,
                "tags": ["ecc", "skill"],
            }
        )
    out.sort(key=lambda x: x["id"])
    return out


def build_commands(*, with_descriptions: bool = False) -> list[dict]:
    entries = list_dir("commands")
    out: list[dict] = []
    for entry in entries:
        if entry.get("type") != "file":
            continue
        fname = str(entry.get("name") or "")
        if not fname.endswith(".md"):
            continue
        stem = fname[: -len(".md")]
        slug = to_slug(stem)
        if not SLUG_RE.match(slug):
            continue
        content_url = f"{ECC_RAW}/commands/{fname}"
        description = f"ECC slash command /{stem}"
        if with_descriptions:
            try:
                description = parse_frontmatter_description(fetch_text(content_url)) or description
            except urllib.error.HTTPError:
                pass
        out.append(
            {
                "id": slug,
                "kind": "command",
                "name": stem,
                "description": description,
                "origin": "ecc",
                "source": "https://github.com/affaan-m/ECC",
                "contentUrl": content_url,
                "tags": ["ecc", "command"],
            }
        )
    out.sort(key=lambda x: x["id"])
    return out


def normalize_mcp_config(name: str, cfg: dict) -> dict:
    """Map Claude/Cursor-style MCP config to OpenCode local/remote shape."""
    if "url" in cfg:
        return {
            "type": "remote",
            "url": str(cfg["url"]),
            "enabled": True,
            "environment": cfg.get("env") if isinstance(cfg.get("env"), dict) else None,
        }
    command = cfg.get("command")
    args = cfg.get("args") if isinstance(cfg.get("args"), list) else []
    parts: list[str] = []
    if isinstance(command, list):
        parts = [str(x) for x in command]
    elif isinstance(command, str) and command.strip():
        parts = [command, *[str(a) for a in args]]
    else:
        parts = ["npx", "-y", name]
    env = cfg.get("env") if isinstance(cfg.get("env"), dict) else None
    out: dict = {"type": "local", "command": parts, "enabled": True}
    if env:
        out["environment"] = {str(k): str(v) for k, v in env.items()}
    return out


def build_mcps() -> list[dict]:
    data = fetch_json(
        "https://api.github.com/repos/affaan-m/ECC/contents/mcp-configs/mcp-servers.json"
    )
    download = data.get("download_url") if isinstance(data, dict) else None
    if not download:
        text = fetch_text(f"{ECC_RAW}/mcp-configs/mcp-servers.json")
    else:
        text = fetch_text(str(download))
    payload = json.loads(text)
    servers = payload.get("mcpServers") if isinstance(payload, dict) else {}
    out: list[dict] = []
    for name, cfg in (servers or {}).items():
        if not isinstance(cfg, dict):
            continue
        slug = to_slug(str(name))
        if not SLUG_RE.match(slug):
            continue
        oc = normalize_mcp_config(str(name), cfg)
        # Drop null environment for cleaner JSON
        if oc.get("environment") is None:
            oc.pop("environment", None)
        out.append(
            {
                "id": slug,
                "kind": "mcp",
                "name": str(name),
                "description": f"ECC MCP server: {name}",
                "origin": "ecc",
                "source": "https://github.com/affaan-m/ECC",
                "mcpConfig": oc,
                "tags": ["ecc", "mcp"],
            }
        )
    out.sort(key=lambda x: x["id"])
    return out


def curated_plugins() -> list[dict]:
    return [
        {
            "id": "graphify",
            "kind": "plugin",
            "name": "Graphify",
            "description": (
                "Knowledge graph for codebases — query, path, and explain via an OpenCode skill "
                "and optional MCP server (graphify --mcp)."
            ),
            "origin": "curated",
            "source": "https://github.com/Graphify-Labs/graphify",
            "tags": ["plugin", "knowledge-graph", "rag"],
            "install": {
                "skills": [
                    {
                        "id": "graphify",
                        "contentFile": GRAPHIFY_SKILL_FILE,
                    }
                ],
                "mcp": {
                    "graphify": {
                        "type": "local",
                        "command": ["graphify", "--mcp"],
                        "enabled": True,
                    }
                },
            },
        },
        {
            "id": "oh-my-opencode",
            "kind": "plugin",
            "name": "Oh My OpenCode",
            "description": (
                "OpenCode plugin pack with agents, hooks, skills, and embedded MCPs. "
                "Installed via opencode.json plugin array (npm auto-install at startup)."
            ),
            "origin": "curated",
            "source": "https://github.com/code-yeongyu/oh-my-opencode",
            "tags": ["plugin", "opencode", "agents"],
            "install": {
                "plugin": ["oh-my-opencode"],
            },
        },
        {
            "id": "headroom",
            "kind": "plugin",
            "name": "Headroom",
            "description": (
                "Local-first context compression for agents — expose compress/retrieve/stats "
                "tools via MCP (requires headroom-ai in the sandbox)."
            ),
            "origin": "curated",
            "source": "https://github.com/headroomlabs-ai/headroom",
            "tags": ["plugin", "mcp", "context"],
            "install": {
                "mcp": {
                    "headroom": {
                        "type": "local",
                        "command": ["headroom", "mcp"],
                        "enabled": True,
                    }
                },
            },
        },
    ]


def curated_everflow_skills() -> list[dict]:
    """First-party Everflow platform skills (also auto-seeded into sandboxes)."""
    return [
        {
            "id": "everflow-knowledge",
            "kind": "skill",
            "name": "Everflow Knowledge",
            "description": (
                "Retrieve and manage Project Everflow Knowledge canvases "
                "(docs, secrets, runbooks) via knowledge_search."
            ),
            "origin": "everflow",
            "source": "everflow",
            "contentFile": EVERFLOW_SKILL_FILES["everflow-knowledge"],
            "tags": ["everflow", "skill", "knowledge"],
        },
        {
            "id": "everflow-jobs",
            "kind": "skill",
            "name": "Everflow Jobs",
            "description": (
                "Run long-lived processes (dev servers) as Everflow Jobs instead of a blocking shell."
            ),
            "origin": "everflow",
            "source": "everflow",
            "contentFile": EVERFLOW_SKILL_FILES["everflow-jobs"],
            "tags": ["everflow", "skill", "jobs"],
        },
        {
            "id": "everflow-browser",
            "kind": "skill",
            "name": "Everflow Browser",
            "description": (
                "Playwright MCP browser automation plus headed/headless mode for the Desktop panel."
            ),
            "origin": "everflow",
            "source": "everflow",
            "contentFile": EVERFLOW_SKILL_FILES["everflow-browser"],
            "tags": ["everflow", "skill", "browser"],
        },
    ]


def curated_everflow_mcps() -> list[dict]:
    """Platform-native MCPs merged after ECC list (dedupe by id prefers these)."""
    return [
        {
            "id": "playwright",
            "kind": "mcp",
            "name": "Browser (Playwright)",
            "description": (
                "Chromium + Playwright MCP for OpenCode: surf the web headless by default, "
                "or headed on the project Desktop panel. Install opt-in; use everflow "
                "browser_set_mode to switch modes."
            ),
            "origin": "everflow",
            "source": "https://github.com/microsoft/playwright-mcp",
            "mcpConfig": {
                "type": "local",
                "command": ["everflow-playwright-mcp"],
                "enabled": True,
                "environment": {
                    "PLAYWRIGHT_BROWSERS_PATH": "/opt/everflow-browsers",
                    "DISPLAY": ":99",
                },
            },
            "tags": ["browser", "playwright", "everflow", "mcp"],
        },
    ]


def curated_tools() -> list[dict]:
    return [
        {
            "id": "httpbin-get",
            "kind": "tool",
            "name": "HTTPBin GET",
            "description": "Sample GET tool against httpbin.org for testing HTTP tool wiring.",
            "origin": "curated",
            "source": "everflow",
            "tags": ["http-tool", "sample"],
            "httpTool": {
                "name": "httpbin-get",
                "method": "GET",
                "url_template": "https://httpbin.org/get",
                "enabled": True,
            },
        },
        {
            "id": "httpbin-post",
            "kind": "tool",
            "name": "HTTPBin POST",
            "description": "Sample POST tool against httpbin.org for testing HTTP tool wiring.",
            "origin": "curated",
            "source": "everflow",
            "tags": ["http-tool", "sample"],
            "httpTool": {
                "name": "httpbin-post",
                "method": "POST",
                "url_template": "https://httpbin.org/post",
                "enabled": True,
            },
        },
        {
            "id": "jsonplaceholder-todos",
            "kind": "tool",
            "name": "JSONPlaceholder Todos",
            "description": "Fetch sample todos from jsonplaceholder.typicode.com.",
            "origin": "curated",
            "source": "everflow",
            "tags": ["http-tool", "sample"],
            "httpTool": {
                "name": "jsonplaceholder-todos",
                "method": "GET",
                "url_template": "https://jsonplaceholder.typicode.com/todos",
                "enabled": True,
            },
        },
    ]


def main() -> int:
    with_descriptions = "--descriptions" in sys.argv
    print("Fetching ECC skills…", file=sys.stderr)
    skills = build_skills(with_descriptions=with_descriptions)
    print(f"  {len(skills)} skills", file=sys.stderr)
    print("Fetching ECC commands…", file=sys.stderr)
    commands = build_commands(with_descriptions=with_descriptions)
    print(f"  {len(commands)} commands", file=sys.stderr)
    print("Fetching ECC MCP configs…", file=sys.stderr)
    mcps = build_mcps()
    print(f"  {len(mcps)} mcps", file=sys.stderr)

    # Everflow-first skills; ECC list may not collide but prepend for discoverability.
    skills = curated_everflow_skills() + [
        s for s in skills if s.get("id") not in EVERFLOW_SKILL_FILES
    ]
    # Prefer Everflow MCP definitions over ECC duplicates (e.g. playwright).
    everflow_mcps = curated_everflow_mcps()
    everflow_mcp_ids = {m["id"] for m in everflow_mcps}
    mcps = everflow_mcps + [m for m in mcps if m.get("id") not in everflow_mcp_ids]
    mcps.sort(key=lambda x: str(x.get("id") or ""))

    catalog = {
        "version": 1,
        "source": {
            "ecc": "https://github.com/affaan-m/ECC",
            "ref": "main",
        },
        "skills": skills,
        "commands": commands,
        "plugins": curated_plugins(),
        "tools": curated_tools(),
        "mcps": mcps,
    }

    for path in (UI_OUT, API_OUT):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
