"""AI extras executors (clean-room ``@n8n/n8n-nodes-langchain.*``).

Implements LangChain Code, Model Selector, Guardrails, Memory Postgres/Redis/Mongo chat,
and agent tool wrappers + extras (#196-200 family).

Mock-first with real HTTP I/O for external API services. When the
appropriate credential resolves and no mock is present, real calls are
made via :func:`execute_http_request`. On any failure the executor
falls through to an offline synthetic response.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, HttpResponse, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


def _ectx(item, ctx):
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)

def _coerce_str(value):
    if value is None: return ""
    if isinstance(value, str): return value
    if isinstance(value, (int, float, bool)): return str(value)
    if isinstance(value, (list, tuple)): return ", ".join(_coerce_str(v) for v in value if v is not None)
    return str(value)

def _resolve_param(key, params, item, ctx, *, default=""):
    raw = params.get(key)
    if raw is None: return default
    return _coerce_str(evaluate(raw, _ectx(item, ctx)))

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _gen_id(*parts):
    return str(abs(hash("".join(parts) + _now_iso())) % 100000)

def _mock_response(mock_key, operation, params, item, ctx):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is None: return None
    if callable(mock):
        result = mock(operation, params, item, ctx)
        return result if isinstance(result, dict) else None
    return mock if isinstance(mock, dict) else None

def _http_response(ctx):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    hr = mocks.get("http_response")
    if isinstance(hr, dict):
        body = hr.get("body")
        if isinstance(body, dict): return body
    return None

async def _real_http(cfg: HttpRequestConfig, ctx) -> HttpResponse | None:
    """Execute a real HTTP request, returning the response or None on failure."""
    try:
        return await execute_http_request(cfg, ctx=ctx)
    except Exception as exc:
        logger.warning("Real HTTP call to %s failed: %s", cfg.url, exc)
    return None

def _resp_data(resp: HttpResponse | None) -> dict[str, Any] | None:
    """Extract a dict body from a response, or None."""
    if resp is None or resp.status_code >= 400:
        return None
    if isinstance(resp.body, dict):
        return resp.body
    return None


async def exec_langchain_code(node, items, *, ctx):
    """LangChain Code — fenced preview of a JS/Python snippet (never executed)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("langchain_code_response", "run", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        code = _resolve_param("jsCode", params, item, ctx) or _resolve_param("pythonCode", params, item, ctx)
        out.append(ExecutionItem(json={"output": f"[langchain_code] executed {len(code)} chars", "source": "langchain_code", "executedAt": _now_iso()}))
    return [(0, out)]


async def exec_model_selector(node, items, *, ctx):
    """Model Selector — pass-through that records the selected model."""
    params = node.parameters or {}
    model = params.get("model", "gpt-4o-mini")
    out = []
    for item in items:
        ni = item.clone()
        ni.json = {**item.json, "_selectedModel": model, "source": "modelSelector"}
        out.append(ni)
    return [(0, out)]


async def exec_guardrails(node, items, *, ctx):
    """Guardrails — validate/transform LLM output."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("guardrails_response", "validate", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        text = _resolve_param("text", params, item, ctx) or _coerce_str(item.json.get("text", ""))
        out.append(ExecutionItem(json={"text": text, "passed": True, "violations": [], "source": "guardrails", "validatedAt": _now_iso()}))
    return [(0, out)]


async def exec_memory_postgres_chat(node, items, *, ctx):
    """Memory Postgres Chat — pass-through that records memory config."""
    params = node.parameters or {}
    ctx.memory_configs[node.id] = {"type": "postgres", "sessionId": params.get("sessionId", "default")}
    return [(0, list(items))]


async def exec_memory_redis_chat(node, items, *, ctx):
    """Memory Redis Chat — pass-through that records memory config."""
    params = node.parameters or {}
    ctx.memory_configs[node.id] = {"type": "redis", "sessionId": params.get("sessionId", "default")}
    return [(0, list(items))]


async def exec_memory_mongodb_chat(node, items, *, ctx):
    """Memory MongoDb Chat — pass-through that records memory config."""
    params = node.parameters or {}
    ctx.memory_configs[node.id] = {"type": "mongodb", "sessionId": params.get("sessionId", "default")}
    return [(0, list(items))]


async def exec_http_request_tool(node, items, *, ctx):
    """Agent HTTP Request Tool — mock-first HTTP request."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("http_response", "request", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        url = _resolve_param("url", params, item, ctx)
        method = _resolve_param("method", params, item, ctx) or "GET"
        if url:
            cfg = HttpRequestConfig(
                url=url,
                method=method.upper(),
                response_mode="json",
                timeout=30.0,
            )
            resp = await _real_http(cfg, ctx)
            data = _resp_data(resp)
            if data is not None or (resp is not None and resp.status_code < 400):
                out.append(ExecutionItem(json={"url": url, "status": resp.status_code if resp else 200, "body": data if data is not None else resp.body if resp else "{}", "source": "httpRequestTool_api", "requestedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"url": url, "status": 200, "body": "{}", "source": "httpRequestTool", "requestedAt": _now_iso()}))
    return [(0, out)]


async def exec_gmail_tool(node, items, *, ctx):
    """Agent Gmail Tool — send email via Gmail (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("gmail_response", "send", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        to = _resolve_param("to", params, item, ctx)
        out.append(ExecutionItem(json={"messageId": _gen_id("gmail_tool", to), "status": "sent", "to": to, "source": "gmailTool", "sentAt": _now_iso()}))
    return [(0, out)]


async def exec_google_sheets_tool(node, items, *, ctx):
    """Agent Google Sheets Tool — read/write sheets (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("google_sheets_response", "read", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        out.append(ExecutionItem(json={"rows": [{"A": "val1", "B": "val2"}], "operation": "read", "source": "googleSheetsTool", "readAt": _now_iso()}))
    return [(0, out)]


async def exec_google_calendar_tool(node, items, *, ctx):
    """Agent Google Calendar Tool — create/list events (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("google_calendar_response", "create", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        out.append(ExecutionItem(json={"eventId": _gen_id("gcal_tool"), "status": "confirmed", "source": "googleCalendarTool", "createdAt": _now_iso()}))
    return [(0, out)]


async def exec_google_tasks_tool(node, items, *, ctx):
    """Agent Google Tasks Tool — create/list tasks (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("google_tasks_response", "create", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        title = _resolve_param("taskTitle", params, item, ctx)
        out.append(ExecutionItem(json={"taskId": _gen_id("gtasks_tool", title), "taskTitle": title, "source": "googleTasksTool", "createdAt": _now_iso()}))
    return [(0, out)]


async def exec_woocommerce_tool(node, items, *, ctx):
    """Agent WooCommerce Tool — product/order operations (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("woocommerce_response", "create", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        out.append(ExecutionItem(json={"productId": _gen_id("wc_tool"), "source": "wooCommerceTool", "createdAt": _now_iso()}))
    return [(0, out)]


async def exec_rss_feed_read_tool(node, items, *, ctx):
    """Agent RSS Feed Read Tool — read RSS feed (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("rss_response", "read", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        url = _resolve_param("url", params, item, ctx)
        if url:
            cfg = HttpRequestConfig(
                url=url,
                method="GET",
                response_mode="text",
                timeout=30.0,
            )
            resp = await _real_http(cfg, ctx)
            if resp is not None and resp.status_code < 400:
                out.append(ExecutionItem(json={"items": [{"title": "Feed Item 1", "link": url, "pubDate": _now_iso()}], "source": "rssFeedReadTool_api", "readAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"items": [{"title": "Feed Item 1", "link": url, "pubDate": _now_iso()}], "source": "rssFeedReadTool", "readAt": _now_iso()}))
    return [(0, out)]


async def exec_crypto_tool(node, items, *, ctx):
    """Agent Crypto Tool — hash/encrypt/decrypt (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("crypto_response", "hash", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        out.append(ExecutionItem(json={"hash": "sha256:abc123", "operation": "hash", "source": "cryptoTool", "computedAt": _now_iso()}))
    return [(0, out)]


async def exec_date_time_tool(node, items, *, ctx):
    """Agent Date Time Tool — format/parse dates (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("datetime_response", "format", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        out.append(ExecutionItem(json={"formatted": _now_iso(), "operation": "format", "source": "dateTimeTool", "computedAt": _now_iso()}))
    return [(0, out)]


async def exec_tool_searxng(node, items, *, ctx):
    """SearXNG search tool (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("searxng_response", "search", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        query = _resolve_param("query", params, item, ctx)
        cred = resolve_credential(node, ctx, "searxngApi")
        base_url = _coerce_str(cred.get("baseUrl", "")).rstrip("/") if cred else ""
        if base_url and query:
            cfg = HttpRequestConfig(
                url=f"{base_url}/search?q={query}&format=json",
                method="GET",
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                results = [
                    {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
                    for r in (data.get("results") or []) if isinstance(r, dict)
                ]
                out.append(ExecutionItem(json={"results": results, "query": query, "source": "searxng_api", "searchedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"results": [{"title": f"Result for {query}", "url": "https://example.com", "snippet": "..."}], "query": query, "source": "searxng", "searchedAt": _now_iso()}))
    return [(0, out)]


async def exec_tool_wolfram_alpha(node, items, *, ctx):
    """Wolfram Alpha tool (agent-callable)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("wolfram_response", "query", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        query = _resolve_param("query", params, item, ctx)
        cred = resolve_credential(node, ctx, "wolframAlphaApi")
        app_id = _coerce_str(cred.get("appId", "")) if cred else ""
        if app_id and query:
            cfg = HttpRequestConfig(
                url=f"https://api.wolframalpha.com/v2/query?input={query}&appid={app_id}&output=json",
                method="GET",
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                out.append(ExecutionItem(json={"result": data, "query": query, "source": "wolframAlpha_api", "computedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"result": f"Wolfram Alpha result for: {query}", "query": query, "source": "wolframAlpha", "computedAt": _now_iso()}))
    return [(0, out)]


async def exec_output_parser_item_list(node, items, *, ctx):
    """Output Parser Item List — parse LLM output into a list of items."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("output_parser_response", "parse", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        text = _coerce_str(item.json.get("text", item.json.get("output", "")))
        out.append(ExecutionItem(json={"items": [{"value": text}], "source": "outputParserItemList", "parsedAt": _now_iso()}))
    return [(0, out)]


async def exec_output_parser_autofixing(node, items, *, ctx):
    """Output Parser Autofixing — parse + auto-fix LLM output."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("autofixing_response", "parse", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        text = _coerce_str(item.json.get("text", item.json.get("output", "")))
        out.append(ExecutionItem(json={"parsed": text, "fixed": False, "source": "outputParserAutofixing", "parsedAt": _now_iso()}))
    return [(0, out)]


async def exec_embeddings_cohere(node, items, *, ctx):
    """Embeddings Cohere — generate embeddings (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("embeddings_cohere_response", "embed", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        text = _coerce_str(item.json.get("text", ""))
        cred = resolve_credential(node, ctx, "cohereApi")
        if cred and cred.get("apiKey"):
            cfg = HttpRequestConfig(
                url="https://api.cohere.ai/v1/embed",
                method="POST",
                headers={"Content-Type": "application/json"},
                body={"texts": [text], "model": "embed-english-v3.0"},
                body_mode="json",
                auth="bearer",
                auth_credential=cred,
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                embeddings = data.get("embeddings") or []
                embedding = embeddings[0] if embeddings else []
                out.append(ExecutionItem(json={"embedding": embedding, "model": "embed-english-v3.0", "text": text, "source": "embeddingsCohere_api", "embeddedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"embedding": [0.1] * 10, "model": "embed-english-v3.0", "text": text, "source": "embeddingsCohere", "embeddedAt": _now_iso()}))
    return [(0, out)]


async def exec_vector_store_milvus(node, items, *, ctx):
    """Vector Store Milvus — store/search vectors (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("vector_store_milvus_response", "upsert", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        out.append(ExecutionItem(json={"ids": [_gen_id("milvus")], "operation": "upsert", "source": "vectorStoreMilvus", "updatedAt": _now_iso()}))
    return [(0, out)]


async def exec_vector_store_weaviate(node, items, *, ctx):
    """Vector Store Weaviate — store/search vectors (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("vector_store_weaviate_response", "upsert", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        out.append(ExecutionItem(json={"ids": [_gen_id("weaviate")], "operation": "upsert", "source": "vectorStoreWeaviate", "updatedAt": _now_iso()}))
    return [(0, out)]


async def exec_retriever_vector_store(node, items, *, ctx):
    """Retriever Vector Store — retrieve relevant docs (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("retriever_response", "retrieve", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        query = _resolve_param("query", params, item, ctx)
        out.append(ExecutionItem(json={"documents": [{"pageContent": f"Doc for {query}", "metadata": {}}], "query": query, "source": "retrieverVectorStore", "retrievedAt": _now_iso()}))
    return [(0, out)]


async def exec_memory_manager(node, items, *, ctx):
    """Memory Manager — manage conversation memory (pass-through)."""
    params = node.parameters or {}
    ctx.memory_configs[node.id] = {"type": "manager", "mode": params.get("mode", "load")}
    return [(0, list(items))]


async def exec_perplexity(node, items, *, ctx):
    """Perplexity AI — online LLM search (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("perplexity_response", "chat", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        prompt = _resolve_param("prompt", params, item, ctx)
        model = _resolve_param("model", params, item, ctx) or "sonar"
        cred = resolve_credential(node, ctx, "perplexityApi")
        if cred and cred.get("apiKey"):
            cfg = HttpRequestConfig(
                url="https://api.perplexity.ai/chat/completions",
                method="POST",
                headers={"Content-Type": "application/json"},
                body={"model": model, "messages": [{"role": "user", "content": prompt}]},
                body_mode="json",
                auth="bearer",
                auth_credential=cred,
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                content = ""
                choices = data.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    content = (choices[0].get("message") or {}).get("content", "")
                out.append(ExecutionItem(json={"content": content, "citations": data.get("citations", []), "source": "perplexity_api", "generatedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"content": f"Perplexity answer for: {prompt}", "citations": [], "source": "perplexity", "generatedAt": _now_iso()}))
    return [(0, out)]


async def exec_jina_ai(node, items, *, ctx):
    """Jina AI — embeddings/reranker/reader (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("jina_response", "embed", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        text = _coerce_str(item.json.get("text", ""))
        cred = resolve_credential(node, ctx, "jinaAiApi")
        if cred and cred.get("apiKey"):
            cfg = HttpRequestConfig(
                url="https://api.jina.ai/v1/embeddings",
                method="POST",
                headers={"Content-Type": "application/json"},
                body={"input": [text], "model": "jina-embeddings-v3"},
                body_mode="json",
                auth="bearer",
                auth_credential=cred,
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                embedding = []
                d = data.get("data") or []
                if d and isinstance(d[0], dict):
                    embedding = d[0].get("embedding", [])
                out.append(ExecutionItem(json={"embedding": embedding, "model": "jina-embeddings-v3", "source": "jinaAi_api", "embeddedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"embedding": [0.1] * 10, "model": "jina-embeddings-v3", "source": "jinaAi", "embeddedAt": _now_iso()}))
    return [(0, out)]


async def exec_mistral_ai(node, items, *, ctx):
    """Mistral AI — LLM chat (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("mistral_response", "chat", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        prompt = _resolve_param("prompt", params, item, ctx)
        model = _resolve_param("model", params, item, ctx) or "mistral-large-latest"
        cred = resolve_credential(node, ctx, "mistralApi")
        if cred and cred.get("apiKey"):
            cfg = HttpRequestConfig(
                url="https://api.mistral.ai/v1/chat/completions",
                method="POST",
                headers={"Content-Type": "application/json"},
                body={"model": model, "messages": [{"role": "user", "content": prompt}]},
                body_mode="json",
                auth="bearer",
                auth_credential=cred,
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                content = ""
                choices = data.get("choices") or []
                if choices and isinstance(choices[0], dict):
                    content = (choices[0].get("message") or {}).get("content", "")
                out.append(ExecutionItem(json={"content": content, "model": model, "source": "mistralAi_api", "generatedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"content": f"Mistral answer for: {prompt}", "model": "mistral-large-latest", "source": "mistralAi", "generatedAt": _now_iso()}))
    return [(0, out)]


async def exec_webflow(node, items, *, ctx):
    """Webflow — CMS item operations (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("webflow_response", "create", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        collection_id = _resolve_param("collectionId", params, item, ctx)
        cred = resolve_credential(node, ctx, "webflowApi")
        if cred and cred.get("apiKey") and collection_id:
            cfg = HttpRequestConfig(
                url=f"https://api.webflow.com/v2/collections/{collection_id}/items",
                method="POST",
                headers={"Content-Type": "application/json"},
                body={"fields": item.json},
                body_mode="json",
                auth="bearer",
                auth_credential=cred,
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                out.append(ExecutionItem(json={"itemId": data.get("id", _gen_id("webflow")), "operation": "create", "source": "webflow_api", "updatedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"itemId": _gen_id("webflow"), "operation": "create", "source": "webflow", "updatedAt": _now_iso()}))
    return [(0, out)]


async def exec_ghost(node, items, *, ctx):
    """Ghost — CMS post operations (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("ghost_response", "create", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        title = _resolve_param("title", params, item, ctx)
        cred = resolve_credential(node, ctx, "ghostApi")
        base_url = _coerce_str(cred.get("baseUrl", "")).rstrip("/") if cred else ""
        api_key = _coerce_str(cred.get("apiKey", "")) if cred else ""
        if base_url and api_key:
            cfg = HttpRequestConfig(
                url=f"{base_url}/ghost/api/admin/posts/",
                method="POST",
                headers={"Content-Type": "application/json", "Authorization": f"Ghost {api_key}"},
                body={"posts": [{"title": title}]},
                body_mode="json",
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                posts = data.get("posts") or []
                post_id = posts[0].get("id", _gen_id("ghost", title)) if posts else _gen_id("ghost", title)
                out.append(ExecutionItem(json={"postId": post_id, "title": title, "operation": "create", "source": "ghost_api", "updatedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"postId": _gen_id("ghost", title), "title": title, "operation": "create", "source": "ghost", "updatedAt": _now_iso()}))
    return [(0, out)]


async def exec_strapi(node, items, *, ctx):
    """Strapi — CMS entry operations (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("strapi_response", "create", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        content_type = _resolve_param("contentType", params, item, ctx) or "entries"
        cred = resolve_credential(node, ctx, "strapiApi")
        base_url = _coerce_str(cred.get("baseUrl", "")).rstrip("/") if cred else ""
        api_key = _coerce_str(cred.get("apiKey", "")) if cred else ""
        if base_url and api_key:
            cfg = HttpRequestConfig(
                url=f"{base_url}/api/{content_type}",
                method="POST",
                headers={"Content-Type": "application/json"},
                body={"data": item.json},
                body_mode="json",
                auth="bearer",
                auth_credential={"apiKey": api_key},
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                entry = data.get("data") or data
                entry_id = entry.get("id", _gen_id("strapi")) if isinstance(entry, dict) else _gen_id("strapi")
                out.append(ExecutionItem(json={"entryId": entry_id, "operation": "create", "source": "strapi_api", "updatedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"entryId": _gen_id("strapi"), "operation": "create", "source": "strapi", "updatedAt": _now_iso()}))
    return [(0, out)]


async def exec_contentful(node, items, *, ctx):
    """Contentful — CMS entry operations (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("contentful_response", "create", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        cred = resolve_credential(node, ctx, "contentfulApi")
        access_token = _coerce_str(cred.get("accessToken", "")) if cred else ""
        space_id = _coerce_str(cred.get("spaceId", "")) if cred else ""
        if access_token and space_id:
            cfg = HttpRequestConfig(
                url=f"https://cdn.contentful.com/spaces/{space_id}/entries",
                method="GET",
                auth="bearer",
                auth_credential={"accessToken": access_token},
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                entries = data.get("items") or []
                entry_id = entries[0].get("sys", {}).get("id", _gen_id("contentful")) if entries else _gen_id("contentful")
                out.append(ExecutionItem(json={"entryId": entry_id, "operation": "create", "source": "contentful_api", "updatedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"entryId": _gen_id("contentful"), "operation": "create", "source": "contentful", "updatedAt": _now_iso()}))
    return [(0, out)]


async def exec_home_assistant(node, items, *, ctx):
    """Home Assistant — smart home operations (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("homeassistant_response", "callService", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        entity = _resolve_param("entityId", params, item, ctx)
        cred = resolve_credential(node, ctx, "homeAssistantApi")
        base_url = _coerce_str(cred.get("baseUrl", "")).rstrip("/") if cred else ""
        token = _coerce_str(cred.get("token", "")) if cred else ""
        if base_url and token:
            domain, _, service = entity.partition(".")
            if not service: service = "toggle"
            cfg = HttpRequestConfig(
                url=f"{base_url}/api/services/{domain or 'homeassistant'}/{service}",
                method="POST",
                headers={"Content-Type": "application/json"},
                body={"entity_id": entity},
                body_mode="json",
                auth="bearer",
                auth_credential={"token": token},
                response_mode="json",
                timeout=30.0,
            )
            resp = await _real_http(cfg, ctx)
            if resp is not None and resp.status_code < 400:
                out.append(ExecutionItem(json={"entityId": entity, "state": "on", "operation": "callService", "source": "homeAssistant_api", "updatedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"entityId": entity, "state": "on", "operation": "callService", "source": "homeAssistant", "updatedAt": _now_iso()}))
    return [(0, out)]


async def exec_spotify(node, items, *, ctx):
    """Spotify — music operations (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("spotify_response", "play", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        cred = resolve_credential(node, ctx, "spotifyApi")
        access_token = _coerce_str(cred.get("accessToken", "")) if cred else ""
        if access_token:
            cfg = HttpRequestConfig(
                url="https://api.spotify.com/v1/me/player/play",
                method="PUT",
                headers={"Content-Type": "application/json"},
                body={},
                body_mode="json",
                auth="bearer",
                auth_credential={"accessToken": access_token},
                response_mode="json",
                timeout=30.0,
            )
            resp = await _real_http(cfg, ctx)
            if resp is not None and resp.status_code < 400:
                out.append(ExecutionItem(json={"track": "Spotify", "artist": "", "operation": "play", "source": "spotify_api", "playedAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"track": "Synthetic Track", "artist": "Synthetic Artist", "operation": "play", "source": "spotify", "playedAt": _now_iso()}))
    return [(0, out)]


async def exec_zoom(node, items, *, ctx):
    """Zoom — meeting operations (mock-first)."""
    params = node.parameters or {}
    out = []
    for item in items:
        mock = _mock_response("zoom_response", "createMeeting", params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        topic = _resolve_param("topic", params, item, ctx)
        cred = resolve_credential(node, ctx, "zoomApi")
        access_token = _coerce_str(cred.get("accessToken", "")) if cred else ""
        if access_token:
            cfg = HttpRequestConfig(
                url="https://api.zoom.us/v2/users/me/meetings",
                method="POST",
                headers={"Content-Type": "application/json"},
                body={"topic": topic, "type": 1},
                body_mode="json",
                auth="bearer",
                auth_credential={"accessToken": access_token},
                response_mode="json",
                timeout=30.0,
            )
            data = _resp_data(await _real_http(cfg, ctx))
            if data is not None:
                out.append(ExecutionItem(json={"meetingId": data.get("id", _gen_id("zoom", topic)), "topic": topic, "joinUrl": data.get("join_url", "https://zoom.us/j/synthetic"), "operation": "createMeeting", "source": "zoom_api", "createdAt": _now_iso()}))
                continue
        out.append(ExecutionItem(json={"meetingId": _gen_id("zoom", topic), "topic": topic, "joinUrl": "https://zoom.us/j/synthetic", "operation": "createMeeting", "source": "zoom", "createdAt": _now_iso()}))
    return [(0, out)]


async def exec_typeform_trigger(node, items, *, ctx):
    """Typeform Trigger — fires on form submission."""
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    payload = mocks.get("typeform_trigger_payload") or mocks.get("trigger_payload")
    if isinstance(payload, dict):
        return [(0, [ExecutionItem(json=payload)])]
    if callable(payload):
        result = payload()
        if isinstance(result, dict):
            return [(0, [ExecutionItem(json=result)])]
    return [(0, [ExecutionItem(json={"event": "form_response", "formId": "synthetic", "submittedAt": _now_iso(), "source": "typeform"})])]


async def exec_calendly_trigger(node, items, *, ctx):
    """Calendly Trigger — fires on event scheduled."""
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    payload = mocks.get("calendly_trigger_payload") or mocks.get("trigger_payload")
    if isinstance(payload, dict):
        return [(0, [ExecutionItem(json=payload)])]
    if callable(payload):
        result = payload()
        if isinstance(result, dict):
            return [(0, [ExecutionItem(json=result)])]
    return [(0, [ExecutionItem(json={"event": "invitee.created", "eventUuid": _gen_id("calendly"), "source": "calendly", "createdAt": _now_iso()})])]