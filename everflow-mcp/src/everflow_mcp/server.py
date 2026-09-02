"""Stdio MCP server exposing Everflow studio tools."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from everflow_mcp.client import EverflowApiError, EverflowClient, dumps

logger = logging.getLogger("everflow_mcp")

mcp = FastMCP(
    "everflow",
    instructions=(
        "Everflow product control plane for this project. "
        "Use these tools to create knowledge canvases, Everflow agent definitions "
        "(not OpenCode built-in modes), test suites/cases, registered HTTP tools, "
        "and background jobs (detached long-lived sandbox processes). "
        "\n\n"
        "PROJECT KNOWLEDGE (vector store — CRITICAL):\n"
        "- Project docs, runbooks, passwords, API keys, and secrets live in Knowledge canvases.\n"
        "- They are NOT MCP resources. Do not say knowledge is missing from 'MCP resources'.\n"
        "- ALWAYS call knowledge_search(query) BEFORE answering questions about project "
        "docs, config, passwords, keys, tokens, credentials, or 'knowledge key'.\n"
        "- If search returns hits, quote the chunk text and cite canvas_name.\n"
        "- If search is empty, call list_canvases then get_canvas for likely docs.\n"
        "- Use reindex_canvas after creating/updating a canvas when retrieval should refresh.\n"
        "\n"
        "BROWSER / WEB SURFING:\n"
        "- Full navigate/click/type/snapshot tools come from the separate Playwright MCP "
        "(install marketplace item 'Browser (Playwright)' / id playwright). "
        "Those tools are typically named playwright_* once enabled.\n"
        "- Use browser_status to see if Playwright is enabled, mode (headless|headed), "
        "and Desktop readiness.\n"
        "- Default mode is headless. Call browser_set_mode(mode='headed') when the user "
        "should watch the browser in the Desktop panel; browser_set_mode(mode='headless') "
        "to return to headless. Mode switches restart OpenCode so Playwright MCP respawns.\n"
        "\n"
        "To spin up a website or dev server, prefer create_job (e.g. npm run dev) "
        "over a blocking shell so the process survives and appears in the Jobs panel. "
        "Use get_job_logs to verify startup; stop_job/kill_job to shut down. "
        "Requires a running project sandbox. All mutations apply only to the bound project."
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
async def whoami() -> str:
    """Return the authenticated user, bound project, org, sandbox status, and scopes."""
    try:
        return _ok(await _client().whoami())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def get_project() -> str:
    """Get the bound Everflow project summary (name, slug, repos, sandbox status)."""
    try:
        return _ok(await _client().get_project())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def list_projects() -> str:
    """List accessible projects. v1 returns only the sandbox-bound project (read-only navigation)."""
    try:
        return _ok(await _client().list_projects())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def list_canvases() -> str:
    """List knowledge canvases for the project (id, name, status — not full markdown)."""
    try:
        return _ok(await _client().list_canvases())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def get_canvas(canvas_id: str) -> str:
    """Get a knowledge canvas including full markdown body."""
    try:
        return _ok(await _client().get_canvas(canvas_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def create_canvas(
    name: str,
    content_md: str = "",
    description: str = "",
    origin: str = "created",
) -> str:
    """Create a knowledge canvas (markdown document) in the Everflow Knowledge panel."""
    try:
        return _ok(
            await _client().create_canvas(
                name=name,
                description=description or None,
                content_md=content_md,
                origin=origin or "created",
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def update_canvas(
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
        return _ok(await _client().update_canvas(canvas_id, **fields))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def delete_canvas(canvas_id: str) -> str:
    """Permanently delete a knowledge canvas."""
    try:
        await _client().delete_canvas(canvas_id)
        return _ok({"deleted": True, "canvas_id": canvas_id})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def reindex_canvas(canvas_id: str) -> str:
    """Chunk and embed a knowledge canvas so it can be retrieved by search."""
    try:
        return _ok(await _client().reindex_canvas(canvas_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def knowledge_search(query: str, top_k: int = 5, agent_id: str = "") -> str:
    """Search the project knowledge vector store (indexed canvases) for chunks.

    MUST use this for passwords, API keys, secrets, knowledge keys, credentials,
    runbooks, architecture notes, and any project documentation Q&A.
    This is NOT an MCP resource list — call this tool. Empty resources does not
    mean knowledge is empty. Returns hits with canvas_id, canvas_name, text, score.
    """
    try:
        return _ok(
            await _client().knowledge_search(
                query,
                top_k=top_k,
                agent_id=agent_id or None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def list_agents() -> str:
    """List Everflow project agent definitions (studio Agents panel — not OpenCode modes)."""
    try:
        return _ok(await _client().list_agents())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def get_agent(agent_id: str) -> str:
    """Get a full Everflow agent definition (system prompt, tools, active)."""
    try:
        return _ok(await _client().get_agent(agent_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def create_agent(
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
            await _client().create_agent(
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
async def update_agent(
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
        return _ok(await _client().update_agent(agent_id, **fields))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def delete_agent(agent_id: str) -> str:
    """Delete an Everflow agent definition."""
    try:
        await _client().delete_agent(agent_id)
        return _ok({"deleted": True, "agent_id": agent_id})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def list_test_suites() -> str:
    """List test suites for the project (includes cases and last_status)."""
    try:
        return _ok(await _client().list_test_suites())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def create_test_suite(name: str, description: str = "") -> str:
    """Create a test suite in the Everflow Tests panel."""
    try:
        return _ok(
            await _client().create_test_suite(
                name=name,
                description=description or None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def create_test_case(
    suite_id: str,
    name: str,
    type: str = "unit",
    command: str = "",
) -> str:
    """Create a test case under a suite. ``type`` is unit, e2e, or smoke; ``command`` runs via sandbox shell."""
    try:
        return _ok(
            await _client().create_test_case(
                suite_id,
                name=name,
                type=type or "unit",
                command=command,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def update_test_case(
    suite_id: str,
    case_id: str,
    name: str | None = None,
    type: str | None = None,
    command: str | None = None,
) -> str:
    """Update a test case name, type, or command."""
    try:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if type is not None:
            fields["type"] = type
        if command is not None:
            fields["command"] = command
        return _ok(await _client().update_test_case(suite_id, case_id, **fields))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def delete_test_case(suite_id: str, case_id: str) -> str:
    """Delete a test case from a suite."""
    try:
        await _client().delete_test_case(suite_id, case_id)
        return _ok({"deleted": True, "suite_id": suite_id, "case_id": case_id})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def run_test_suite(suite_id: str) -> str:
    """Run all cases in a suite via sandbox shell; updates each case last_status."""
    try:
        return _ok(await _client().run_test_suite(suite_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def list_http_tools() -> str:
    """List registered HTTP tools for the project (name, method, url_template, enabled)."""
    try:
        return _ok(await _client().list_http_tools())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def call_http_tool(
    tool_id: str,
    path_params_json: str = "{}",
    query_json: str = "{}",
    headers_json: str = "{}",
    body_json: str = "",
) -> str:
    """Execute an enabled HTTP tool by id.

    ``path_params_json`` / ``query_json`` / ``headers_json`` are JSON objects.
    ``body_json`` is optional JSON for the request body (POST/PUT/PATCH).
    SSRF guard blocks private/loopback/link-local/metadata unless the API allows sandbox-internal.
    """
    try:
        path_params = json.loads(path_params_json or "{}")
        query = json.loads(query_json or "{}")
        headers = json.loads(headers_json or "{}")
        if not isinstance(path_params, dict) or not isinstance(query, dict) or not isinstance(headers, dict):
            return _err(ValueError("path_params_json, query_json, and headers_json must be JSON objects"))
        body: Any | None = None
        if body_json and body_json.strip():
            body = json.loads(body_json)
        return _ok(
            await _client().call_http_tool(
                tool_id,
                path_params={str(k): str(v) for k, v in path_params.items()},
                query={str(k): str(v) for k, v in query.items()},
                headers={str(k): str(v) for k, v in headers.items()},
                body=body,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def list_jobs() -> str:
    """List background jobs for this project (title, command, status, pid).

    Jobs are detached sandbox processes managed by Everflow (Jobs panel).
    Requires a running sandbox.
    """
    try:
        return _ok(await _client().list_jobs())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def create_job(title: str, command: str, cwd: str = "") -> str:
    """Start a detached background job in the project sandbox (Jobs panel).

    Use this to spin up websites or long-lived services (e.g. ``npm run dev``,
    ``pnpm dev``, ``python -m http.server``). Prefer this over a blocking shell
    so the process keeps running and is visible in Everflow.

    ``cwd`` is optional (guest path relative to workspace, default sandbox cwd).
    Returns job id, status, and pid. Follow up with ``get_job_logs`` if needed.
    """
    try:
        return _ok(
            await _client().create_job(
                title=title,
                command=command,
                cwd=cwd or None,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def get_job_logs(job_id: str, tail: int = 200) -> str:
    """Tail stdout/stderr logs for a background job (default last 200 lines)."""
    try:
        return _ok(await _client().get_job_logs(job_id, tail=tail))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def update_job(
    job_id: str,
    title: str | None = None,
    command: str | None = None,
    cwd: str | None = None,
) -> str:
    """Update a job's title, command, or cwd. Command/cwd only when the job is not running."""
    try:
        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if command is not None:
            fields["command"] = command
        if cwd is not None:
            fields["cwd"] = cwd
        if not fields:
            return _err(ValueError("Provide at least one of title, command, cwd"))
        return _ok(await _client().update_job(job_id, **fields))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def start_job(job_id: str) -> str:
    """Start a previously stopped background job using its stored command/cwd."""
    try:
        return _ok(await _client().start_job(job_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def stop_job(job_id: str) -> str:
    """Gracefully stop a running background job."""
    try:
        return _ok(await _client().stop_job(job_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def kill_job(job_id: str) -> str:
    """Force-kill a running background job."""
    try:
        return _ok(await _client().kill_job(job_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def restart_job(job_id: str) -> str:
    """Restart a background job (stop if needed, then start with stored command)."""
    try:
        return _ok(await _client().restart_job(job_id))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def list_seats() -> str:
    """List org-chart seats (humans and bots) for this project."""
    try:
        return _ok(await _client().list_seats())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def list_teams() -> str:
    """List @mention teams (e.g. eng, services) for this project."""
    try:
        return _ok(await _client().list_teams())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def compile_run(sentence: str) -> str:
    """Compile a room sentence into a Conductor-owned run graph (Floor does not write code)."""
    try:
        return _ok(await _client().compile_run(sentence))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def bus_send_message(
    from_seat_id: str,
    to_seat_id: str,
    body: str = "",
    run_id: str | None = None,
) -> str:
    """Send an audited bus message from one seat to another. Cycle-detected per run."""
    try:
        return _ok(
            await _client().bus_dispatch(
                "send_message",
                from_seat_id=from_seat_id,
                to_seat_id=to_seat_id,
                run_id=run_id,
                payload={"body": body},
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def bus_handoff(
    from_seat_id: str,
    to_seat_id: str,
    brief: str = "",
    run_id: str | None = None,
) -> str:
    """Close the current seat's phase and open the next with a brief."""
    try:
        return _ok(
            await _client().bus_dispatch(
                "handoff",
                from_seat_id=from_seat_id,
                to_seat_id=to_seat_id,
                run_id=run_id,
                payload={"brief": brief},
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def bus_share_memory(
    name: str,
    body: str,
    scope: str = "project",
    scope_id: str = "",
    from_seat_id: str | None = None,
) -> str:
    """Write a scoped memory block (seat / team / project / org)."""
    try:
        return _ok(
            await _client().bus_dispatch(
                "share_memory",
                from_seat_id=from_seat_id,
                payload={"name": name, "body": body, "scope": scope, "scope_id": scope_id},
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def bus_ask_human(from_seat_id: str, reason: str, run_id: str | None = None) -> str:
    """Park the run and escalate along reports_to. Never dumps to #general."""
    try:
        return _ok(
            await _client().bus_dispatch(
                "ask_human",
                from_seat_id=from_seat_id,
                run_id=run_id,
                payload={"reason": reason},
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def bus_report(
    from_seat_id: str,
    result: str,
    run_id: str | None = None,
    ok: bool = True,
) -> str:
    """Post a structured result back to the originating run/thread."""
    try:
        return _ok(
            await _client().bus_dispatch(
                "report",
                from_seat_id=from_seat_id,
                run_id=run_id,
                payload={"result": result, "ok": ok},
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def browser_status() -> str:
    """Status of the opt-in Playwright browser harness (enabled, mode, desktop, prebake).

    Browse tools themselves are on the playwright MCP after marketplace install.
    """
    try:
        return _ok(await _client().browser_status())
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def browser_set_mode(mode: str, restart_opencode: bool = True) -> str:
    """Set browser mode to headless or headed (visible on project Desktop).

    Args:
        mode: headless (default) or headed / headful / visible.
        restart_opencode: Recycle Playwright MCP so it re-reads the mode file
            (default true). Does not kill OpenCode itself — a full serve restart
            would abort this in-flight MCP tool call.
    """
    try:
        return _ok(
            await _client().browser_set_mode(mode, restart_opencode=restart_opencode)
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
async def delete_job(job_id: str) -> str:
    """Delete a background job (stops if running) and remove its metadata."""
    try:
        return _ok(await _client().delete_job(job_id))
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
