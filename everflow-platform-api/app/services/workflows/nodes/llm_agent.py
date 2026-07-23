"""LangChain agent / OpenAI chat / MCP tool executors."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import httpx

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext

logger = logging.getLogger(__name__)


async def exec_lm_chat_openai(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Language model sub-node — not run on main chain; config stored for agent."""
    del items
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": node.parameters,
        "credentials": node.credentials,
    }
    return [(0, [])]


async def exec_mcp_tool_stub(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Register tool definition for agent (ai_tool sub-node)."""
    del items
    params = node.parameters or {}
    ctx.tool_configs[node.id] = {
        "name": node.name,
        "type": node.type,
        "parameters": params,
        "credentials": node.credentials,
        "endpointUrl": params.get("endpointUrl"),
        "operation": params.get("operation"),
    }
    return [(0, [])]


async def exec_agent(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    # Resolve connected LM + tools from graph
    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    tool_nodes = ctx.graph.ai_inputs(node.id, "ai_tool")

    for ln in lm_nodes:
        await exec_lm_chat_openai(ln, [], ctx=ctx)
    for tn in tool_nodes:
        await exec_mcp_tool_stub(tn, [], ctx=ctx)

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        prompt = evaluate(params.get("text"), ectx)
        system = ""
        options = params.get("options") if isinstance(params.get("options"), dict) else {}
        if options.get("systemMessage"):
            system = str(evaluate(options.get("systemMessage"), ectx) or "")

        # Mock agent
        if ctx.mocks and "agent_output" in ctx.mocks:
            text = ctx.mocks["agent_output"]
            if callable(text):
                text = text(prompt, item.json)
            ni = item.clone()
            ni.json = {**item.json, "output": str(text)}
            out.append(ni)
            continue

        lm_cred: dict[str, Any] = {}
        model = "gpt-4o-mini"
        if lm_nodes:
            lm = lm_nodes[0]
            lm_cred = ctx.resolve_credential(lm, "openAiApi") or {}
            mparam = (lm.parameters or {}).get("model")
            if isinstance(mparam, dict):
                model = str(mparam.get("value") or model)
            elif mparam:
                model = str(mparam)

        api_key = lm_cred.get("apiKey") or lm_cred.get("api_key") or ctx.mocks.get("openai_api_key") if ctx.mocks else None
        base_url = (
            lm_cred.get("url")
            or lm_cred.get("baseUrl")
            or lm_cred.get("base_url")
            or "https://api.openai.com/v1"
        )
        if not api_key:
            # Deterministic offline fallback for tests / missing creds
            summary = _offline_research(prompt, item.json, tool_nodes)
            ni = item.clone()
            ni.json = {**item.json, "output": summary}
            out.append(ni)
            continue

        tools_schema = _tools_for_openai(tool_nodes, ctx)
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": str(prompt)})

        max_tries = node.max_tries or 3
        final_text = ""
        async with httpx.AsyncClient(timeout=120.0) as client:
            for _attempt in range(max_tries):
                body: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                }
                if tools_schema:
                    body["tools"] = tools_schema
                    body["tool_choice"] = "auto"
                resp = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                tool_calls = msg.get("tool_calls") or []
                if tool_calls:
                    messages.append(msg)
                    for tc in tool_calls:
                        result = await _run_tool_call(tc, tool_nodes, ctx)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "content": result,
                            }
                        )
                    continue
                final_text = str(msg.get("content") or "")
                break

        ni = item.clone()
        ni.json = {**item.json, "output": final_text or _offline_research(prompt, item.json, tool_nodes)}
        out.append(ni)
    return [(0, out)]


def _tools_for_openai(tool_nodes: list[ExecNode], ctx: EngineContext) -> list[dict[str, Any]]:
    tools = []
    for tn in tool_nodes:
        name = tn.name.replace(" ", "_").replace("-", "_")[:64]
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Tool from n8n node {tn.name}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search or request query"},
                        },
                    },
                },
            }
        )
    return tools


async def _run_tool_call(
    tc: dict[str, Any],
    tool_nodes: list[ExecNode],
    ctx: EngineContext,
) -> str:
    fn = (tc.get("function") or {})
    name = str(fn.get("name") or "")
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except json.JSONDecodeError:
        args = {"raw": fn.get("arguments")}

    if ctx.mocks and "tool_results" in ctx.mocks:
        tr = ctx.mocks["tool_results"]
        if isinstance(tr, dict) and name in tr:
            return str(tr[name])
        if callable(tr):
            return str(tr(name, args))

    # Match tool node by sanitized name
    node = None
    for tn in tool_nodes:
        sn = tn.name.replace(" ", "_").replace("-", "_")[:64]
        if sn == name or tn.name == name:
            node = tn
            break
    if node is None and tool_nodes:
        node = tool_nodes[0]

    if node is None:
        return json.dumps({"error": "no tool", "name": name})

    # HTTP MCP / RapidAPI style
    params = node.parameters or {}
    endpoint = params.get("endpointUrl")
    if endpoint:
        headers: dict[str, str] = {}
        cred = ctx.resolve_credential(node, "httpMultipleHeadersAuth") or {}
        # headers may be JSON string or dict
        raw_headers = cred.get("headers") or cred.get("header") or {}
        if isinstance(raw_headers, str):
            try:
                raw_headers = json.loads(raw_headers)
            except json.JSONDecodeError:
                raw_headers = {}
        if isinstance(raw_headers, dict):
            headers = {str(k): str(v) for k, v in raw_headers.items()}
        # also common RapidAPI fields
        if cred.get("x-rapidapi-key"):
            headers["X-RapidAPI-Key"] = str(cred["x-rapidapi-key"])
        if cred.get("x-rapidapi-host"):
            headers["X-RapidAPI-Host"] = str(cred["x-rapidapi-host"])
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Many MCP endpoints are POST with JSON body
                r = await client.post(str(endpoint), headers=headers, json={"query": args})
                return r.text[:8000]
        except Exception as exc:
            return json.dumps({"error": str(exc), "tool": node.name})

    return json.dumps({"tool": node.name, "args": args, "note": "no endpoint configured"})


def _offline_research(prompt: Any, item_json: dict[str, Any], tool_nodes: list[ExecNode]) -> str:
    """Deterministic research summary when no LLM key is available."""
    tools = ", ".join(t.name for t in tool_nodes) or "none"
    rows = item_json.get("rows")
    n_rows = len(rows) if isinstance(rows, list) else 0
    keys = list(item_json.keys())[:12]
    return (
        "# Portfolio Research Report\n\n"
        f"## Summary\n\n"
        f"Offline agent run (no OpenAI credential). Prompt length: {len(str(prompt))} chars.\n\n"
        f"- Input fields: {', '.join(keys)}\n"
        f"- Portfolio rows attached: {n_rows}\n"
        f"- Tools available: {tools}\n\n"
        "## Recommendations\n\n"
        "1. **Hold** core positions pending live market tool data.\n"
        "2. **Watch** concentration risk if a single name dominates cost basis.\n"
        "3. **Review** transaction history for recent large buys/sells.\n\n"
        "*Connect an `openAiApi` credential and RapidAPI/MCP tools for live research.*\n"
    )
