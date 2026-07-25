"""Marketplace catalog + install pack builders."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CATALOG_PATH = DATA_DIR / "marketplace_catalog.json"
BUNDLED_SKILLS_DIR = DATA_DIR / "marketplace_skills"

ALLOWED_CONTENT_PREFIXES = (
    "https://raw.githubusercontent.com/affaan-m/ECC/",
    "https://raw.githubusercontent.com/Graphify-Labs/graphify/",
)

KIND_PLURAL = {
    "skill": "skills",
    "command": "commands",
    "plugin": "plugins",
    "tool": "tools",
    "mcp": "mcps",
}


class MarketplaceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.is_file():
        raise MarketplaceError("Marketplace catalog not found", status_code=503)
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MarketplaceError("Invalid marketplace catalog", status_code=503)
    return data


def reload_catalog() -> dict[str, Any]:
    load_catalog.cache_clear()
    return load_catalog()


def find_item(kind: str, item_id: str) -> dict[str, Any]:
    catalog = load_catalog()
    key = KIND_PLURAL.get(kind)
    if not key:
        raise MarketplaceError(f"Unknown marketplace kind: {kind}")
    rows = catalog.get(key) or []
    if not isinstance(rows, list):
        raise MarketplaceError("Invalid catalog section", status_code=503)
    for row in rows:
        if isinstance(row, dict) and str(row.get("id")) == item_id:
            return row
    raise MarketplaceError(f"Marketplace item not found: {kind}/{item_id}", status_code=404)


def is_allowed_content_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    return any(url.startswith(prefix) for prefix in ALLOWED_CONTENT_PREFIXES)


async def fetch_allowlisted_text(url: str) -> str:
    if not is_allowed_content_url(url):
        raise MarketplaceError(f"Content URL not allowlisted: {url}")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url, headers={"User-Agent": "everflow-marketplace"})
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPError as exc:
        raise MarketplaceError(f"Failed to fetch marketplace content: {exc}", status_code=502) from exc


def read_bundled_skill(rel_path: str) -> str:
    """Read a skill file bundled under app/data/marketplace_skills/."""
    rel = rel_path.lstrip("/")
    if ".." in rel.split("/"):
        raise MarketplaceError("Invalid bundled skill path")
    path = (BUNDLED_SKILLS_DIR / rel).resolve()
    if not str(path).startswith(str(BUNDLED_SKILLS_DIR.resolve())):
        raise MarketplaceError("Bundled skill path escapes data dir")
    if not path.is_file():
        raise MarketplaceError(f"Bundled skill not found: {rel}", status_code=500)
    return path.read_text(encoding="utf-8")


async def resolve_skill_content(spec: dict[str, Any]) -> str:
    if isinstance(spec.get("content"), str) and spec["content"].strip():
        return str(spec["content"])
    bundled = spec.get("contentFile")
    if isinstance(bundled, str) and bundled.strip():
        return read_bundled_skill(bundled)
    content_url = str(spec.get("contentUrl") or "")
    if content_url:
        return await fetch_allowlisted_text(content_url)
    raise MarketplaceError("Skill install missing content/contentFile/contentUrl")


# Process-local content cache (kind/id → text). Avoids re-fetching ECC raw URLs on every detail open.
_CONTENT_CACHE: dict[tuple[str, str], str] = {}


def public_item_fields(item: dict[str, Any]) -> dict[str, Any]:
    """Catalog row fields safe to return from the item detail API."""
    out: dict[str, Any] = {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "name": item.get("name"),
        "description": item.get("description"),
        "origin": item.get("origin"),
        "source": item.get("source"),
        "tags": item.get("tags") or [],
    }
    for key in ("contentUrl", "contentFile", "mcpConfig", "httpTool", "install"):
        if key in item:
            out[key] = item[key]
    return out


async def get_item_content(kind: str, item_id: str) -> dict[str, Any]:
    """Resolve skill/command markdown for detail preview (cached)."""
    if kind not in ("skill", "command"):
        raise MarketplaceError(
            f"Content preview is only available for skills and commands (got {kind})",
            status_code=400,
        )
    item = find_item(kind, item_id)
    cache_key = (kind, item_id)
    if cache_key in _CONTENT_CACHE:
        content = _CONTENT_CACHE[cache_key]
    else:
        content = await resolve_skill_content(item)
        _CONTENT_CACHE[cache_key] = content
    return {
        "kind": kind,
        "id": item_id,
        "name": item.get("name") or item_id,
        "content": content,
        "content_type": "text/markdown",
    }


def _slugify(value: str) -> str:
    import re

    s = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s[:64] or "item"


async def build_install_pack(kind: str, item_id: str) -> dict[str, Any]:
    """Build an OpenCode harness pack (and optional http tool) for an install."""
    item = find_item(kind, item_id)
    provenance = {
        "kind": kind,
        "id": item_id,
        "source": str(item.get("origin") or item.get("source") or "marketplace"),
        "name": str(item.get("name") or item_id),
    }

    if kind == "skill":
        content = await resolve_skill_content(item)
        return {
            "skills": [{"id": item_id, "name": item_id, "content": content}],
            "marketplace_items": [provenance],
        }

    if kind == "command":
        content = await resolve_skill_content(item)
        return {
            "commands": [{"id": item_id, "name": item_id, "content": content}],
            "marketplace_items": [provenance],
        }

    if kind == "mcp":
        cfg = item.get("mcpConfig")
        if not isinstance(cfg, dict):
            raise MarketplaceError("MCP item missing mcpConfig", status_code=500)
        return {
            "mcp": {item_id: cfg},
            "marketplace_items": [provenance],
        }

    if kind == "plugin":
        install = item.get("install") if isinstance(item.get("install"), dict) else {}
        pack: dict[str, Any] = {"marketplace_items": [provenance]}
        plugin_list = install.get("plugin")
        if isinstance(plugin_list, list):
            pack["plugin"] = [str(p) for p in plugin_list]
        mcp = install.get("mcp")
        if isinstance(mcp, dict):
            pack["mcp"] = mcp
        skills_spec = install.get("skills")
        if isinstance(skills_spec, list):
            skills: list[dict[str, Any]] = []
            for spec in skills_spec:
                if not isinstance(spec, dict):
                    continue
                sid = _slugify(str(spec.get("id") or item_id))
                content = await resolve_skill_content(spec)
                skills.append({"id": sid, "name": sid, "content": content})
            if skills:
                pack["skills"] = skills
        return pack

    if kind == "tool":
        http_tool = item.get("httpTool")
        if not isinstance(http_tool, dict):
            raise MarketplaceError("Tool item missing httpTool", status_code=500)
        return {
            "http_tool": http_tool,
            "marketplace_items": [provenance],
            # Tools are DB-backed; harness pack unused except provenance tracking is N/A
        }

    raise MarketplaceError(f"Unsupported kind: {kind}")


def build_uninstall_pack(kind: str, item_id: str, item: dict[str, Any] | None = None) -> dict[str, Any]:
    item = item or find_item(kind, item_id)
    remove_meta = [{"kind": kind, "id": item_id}]
    if kind == "skill":
        return {"remove_skills": [item_id], "remove_marketplace_items": remove_meta}
    if kind == "command":
        return {"remove_commands": [item_id], "remove_marketplace_items": remove_meta}
    if kind == "mcp":
        return {
            "mcp": {item_id: None},
            "remove_marketplace_items": remove_meta,
        }
    if kind == "plugin":
        install = item.get("install") if isinstance(item.get("install"), dict) else {}
        pack: dict[str, Any] = {"remove_marketplace_items": remove_meta}
        plugins = install.get("plugin")
        if isinstance(plugins, list):
            pack["remove_plugins"] = [str(p) for p in plugins]
        mcp = install.get("mcp")
        if isinstance(mcp, dict):
            pack["mcp"] = {str(k): None for k in mcp}
        skills = install.get("skills")
        if isinstance(skills, list):
            pack["remove_skills"] = [
                _slugify(str(s.get("id") or item_id)) for s in skills if isinstance(s, dict)
            ]
        return pack
    if kind == "tool":
        return {"remove_http_tool_name": item_id, "remove_marketplace_items": remove_meta}
    raise MarketplaceError(f"Unsupported kind: {kind}")


def catalog_summary() -> dict[str, Any]:
    catalog = load_catalog()
    return {
        "version": catalog.get("version"),
        "source": catalog.get("source"),
        "counts": {
            "skills": len(catalog.get("skills") or []),
            "commands": len(catalog.get("commands") or []),
            "plugins": len(catalog.get("plugins") or []),
            "tools": len(catalog.get("tools") or []),
            "mcps": len(catalog.get("mcps") or []),
        },
        "skills": catalog.get("skills") or [],
        "commands": catalog.get("commands") or [],
        "plugins": catalog.get("plugins") or [],
        "tools": catalog.get("tools") or [],
        "mcps": catalog.get("mcps") or [],
    }
