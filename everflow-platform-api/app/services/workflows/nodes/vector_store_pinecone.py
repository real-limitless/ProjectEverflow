"""Pinecone vector store executor for the LangChain ``vectorStorePinecone`` node.

Clean-room n8n ``@n8n/n8n-nodes-langchain.vectorStorePinecone`` v1.

A faithful Pinecone binding would talk to the Pinecone HTTP API (or
``pinecone-client``) and call ``index.upsert`` / ``index.query``. v1 is
fully mock-driven — there is **no** network call. The store is a
module-level ``dict`` keyed by
``f"{run_id}:{node.id}:{indexName}:{namespace}"`` so two parallel runs,
two vector-store nodes in the same run, and the same node addressing
different ``indexName`` / ``namespace`` pairs all stay isolated.

Stored records are Pinecone-flavoured dicts:

- ``id``        — auto-assigned string id (``"doc-1"``, ``"doc-2"`` …)
- ``values``    — ``list[float] | None`` — vector for cosine similarity
  during ``retrieve``. Populated from ``ctx.mocks['embeddings_output']``
  when a connected embedding model is present; otherwise an empty list
  and the executor falls back to a keyword match.
- ``metadata``  — the document metadata dict (which always carries the
  document ``text`` under the ``"text"`` key so the pageContent survives
  a round-trip in metadata form).

The executor accepts a connected embedding model via
``ctx.graph.ai_inputs(node.id, "ai_embedding")`` so the model name can be
echoed into the output payload; the actual embedding vector is resolved
through ``ctx.mocks['embeddings_output']`` (offline SHA-256 fallback in
``llm_agent.exec_embeddings_openai``) so this is fully mock-driven.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


# Module-level per-run Pinecone-style index.
# Key: f"{run_id}:{node.id}:{indexName}:{namespace}".
_PINECONE_INDEXES: dict[str, list[dict[str, Any]]] = {}


def _store_key(
    ctx: "EngineContext",
    node: "ExecNode",
    index_name: str,
    namespace: str,
) -> str:
    return f"{ctx.run_id or 'no-run'}:{node.id}:{index_name}:{namespace}"


def _coerce_doc(raw: Any) -> dict[str, Any] | None:
    """Coerce a mock / upstream value into a single ``{pageContent, metadata}`` dict.

    Accepts dicts, strings, and anything else (stringified). Returns ``None``
    for inputs that are clearly not document-shaped (e.g. ``None``). The
    ``score``, ``embedding``, and ``values`` fields are preserved on the
    returned dict so the retrieve path can use a pre-supplied ``score``
    from the mock.
    """
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
        meta = (
            raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        )
        embedding = raw.get("embedding") or raw.get("values")
        if not isinstance(embedding, list):
            embedding = None
        score = raw.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            score = None
        return {
            "pageContent": str(page),
            "metadata": dict(meta),
            "embedding": embedding,
            "values": embedding,
            "score": float(score) if score is not None else None,
        }
    if isinstance(raw, str):
        return {
            "pageContent": raw,
            "metadata": {},
            "embedding": None,
            "values": None,
            "score": None,
        }
    return {
        "pageContent": str(raw),
        "metadata": {},
        "embedding": None,
        "values": None,
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
    """Return mock-supplied docs, or ``None`` to use the offline path.

    ``ctx.mocks['vector_store_output']`` is honored first:

    - callable ``(mode, items, params, ctx)`` — return value is normalised
      via :func:`_coerce_doc_list`. A callable that returns ``None``
      means "no mock data" and the offline path is used.
    - non-callable value — treated as the raw result and normalised the
      same way.
    """
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
    """Turn an upstream execution item into a ``{pageContent, metadata}`` doc.

    Prefers explicit ``pageContent`` / ``text`` fields on the item, then
    falls back to a JSON-serialised body so every item produces *something*
    even when the upstream document loader is misconfigured.
    """
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
    """Pick the query text for a retrieve-mode item.

    Order:

    1. ``parameters.query`` — a leading ``=`` triggers expression
       evaluation, otherwise the bare string is used as the literal query.
    2. ``item.json['query']``
    3. ``item.json['chatInput']``
    4. ``item.json['text']``
    """
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


def _coerce_index_name(value: Any) -> str:
    """Best-effort coercion of an ``indexName`` parameter to a non-empty string."""
    if value is None:
        return "n8n-vector-store"
    if isinstance(value, str):
        s = value.strip()
        return s or "n8n-vector-store"
    s = str(value).strip()
    return s or "n8n-vector-store"


def _coerce_namespace(value: Any) -> str:
    """Best-effort coercion of a ``namespace`` parameter; default is empty string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


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


def _keyword_score(query: str, text: str) -> float:
    """Substring-overlap score in ``[0, 1]`` for the keyword-match fallback.

    Counts whitespace-separated query tokens that appear in ``text`` (case
    insensitive), normalised by the total number of query tokens. Empty
    query yields ``0.0``.
    """
    if not query:
        return 0.0
    q_tokens = [t for t in query.lower().split() if t]
    if not q_tokens:
        return 0.0
    hay = (text or "").lower()
    hits = sum(1 for t in q_tokens if t in hay)
    return hits / len(q_tokens)


def _resolve_embedding_for(
    ctx: "EngineContext",
    text: str,
    item: ExecutionItem,
    model: str,
) -> list[float] | None:
    """Return an embedding for ``text`` from ``ctx.mocks['embeddings_output']`` or ``None``.

    Mirrors :func:`app.services.workflows.nodes.llm_agent._resolve_embeddings_mock`
    so a connected embeddingsOpenAi sub-node's mock flows through cleanly.
    """
    if not ctx.mocks or "embeddings_output" not in ctx.mocks:
        return None
    raw = ctx.mocks["embeddings_output"]
    if callable(raw):
        result = raw(text, item, model)
    else:
        result = raw
    if isinstance(result, (list, tuple)):
        try:
            return [float(v) for v in result]
        except (TypeError, ValueError):
            return None
    if isinstance(result, str):
        import re as _re

        parts = [p for p in _re.split(r"[\s,]+", result.strip()) if p]
        try:
            return [float(p) for p in parts]
        except ValueError:
            return None
    return None


def _resolve_embedding_model_name(
    node: "ExecNode", ctx: "EngineContext"
) -> str:
    """Echo the connected embedding model name (best-effort, never raises)."""
    try:
        emb_nodes = ctx.graph.ai_inputs(node.id, "ai_embedding")
    except Exception:
        return ""
    if not emb_nodes:
        return ""
    emb = emb_nodes[0]
    cfg = ctx.lm_configs.get(emb.id) or {}
    params = cfg.get("parameters") if isinstance(cfg.get("parameters"), dict) else {}
    raw = params.get("model")
    if isinstance(raw, dict):
        for k in ("value", "cachedResultName", "name", "id", "model"):
            inner = raw.get(k)
            if isinstance(inner, str) and inner:
                return inner
        return ""
    if isinstance(raw, str) and raw:
        return raw
    direct = (emb.parameters or {}).get("model")
    if isinstance(direct, str) and direct:
        return direct
    if isinstance(direct, dict):
        for k in ("value", "cachedResultName", "name", "id", "model"):
            inner = direct.get(k)
            if isinstance(inner, str) and inner:
                return inner
    return ""


async def exec_vector_store_pinecone(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Pinecone vector store — insert / load / retrieve with cosine similarity.

    Reads ``parameters.mode`` (one of ``"insert"``, ``"load"``, ``"retrieve"``;
    defaults to ``"retrieve"`` when ``parameters.query`` is present, otherwise
    ``"insert"``) and ``parameters.topK`` (default 4). The store is keyed by
    ``f"{run_id}:{node.id}:{indexName}:{namespace}"`` (``indexName`` default
    ``"n8n-vector-store"``; ``namespace`` default empty string) so multiple
    runs, multiple vector-store nodes, and the same node addressing
    different ``indexName`` / ``namespace`` pairs all stay isolated.

    Mocks honored:

    - ``ctx.mocks['vector_store_output']`` — preferred source of documents
      for ``insert`` and ``load``. Callable receives
      ``(mode, items, params, ctx)``; non-callable values are normalised
      into a list of ``{pageContent, metadata[, embedding]}`` dicts.
    - ``ctx.mocks['embeddings_output']`` — when an embedding sub-node is
      connected, its mock is invoked to produce the vector stored alongside
      each document. Callable receives ``(text, item, model)``.

    On ``insert`` / ``load``: each resolved doc is stored with an auto
    ``id`` (``"doc-1"`` …), its ``values`` (embedding vector or empty
    list), and ``metadata`` (which carries the document text under the
    ``"text"`` key for round-trip retrieval). On ``retrieve``: the query
    is either cosine-compared against stored vectors or substring-matched
    against the metadata text (when no vectors are present), the
    top-``topK`` docs are returned, each carrying
    ``{document, score, indexName, namespace, source}``.
    """
    params = node.parameters or {}
    raw_mode = params.get("mode")
    if isinstance(raw_mode, str) and raw_mode in ("insert", "load", "retrieve"):
        mode = raw_mode
    else:
        # Default: retrieve when a query is set (or any item carries one),
        # otherwise insert. Matches n8n's auto mode behavior.
        configured_query = params.get("query")
        if configured_query:
            mode = "retrieve"
        elif any(
            isinstance(it.json.get(k), str) and it.json.get(k)
            for it in items
            for k in ("query", "chatInput")
        ):
            mode = "retrieve"
        else:
            mode = "insert"
    top_k = _coerce_top_k(params.get("topK"))

    index_name = _coerce_index_name(params.get("indexName"))
    namespace = _coerce_namespace(params.get("namespace"))

    key = _store_key(ctx, node, index_name, namespace)

    # ── insert / load ────────────────────────────────────────────────
    if mode in ("insert", "load"):
        mock_docs = _resolve_vector_store_mock(ctx, mode, items, params)
        if mock_docs is not None:
            docs = mock_docs
        else:
            docs = _items_to_docs(items)

        model_name = _resolve_embedding_model_name(node, ctx)
        if model_name:
            for doc, src_item in zip(docs, items):
                if not doc.get("embedding"):
                    emb = _resolve_embedding_for(
                        ctx, doc.get("pageContent", ""), src_item, model_name
                    )
                    if emb is not None:
                        doc["embedding"] = emb

        bucket = _PINECONE_INDEXES.setdefault(key, [])
        next_n = len(bucket) + 1
        for doc in docs:
            doc_id = f"doc-{next_n}"
            metadata = dict(doc.get("metadata") or {})
            # Pinecone metadata is plain dicts; the text rides along so
            # the pageContent survives a round-trip in metadata form.
            metadata.setdefault("text", doc.get("pageContent", ""))
            values = doc.get("embedding") or []
            entry: dict[str, Any] = {
                "id": doc_id,
                "values": list(values) if isinstance(values, list) else [],
                "metadata": metadata,
            }
            bucket.append(entry)
            next_n += 1

        out: list[ExecutionItem] = []
        for entry in bucket[-len(docs):]:
            ni = ExecutionItem(
                json={
                    "document": {
                        "pageContent": entry["metadata"].get("text", ""),
                        "metadata": {
                            k: v for k, v in entry["metadata"].items() if k != "text"
                        }
                        if "text" in entry["metadata"]
                        else dict(entry["metadata"]),
                    },
                    "stored": True,
                    "mode": mode,
                    "id": entry["id"],
                    "indexName": index_name,
                    "namespace": namespace,
                    "source": "vectorStorePinecone",
                }
            )
            out.append(ni)
        return [(0, out)]

    # ── retrieve ─────────────────────────────────────────────────────
    out_retrieve: list[ExecutionItem] = []
    bucket = list(_PINECONE_INDEXES.get(key) or [])

    # A mock may also drive retrieve: a callable receives (mode, items,
    # params, ctx) and returns either a flat list of documents (the
    # executor scores them against the query) or a list of docs carrying
    # a ``score`` field already (used verbatim, sliced by ``topK``).
    mock_docs = _resolve_vector_store_mock(ctx, "retrieve", items, params)
    if mock_docs is not None:
        bucket = mock_docs

    model_name = _resolve_embedding_model_name(node, ctx)
    for item in items:
        query = _resolve_query(node, item, ctx)
        if not query:
            # No query → empty result for this item
            continue
        # Build a query embedding when stored docs have one.
        query_embedding: list[float] | None = None
        if bucket and any(
            d.get("values") if isinstance(d, dict) else False for d in bucket
        ) and model_name:
            query_embedding = _resolve_embedding_for(ctx, query, item, model_name)

        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in bucket:
            pre_score = entry.get("score") if isinstance(entry, dict) else None
            if isinstance(pre_score, (int, float)) and not isinstance(pre_score, bool):
                # Mock already supplied a score — trust it.
                scored.append((float(pre_score), entry))
                continue
            doc_emb = entry.get("values") if isinstance(entry, dict) else None
            metadata = entry.get("metadata") or {} if isinstance(entry, dict) else {}
            text = str(metadata.get("text", "")) if isinstance(metadata, dict) else ""
            if (
                query_embedding is not None
                and isinstance(doc_emb, list)
                and doc_emb
            ):
                score = _cosine_similarity(query_embedding, [float(v) for v in doc_emb])
            else:
                score = _keyword_score(query, text)
            scored.append((score, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        for score, entry in scored[:top_k]:
            metadata = entry.get("metadata") or {} if isinstance(entry, dict) else {}
            text = str(metadata.get("text", "")) if isinstance(metadata, dict) else ""
            page_content = text
            # If the mock supplied a top-level pageContent, prefer that.
            if isinstance(entry, dict) and entry.get("pageContent") is not None:
                page_content = str(entry.get("pageContent") or "")
            extra_meta = (
                {
                    k: v
                    for k, v in (metadata.items() if isinstance(metadata, dict) else [])
                    if k != "text"
                }
                if isinstance(metadata, dict) and "text" in metadata
                else dict(metadata) if isinstance(metadata, dict) else {}
            )
            ni = item.clone()
            ni.json = {
                **item.json,
                "document": {
                    "pageContent": page_content,
                    "metadata": extra_meta,
                },
                "score": float(score),
                "id": entry.get("id", "") if isinstance(entry, dict) else "",
                "indexName": index_name,
                "namespace": namespace,
                "source": "vectorStorePinecone",
            }
            out_retrieve.append(ni)
    return [(0, out_retrieve)]
