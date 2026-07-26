"""Vector store extra executors (clean-room ``@n8n/n8n-nodes-langchain.*``).

Clean-room implementations of four n8n LangChain vector store nodes:

- ``vectorStoreMilvus``   — Milvus vector store
- ``vectorStoreWeaviate`` — Weaviate vector store
- ``vectorStoreRedis``    — Redis vector store
- ``vectorStoreMongoDb``  — MongoDB Atlas vector store

Each store supports ``insert`` / ``load`` / ``retrieve`` modes with
in-memory storage keyed by ``f"{run_id}:{node.id}:{<store-specific-key>}"``
so parallel runs, multiple nodes, and the same node addressing different
collections all stay isolated.

Mock-first via ``ctx.mocks['vector_store_output']``; offline fallback uses
cosine similarity over deterministic SHA-256 embeddings (384-dim). A
connected embedding model is resolved through ``ctx.mocks['embeddings_output']``
or ``ctx.node_outputs`` (items carrying an ``embedding`` field).
"""

from __future__ import annotations

import hashlib
import logging
import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


_MILVUS_COLLECTIONS: dict[str, list[dict[str, Any]]] = {}
_WEAVIATE_COLLECTIONS: dict[str, list[dict[str, Any]]] = {}
_REDIS_INDEXES: dict[str, list[dict[str, Any]]] = {}
_MONGODB_COLLECTIONS: dict[str, list[dict[str, Any]]] = {}


def _coerce_mode(value: Any) -> str:
    """Coerce a ``mode`` parameter; defaults to ``"insert"``."""
    if isinstance(value, str) and value in ("insert", "load", "retrieve"):
        return value
    return "insert"


def _coerce_top_k(value: Any) -> int:
    """Best-effort coercion of a ``topK`` parameter to a positive int."""
    if value is None:
        return 4
    if isinstance(value, bool):
        return 4
    if isinstance(value, int):
        return value if value > 0 else 4
    if isinstance(value, float):
        return int(value) if value > 0 else 4
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return 4
        try:
            n = int(s)
        except ValueError:
            try:
                n = int(float(s))
            except ValueError:
                return 4
        return n if n > 0 else 4
    return 4


def _coerce_str(value: Any, default: str) -> str:
    """Coerce a parameter to a non-empty string with a fallback default."""
    if value is None:
        return default
    if isinstance(value, str):
        s = value.strip()
        return s or default
    s = str(value).strip()
    return s or default


def _coerce_int(value: Any, default: int) -> int:
    """Coerce a parameter to an int with a fallback default."""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


def _coerce_doc(raw: Any) -> dict[str, Any] | None:
    """Coerce a mock / upstream value into a ``{pageContent, metadata}`` dict."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        page = (
            raw.get("pageContent")
            or raw.get("page_content")
            or raw.get("content")
            or raw.get("text")
            or ""
        )
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        embedding = raw.get("embedding") or raw.get("values") or raw.get("vector")
        if not isinstance(embedding, list):
            embedding = None
        score = raw.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            score = None
        return {
            "pageContent": str(page),
            "metadata": dict(meta),
            "embedding": embedding,
            "score": float(score) if score is not None else None,
        }
    if isinstance(raw, str):
        return {
            "pageContent": raw,
            "metadata": {},
            "embedding": None,
            "score": None,
        }
    return {
        "pageContent": str(raw),
        "metadata": {},
        "embedding": None,
        "score": None,
    }


def _coerce_doc_list(raw: Any) -> list[dict[str, Any]]:
    """Wrap a mock / item value into a list of ``{pageContent, metadata}`` dicts."""
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for el in raw:
            d = _coerce_doc(el)
            if d is not None:
                out.append(d)
        return out
    d = _coerce_doc(raw)
    return [d] if d is not None else []


def _resolve_vector_store_mock(
    ctx: "EngineContext",
    mode: str,
    items: list[ExecutionItem],
    params: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Return mock-supplied docs, or ``None`` to use the offline path."""
    if not ctx.mocks or "vector_store_output" not in ctx.mocks:
        return None
    raw = ctx.mocks["vector_store_output"]
    if callable(raw):
        result = raw(mode, items, params, ctx)
    else:
        result = raw
    if result is None:
        return None
    return _coerce_doc_list(result)


def _item_to_doc(item: ExecutionItem) -> dict[str, Any]:
    """Turn an upstream execution item into a ``{pageContent, metadata}`` doc."""
    page = ""
    for key in ("pageContent", "text", "content"):
        v = item.json.get(key)
        if isinstance(v, str) and v:
            page = v
            break
    if not page:
        try:
            import json as _json

            page = _json.dumps(item.json or {}, default=str)
        except Exception:
            page = ""
    meta: dict[str, Any] = {}
    raw_meta = item.json.get("metadata")
    if isinstance(raw_meta, dict):
        meta.update(raw_meta)
    return {"pageContent": page, "metadata": meta, "embedding": None}


def _items_to_docs(items: list[ExecutionItem]) -> list[dict[str, Any]]:
    return [_item_to_doc(it) for it in items]


def _resolve_query(
    node: "ExecNode", item: ExecutionItem, ctx: "EngineContext"
) -> str:
    """Pick the query text for a retrieve-mode item."""
    params = node.parameters or {}
    configured = params.get("query")
    ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
    if isinstance(configured, str) and configured:
        if configured.startswith("="):
            value = evaluate(configured, ectx)
            if isinstance(value, str) and value:
                return value
            if value is not None and not isinstance(value, (dict, list)):
                return str(value)
        else:
            return configured
    for key in ("query", "chatInput", "text"):
        v = item.json.get(key)
        if isinstance(v, str) and v:
            return v
        if v is not None and not isinstance(v, (dict, list)):
            return str(v)
    return ""


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1]. Zero-length or zero-norm → ``0.0``."""
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    dot = 0.0
    sum_a = 0.0
    sum_b = 0.0
    for i in range(n):
        ai = float(a[i])
        bi = float(b[i])
        dot += ai * bi
        sum_a += ai * ai
        sum_b += bi * bi
    if sum_a <= 0.0 or sum_b <= 0.0:
        return 0.0
    return dot / math.sqrt(sum_a * sum_b)


def _resolve_embedding(
    item: ExecutionItem,
    ctx: "EngineContext",
    text: str,
) -> list[float]:
    """Resolve an embedding vector for ``text``.

    Order:

    1. ``ctx.mocks['embeddings_output']`` (callable ``(text, item, model)`` or value)
    2. Connected ``ai_embedding`` sub-node output found in ``ctx.node_outputs``
       (items carrying an ``embedding`` field)
    3. Deterministic SHA-256 fallback (384-dim)
    """
    if ctx.mocks and "embeddings_output" in ctx.mocks:
        raw = ctx.mocks["embeddings_output"]
        if callable(raw):
            result = raw(text, item, "")
        else:
            result = raw
        if isinstance(result, (list, tuple)):
            try:
                return [float(v) for v in result]
            except (TypeError, ValueError):
                pass
    for outputs in ctx.node_outputs.values():
        for out_item in outputs:
            emb = out_item.json.get("embedding")
            if isinstance(emb, list):
                try:
                    return [float(v) for v in emb]
                except (TypeError, ValueError):
                    pass
    h = hashlib.sha256(text.encode()).digest()
    vec = [(b - 128) / 128.0 for b in h]
    while len(vec) < 384:
        h = hashlib.sha256(h).digest()
        vec.extend((b - 128) / 128.0 for b in h)
    return vec[:384]


def _strip_text_from_meta(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``metadata`` with the ``text`` key removed."""
    if "text" in metadata:
        return {k: v for k, v in metadata.items() if k != "text"}
    return dict(metadata)


async def _exec_vector_store(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
    source: str,
    store: dict[str, list[dict[str, Any]]],
    key: str,
    mode: str,
    top_k: int,
    extra_output: dict[str, Any],
) -> list[tuple[int, list[ExecutionItem]]]:
    """Shared core for all four vector store executors.

    ``insert``  — store docs (from mock or items) with embeddings, return them.
    ``load``    — return all docs currently in the store.
    ``retrieve`` — cosine-similarity top-K against stored (or mock) docs.
    """
    params = node.parameters or {}

    if mode == "insert":
        mock_docs = _resolve_vector_store_mock(ctx, mode, items, params)
        if mock_docs is not None:
            docs = mock_docs
        else:
            docs = _items_to_docs(items)

        bucket = store.setdefault(key, [])
        next_n = len(bucket) + 1
        out: list[ExecutionItem] = []
        for i, doc in enumerate(docs):
            doc_id = f"doc-{next_n}"
            text = doc.get("pageContent", "")
            embedding = doc.get("embedding")
            if not isinstance(embedding, list):
                src_item = items[i] if i < len(items) else ExecutionItem(json={})
                embedding = _resolve_embedding(src_item, ctx, text)
            metadata = dict(doc.get("metadata") or {})
            metadata.setdefault("text", text)
            entry: dict[str, Any] = {
                "id": doc_id,
                "embedding": list(embedding) if isinstance(embedding, list) else [],
                "metadata": metadata,
            }
            bucket.append(entry)
            next_n += 1
            out.append(
                ExecutionItem(
                    json={
                        "document": {
                            "pageContent": text,
                            "metadata": _strip_text_from_meta(metadata),
                        },
                        "stored": True,
                        "mode": "insert",
                        "id": doc_id,
                        **extra_output,
                        "source": source,
                    }
                )
            )
        return [(0, out)]

    if mode == "load":
        bucket = store.get(key) or []
        out: list[ExecutionItem] = []
        for entry in bucket:
            metadata = entry.get("metadata") or {}
            text = str(metadata.get("text", ""))
            out.append(
                ExecutionItem(
                    json={
                        "document": {
                            "pageContent": text,
                            "metadata": _strip_text_from_meta(metadata),
                        },
                        "mode": "load",
                        "id": entry.get("id", ""),
                        **extra_output,
                        "source": source,
                    }
                )
            )
        return [(0, out)]

    out_retrieve: list[ExecutionItem] = []
    bucket = list(store.get(key) or [])

    mock_docs = _resolve_vector_store_mock(ctx, "retrieve", items, params)
    if mock_docs is not None:
        bucket = [
            {
                "id": f"doc-{i + 1}",
                "embedding": d.get("embedding") or [],
                "metadata": {
                    "text": d.get("pageContent", ""),
                    **dict(d.get("metadata") or {}),
                },
                "pageContent": d.get("pageContent", ""),
                "score": d.get("score"),
            }
            for i, d in enumerate(mock_docs)
        ]

    for item in items:
        query = _resolve_query(node, item, ctx)
        if not query:
            continue
        query_embedding = _resolve_embedding(item, ctx, query)

        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in bucket:
            pre_score = entry.get("score") if isinstance(entry, dict) else None
            if isinstance(pre_score, (int, float)) and not isinstance(pre_score, bool):
                scored.append((float(pre_score), entry))
                continue
            doc_emb = entry.get("embedding") if isinstance(entry, dict) else None
            if isinstance(doc_emb, list) and doc_emb:
                score = _cosine_similarity(
                    query_embedding, [float(v) for v in doc_emb]
                )
            else:
                metadata = entry.get("metadata") or {}
                doc_text = str(metadata.get("text", ""))
                doc_emb = _resolve_embedding(item, ctx, doc_text)
                score = _cosine_similarity(query_embedding, doc_emb)
            scored.append((score, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        for score, entry in scored[:top_k]:
            metadata = entry.get("metadata") or {}
            text = str(metadata.get("text", ""))
            page_content = text
            if entry.get("pageContent") is not None:
                page_content = str(entry.get("pageContent") or "")
            ni = item.clone()
            ni.json = {
                **item.json,
                "document": {
                    "pageContent": page_content,
                    "metadata": _strip_text_from_meta(metadata),
                },
                "score": float(score),
                "id": entry.get("id", ""),
                **extra_output,
                "source": source,
            }
            out_retrieve.append(ni)
    return [(0, out_retrieve)]


async def exec_vector_store_milvus(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Milvus Vector Store — insert / load / retrieve with cosine similarity.

    Honors ``parameters.mode`` (default ``"insert"``), ``parameters.topK``
    (default 4), ``parameters.collectionName`` (default ``"n8n_milvus"``),
    ``parameters.host`` (default ``"localhost"``, echoed only), and
    ``parameters.port`` (default ``19530``, echoed only). The store is keyed
    by ``f"{run_id}:{node.id}:{collectionName}"``.
    """
    params = node.parameters or {}
    mode = _coerce_mode(params.get("mode"))
    top_k = _coerce_top_k(params.get("topK"))
    collection_name = _coerce_str(params.get("collectionName"), "n8n_milvus")
    host = _coerce_str(params.get("host"), "localhost")
    port = _coerce_int(params.get("port"), 19530)
    key = f"{ctx.run_id or 'no-run'}:{node.id}:{collection_name}"
    return await _exec_vector_store(
        node,
        items,
        ctx=ctx,
        source="vectorStoreMilvus",
        store=_MILVUS_COLLECTIONS,
        key=key,
        mode=mode,
        top_k=top_k,
        extra_output={
            "collectionName": collection_name,
            "host": host,
            "port": port,
        },
    )


async def exec_vector_store_weaviate(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Weaviate Vector Store — insert / load / retrieve with cosine similarity.

    Honors ``parameters.mode`` (default ``"insert"``), ``parameters.topK``
    (default 4), ``parameters.className`` (default ``"Document"``), and
    ``parameters.url`` (default ``"http://localhost:8080"``, echoed only).
    The store is keyed by ``f"{run_id}:{node.id}:{className}"``.
    """
    params = node.parameters or {}
    mode = _coerce_mode(params.get("mode"))
    top_k = _coerce_top_k(params.get("topK"))
    class_name = _coerce_str(params.get("className"), "Document")
    url = _coerce_str(params.get("url"), "http://localhost:8080")
    key = f"{ctx.run_id or 'no-run'}:{node.id}:{class_name}"
    return await _exec_vector_store(
        node,
        items,
        ctx=ctx,
        source="vectorStoreWeaviate",
        store=_WEAVIATE_COLLECTIONS,
        key=key,
        mode=mode,
        top_k=top_k,
        extra_output={
            "className": class_name,
            "url": url,
        },
    )


async def exec_vector_store_redis(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Redis Vector Store — insert / load / retrieve with cosine similarity.

    Honors ``parameters.mode`` (default ``"insert"``), ``parameters.topK``
    (default 4), ``parameters.indexName`` (default ``"n8n_redis_index"``),
    and ``parameters.redisUrl`` (default ``"redis://localhost:6379"``,
    echoed only). The store is keyed by ``f"{run_id}:{node.id}:{indexName}"``.
    """
    params = node.parameters or {}
    mode = _coerce_mode(params.get("mode"))
    top_k = _coerce_top_k(params.get("topK"))
    index_name = _coerce_str(params.get("indexName"), "n8n_redis_index")
    redis_url = _coerce_str(params.get("redisUrl"), "redis://localhost:6379")
    key = f"{ctx.run_id or 'no-run'}:{node.id}:{index_name}"
    return await _exec_vector_store(
        node,
        items,
        ctx=ctx,
        source="vectorStoreRedis",
        store=_REDIS_INDEXES,
        key=key,
        mode=mode,
        top_k=top_k,
        extra_output={
            "indexName": index_name,
            "redisUrl": redis_url,
        },
    )


async def exec_vector_store_mongodb(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """MongoDB Atlas Vector Store — insert / load / retrieve with cosine similarity.

    Honors ``parameters.mode`` (default ``"insert"``), ``parameters.topK``
    (default 4), ``parameters.collectionName`` (default ``"documents"``),
    ``parameters.indexName`` (default ``"vector_index"``), and
    ``parameters.databaseName`` (default ``"default"``). The store is keyed
    by ``f"{run_id}:{node.id}:{databaseName}:{collectionName}:{indexName}"``.
    """
    params = node.parameters or {}
    mode = _coerce_mode(params.get("mode"))
    top_k = _coerce_top_k(params.get("topK"))
    collection_name = _coerce_str(params.get("collectionName"), "documents")
    index_name = _coerce_str(params.get("indexName"), "vector_index")
    database_name = _coerce_str(params.get("databaseName"), "default")
    key = (
        f"{ctx.run_id or 'no-run'}:{node.id}:"
        f"{database_name}:{collection_name}:{index_name}"
    )
    return await _exec_vector_store(
        node,
        items,
        ctx=ctx,
        source="vectorStoreMongoDb",
        store=_MONGODB_COLLECTIONS,
        key=key,
        mode=mode,
        top_k=top_k,
        extra_output={
            "collectionName": collection_name,
            "indexName": index_name,
            "databaseName": database_name,
        },
    )