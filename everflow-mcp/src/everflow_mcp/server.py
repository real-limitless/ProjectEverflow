"""Stdio MCP server exposing Everflow studio tools."""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from everflow_mcp.client import EverflowApiError, EverflowClient, dumps

logger = logging.getLogger("everflow_mcp")

mcp = FastMCP(
    "everflow",
    instructions=(
        "Everflow product control plane for this project. "
        "Use these tools to create knowledge canvases and Everflow agent definitions "
        "(not OpenCode built-in modes). All mutations apply only to the bound project."
    ),
)


def _client() -> EverflowClient:
    return EverflowClient()


def _ok(data: Any) -> str:
    return dumps(data)


def _err(exc: Exception) -> str:
    if isinstance(exc, EverflowApiError):
        return dumps({"error": str(exc), "status_code": exc.status_code, "body": exc.body})
    return dumps({"error": str(exc)})


@mcp.tool()
def everflow_whoami() -> str:
    """Return the authenticated user, bound project, org, sandbox status, and scopes."""
    try:
        return _ok(_client().whoami())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_get_project() -> str:
    """Get the bound Everflow project summary (name, slug, repos, sandbox status)."""
    try:
        return _ok(_client().get_project())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_list_projects() -> str:
    """List accessible projects. v1 returns only the sandbox-bound project (read-only navigation)."""
    try:
        return _ok(_client().list_projects())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_list_canvases() -> str:
    """List knowledge canvases for the project (id, name, status — not full markdown)."""
    try:
        return _ok(_client().list_canvases())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_get_canvas(canvas_id: str) -> str:
    """Get a knowledge canvas including full markdown body."""
    try:
        return _ok(_client().get_canvas(canvas_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_create_canvas(
    name: str,
    content_md: str = "",
    description: str = "",
    origin: str = "created",
) -> str:
    """Create a knowledge canvas (markdown document) in the Everflow Knowledge panel."""
    try:
        return _ok(
            _client().create_canvas(
                name=name,
                description=description or None,
                content_md=content_md,
                origin=origin or "created",
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_update_canvas(
    canvas_id: str,
    name: str | None = None,
    content_md: str | None = None,
    description: str | None = None,
    status: str | None = None,
) -> str:
    """Update a knowledge canvas. Content changes on an indexed canvas mark it stale."""
    try:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if content_md is not None:
            fields["content_md"] = content_md
        if description is not None:
            fields["description"] = description
        if status is not None:
            fields["status"] = status
        return _ok(_client().update_canvas(canvas_id, **fields))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_delete_canvas(canvas_id: str) -> str:
    """Permanently delete a knowledge canvas."""
    try:
        _client().delete_canvas(canvas_id)
        return _ok({"deleted": True, "canvas_id": canvas_id})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_list_agents() -> str:
    """List Everflow project agent definitions (studio Agents panel — not OpenCode modes)."""
    try:
        return _ok(_client().list_agents())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_get_agent(agent_id: str) -> str:
    """Get a full Everflow agent definition (system prompt, tools, active)."""
    try:
        return _ok(_client().get_agent(agent_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_create_agent(
    name: str,
    role: str = "general",
    description: str = "",
    system_prompt: str = "",
    tools: str = "",
    active: bool = True,
) -> str:
    """Create an Everflow agent definition for the studio Agents panel.

    ``tools`` is a comma-separated list of tool names (e.g. ``file_read,git_status``).
    This does not create an OpenCode built-in agent mode.
    """
    try:
        tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []
        return _ok(
            _client().create_agent(
                name=name,
                role=role,
                description=description,
                system_prompt=system_prompt or f"You are {name}.",
                tools=tool_list,
                active=active,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_update_agent(
    agent_id: str,
    name: str | None = None,
    role: str | None = None,
    description: str | None = None,
    system_prompt: str | None = None,
    tools: str | None = None,
    active: bool | None = None,
) -> str:
    """Update an Everflow agent definition. ``tools`` is comma-separated when provided."""
    try:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if role is not None:
            fields["role"] = role
        if description is not None:
            fields["description"] = description
        if system_prompt is not None:
            fields["system_prompt"] = system_prompt
        if tools is not None:
            fields["tools"] = [t.strip() for t in tools.split(",") if t.strip()]
        if active is not None:
            fields["active"] = active
        return _ok(_client().update_agent(agent_id, **fields))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def everflow_delete_agent(agent_id: str) -> str:
    """Delete an Everflow agent definition."""
    try:
        _client().delete_agent(agent_id)
        return _ok({"deleted": True, "agent_id": agent_id})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # Validate env only — do not HTTP-probe on startup (OpenCode times out MCP
    # connect at ~5–30s; reverse-tunnel/API may not be ready yet).
    try:
        _client()
    except Exception as exc:  # noqa: BLE001
        logger.error("invalid Everflow MCP environment: %s", exc)
        raise
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
