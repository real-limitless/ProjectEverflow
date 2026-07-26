"""Embeddings extra executors (clean-room ``@n8n/n8n-nodes-langchain.*``).

Implements four embedding providers with mock-first, real-HTTP-when-credential
semantics:

- ``embeddingsCohere``       — Cohere API
- ``embeddingsAzureOpenAi``  — Azure OpenAI
- ``embeddingsHuggingFace``  — HuggingFace inference API
- ``embeddingsMistral``      — Mistral AI

Precedence per item:

1. ``ctx.mocks['<node>_response']`` — callable or dict. If callable,
   invoked as ``mock(text, params, item, ctx)``.
2. ``ctx.mocks['http_response']`` — generic HTTP mock fallback.
3. If credentials resolve AND no mock → call real API via
   :func:`execute_http_request`.
4. Offline synthetic response — deterministic SHA-256-based vector
   with ``source: "<provider>"``.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


DEFAULT_DIMS = 1536


def _resolve_credential(
    node: "ExecNode", ctx: "EngineContext", cred_type: str
) -> dict[str, Any]:
    cred = ctx.resolve_credential(node, cred_type) or {}
    if not cred and node.credentials:
        for v in node.credentials.values():
            if isinstance(v, dict):
                cred = v
                break
    return cred


def _offline_embedding(text: str, dims: int = DEFAULT_DIMS) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    vec = [(b - 128) / 128.0 for b in h]
    while len(vec) < dims:
        h = hashlib.sha256(h).digest()
        vec.extend((b - 128) / 128.0 for b in h)
    return vec[:dims]


def _resolve_text(
    item: ExecutionItem, params: dict[str, Any], ctx: "EngineContext"
) -> str:
    ectx = ExpressionContext(
        item=item, node_outputs=ctx.node_outputs, now=ctx.now
    )
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


def _extract_embedding(data: Any) -> list[float]:
    if isinstance(data, list):
        if data and isinstance(data[0], list):
            return [float(v) for v in data[0] if isinstance(v, (int, float))]
        return [float(v) for v in data if isinstance(v, (int, float))]
    if isinstance(data, dict):
        emb = data.get("embedding")
        if isinstance(emb, list):
            return [float(v) for v in emb if isinstance(v, (int, float))]
        data_list = data.get("data")
        if isinstance(data_list, list) and data_list:
            first = data_list[0]
            if isinstance(first, dict):
                inner = first.get("embedding")
                if isinstance(inner, list):
                    return [float(v) for v in inner if isinstance(v, (int, float))]
        emb_list = data.get("embeddings")
        if isinstance(emb_list, list) and emb_list:
            first = emb_list[0]
            if isinstance(first, list):
                return [float(v) for v in first if isinstance(v, (int, float))]
    return []


def _http_response_data(ctx: "EngineContext") -> Any:
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    hr = mocks.get("http_response")
    if hr is None:
        return None
    if isinstance(hr, dict) and "body" in hr:
        return hr["body"]
    return hr


def _emit(
    item: ExecutionItem, embedding: list[float], model: str, source: str
) -> ExecutionItem:
    ni = item.clone()
    ni.json = {
        **item.json,
        "embedding": embedding,
        "model": model,
        "source": source,
    }
    return ni


# ── Cohere ───────────────────────────────────────────────────────────


async def exec_embeddings_cohere(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Cohere Embeddings — embed text via Cohere API."""
    params = node.parameters or {}
    model = str(params.get("model") or "embed-english-v3.0")
    input_type = str(params.get("inputType") or "search_document")
    out: list[ExecutionItem] = []
    for item in items:
        text = _resolve_text(item, params, ctx)

        mock = (ctx.mocks or {}).get("embeddings_cohere_response")
        if mock is not None:
            data = mock(text, params, item, ctx) if callable(mock) else mock
            embedding = _extract_embedding(data)
            out.append(_emit(item, embedding, model, "cohere"))
            continue

        http_data = _http_response_data(ctx)
        if http_data is not None:
            embedding = _extract_embedding(http_data)
            out.append(_emit(item, embedding, model, "cohere"))
            continue

        cred = _resolve_credential(node, ctx, "cohereApi")
        api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
        if api_key:
            cfg = HttpRequestConfig(
                url="https://api.cohere.ai/v1/embed",
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body={
                    "model": model,
                    "texts": [text],
                    "input_type": input_type,
                },
                body_mode="json",
                response_mode="json",
                timeout=30.0,
            )
            resp = await execute_http_request(cfg, ctx=ctx)
            data = resp.body if isinstance(resp.body, dict) else {}
            embedding = _extract_embedding(data)
            out.append(_emit(item, embedding, model, "cohere"))
            continue

        embedding = _offline_embedding(text)
        out.append(_emit(item, embedding, model, "cohere"))
    return [(0, out)]


# ── Azure OpenAI ─────────────────────────────────────────────────────


async def exec_embeddings_azure_openai(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Azure OpenAI Embeddings — embed text via Azure OpenAI."""
    params = node.parameters or {}
    model = str(params.get("model") or "text-embedding-3-small")
    deployment_name = str(
        params.get("deploymentName") or params.get("deployment") or ""
    )
    resource_name = str(params.get("resourceName") or "")
    out: list[ExecutionItem] = []
    for item in items:
        text = _resolve_text(item, params, ctx)

        mock = (ctx.mocks or {}).get("embeddings_azure_response")
        if mock is not None:
            data = mock(text, params, item, ctx) if callable(mock) else mock
            embedding = _extract_embedding(data)
            out.append(_emit(item, embedding, model, "azureOpenAi"))
            continue

        http_data = _http_response_data(ctx)
        if http_data is not None:
            embedding = _extract_embedding(http_data)
            out.append(_emit(item, embedding, model, "azureOpenAi"))
            continue

        cred = _resolve_credential(node, ctx, "azureOpenAiApi")
        api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
        cred_resource = str(
            cred.get("resourceName") or cred.get("resource_name") or ""
        )
        cred_deployment = str(
            cred.get("deploymentId") or cred.get("deployment_id") or ""
        )
        effective_resource = resource_name or cred_resource
        effective_deployment = deployment_name or cred_deployment
        if api_key and effective_resource and effective_deployment:
            url = (
                f"https://{effective_resource}.openai.azure.com/openai/deployments/"
                f"{effective_deployment}/embeddings?api-version=2024-02-01"
            )
            cfg = HttpRequestConfig(
                url=url,
                method="POST",
                headers={
                    "api-key": api_key,
                    "Content-Type": "application/json",
                },
                body={"model": model, "input": text},
                body_mode="json",
                response_mode="json",
                timeout=30.0,
            )
            resp = await execute_http_request(cfg, ctx=ctx)
            data = resp.body if isinstance(resp.body, dict) else {}
            embedding = _extract_embedding(data)
            out.append(_emit(item, embedding, model, "azureOpenAi"))
            continue

        embedding = _offline_embedding(text)
        out.append(_emit(item, embedding, model, "azureOpenAi"))
    return [(0, out)]


# ── HuggingFace ──────────────────────────────────────────────────────


async def exec_embeddings_huggingface(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """HuggingFace Embeddings — embed text via HF inference API."""
    params = node.parameters or {}
    model = str(
        params.get("model")
        or "sentence-transformers/all-MiniLM-L6-v2"
    )
    out: list[ExecutionItem] = []
    for item in items:
        text = _resolve_text(item, params, ctx)

        mock = (ctx.mocks or {}).get("embeddings_hf_response")
        if mock is not None:
            data = mock(text, params, item, ctx) if callable(mock) else mock
            embedding = _extract_embedding(data)
            out.append(_emit(item, embedding, model, "huggingFace"))
            continue

        http_data = _http_response_data(ctx)
        if http_data is not None:
            embedding = _extract_embedding(http_data)
            out.append(_emit(item, embedding, model, "huggingFace"))
            continue

        cred = _resolve_credential(node, ctx, "huggingFaceApi")
        api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
        if api_key:
            cfg = HttpRequestConfig(
                url=f"https://api-inference.huggingface.co/models/{model}",
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body={"inputs": text},
                body_mode="json",
                response_mode="json",
                timeout=30.0,
            )
            resp = await execute_http_request(cfg, ctx=ctx)
            data = resp.body
            embedding = _extract_embedding(data)
            out.append(_emit(item, embedding, model, "huggingFace"))
            continue

        embedding = _offline_embedding(text)
        out.append(_emit(item, embedding, model, "huggingFace"))
    return [(0, out)]


# ── Mistral ──────────────────────────────────────────────────────────


async def exec_embeddings_mistral(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Mistral Embeddings — embed text via Mistral AI."""
    params = node.parameters or {}
    model = str(params.get("model") or "mistral-embed")
    out: list[ExecutionItem] = []
    for item in items:
        text = _resolve_text(item, params, ctx)

        mock = (ctx.mocks or {}).get("embeddings_mistral_response")
        if mock is not None:
            data = mock(text, params, item, ctx) if callable(mock) else mock
            embedding = _extract_embedding(data)
            out.append(_emit(item, embedding, model, "mistral"))
            continue

        http_data = _http_response_data(ctx)
        if http_data is not None:
            embedding = _extract_embedding(http_data)
            out.append(_emit(item, embedding, model, "mistral"))
            continue

        cred = _resolve_credential(node, ctx, "mistralApi")
        api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
        if api_key:
            cfg = HttpRequestConfig(
                url="https://api.mistral.ai/v1/embeddings",
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                body={"model": model, "input": text},
                body_mode="json",
                response_mode="json",
                timeout=30.0,
            )
            resp = await execute_http_request(cfg, ctx=ctx)
            data = resp.body if isinstance(resp.body, dict) else {}
            embedding = _extract_embedding(data)
            out.append(_emit(item, embedding, model, "mistral"))
            continue

        embedding = _offline_embedding(text)
        out.append(_emit(item, embedding, model, "mistral"))
    return [(0, out)]


__all__ = [
    "exec_embeddings_cohere",
    "exec_embeddings_azure_openai",
    "exec_embeddings_huggingface",
    "exec_embeddings_mistral",
]