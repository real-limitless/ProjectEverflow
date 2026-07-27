"""MCP Trigger executor.

Clean-room n8n ``@n8n/n8n-nodes-langchain.mcpTrigger`` v1.

The MCP Trigger fires when an MCP (Model Context Protocol) message is
received on the configured endpoint. v1 is an in-engine stub: real
transport handling (stdio / sse / streamable-http) is a platform concern,
so the executor just shapes the payload.

Resolution order for the incoming MCP message:

1. ``ctx.mocks['mcp_payload']``
   - callable: invoked as ``mcp_payload(node, ctx)`` and the return value
     is treated as the raw MCP payload
   - non-callable: used as the raw MCP payload directly
2. ``ctx.mocks['trigger_payload']`` fallback (dict-shaped, treated as the
   raw MCP payload)
3. Offline synthetic payload:
   ``{jsonrpc: '2.0', method: 'message', params: {content: 'Mock MCP message', from: 'mock-mcp-client'}}``

The emitted item carries both the original RPC envelope (``jsonrpc``,
``method``, ``params``) and flat fields downstream nodes typically read
(``content``, ``serverName``, ``path``), plus a ``source: 'mcpTrigger'``
marker for routing/log debugging.

Parameters consumed:

- ``serverName`` (default ``'n8n-mcp-server'``) — the configured MCP server
  name to identify the source.
- ``path`` (default ``'/mcp'``) — the URL path the trigger is bound to.

If items list is non-empty (upstream pre-seeded), each existing item is
passed through with the MCP context fields (``serverName``, ``path``,
``source``) merged in so downstream nodes can still identify the trigger
origin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext


_DEFAULT_SERVER_NAME = "n8n-mcp-server"
_DEFAULT_PATH = "/mcp"


def _synthetic_payload() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "method": "message",
        "params": {"content": "Mock MCP message", "from": "mock-mcp-client"},
    }


def _resolve_payload(
    node: ExecNode, ctx: EngineContext
) -> dict[str, Any]:
    """Pick the MCP payload from mocks or fall back to the synthetic one."""
    if isinstance(ctx.mocks, dict):
        mock = ctx.mocks.get("mcp_payload")
        if mock is not None:
            if callable(mock):
                result = mock(node, ctx)
                if isinstance(result, dict):
                    return dict(result)
                # Non-dict callable result: ignore and fall through
            elif isinstance(mock, dict):
                return dict(mock)
            else:
                # Non-dict, non-callable: ignore and fall through
                pass

        fallback = ctx.mocks.get("trigger_payload")
        if isinstance(fallback, dict):
            return dict(fallback)

    return _synthetic_payload()


def _extract_content(params: Any) -> str:
    """Best-effort string extraction of the message body from ``params``."""
    if not isinstance(params, dict):
        return ""
    for key in ("content", "message", "text", "body"):
        val = params.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


async def exec_mcp_trigger(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """MCP Trigger — emit one item per received MCP message.

    See module docstring for the full resolution order and emitted
    payload shape.
    """
    params = node.parameters or {}
    server_name = str(params.get("serverName") or _DEFAULT_SERVER_NAME)
    path = str(params.get("path") or _DEFAULT_PATH)

    payload = _resolve_payload(node, ctx)

    jsonrpc = str(payload.get("jsonrpc") or "2.0")
    method = str(payload.get("method") or "message")
    params_field = payload.get("params")
    if not isinstance(params_field, dict):
        params_field = {}

    content = _extract_content(params_field)

    base: dict[str, Any] = {
        "jsonrpc": jsonrpc,
        "method": method,
        "params": dict(params_field),
        "content": content,
        "serverName": server_name,
        "path": path,
        "source": "mcpTrigger",
    }

    if items:
        # Pass-through mode: keep upstream data, just add MCP context.
        out: list[ExecutionItem] = []
        for item in items:
            merged = dict(item.json)
            merged.setdefault("serverName", server_name)
            merged.setdefault("path", path)
            merged.setdefault("source", "mcpTrigger")
            # Only fill the RPC envelope / content when not already present.
            merged.setdefault("jsonrpc", jsonrpc)
            merged.setdefault("method", method)
            merged.setdefault("params", dict(params_field))
            if "content" not in merged:
                merged["content"] = content
            ni = item.clone()
            ni.json = merged
            out.append(ni)
        return [(0, out)]

    return [(0, [ExecutionItem(json=base)])]
