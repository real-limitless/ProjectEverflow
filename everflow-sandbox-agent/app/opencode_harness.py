"""Read/write OpenCode agent + skill + MCP packs into a sandbox workspace.

Layout (OpenCode-native + Everflow metadata):

  <workspace>/
    opencode.json
    .opencode/agents/<slug>.md
    .opencode/skills/<name>/SKILL.md
    .everflow/harness-manifest.json
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MANIFEST_REL = ".everflow/harness-manifest.json"
AGENTS_DIR = ".opencode/agents"
SKILLS_DIR = ".opencode/skills"
OPENCODE_JSON = "opencode.json"

# Built-in OpenCode agent names (not managed via markdown files we own)
BUILTIN_AGENT_HINTS = frozenset(
    {"build", "plan", "general", "explore", "scout", "compaction", "title", "summary"}
)


def is_valid_slug(name: str) -> bool:
    return bool(name and SLUG_RE.match(name) and len(name) <= 64)


def _safe_join(root: Path, *parts: str) -> Path:
    target = (root.joinpath(*parts)).resolve()
    root_r = root.resolve()
    if not str(target).startswith(str(root_r)):
        raise PermissionError(f"path escapes workspace: {parts}")
    return target


def dump_yaml_scalar(value: Any) -> str:
    """Minimal YAML scalar encoding for frontmatter (no full YAML lib required)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if value == "" or any(c in value for c in ":#{}[]&*!|>%@`'\"\n") or value.strip() != value:
            return json.dumps(value)
        return value
    # nested dict/list → JSON (valid enough for simple frontmatter consumers)
    return json.dumps(value, ensure_ascii=False)


def permission_to_yaml(perm: dict[str, Any], indent: int = 2) -> list[str]:
    """Render permission map as YAML lines (2-space indent under frontmatter key)."""
    lines: list[str] = []
    pad = " " * indent
    for key, val in perm.items():
        if isinstance(val, dict):
            lines.append(f"{pad}{key}:")
            for sk, sv in val.items():
                lines.append(f"{pad}  {dump_yaml_scalar(sk)}: {dump_yaml_scalar(sv)}")
        else:
            lines.append(f"{pad}{key}: {dump_yaml_scalar(val)}")
    return lines


def render_agent_markdown(agent: dict[str, Any]) -> str:
    """Build OpenCode agent markdown file content from a pack agent dict."""
    name = str(agent.get("id") or agent.get("name") or "").strip()
    if not is_valid_slug(name):
        raise ValueError(f"invalid agent id/slug: {name!r}")

    description = str(agent.get("description") or "").strip() or f"Everflow agent {name}"
    mode = str(agent.get("mode") or "all").strip()
    if mode not in ("primary", "subagent", "all"):
        mode = "all"

    lines = ["---", f"description: {dump_yaml_scalar(description)}", f"mode: {mode}"]

    model = agent.get("model")
    if model:
        lines.append(f"model: {dump_yaml_scalar(str(model))}")

    if agent.get("temperature") is not None:
        try:
            lines.append(f"temperature: {float(agent['temperature'])}")
        except (TypeError, ValueError):
            pass

    if agent.get("color"):
        lines.append(f"color: {dump_yaml_scalar(str(agent['color']))}")

    if agent.get("disable") is True:
        lines.append("disable: true")

    perm = agent.get("permission")
    if isinstance(perm, dict) and perm:
        lines.append("permission:")
        lines.extend(permission_to_yaml(perm, indent=2))

    # Everflow-only metadata (OpenCode ignores unknown frontmatter keys)
    preferred = agent.get("modelsPreferred") or agent.get("models_preferred")
    if isinstance(preferred, list) and preferred:
        lines.append(f"everflow_models_preferred: {json.dumps([str(x) for x in preferred])}")

    mcp_ids = agent.get("mcpIds") or agent.get("mcp_ids")
    if isinstance(mcp_ids, list) and mcp_ids:
        lines.append(f"everflow_mcp_ids: {json.dumps([str(x) for x in mcp_ids])}")

    skill_allow = agent.get("skillAllow") or agent.get("skill_allow")
    if isinstance(skill_allow, list) and skill_allow:
        lines.append(f"everflow_skill_allow: {json.dumps([str(x) for x in skill_allow])}")

    lines.append("---")
    lines.append("")
    prompt = str(agent.get("prompt") or agent.get("systemPrompt") or "").rstrip()
    if prompt:
        lines.append(prompt)
        lines.append("")
    return "\n".join(lines)


def parse_agent_markdown(text: str, *, slug: str) -> dict[str, Any]:
    """Parse agent markdown (YAML frontmatter + body) into a pack agent dict."""
    agent: dict[str, Any] = {
        "id": slug,
        "description": "",
        "mode": "all",
        "prompt": "",
        "managed": True,
        "source": "opencode-file",
    }
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        agent["prompt"] = raw.strip()
        agent["description"] = f"Agent {slug}"
        return agent

    end = raw.find("\n---", 3)
    if end < 0:
        agent["prompt"] = raw.strip()
        agent["description"] = f"Agent {slug}"
        return agent

    fm_block = raw[3:end].strip("\n")
    body = raw[end + 4 :].lstrip("\n")
    agent["prompt"] = body.rstrip()

    # Lightweight line parser (handles nested permission one level deep)
    current_map: str | None = None
    nested_key: str | None = None
    permission: dict[str, Any] = {}

    for line in fm_block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        # nested under permission.<key>:
        if current_map == "permission" and nested_key and line.startswith("    "):
            m = re.match(r"^\s+([^:]+):\s*(.*)$", line)
            if m:
                sk, sv = m.group(1).strip().strip("'\""), m.group(2).strip()
                if not isinstance(permission.get(nested_key), dict):
                    permission[nested_key] = {}
                permission[nested_key][sk] = _parse_fm_value(sv)
            continue
        if current_map == "permission" and line.startswith("  ") and not line.startswith("    "):
            m = re.match(r"^\s+([^:]+):\s*(.*)$", line)
            if m:
                key, rest = m.group(1).strip(), m.group(2).strip()
                if rest == "":
                    nested_key = key
                    permission[key] = {}
                else:
                    nested_key = None
                    permission[key] = _parse_fm_value(rest)
            continue

        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        current_map = None
        nested_key = None
        if key == "permission":
            current_map = "permission"
            continue
        val = _parse_fm_value(rest)
        if key == "description":
            agent["description"] = str(val)
        elif key == "mode":
            agent["mode"] = str(val) if val in ("primary", "subagent", "all") else "all"
        elif key == "model":
            agent["model"] = str(val)
        elif key == "temperature":
            try:
                agent["temperature"] = float(val)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        elif key == "color":
            agent["color"] = str(val)
        elif key == "disable":
            agent["disable"] = bool(val)
        elif key == "everflow_models_preferred" and isinstance(val, list):
            agent["modelsPreferred"] = [str(x) for x in val]
        elif key == "everflow_mcp_ids" and isinstance(val, list):
            agent["mcpIds"] = [str(x) for x in val]
        elif key == "everflow_skill_allow" and isinstance(val, list):
            agent["skillAllow"] = [str(x) for x in val]

    if permission:
        agent["permission"] = permission
    if not agent["description"]:
        agent["description"] = f"Agent {slug}"
    return agent


def _parse_fm_value(raw: str) -> Any:
    s = raw.strip()
    if not s:
        return ""
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "Null", "~"):
        return None
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        try:
            return json.loads(s.replace("'", '"') if s.startswith("'") else s)
        except json.JSONDecodeError:
            return s[1:-1]
    if s.startswith("[") or s.startswith("{"):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return s
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        return s


def render_skill_markdown(skill: dict[str, Any]) -> str:
    name = str(skill.get("id") or skill.get("name") or "").strip()
    if not is_valid_slug(name):
        raise ValueError(f"invalid skill name: {name!r}")
    description = str(skill.get("description") or "").strip() or f"Skill {name}"
    body = str(skill.get("body") or skill.get("prompt") or "").rstrip()
    lines = [
        "---",
        f"name: {name}",
        f"description: {dump_yaml_scalar(description)}",
        "compatibility: opencode",
        "---",
        "",
    ]
    if body:
        lines.append(body)
        lines.append("")
    return "\n".join(lines)


def parse_skill_markdown(text: str, *, name: str) -> dict[str, Any]:
    skill: dict[str, Any] = {
        "id": name,
        "name": name,
        "description": "",
        "body": "",
        "managed": True,
        "source": "opencode-file",
    }
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        skill["body"] = raw.strip()
        skill["description"] = f"Skill {name}"
        return skill
    end = raw.find("\n---", 3)
    if end < 0:
        skill["body"] = raw.strip()
        skill["description"] = f"Skill {name}"
        return skill
    fm_block = raw[3:end].strip("\n")
    body = raw[end + 4 :].lstrip("\n")
    skill["body"] = body.rstrip()
    for line in fm_block.splitlines():
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        val = _parse_fm_value(rest)
        if key == "name":
            skill["name"] = str(val)
            skill["id"] = str(val)
        elif key == "description":
            skill["description"] = str(val)
    if not skill["description"]:
        skill["description"] = f"Skill {name}"
    return skill


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("failed to read json %s: %s", path, exc)
        return {}


def deep_merge_mcp(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge MCP server maps; incoming wins per-server key."""
    out = dict(existing)
    for name, cfg in incoming.items():
        if cfg is None:
            out.pop(str(name), None)
            continue
        if isinstance(cfg, dict):
            prev = out.get(str(name))
            if isinstance(prev, dict):
                merged = {**prev, **cfg}
                out[str(name)] = merged
            else:
                out[str(name)] = dict(cfg)
        else:
            out[str(name)] = cfg
    return out


def merge_opencode_json(existing: dict[str, Any], *, mcp: dict[str, Any] | None) -> dict[str, Any]:
    """Merge managed sections into opencode.json without dropping server/config."""
    out = dict(existing) if existing else {}
    if "$schema" not in out:
        out["$schema"] = "https://opencode.ai/config.json"
    if mcp is not None:
        prev_mcp = out.get("mcp") if isinstance(out.get("mcp"), dict) else {}
        out["mcp"] = deep_merge_mcp(prev_mcp, mcp)
    return out


def read_pack_from_workspace(workspace: Path) -> dict[str, Any]:
    """Scan workspace for agents, skills, mcp, manifest."""
    root = workspace.resolve()
    agents: list[dict[str, Any]] = []
    agents_dir = _safe_join(root, AGENTS_DIR)
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.md")):
            slug = path.stem
            if not is_valid_slug(slug):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            agent = parse_agent_markdown(text, slug=slug)
            agent["managed"] = True
            agent["source"] = "opencode-file"
            agents.append(agent)

    skills: list[dict[str, Any]] = []
    skills_dir = _safe_join(root, SKILLS_DIR)
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            name = child.name
            if not is_valid_slug(name):
                continue
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            skills.append(parse_skill_markdown(text, name=name))

    oc = load_json_file(_safe_join(root, OPENCODE_JSON))
    mcp = oc.get("mcp") if isinstance(oc.get("mcp"), dict) else {}
    manifest = load_json_file(_safe_join(root, MANIFEST_REL))

    return {
        "agents": agents,
        "skills": skills,
        "mcp": mcp,
        "manifest": manifest,
        "opencode_json": {
            k: v
            for k, v in oc.items()
            if k in ("model", "small_model", "default_agent", "server", "$schema")
        },
    }


def apply_pack_to_workspace(
    workspace: Path,
    pack: dict[str, Any],
    *,
    replace_managed_agents: bool = True,
    replace_managed_skills: bool = True,
) -> dict[str, Any]:
    """
    Write pack into workspace.

    - agents: list of agent dicts → .opencode/agents/<id>.md
    - skills: list of skill dicts → .opencode/skills/<id>/SKILL.md
    - mcp: dict merged into opencode.json
    - remove_agents / remove_skills: list of slugs to delete (managed only)
    - manifest: merged into .everflow/harness-manifest.json
    """
    root = workspace.resolve()
    root.mkdir(parents=True, exist_ok=True)

    written_agents: list[str] = []
    written_skills: list[str] = []
    removed_agents: list[str] = []
    removed_skills: list[str] = []

    manifest_path = _safe_join(root, MANIFEST_REL)
    manifest = load_json_file(manifest_path)
    managed_agents: set[str] = set(manifest.get("managed_agents") or [])
    managed_skills: set[str] = set(manifest.get("managed_skills") or [])

    # Removals
    for slug in pack.get("remove_agents") or []:
        s = str(slug)
        if not is_valid_slug(s):
            continue
        path = _safe_join(root, AGENTS_DIR, f"{s}.md")
        if path.is_file():
            path.unlink()
            removed_agents.append(s)
        managed_agents.discard(s)

    for slug in pack.get("remove_skills") or []:
        s = str(slug)
        if not is_valid_slug(s):
            continue
        skill_dir = _safe_join(root, SKILLS_DIR, s)
        skill_md = skill_dir / "SKILL.md"
        if skill_md.is_file():
            skill_md.unlink()
            removed_skills.append(s)
        # remove empty dir
        try:
            if skill_dir.is_dir() and not any(skill_dir.iterdir()):
                skill_dir.rmdir()
        except OSError:
            pass
        managed_skills.discard(s)

    # Agents upsert
    agents_in = pack.get("agents")
    if isinstance(agents_in, list):
        if replace_managed_agents and pack.get("replace_all_agents"):
            for old in list(managed_agents):
                path = _safe_join(root, AGENTS_DIR, f"{old}.md")
                if path.is_file():
                    path.unlink()
                    removed_agents.append(old)
            managed_agents.clear()

        agents_dir = _safe_join(root, AGENTS_DIR)
        agents_dir.mkdir(parents=True, exist_ok=True)
        for agent in agents_in:
            if not isinstance(agent, dict):
                continue
            slug = str(agent.get("id") or agent.get("name") or "").strip()
            if not is_valid_slug(slug):
                raise ValueError(f"invalid agent id: {slug!r}")
            content = render_agent_markdown(agent)
            path = agents_dir / f"{slug}.md"
            path.write_text(content, encoding="utf-8")
            written_agents.append(slug)
            managed_agents.add(slug)

    # Skills upsert
    skills_in = pack.get("skills")
    if isinstance(skills_in, list):
        if replace_managed_skills and pack.get("replace_all_skills"):
            for old in list(managed_skills):
                skill_dir = _safe_join(root, SKILLS_DIR, old)
                skill_md = skill_dir / "SKILL.md"
                if skill_md.is_file():
                    skill_md.unlink()
                    removed_skills.append(old)
            managed_skills.clear()

        for skill in skills_in:
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("id") or skill.get("name") or "").strip()
            if not is_valid_slug(name):
                raise ValueError(f"invalid skill name: {name!r}")
            content = render_skill_markdown(skill)
            skill_dir = _safe_join(root, SKILLS_DIR, name)
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
            written_skills.append(name)
            managed_skills.add(name)

    # MCP merge into opencode.json
    mcp_in = pack.get("mcp")
    oc_path = _safe_join(root, OPENCODE_JSON)
    existing_oc = load_json_file(oc_path)
    if isinstance(mcp_in, dict) or pack.get("small_model") or pack.get("model") or pack.get(
        "default_agent"
    ):
        merged = merge_opencode_json(
            existing_oc,
            mcp=mcp_in if isinstance(mcp_in, dict) else None,
        )
        if pack.get("model"):
            merged["model"] = str(pack["model"])
        if pack.get("small_model"):
            merged["small_model"] = str(pack["small_model"])
        if pack.get("default_agent"):
            merged["default_agent"] = str(pack["default_agent"])
        # Preserve server block already present
        oc_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        existing_oc = merged

    # Manifest
    extra_meta = pack.get("manifest") if isinstance(pack.get("manifest"), dict) else {}
    agent_meta = pack.get("agent_meta") if isinstance(pack.get("agent_meta"), dict) else {}
    new_manifest = {
        **manifest,
        **extra_meta,
        "managed_agents": sorted(managed_agents),
        "managed_skills": sorted(managed_skills),
        "version": int(manifest.get("version") or 0) + 1,
    }
    if agent_meta:
        prev_am = new_manifest.get("agent_meta") if isinstance(new_manifest.get("agent_meta"), dict) else {}
        new_manifest["agent_meta"] = {**prev_am, **agent_meta}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(new_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    result = read_pack_from_workspace(root)
    result["written"] = {
        "agents": written_agents,
        "skills": written_skills,
        "removed_agents": removed_agents,
        "removed_skills": removed_skills,
    }
    return result


# ---------------------------------------------------------------------------
# Guest FS pack ops (named volume / guest-only sandboxes — no host Path)
# ---------------------------------------------------------------------------


async def _guest_read_text(backend: Any, sandbox_name: str, path: str) -> str | None:
    try:
        data = await backend.read_fs(sandbox_name, path)
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return str(data)
    except Exception as exc:  # noqa: BLE001 — missing file is normal
        logger.debug("guest read miss %s/%s: %s", sandbox_name, path, exc)
        return None


async def _guest_list(backend: Any, sandbox_name: str, path: str) -> list[dict[str, Any]]:
    try:
        entries = await backend.list_fs(sandbox_name, path)
        return list(entries or [])
    except Exception as exc:  # noqa: BLE001
        logger.debug("guest list miss %s/%s: %s", sandbox_name, path, exc)
        return []


async def _guest_write_text(backend: Any, sandbox_name: str, path: str, text: str) -> None:
    await backend.write_fs(sandbox_name, path, text.encode("utf-8"))


async def _guest_rm(backend: Any, sandbox_name: str, path: str) -> bool:
    """Best-effort remove file or directory inside the guest workspace."""
    # Paths are relative under /workspace via normalize_guest_path in backends
    try:
        code, _, _ = await backend.exec(
            sandbox_name,
            "rm",
            ["-rf", path],
            cwd="/workspace",
        )
        return code == 0
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest rm failed %s/%s: %s", sandbox_name, path, exc)
        return False


async def read_pack_via_backend(backend: Any, sandbox_name: str) -> dict[str, Any]:
    """Scan guest workspace for agents/skills/mcp/manifest via list_fs + read_fs."""
    agents: list[dict[str, Any]] = []
    for entry in await _guest_list(backend, sandbox_name, AGENTS_DIR):
        name = str(entry.get("name") or "")
        if entry.get("is_dir") or not name.endswith(".md"):
            continue
        slug = name[: -len(".md")]
        if not is_valid_slug(slug):
            continue
        text = await _guest_read_text(backend, sandbox_name, f"{AGENTS_DIR}/{name}")
        if text is None:
            continue
        agent = parse_agent_markdown(text, slug=slug)
        agent["managed"] = True
        agent["source"] = "opencode-file"
        agents.append(agent)

    skills: list[dict[str, Any]] = []
    for entry in await _guest_list(backend, sandbox_name, SKILLS_DIR):
        if not entry.get("is_dir"):
            continue
        name = str(entry.get("name") or "")
        if not is_valid_slug(name):
            continue
        text = await _guest_read_text(backend, sandbox_name, f"{SKILLS_DIR}/{name}/SKILL.md")
        if text is None:
            continue
        skills.append(parse_skill_markdown(text, name=name))

    oc_raw = await _guest_read_text(backend, sandbox_name, OPENCODE_JSON)
    oc: dict[str, Any] = {}
    if oc_raw:
        try:
            parsed = json.loads(oc_raw)
            if isinstance(parsed, dict):
                oc = parsed
        except json.JSONDecodeError:
            oc = {}
    mcp = oc.get("mcp") if isinstance(oc.get("mcp"), dict) else {}

    man_raw = await _guest_read_text(backend, sandbox_name, MANIFEST_REL)
    manifest: dict[str, Any] = {}
    if man_raw:
        try:
            parsed = json.loads(man_raw)
            if isinstance(parsed, dict):
                manifest = parsed
        except json.JSONDecodeError:
            manifest = {}

    return {
        "agents": agents,
        "skills": skills,
        "mcp": mcp,
        "manifest": manifest,
        "opencode_json": {
            k: v
            for k, v in oc.items()
            if k in ("model", "small_model", "default_agent", "server", "$schema")
        },
    }


async def apply_pack_via_backend(
    backend: Any,
    sandbox_name: str,
    pack: dict[str, Any],
    *,
    replace_managed_agents: bool = True,
    replace_managed_skills: bool = True,
) -> dict[str, Any]:
    """Write pack into guest workspace using write_fs / exec rm (no host mount)."""
    written_agents: list[str] = []
    written_skills: list[str] = []
    removed_agents: list[str] = []
    removed_skills: list[str] = []

    man_raw = await _guest_read_text(backend, sandbox_name, MANIFEST_REL)
    manifest: dict[str, Any] = {}
    if man_raw:
        try:
            parsed = json.loads(man_raw)
            if isinstance(parsed, dict):
                manifest = parsed
        except json.JSONDecodeError:
            manifest = {}
    managed_agents: set[str] = set(manifest.get("managed_agents") or [])
    managed_skills: set[str] = set(manifest.get("managed_skills") or [])

    for slug in pack.get("remove_agents") or []:
        s = str(slug)
        if not is_valid_slug(s):
            continue
        if await _guest_rm(backend, sandbox_name, f"{AGENTS_DIR}/{s}.md"):
            removed_agents.append(s)
        managed_agents.discard(s)

    for slug in pack.get("remove_skills") or []:
        s = str(slug)
        if not is_valid_slug(s):
            continue
        if await _guest_rm(backend, sandbox_name, f"{SKILLS_DIR}/{s}"):
            removed_skills.append(s)
        managed_skills.discard(s)

    agents_in = pack.get("agents")
    if isinstance(agents_in, list):
        if replace_managed_agents and pack.get("replace_all_agents"):
            for old in list(managed_agents):
                if await _guest_rm(backend, sandbox_name, f"{AGENTS_DIR}/{old}.md"):
                    removed_agents.append(old)
            managed_agents.clear()

        for agent in agents_in:
            if not isinstance(agent, dict):
                continue
            slug = str(agent.get("id") or agent.get("name") or "").strip()
            if not is_valid_slug(slug):
                raise ValueError(f"invalid agent id: {slug!r}")
            content = render_agent_markdown(agent)
            await _guest_write_text(backend, sandbox_name, f"{AGENTS_DIR}/{slug}.md", content)
            written_agents.append(slug)
            managed_agents.add(slug)

    skills_in = pack.get("skills")
    if isinstance(skills_in, list):
        if replace_managed_skills and pack.get("replace_all_skills"):
            for old in list(managed_skills):
                if await _guest_rm(backend, sandbox_name, f"{SKILLS_DIR}/{old}"):
                    removed_skills.append(old)
            managed_skills.clear()

        for skill in skills_in:
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("id") or skill.get("name") or "").strip()
            if not is_valid_slug(name):
                raise ValueError(f"invalid skill name: {name!r}")
            content = render_skill_markdown(skill)
            await _guest_write_text(
                backend,
                sandbox_name,
                f"{SKILLS_DIR}/{name}/SKILL.md",
                content,
            )
            written_skills.append(name)
            managed_skills.add(name)

    mcp_in = pack.get("mcp")
    oc_raw = await _guest_read_text(backend, sandbox_name, OPENCODE_JSON)
    existing_oc: dict[str, Any] = {}
    if oc_raw:
        try:
            parsed = json.loads(oc_raw)
            if isinstance(parsed, dict):
                existing_oc = parsed
        except json.JSONDecodeError:
            existing_oc = {}

    if isinstance(mcp_in, dict) or pack.get("small_model") or pack.get("model") or pack.get(
        "default_agent"
    ):
        merged = merge_opencode_json(
            existing_oc,
            mcp=mcp_in if isinstance(mcp_in, dict) else None,
        )
        if pack.get("model"):
            merged["model"] = str(pack["model"])
        if pack.get("small_model"):
            merged["small_model"] = str(pack["small_model"])
        if pack.get("default_agent"):
            merged["default_agent"] = str(pack["default_agent"])
        await _guest_write_text(
            backend,
            sandbox_name,
            OPENCODE_JSON,
            json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        )

    extra_meta = pack.get("manifest") if isinstance(pack.get("manifest"), dict) else {}
    agent_meta = pack.get("agent_meta") if isinstance(pack.get("agent_meta"), dict) else {}
    new_manifest = {
        **manifest,
        **extra_meta,
        "managed_agents": sorted(managed_agents),
        "managed_skills": sorted(managed_skills),
        "version": int(manifest.get("version") or 0) + 1,
    }
    if agent_meta:
        prev_am = new_manifest.get("agent_meta") if isinstance(new_manifest.get("agent_meta"), dict) else {}
        new_manifest["agent_meta"] = {**prev_am, **agent_meta}
    await _guest_write_text(
        backend,
        sandbox_name,
        MANIFEST_REL,
        json.dumps(new_manifest, indent=2, ensure_ascii=False) + "\n",
    )

    result = await read_pack_via_backend(backend, sandbox_name)
    result["written"] = {
        "agents": written_agents,
        "skills": written_skills,
        "removed_agents": removed_agents,
        "removed_skills": removed_skills,
    }
    return result
