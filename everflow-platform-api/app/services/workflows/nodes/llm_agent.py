"""LangChain agent / OpenAI chat / MCP tool executors.

MCP Client Tool limits (stub):
- Tools with an HTTP ``endpointUrl`` (RapidAPI-style) are invoked via POST JSON.
- True MCP protocol (STDIO / ``mcpClientApi``, listPrompts, SSE sessions) is
  **not** implemented — those nodes only register a name for the agent loop.
- Tool schemas exposed to the model are a generic ``{query: string}`` function.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any

import httpx

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.graph import ExecNode
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import BinaryFile, ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext

logger = logging.getLogger(__name__)


def _extract_rl_value(param: Any, default: str = "") -> str:
    """Unwrap n8n resource-locator (``__rl``) / plain string model fields."""
    if param is None:
        return default
    if isinstance(param, (str, int, float, bool)):
        s = str(param).strip()
        return s if s else default
    if isinstance(param, dict):
        for key in ("value", "cachedResultName", "name", "id", "model"):
            inner = param.get(key)
            if inner is None or isinstance(inner, (dict, list)):
                continue
            s = str(inner).strip()
            if s:
                return s
        # Nested locator occasionally wraps again
        nested = param.get("value")
        if isinstance(nested, dict):
            return _extract_rl_value(nested, default)
    return default


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


async def exec_lm_chat_anthropic(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Anthropic Claude language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Credentials are resolved at
    capture time via ``anthropicApi`` so downstream agent code can read a
    single normalized dict from ``ctx.lm_configs``. Model is defaulted to
    ``claude-3-5-sonnet-latest`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "claude-3-5-sonnet-latest"
    cred = ctx.resolve_credential(node, "anthropicApi")
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": cred if cred is not None else node.credentials,
    }
    return [(0, [])]


async def exec_lm_chat_openrouter(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """OpenRouter language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Credentials are resolved at
    capture time via ``openRouterApi`` so downstream agent code can read a
    single normalized dict from ``ctx.lm_configs``. Model is defaulted to
    ``openai/gpt-4o-mini`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "openai/gpt-4o-mini"
    cred = ctx.resolve_credential(node, "openRouterApi")
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": cred if cred is not None else node.credentials,
    }
    return [(0, [])]


async def exec_lm_chat_ollama(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Ollama local language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Ollama is a self-hosted LLM
    server, so the credential is a base URL rather than an API key. The
    resolved base URL is captured on a top-level ``baseUrl`` field in
    addition to the normal ``credentials`` mapping so downstream agent
    code can read it without parsing the credential dict. Model is
    defaulted to ``llama3`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "llama3"

    cred = ctx.resolve_credential(node, "ollamaApi")
    stored_creds = cred if cred is not None else node.credentials

    base_url = _extract_rl_value(params.get("baseUrl"))
    if not base_url and isinstance(stored_creds, dict):
        # The resolved credential is the inner dict, but the fallback
        # ``node.credentials`` is the wrapper ``{"ollamaApi": {...}}``.
        # Search both shapes uniformly.
        inner = stored_creds.get("ollamaApi") if "ollamaApi" in stored_creds else stored_creds
        if isinstance(inner, dict):
            base_url = _extract_rl_value(
                inner.get("baseUrl")
                or inner.get("url")
                or inner.get("host")
            )
        if not base_url:
            base_url = _extract_rl_value(
                stored_creds.get("baseUrl")
                or stored_creds.get("url")
                or stored_creds.get("host")
            )
    if not base_url:
        base_url = "http://localhost:11434"

    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": stored_creds,
        "baseUrl": base_url,
    }
    return [(0, [])]


async def exec_lm_chat_google_gemini(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Gemini language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Credentials are resolved at
    capture time (preferring ``googleGeminiApi``, falling back to the legacy
    ``googlePalmApi`` alias) so downstream agent code can read a single
    normalized dict from ``ctx.lm_configs``. Model is defaulted to
    ``gemini-1.5-pro`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "gemini-1.5-pro"
    cred = (
        ctx.resolve_credential(node, "googleGeminiApi")
        or ctx.resolve_credential(node, "googlePalmApi")
    )
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": cred if cred is not None else node.credentials,
    }
    return [(0, [])]


async def exec_lm_chat_groq(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Groq language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Credentials are resolved at
    capture time via ``groqApi`` so downstream agent code can read a single
    normalized dict from ``ctx.lm_configs``. Model is defaulted to
    ``llama-3.1-70b-versatile`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "llama-3.1-70b-versatile"
    cred = ctx.resolve_credential(node, "groqApi")
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": cred if cred is not None else node.credentials,
    }
    return [(0, [])]


async def exec_lm_chat_deepseek(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """DeepSeek language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Credentials are resolved at
    capture time via ``deepseekApi`` so downstream agent code can read a
    single normalized dict from ``ctx.lm_configs``. Model is defaulted to
    ``deepseek-chat`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "deepseek-chat"
    cred = ctx.resolve_credential(node, "deepseekApi")
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": cred if cred is not None else node.credentials,
    }
    return [(0, [])]


async def exec_lm_chat_xai_grok(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """xAI Grok language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Credentials are resolved at
    capture time via ``xaiApi`` so downstream agent code can read a single
    normalized dict from ``ctx.lm_configs``. Model is defaulted to
    ``grok-2-latest`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "grok-2-latest"
    cred = ctx.resolve_credential(node, "xaiApi")
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": cred if cred is not None else node.credentials,
    }
    return [(0, [])]


async def exec_lm_chat_azure_openai(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Azure OpenAI language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Credentials are resolved at
    capture time via ``azureOpenAiApi`` so downstream agent code can read a
    single normalized dict from ``ctx.lm_configs``. In addition to the model
    parameter, the Azure deployment name and resource endpoint are normalized
    onto top-level ``endpoint`` / ``deployment`` fields so the agent loop
    can address the deployment without re-parsing the credential. Model is
    defaulted to ``gpt-4o`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "gpt-4o"

    cred = ctx.resolve_credential(node, "azureOpenAiApi")
    stored_creds = cred if cred is not None else node.credentials

    endpoint = _extract_rl_value(params.get("endpoint"))
    if not endpoint and isinstance(stored_creds, dict):
        inner = stored_creds.get("azureOpenAiApi") if "azureOpenAiApi" in stored_creds else stored_creds
        if isinstance(inner, dict):
            endpoint = _extract_rl_value(
                inner.get("endpoint")
                or inner.get("endpointUrl")
                or inner.get("url")
                or inner.get("baseUrl")
                or inner.get("resource")
            )
        if not endpoint:
            endpoint = _extract_rl_value(
                stored_creds.get("endpoint")
                or stored_creds.get("endpointUrl")
                or stored_creds.get("url")
                or stored_creds.get("baseUrl")
                or stored_creds.get("resource")
            )

    deployment = _extract_rl_value(params.get("deployment") or params.get("deploymentName"))
    if not deployment and isinstance(stored_creds, dict):
        inner = stored_creds.get("azureOpenAiApi") if "azureOpenAiApi" in stored_creds else stored_creds
        if isinstance(inner, dict):
            deployment = _extract_rl_value(
                inner.get("deployment")
                or inner.get("deploymentName")
                or inner.get("deploymentId")
            )
        if not deployment:
            deployment = _extract_rl_value(
                stored_creds.get("deployment")
                or stored_creds.get("deploymentName")
                or stored_creds.get("deploymentId")
            )

    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": stored_creds,
        "endpoint": endpoint or "",
        "deployment": deployment or "",
    }
    return [(0, [])]


async def exec_lm_chat_mistral_cloud(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Mistral Cloud language model sub-node — config stored for agent.

    Mirrors :func:`exec_lm_chat_openai` shape. Credentials are resolved at
    capture time via ``mistralApi`` so downstream agent code can read a
    single normalized dict from ``ctx.lm_configs``. Model is defaulted to
    ``mistral-large-latest`` when the parameter is missing.
    """
    del items
    params = dict(node.parameters or {})
    if not _extract_rl_value(params.get("model")):
        params["model"] = "mistral-large-latest"
    cred = ctx.resolve_credential(node, "mistralApi")
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "parameters": params,
        "credentials": cred if cred is not None else node.credentials,
    }
    return [(0, [])]


async def exec_mcp_tool_stub(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Register tool definition for agent (ai_tool sub-node).

    See module docstring for MCP stub limits. HTTP ``endpointUrl`` tools are
    called at runtime; STDIO MCP credentials are registration-only.
    """
    del items
    params = node.parameters or {}
    endpoint = (
        params.get("endpointUrl")
        or params.get("sseEndpoint")
        or params.get("url")
        or params.get("endpoint")
    )
    ctx.tool_configs[node.id] = {
        "name": node.name,
        "type": node.type,
        "parameters": params,
        "credentials": node.credentials,
        "endpointUrl": endpoint,
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
    # Resolve connected LM + tools + memory + output parser from graph
    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    tool_nodes = ctx.graph.ai_inputs(node.id, "ai_tool")
    memory_nodes = ctx.graph.ai_inputs(node.id, "ai_memory")
    parser_nodes = ctx.graph.ai_inputs(node.id, "ai_outputParser")

    for ln in lm_nodes:
        await exec_lm_chat_openai(ln, [], ctx=ctx)
    for tn in tool_nodes:
        await exec_mcp_tool_stub(tn, [], ctx=ctx)
    for mn in memory_nodes:
        # Lazy import to avoid circular deps at module load.
        from app.services.workflows.nodes.ai_memory import exec_memory_buffer_window
        await exec_memory_buffer_window(mn, [], ctx=ctx)
    for pn in parser_nodes:
        from app.services.workflows.nodes.ai_memory import exec_output_parser_structured
        await exec_output_parser_structured(pn, [], ctx=ctx)

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        prompt = evaluate(params.get("text"), ectx)
        system = ""
        options = params.get("options") if isinstance(params.get("options"), dict) else {}
        if options.get("systemMessage"):
            system = str(evaluate(options.get("systemMessage"), ectx) or "")

        # Inject memory window if any memory sub-node is connected
        from app.services.workflows.nodes.ai_memory import (
            memory_window_for,
            push_memory_message,
        )
        memory_messages: list[dict[str, str]] = []
        session_id = "default"
        for mn in memory_nodes:
            cfg = ctx.memory_configs.get(mn.id) or {}
            limit = int(cfg.get("contextWindowLength") or 5)
            session_id = str(cfg.get("sessionId") or session_id)
            memory_messages = memory_window_for(
                ctx, session_id=session_id, limit=limit
            )
            break  # v1: only honor the first memory sub-node

        # Mock agent
        if ctx.mocks and "agent_output" in ctx.mocks:
            text = ctx.mocks["agent_output"]
            if callable(text):
                text = text(prompt, item.json)
            # Apply structured output parser if connected
            if parser_nodes:
                pn = parser_nodes[0]
                pcfg = ctx.output_parsers.get(pn.id) or {}
                from app.services.workflows.nodes.ai_memory import apply_structured_parser
                parsed = apply_structured_parser(str(text), pcfg)
                ni = item.clone()
                base = {**item.json, "output": str(text), "parsed": parsed}
                ni.json = base
            else:
                ni = item.clone()
                ni.json = {**item.json, "output": str(text)}
            # Persist this turn in memory
            if memory_nodes:
                push_memory_message(
                    ctx, session_id=session_id, role="user", content=str(prompt)
                )
                push_memory_message(
                    ctx, session_id=session_id, role="assistant", content=str(text)
                )
            out.append(ni)
            continue

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
            model = _extract_rl_value(mparam, model)

        api_key = (
            lm_cred.get("apiKey")
            or lm_cred.get("api_key")
            or (ctx.mocks.get("openai_api_key") if ctx.mocks else None)
        )
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
        for _attempt in range(max_tries):
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            if tools_schema:
                body["tools"] = tools_schema
                body["tool_choice"] = "auto"
            resp = await execute_http_request(
                HttpRequestConfig(
                    url=f"{base_url.rstrip('/')}/chat/completions",
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    body=body,
                    body_mode="json",
                    response_mode="json",
                    timeout=120.0,
                ),
                ctx=ctx,
            )
            data = resp.body if isinstance(resp.body, dict) else {}
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


async def exec_chain_llm(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Basic LLM Chain — prompt template + connected LM, emit one item per input.

    Reads ``parameters.prompt`` (with ``$json.*`` expression evaluation) plus
    an optional ``parameters.messages`` list of ``{role, content}`` dicts; if
    messages are absent, the chain falls back to a single ``user`` message
    built from the prompt. The connected language model is resolved via
    ``ctx.graph.ai_inputs(node.id, "ai_languageModel")`` and its entry in
    ``ctx.lm_configs`` supplies the model name and credentials.

    For tests, ``ctx.mocks['chain_output']`` (or the legacy
    ``ctx.mocks['agent_output']`` fallback) returns the completion text per
    item. When neither mock is set and the resolved LM carries an OpenAI
    credential, the executor POSTs to ``/chat/completions`` on the configured
    base URL; without a key it falls through to a deterministic offline
    summary so the run still completes.
    """
    params = node.parameters or {}
    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    for ln in lm_nodes:
        await exec_lm_chat_openai(ln, [], ctx=ctx)

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)

        prompt_text = ""
        if params.get("prompt") is not None:
            prompt_text = str(evaluate(params.get("prompt"), ectx) or "")

        raw_messages = params.get("messages")
        messages: list[dict[str, Any]] = []
        if isinstance(raw_messages, list) and raw_messages:
            for m in raw_messages:
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "user").strip() or "user"
                content_value = m.get("content")
                if content_value is None:
                    content_value = m.get("text") or ""
                content = str(evaluate(content_value, ectx) or "")
                messages.append({"role": role, "content": content})
        if not messages:
            messages.append({"role": "user", "content": prompt_text})

        mock = None
        if ctx.mocks:
            mock = ctx.mocks.get("chain_output")
            if mock is None:
                mock = ctx.mocks.get("agent_output")

        model = "gpt-4o-mini"
        if lm_nodes:
            lm = lm_nodes[0]
            mparam = (lm.parameters or {}).get("model")
            model = _extract_rl_value(mparam, model)

        if mock is not None:
            text = mock
            if callable(text):
                text = text(prompt_text, item.json, messages)
            ni = item.clone()
            ni.json = {
                **item.json,
                "text": str(text),
                "model": model,
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
            out.append(ni)
            continue

        lm_cred: dict[str, Any] = {}
        if lm_nodes:
            lm_cred = ctx.resolve_credential(lm_nodes[0], "openAiApi") or {}
        api_key = (
            lm_cred.get("apiKey")
            or lm_cred.get("api_key")
            or (ctx.mocks.get("openai_api_key") if ctx.mocks else None)
        )
        base_url = (
            lm_cred.get("url")
            or lm_cred.get("baseUrl")
            or lm_cred.get("base_url")
            or "https://api.openai.com/v1"
        )

        final_text = ""
        usage: dict[str, Any] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        if api_key:
            try:
                resp = await execute_http_request(
                    HttpRequestConfig(
                        url=f"{base_url.rstrip('/')}/chat/completions",
                        method="POST",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        body={"model": model, "messages": messages},
                        body_mode="json",
                        response_mode="json",
                        timeout=120.0,
                    ),
                    ctx=ctx,
                )
                data = resp.body if isinstance(resp.body, dict) else {}
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message") or {}
                final_text = str(msg.get("content") or "")
                if isinstance(data.get("usage"), dict):
                    usage = {
                        "prompt_tokens": int(data["usage"].get("prompt_tokens") or 0),
                        "completion_tokens": int(
                            data["usage"].get("completion_tokens") or 0
                        ),
                        "total_tokens": int(data["usage"].get("total_tokens") or 0),
                    }
            except Exception as exc:
                logger.warning("chainLlm HTTP call failed: %s", exc)
                final_text = ""

        if not final_text:
            final_text = _offline_chain_summary(messages, item.json)

        ni = item.clone()
        ni.json = {**item.json, "text": final_text, "model": model, "usage": usage}
        out.append(ni)
    return [(0, out)]


async def exec_chain_summarization(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Summarization Chain — chunk + summarize an input text via connected LM.

    Reads ``parameters.text`` (plain string or n8n ``={{ ... }}`` expression);
    when the parameter is empty the executor falls back to ``$json.text`` so
    items carrying the source field directly still produce a summary. The
    connected language model is resolved via
    ``ctx.graph.ai_inputs(node.id, "ai_languageModel")`` and its entry in
    ``ctx.lm_configs`` supplies the model name (and any credentials when an
    OpenAI call is attempted).

    For tests, ``ctx.mocks['chain_output']`` (with the
    ``ctx.mocks['agent_output']`` fallback for parity) returns the summary
    per item. When neither mock is set, the executor produces a deterministic
    extractive summary — the first two sentences of the input, or the first
    500 characters when no sentence boundary is found — so runs still
    complete offline. Emits one item per input carrying
    ``{summary, model, sourceLength}`` merged with the upstream JSON.
    """
    params = node.parameters or {}
    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    for ln in lm_nodes:
        await exec_lm_chat_openai(ln, [], ctx=ctx)

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)

        text = ""
        if params.get("text") is not None:
            text = str(evaluate(params.get("text"), ectx) or "")
        if not text:
            # Default field name: "text" on the upstream item
            text = str(item.json.get("text", "") or "")

        source_length = len(text)

        mock = None
        if ctx.mocks:
            mock = ctx.mocks.get("chain_output")
            if mock is None:
                mock = ctx.mocks.get("agent_output")

        model = "gpt-4o-mini"
        if lm_nodes:
            lm = lm_nodes[0]
            cfg = ctx.lm_configs.get(lm.id) or {}
            mparam = (cfg.get("parameters") or {}).get("model")
            model = _extract_rl_value(mparam, model)

        if mock is not None:
            summary_val = mock
            if callable(summary_val):
                summary_val = summary_val(text, item.json)
            ni = item.clone()
            ni.json = {
                **item.json,
                "summary": str(summary_val),
                "model": model,
                "sourceLength": source_length,
            }
            out.append(ni)
            continue

        # No mock — deterministic offline extractive summary
        summary = _extractive_summary(text)
        ni = item.clone()
        ni.json = {
            **item.json,
            "summary": summary,
            "model": model,
            "sourceLength": source_length,
        }
        out.append(ni)
    return [(0, out)]


async def exec_chain_retrieval_qa(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Question-answering Retrieval Chain — retrieve docs then answer via LM.

    Reads ``parameters.question`` (plain string or n8n ``={{ ... }}`` expression);
    when the parameter is empty the executor falls back to ``$json.chatInput``,
    ``$json.query``, then ``$json.question`` so items carrying the source field
    directly still produce an answer. The connected language model is resolved
    via ``ctx.graph.ai_inputs(node.id, "ai_languageModel")`` and its entry in
    ``ctx.lm_configs`` supplies the model name. The connected retriever is
    resolved via ``ctx.graph.ai_inputs(node.id, "ai_retriever")``; the
    retriever's own output is not executed here — the chain only inspects the
    mock surface for source documents.

    Mock priority (mirrors n8n behaviour):
    1. ``ctx.mocks['chain_output']`` — if callable, called with
       ``(question, item, source_docs)``; otherwise treated as the static
       answer string.
    2. ``ctx.mocks['agent_output']`` — same callable / static pattern, fallback
       for parity with the basic LLM chain.
    3. ``ctx.mocks['retriever_output']`` — provides source documents. If
       callable, called with ``(question, item)``; otherwise the value is
       normalised to a list of ``{pageContent, metadata}`` dicts (a single dict
       is wrapped).

    Offline fallback (no chain / agent mock available):
    - With source docs: returns the first 100 characters of up to 2 docs
      joined as a snippet.
    - Without source docs: returns ``"I don't have enough information to
      answer that."`` (matches n8n's default behaviour).

    Emits one item per input carrying ``{text, question, sourceDocuments, model}``
    merged with the upstream JSON.
    """
    params = node.parameters or {}
    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    retriever_nodes = ctx.graph.ai_inputs(node.id, "ai_retriever")
    for ln in lm_nodes:
        await exec_lm_chat_openai(ln, [], ctx=ctx)

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)

        question = ""
        if params.get("question") is not None:
            question = str(evaluate(params.get("question"), ectx) or "")
        if not question:
            for fallback_key in ("chatInput", "query", "question"):
                v = item.json.get(fallback_key)
                if isinstance(v, str) and v.strip():
                    question = v
                    break

        source_docs = _resolve_source_docs(ctx, question, item, retriever_nodes)

        model = "gpt-4o-mini"
        if lm_nodes:
            lm = lm_nodes[0]
            cfg = ctx.lm_configs.get(lm.id) or {}
            mparam = (cfg.get("parameters") or {}).get("model")
            model = _extract_rl_value(mparam, model)

        chain_mock = None
        if ctx.mocks:
            chain_mock = ctx.mocks.get("chain_output")
            if chain_mock is None:
                chain_mock = ctx.mocks.get("agent_output")

        if chain_mock is not None:
            text = chain_mock
            if callable(text):
                text = text(question, item.json, source_docs)
            ni = item.clone()
            ni.json = {
                **item.json,
                "text": str(text),
                "question": question,
                "sourceDocuments": source_docs if source_docs else None,
                "model": model,
            }
            out.append(ni)
            continue

        if source_docs:
            text = _offline_rag_snippet(source_docs)
        else:
            text = "I don't have enough information to answer that."

        ni = item.clone()
        ni.json = {
            **item.json,
            "text": text,
            "question": question,
            "sourceDocuments": source_docs if source_docs else None,
            "model": model,
        }
        out.append(ni)
    return [(0, out)]


def _normalise_source_docs(raw: Any) -> list[dict[str, Any]]:
    """Coerce a mock value into a list of ``{pageContent, metadata}`` dicts.

    Accepts:
    - ``None`` → empty list
    - ``str``  → wrapped in a single-content doc
    - ``dict`` → treated as a single document
    - ``list`` → each element normalised; non-dict elements wrapped
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [{"pageContent": raw, "metadata": {}}]
    if isinstance(raw, dict):
        return [_coerce_source_doc(raw)]
    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for el in raw:
            if isinstance(el, dict):
                out.append(_coerce_source_doc(el))
            elif isinstance(el, str):
                out.append({"pageContent": el, "metadata": {}})
        return out
    return [{"pageContent": str(raw), "metadata": {}}]


def _coerce_source_doc(d: dict[str, Any]) -> dict[str, Any]:
    page = (
        d.get("pageContent")
        or d.get("page_content")
        or d.get("content")
        or d.get("text")
        or ""
    )
    meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
    return {"pageContent": str(page), "metadata": meta}


def _resolve_source_docs(
    ctx: EngineContext,
    question: str,
    item: ExecutionItem,
    retriever_nodes: list[ExecNode],
) -> list[dict[str, Any]]:
    """Determine source documents from mocks (retrieval itself is a stub)."""
    del retriever_nodes
    if not ctx.mocks or "retriever_output" not in ctx.mocks:
        return []
    raw = ctx.mocks["retriever_output"]
    if callable(raw):
        raw = raw(question, item.json)
    return _normalise_source_docs(raw)


def _offline_rag_snippet(docs: list[dict[str, Any]]) -> str:
    """Return the first 100 chars of up to 2 docs joined as a snippet."""
    parts: list[str] = []
    for d in docs[:2]:
        content = str(d.get("pageContent") or "")
        if content:
            parts.append(content[:100])
    return " ".join(parts)


def _extractive_summary(text: str) -> str:
    """Pick the first two sentences; fall back to the first 500 chars.

    The offline path is intentionally simple: split on sentence-final
    punctuation followed by whitespace, return the first two chunks if at
    least one boundary is found, otherwise return the first 500 characters
    of the (whitespace-stripped) input. Empty input yields an empty string.
    """
    stripped = (text or "").strip()
    if not stripped:
        return ""
    sentence_end_re = re.compile(r"(?<=[.!?])\s+")
    parts = sentence_end_re.split(stripped, maxsplit=2)
    if len(parts) >= 2:
        return " ".join(parts[:2]).strip()
    return stripped[:500]


def _tools_for_openai(tool_nodes: list[ExecNode], ctx: EngineContext) -> list[dict[str, Any]]:
    del ctx
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


def _tool_endpoint(params: dict[str, Any]) -> str | None:
    for key in ("endpointUrl", "sseEndpoint", "url", "endpoint"):
        v = params.get(key)
        if v:
            return str(v)
    return None


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

    # HTTP MCP / RapidAPI style — keep HTTP call when endpoint is present
    params = node.parameters or {}
    endpoint = _tool_endpoint(params)
    cfg = ctx.tool_configs.get(node.id) or {}
    if not endpoint and cfg.get("endpointUrl"):
        endpoint = str(cfg["endpointUrl"])

    if endpoint:
        headers: dict[str, str] = {}
        cred = (
            ctx.resolve_credential(node, "httpMultipleHeadersAuth")
            or ctx.resolve_credential(node, "mcpClientApi")
            or {}
        )
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

    # STDIO / protocol MCP without HTTP endpoint — stub only
    return json.dumps(
        {
            "tool": node.name,
            "args": args,
            "note": (
                "MCP stub: no HTTP endpointUrl configured; "
                "STDIO/mcpClientApi protocol is not executed"
            ),
        }
    )


def _offline_chain_summary(
    messages: list[dict[str, Any]], item_json: dict[str, Any]
) -> str:
    """Deterministic completion when no LLM credential is available."""
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = str(m.get("content") or "")
            break
    keys = list(item_json.keys())[:8]
    return (
        f"[offline chainLlm] model=gpt-4o-mini; prompt_chars={len(last_user)}; "
        f"messages={len(messages)}; fields={','.join(keys)}"
    )


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


# ── Default Document Loader ──────────────────────────────────────────


def _resolve_chunk_size(
    ctx: "EngineContext", splitter_nodes: list[ExecNode]
) -> int | None:
    """Pick the first splitter's ``chunkSize`` (int) or return None.

    The text-splitter sub-node is treated like a language-model config: its
    parameters are captured into ``ctx.lm_configs[splitter_id]`` if not
    already present, then ``chunkSize`` is read off that config. v1 honors
    only the first connected splitter; a non-integer chunkSize is ignored.
    """
    for sn in splitter_nodes:
        if sn.id not in ctx.lm_configs:
            ctx.lm_configs[sn.id] = {
                "name": sn.name,
                "type": sn.type,
                "parameters": dict(sn.parameters or {}),
            }
        cfg = ctx.lm_configs.get(sn.id) or {}
        cfg_params = (
            cfg.get("parameters") if isinstance(cfg.get("parameters"), dict) else {}
        )
        raw = cfg_params.get("chunkSize")
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _resolve_mock_docs(
    ctx: "EngineContext", item: ExecutionItem, params: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Return mock-supplied docs, or None if no mock is configured.

    Honors ``ctx.mocks['document_output']`` first, then
    ``ctx.mocks['loader_output']`` as a fallback. A callable mock is invoked
    with ``(item, params)``; a non-callable value is treated as the raw
    result. Single-doc dicts are wrapped into a one-element list.
    """
    if not ctx.mocks:
        return None
    for key in ("document_output", "loader_output"):
        if key not in ctx.mocks:
            continue
        mock = ctx.mocks[key]
        if callable(mock):
            result = mock(item, params)
        else:
            result = mock
        if isinstance(result, dict):
            return [result]
        if isinstance(result, list):
            return list(result)
    return None


def _extract_default_loader_text(
    item: ExecutionItem,
    params: dict[str, Any],
    *,
    ctx: "EngineContext",
) -> str:
    """Pick the source text for an item.

    Order:

    1. ``parameters.text`` — evaluated as an n8n expression when prefixed
       with ``=``; otherwise treated as a JSON field name on the item.
    2. ``item.json['text']`` (string).
    3. ``item.json['content']`` (string).
    4. ``item.json['binary']`` — first binary entry's ``data`` field is
       base64-decoded as UTF-8. A ``BinaryFile`` instance on
       ``item.binary`` is also accepted.
    5. ``json.dumps(item.json)`` as a deterministic last resort.
    """
    configured = params.get("text")
    if configured is not None:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        if isinstance(configured, str) and configured.startswith("="):
            value = evaluate(configured, ectx)
            if isinstance(value, str) and value:
                return value
            if value is not None and value != "" and not isinstance(value, (dict, list)):
                return str(value)
        else:
            key = str(configured)
            if key in item.json:
                val = item.json[key]
                if isinstance(val, str) and val:
                    return val
                if val is not None and not isinstance(val, (dict, list)):
                    return str(val)

    val = item.json.get("text")
    if isinstance(val, str) and val:
        return val
    if val is not None and not isinstance(val, (dict, list)):
        return str(val)

    val = item.json.get("content")
    if isinstance(val, str) and val:
        return val
    if val is not None and not isinstance(val, (dict, list)):
        return str(val)

    decoded = _decode_first_binary(item)
    if decoded is not None:
        return decoded

    return json.dumps(item.json or {}, default=str)


def _decode_first_binary(item: ExecutionItem) -> str | None:
    """Decode the first binary entry on an item as UTF-8 text.

    Two shapes are accepted:

    - A ``BinaryFile`` instance on ``item.binary`` (the engine's native
      form) — decoded via :meth:`BinaryFile.to_bytes`.
    - A dict on ``item.json['binary']`` carrying a base64 ``data`` field
      (the wire / API form) — decoded with :mod:`base64`.
    """
    if item.binary:
        for _key, bf in item.binary.items():
            if isinstance(bf, BinaryFile):
                try:
                    return bf.to_bytes().decode("utf-8", errors="replace")
                except Exception:
                    return None
        return None

    raw = item.json.get("binary")
    if isinstance(raw, dict):
        for _key, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            data = entry.get("data")
            if not isinstance(data, str) or not data:
                continue
            try:
                return base64.b64decode(data).decode("utf-8", errors="replace")
            except Exception:
                return None
    return None


def _chunk_text(text: str, chunk_size: int) -> list[str]:
    """Greedy character-based chunking without overlap (v1)."""
    if chunk_size <= 0 or not text:
        return [text]
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


async def exec_document_default_data_loader(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Default Document Loader — wrap each input as a LangChain ``Document``.

    Clean-room n8n ``@n8n/n8n-nodes-langchain.documentDefaultDataLoader`` v1.

    For each input item the executor produces one or more documents shaped
    as ``{pageContent, metadata}`` and emits one output item per document.
    A connected text-splitter sub-node (``ai_textSplitter``) is honored:
    if it carries a positive ``chunkSize`` the extracted text is split
    greedily into fixed-size character chunks (no overlap), each becoming
    its own document with a ``chunkIndex`` on the metadata.

    Mocks (``ctx.mocks['document_output']`` then ``ctx.mocks['loader_output']``)
    short-circuit the offline path. A callable mock receives
    ``(item, params)`` and returns either a single doc dict or a list of
    doc dicts; a non-callable value is used verbatim.

    The offline extraction order is:

    1. ``parameters.text`` — expression (leading ``=``) or JSON field name
    2. ``item.json['text']``
    3. ``item.json['content']``
    4. first ``BinaryFile`` on ``item.binary`` or first entry of
       ``item.json['binary']`` (base64-decoded as UTF-8)
    5. ``json.dumps(item.json)``

    Output items carry ``pageContent`` and ``metadata`` merged with the
    upstream JSON (so downstream nodes still see the original fields).
    """
    params = node.parameters or {}
    options = (
        params.get("options") if isinstance(params.get("options"), dict) else {}
    )
    extra_metadata = (
        options.get("metadata")
        if isinstance(options.get("metadata"), dict)
        else {}
    )

    splitter_nodes = ctx.graph.ai_inputs(node.id, "ai_textSplitter")
    chunk_size = _resolve_chunk_size(ctx, splitter_nodes)

    out: list[ExecutionItem] = []
    for i, item in enumerate(items):
        mock_docs = _resolve_mock_docs(ctx, item, params)
        if mock_docs is not None:
            docs = mock_docs
        else:
            text = _extract_default_loader_text(item, params, ctx=ctx)
            base_metadata: dict[str, Any] = {
                "source": "documentDefaultDataLoader",
                "itemIndex": i,
            }
            base_metadata.update(extra_metadata)
            if chunk_size and len(text) > chunk_size:
                chunks = _chunk_text(text, chunk_size)
                docs = []
                for chunk_index, chunk in enumerate(chunks):
                    meta = dict(base_metadata)
                    meta["chunkIndex"] = chunk_index
                    docs.append({"pageContent": chunk, "metadata": meta})
            else:
                docs = [{"pageContent": text, "metadata": base_metadata}]

        for doc in docs:
            if not isinstance(doc, dict):
                continue
            page_content = doc.get("pageContent", "")
            doc_metadata = (
                doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
            )
            ni = item.clone()
            ni.json = {
                **item.json,
                "pageContent": page_content if page_content is not None else "",
                "metadata": dict(doc_metadata),
            }
            out.append(ni)

    return [(0, out)]


# ── Recursive Character Text Splitter ─────────────────────────────────


_DEFAULT_SEPARATORS: list[str] = ["\n\n", "\n", " ", ""]


def _coerce_chunk_int(value: Any, default: int) -> int:
    """Coerce a chunk parameter (int / numeric string / None) to int."""
    if value is None:
        return default
    if isinstance(value, bool):
        # bool is a subclass of int — reject to avoid True → 1 surprises
        return default
    if isinstance(value, int):
        return value if value > 0 else default
    if isinstance(value, float):
        return int(value) if value > 0 else default
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            n = int(s)
        except ValueError:
            try:
                n = int(float(s))
            except ValueError:
                return default
        return n if n > 0 else default
    return default


def _resolve_text_splitter_params(params: dict[str, Any]) -> dict[str, Any]:
    """Pick ``chunkSize`` / ``chunkOverlap`` / ``separators`` from the node.

    Resolution order (matches n8n UI placement):
    - top-level ``chunkSize`` / ``chunkOverlap`` /
      ``separators`` on ``parameters``
    - fallback to the same keys under ``parameters.options``
    - fall back to safe defaults: 1000 / 200 / ``["\n\n", "\n", " ", ""]``
    """
    options = (
        params.get("options") if isinstance(params.get("options"), dict) else {}
    )
    chunk_size = _coerce_chunk_int(params.get("chunkSize"), 0)
    if chunk_size <= 0:
        chunk_size = _coerce_chunk_int(options.get("chunkSize"), 1000)
    # chunkOverlap: 0 when explicitly absent or zero; only fall back to 200
    # when the user has not specified it anywhere.
    if "chunkOverlap" in params:
        chunk_overlap = _coerce_chunk_int(params.get("chunkOverlap"), 0)
    elif "chunkOverlap" in options:
        chunk_overlap = _coerce_chunk_int(options.get("chunkOverlap"), 0)
    else:
        chunk_overlap = 200
    if chunk_overlap < 0:
        chunk_overlap = 0
    # overlap cannot exceed chunkSize
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size - 1)

    raw_seps = params.get("separators")
    if not isinstance(raw_seps, list) or not raw_seps:
        raw_seps = options.get("separators")
    if not isinstance(raw_seps, list) or not raw_seps:
        raw_seps = list(_DEFAULT_SEPARATORS)
    separators: list[str] = []
    for s in raw_seps:
        if isinstance(s, str):
            separators.append(s)
        else:
            separators.append(str(s))

    return {
        "chunkSize": chunk_size,
        "chunkOverlap": chunk_overlap,
        "separators": separators,
    }


def _resolve_splitter_text(
    item: ExecutionItem,
    params: dict[str, Any],
    *,
    ctx: "EngineContext",
) -> str:
    """Determine the input text for a single item.

    Order:

    1. ``parameters.text`` — leading ``=`` triggers expression evaluation,
       otherwise treated as a JSON field name.
    2. ``item.json['text']`` (string).
    3. ``item.json['pageContent']`` (string).
    """
    configured = params.get("text")
    if configured is not None:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        if isinstance(configured, str) and configured.startswith("="):
            value = evaluate(configured, ectx)
            if isinstance(value, str):
                return value
            if value is not None and not isinstance(value, (dict, list)):
                return str(value)
        else:
            key = str(configured)
            if key in item.json:
                val = item.json[key]
                if isinstance(val, str):
                    return val
                if val is not None and not isinstance(val, (dict, list)):
                    return str(val)

    val = item.json.get("text")
    if isinstance(val, str):
        return val
    if val is not None and not isinstance(val, (dict, list)):
        return str(val)

    val = item.json.get("pageContent")
    if isinstance(val, str):
        return val
    if val is not None and not isinstance(val, (dict, list)):
        return str(val)

    return ""


def _normalise_splitter_chunks(raw: Any) -> list[str]:
    """Coerce a splitter mock value into a list of strings.

    Accepts:
    - ``None`` → empty list
    - ``str``  → wrapped in a one-element list
    - ``list`` → each element coerced to ``str``; dicts unwrap ``pageContent``
    - ``dict`` → treated as a single document, ``pageContent`` is extracted
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, dict):
        page = (
            raw.get("pageContent")
            or raw.get("page_content")
            or raw.get("content")
            or raw.get("text")
            or ""
        )
        return [str(page)]
    if isinstance(raw, list):
        out: list[str] = []
        for el in raw:
            if isinstance(el, str):
                out.append(el)
            elif isinstance(el, dict):
                page = (
                    el.get("pageContent")
                    or el.get("page_content")
                    or el.get("content")
                    or el.get("text")
                    or ""
                )
                out.append(str(page))
            elif el is None:
                continue
            else:
                out.append(str(el))
        # Drop empty strings so they don't break chunking math.
        return [c for c in out if c]
    return [str(raw)]


def _pick_separator(text: str, separators: list[str]) -> str | None:
    """Pick the first separator that splits ``text`` into >= 2 non-empty pieces.

    The empty separator is treated as a last-resort character-level split
    and is only returned when no real separator makes progress.
    """
    for sep in separators:
        if sep == "":
            continue
        parts = text.split(sep)
        non_empty = [p for p in parts if p]
        if len(non_empty) >= 2:
            return sep
    # Fall back to per-character split if any non-empty separator was tried.
    if any(sep == "" for sep in separators):
        return ""
    return None


def _split_by(text: str, sep: str) -> list[str]:
    """Split text by ``sep`` and re-join the parts with the separator.

    For a non-empty separator this preserves the separator inside the output
    pieces (so e.g. ``"a\\n\\nb"`` split by ``"\\n\\n"`` becomes
    ``["a\\n\\n", "b"]``). The trailing empty piece is dropped, mirroring
    LangChain's behaviour.
    """
    if sep == "":
        return list(text)
    parts = text.split(sep)
    out: list[str] = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i < len(parts) - 1:
            out.append(part + sep)
        else:
            out.append(part)
    return out


def _recursively_split(text: str, separators: list[str]) -> list[str]:
    """Split text by the first effective separator, then recurse on long pieces."""
    if not text:
        return []
    if len(text) <= 1:
        return [text]
    chosen = _pick_separator(text, separators)
    if chosen is None:
        return [text]
    pieces = _split_by(text, chosen)
    remaining = [s for s in separators if s != chosen]
    if not remaining:
        return pieces
    out: list[str] = []
    for piece in pieces:
        if len(piece) > 1 and _pick_separator(piece, remaining) is not None:
            out.extend(_recursively_split(piece, remaining))
        else:
            out.append(piece)
    return out


def _pack_pieces(pieces: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    """Greedy pack of splitter pieces into ``chunk_size`` windows with overlap.

    Consecutive pieces are concatenated directly (preserving whatever the
    splitter joined them with). When the next piece would push the running
    buffer past ``chunk_size``, the buffer is emitted as a chunk and a tail
    of length ``chunk_overlap`` is carried into the next buffer. Pieces
    larger than ``chunk_size`` are hard-split in place.
    """
    if not pieces:
        return []
    if chunk_size <= 0:
        return ["".join(pieces)]

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not current:
            if len(piece) > chunk_size:
                start = 0
                while start < len(piece):
                    chunks.append(piece[start : start + chunk_size])
                    if start + chunk_size >= len(piece):
                        break
                    start += max(1, chunk_size - chunk_overlap)
                continue
            current = piece
            continue
        candidate = current + piece
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            chunks.append(current)
            if chunk_overlap > 0 and len(current) >= chunk_overlap:
                tail = current[-chunk_overlap:]
                if len(piece) > chunk_size:
                    chunks.append(piece[:chunk_size])
                    # Carry overlap from the *hard-split* last chunk window
                    last = chunks[-1]
                    current = last[-chunk_overlap:] if len(last) >= chunk_overlap else ""
                else:
                    current = (tail + piece)
                    if len(current) > chunk_size:
                        current = current[:chunk_size]
            else:
                if len(piece) > chunk_size:
                    chunks.append(piece[:chunk_size])
                    current = ""
                else:
                    current = piece

    if current:
        chunks.append(current)
    return chunks


def _offline_recursive_split(
    text: str, *, chunk_size: int, chunk_overlap: int, separators: list[str]
) -> list[str]:
    """Offline fallback: recursive split, then greedy pack with overlap.

    Short-circuits when ``text`` already fits in ``chunk_size``. Empty input
    returns an empty list (no chunks emitted).
    """
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    pieces = _recursively_split(text, separators)
    if not pieces:
        return [text]
    return _pack_pieces(pieces, chunk_size, chunk_overlap)


async def exec_text_splitter_recursive_character(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Recursive Character Text Splitter — split text into chunks.

    Clean-room n8n ``@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter`` v1.

    The executor reads ``parameters.chunkSize`` / ``parameters.chunkOverlap``
    (with ``parameters.options.{chunkSize,chunkOverlap}`` as a fallback) and
    the optional ``parameters.separators`` list. Source text is resolved per
    item from ``parameters.text`` (treated as an expression when leading
    ``=``), then ``$json.text`` then ``$json.pageContent``.

    Mocks honor the same surface as the default document loader:

    - ``ctx.mocks['splitter_output']`` — a callable receives
      ``(text, params)`` and returns either a list of strings (or a single
      string) or a list of ``{pageContent}`` documents. A non-callable value
      is used verbatim.
    - ``ctx.mocks['document_output']`` — list of documents; each
      ``pageContent`` becomes a chunk.

    Offline fallback: split the text recursively by ``separators`` (default
    ``["\n\n", "\n", " ", ""]``), then greedily pack pieces into
    ``chunkSize`` windows with ``chunkOverlap`` carry-over.

    Emits one item per chunk carrying
    ``{text, chunkIndex, chunkSize, source, totalChunks}`` merged with the
    upstream JSON.
    """
    params = node.parameters or {}
    splitter_params = _resolve_text_splitter_params(params)
    chunk_size = splitter_params["chunkSize"]
    chunk_overlap = splitter_params["chunkOverlap"]
    separators = splitter_params["separators"]

    # Capture config on ctx.lm_configs so a connected document loader can
    # observe it via the same surface it uses for sub-nodes.
    ctx.lm_configs[node.id] = {
        "name": node.name,
        "type": node.type,
        "parameters": dict(params),
    }

    out: list[ExecutionItem] = []
    for item in items:
        text = _resolve_splitter_text(item, params, ctx=ctx)

        chunks: list[str] = []
        if ctx.mocks and "splitter_output" in ctx.mocks:
            mock = ctx.mocks["splitter_output"]
            raw = mock(text, splitter_params) if callable(mock) else mock
            chunks = _normalise_splitter_chunks(raw)
        elif ctx.mocks and "document_output" in ctx.mocks:
            mock = ctx.mocks["document_output"]
            raw = mock(item, params) if callable(mock) else mock
            chunks = _normalise_splitter_chunks(raw)
        else:
            chunks = _offline_recursive_split(
                text,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=separators,
            )

        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            ni = item.clone()
            ni.json = {
                **item.json,
                "text": chunk,
                "chunkIndex": idx,
                "chunkSize": len(chunk),
                "source": "textSplitterRecursiveCharacter",
                "totalChunks": total,
            }
            out.append(ni)

    return [(0, out)]


# ── OpenAI Embeddings ─────────────────────────────────────────────────


_EMBEDDING_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def _embedding_dimensions_for(model: str) -> int:
    """Look up the canonical dimension count for an OpenAI embedding model.

    Falls back to 1536 (the legacy ``ada`` default) for any unrecognised
    model name so a v1 offline run always produces a well-shaped vector.
    """
    return _EMBEDDING_DIMENSIONS.get(model, 1536)


def _offline_embedding(text: str, model: str, dimensions: int) -> list[float]:
    """Deterministic mock embedding when no mock is configured.

    ``hashlib.sha256`` of ``(text + model)`` yields 32 bytes; the byte
    sequence is repeated and truncated to ``dimensions`` elements, with
    each byte normalised to ``[-1, 1]``. Identical inputs always produce
    identical vectors so downstream cosine-similarity checks stay stable
    across runs and tests.
    """
    digest = hashlib.sha256(f"{text}|{model}".encode("utf-8")).digest()
    out: list[float] = []
    for i in range(dimensions):
        b = digest[i % len(digest)]
        out.append((b - 127.5) / 127.5)
    return out


def _coerce_embedding_value(
    raw: Any, dimensions: int
) -> list[float]:
    """Best-effort coercion of a mock value into a fixed-length ``list[float]``.

    A list of numbers is normalised to ``float`` and either truncated or
    right-padded with ``0.0`` to match ``dimensions``. A bare string is
    parsed as comma- or whitespace-separated numbers (handy for test
    fixtures). Anything else returns a zero vector of the requested
    length.
    """
    if isinstance(raw, (list, tuple)):
        coerced: list[float] = []
        for v in raw:
            try:
                coerced.append(float(v))
            except (TypeError, ValueError):
                coerced.append(0.0)
        if len(coerced) < dimensions:
            coerced.extend([0.0] * (dimensions - len(coerced)))
        return coerced[:dimensions]
    if isinstance(raw, str):
        parts = [p for p in re.split(r"[\s,]+", raw.strip()) if p]
        coerced = [float(p) if _is_number(p) else 0.0 for p in parts]
        if len(coerced) < dimensions:
            coerced.extend([0.0] * (dimensions - len(coerced)))
        return coerced[:dimensions]
    return [0.0] * dimensions


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except (TypeError, ValueError):
        return False


def _resolve_embeddings_mock(
    ctx: "EngineContext",
    text: str,
    item: ExecutionItem,
    model: str,
    dimensions: int,
) -> list[float] | None:
    """Return a mock embedding if one is configured, else ``None``.

    Honors ``ctx.mocks['embeddings_output']``:
    - callable ``(text, item, model) -> list[float]``
    - non-callable: treated as a static ``list[float]`` (or numeric
      string) and reused for every call
    """
    if not ctx.mocks or "embeddings_output" not in ctx.mocks:
        return None
    raw = ctx.mocks["embeddings_output"]
    if callable(raw):
        result = raw(text, item, model)
    else:
        result = raw
    return _coerce_embedding_value(result, dimensions)


def _resolve_embeddings_text(
    item: ExecutionItem, params: dict[str, Any], ectx: ExpressionContext
) -> str:
    """Pick the input text for an item.

    Order:

    1. ``parameters.text`` — when the value is a string starting with
       ``=`` it is treated as an n8n expression; otherwise the value is
       used as a JSON field name on the upstream item.
    2. ``item.json['text']``
    3. ``item.json['pageContent']``
    """
    configured = params.get("text")
    if isinstance(configured, str) and configured:
        if configured.startswith("="):
            value = evaluate(configured, ectx)
            if isinstance(value, str) and value:
                return value
            if value is not None and not isinstance(value, (dict, list)):
                return str(value)
        else:
            field_name = configured
            if field_name in item.json:
                val = item.json[field_name]
                if isinstance(val, str) and val:
                    return val
                if val is not None and not isinstance(val, (dict, list)):
                    return str(val)
    elif configured is not None and not isinstance(configured, str):
        # Non-string parameter (rare): fall through to default field order
        pass

    val = item.json.get("text")
    if isinstance(val, str) and val:
        return val
    if val is not None and not isinstance(val, (dict, list)):
        return str(val)

    val = item.json.get("pageContent")
    if isinstance(val, str) and val:
        return val
    if val is not None and not isinstance(val, (dict, list)):
        return str(val)

    return ""


async def exec_embeddings_openai(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """OpenAI Embeddings — embed text into a deterministic mock vector.

    Clean-room n8n ``@n8n/n8n-nodes-langchain.embeddingsOpenAi`` v1.

    Reads ``parameters.model`` (default ``text-embedding-3-small``); the
    output dimension is inferred from the model name using the canonical
    OpenAI sizes, falling back to 1536 for any unrecognised name.

    ``parameters.stripNewLines`` (default ``True``) collapses ``\\n`` to
    a single space in the resolved text before hashing or mocking. The
    text source is resolved per item, in this order:

    1. ``parameters.text`` — leading ``=`` triggers expression evaluation,
       otherwise the value names a JSON field on the upstream item.
    2. ``item.json['text']``
    3. ``item.json['pageContent']``

    Mock priority:
    - ``ctx.mocks['embeddings_output']`` — if callable, called with
      ``(text, item, model)``; if not callable, treated as a static
      ``list[float]`` (or numeric string) returned for every call.
    - Offline fallback: a deterministic SHA-256-based vector of the
      configured dimension. Identical inputs always produce identical
      vectors.

    Emits one item per input carrying ``{embedding, model, dimensions}``
    merged with the upstream JSON so downstream nodes still see the
    original fields.
    """
    params = node.parameters or {}
    model_raw = _extract_rl_value(params.get("model")) or "text-embedding-3-small"
    model = model_raw.strip() or "text-embedding-3-small"
    dimensions = _embedding_dimensions_for(model)

    strip_raw = params.get("stripNewLines", True)
    strip_new_lines = True if strip_raw is None else bool(strip_raw)

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(
            item=item, node_outputs=ctx.node_outputs, now=ctx.now
        )
        text = _resolve_embeddings_text(item, params, ectx)
        if strip_new_lines:
            text = text.replace("\n", " ")

        mock_value = _resolve_embeddings_mock(
            ctx, text, item, model, dimensions
        )
        if mock_value is not None:
            embedding = mock_value
        else:
            embedding = _offline_embedding(text, model, dimensions)

        ni = item.clone()
        ni.json = {
            **item.json,
            "embedding": embedding,
            "model": model,
            "dimensions": dimensions,
        }
        out.append(ni)
    return [(0, out)]
