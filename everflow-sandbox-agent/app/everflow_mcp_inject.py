"""Inject Everflow MCP config into sandbox workspaces (host path or guest FS)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.opencode_harness import OPENCODE_JSON, _guest_read_text, _guest_write_text

logger = logging.getLogger(__name__)

DEFAULT_MCP_COMMAND = "everflow-mcp"
MCP_ENV_REL = ".everflow/mcp.env"
# Local listener inside guest for API reverse tunnel
DEFAULT_GUEST_API_PORT = 18765


def build_everflow_mcp_config(
    *,
    api_url: str,
    token: str,
    project_id: str,
    command: str = DEFAULT_MCP_COMMAND,
) -> dict[str, Any]:
    return {
        "type": "local",
        "command": [command],
        "enabled": True,
        "environment": {
            "EVERFLOW_API_URL": api_url,
            "EVERFLOW_TOKEN": token,
            "EVERFLOW_PROJECT_ID": project_id,
        },
    }


def merge_opencode_mcp(existing: dict[str, Any], mcp_entry: dict[str, Any]) -> dict[str, Any]:
    """Merge everflow MCP entry into opencode.json without clobbering other keys."""
    data = dict(existing) if existing else {}
    data.setdefault("$schema", "https://opencode.ai/config.json")
    mcp_block = data.get("mcp") if isinstance(data.get("mcp"), dict) else {}
    mcp_block = dict(mcp_block)
    mcp_block["everflow"] = mcp_entry
    data["mcp"] = mcp_block
    return data


def write_everflow_mcp_host(
    workspace: Path,
    *,
    api_url: str,
    token: str,
    project_id: str,
    command: str = DEFAULT_MCP_COMMAND,
) -> dict[str, Any]:
    """Write MCP env + opencode.json on a host-accessible workspace path."""
    ws = Path(workspace)
    ef = ws / ".everflow"
    ef.mkdir(parents=True, exist_ok=True)
    env_path = ef / "mcp.env"
    try:
        env_path.write_text(
            f'EVERFLOW_API_URL="{api_url}"\n'
            f'EVERFLOW_TOKEN="{token}"\n'
            f'EVERFLOW_PROJECT_ID="{project_id}"\n',
            encoding="utf-8",
        )
        try:
            env_path.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        return {"configured": False, "error": f"write mcp.env failed: {exc}", "mode": "host"}

    mcp_cfg = build_everflow_mcp_config(
        api_url=api_url, token=token, project_id=project_id, command=command
    )
    cfg_path = ws / OPENCODE_JSON
    existing: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}
    merged = merge_opencode_mcp(existing, mcp_cfg)
    try:
        cfg_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"configured": False, "error": f"write opencode.json failed: {exc}", "mode": "host"}

    return {
        "configured": True,
        "mode": "host",
        "command": command,
        "env_path": str(env_path),
        "project_id": project_id,
        "api_url": api_url,
    }


async def write_everflow_mcp_guest(
    backend: Any,
    sandbox_name: str,
    *,
    api_url: str,
    token: str,
    project_id: str,
    command: str = DEFAULT_MCP_COMMAND,
) -> dict[str, Any]:
    """Write MCP env + opencode.json into the guest workspace via write_fs."""
    mcp_cfg = build_everflow_mcp_config(
        api_url=api_url, token=token, project_id=project_id, command=command
    )
    env_body = (
        f'EVERFLOW_API_URL="{api_url}"\n'
        f'EVERFLOW_TOKEN="{token}"\n'
        f'EVERFLOW_PROJECT_ID="{project_id}"\n'
    )
    try:
        await _guest_write_text(backend, sandbox_name, MCP_ENV_REL, env_body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest mcp.env write failed name=%s: %s", sandbox_name, exc)
        return {"configured": False, "error": f"write mcp.env failed: {exc}", "mode": "guest"}

    oc_raw = await _guest_read_text(backend, sandbox_name, OPENCODE_JSON)
    existing: dict[str, Any] = {}
    if oc_raw:
        try:
            parsed = json.loads(oc_raw)
            if isinstance(parsed, dict):
                existing = parsed
        except json.JSONDecodeError:
            existing = {}
    merged = merge_opencode_mcp(existing, mcp_cfg)
    try:
        await _guest_write_text(
            backend,
            sandbox_name,
            OPENCODE_JSON,
            json.dumps(merged, indent=2) + "\n",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest opencode.json write failed name=%s: %s", sandbox_name, exc)
        return {
            "configured": False,
            "error": f"write opencode.json failed: {exc}",
            "mode": "guest",
        }

    return {
        "configured": True,
        "mode": "guest",
        "command": command,
        "env_path": f"/workspace/{MCP_ENV_REL}",
        "project_id": project_id,
        "api_url": api_url,
    }
