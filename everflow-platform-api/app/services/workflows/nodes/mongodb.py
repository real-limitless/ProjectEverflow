"""MongoDb executor (clean-room n8n ``n8n-nodes-base.mongoDb``).

v1 supports the five operations most commonly used in n8n templates:

- ``find``      — query documents; emit one item per document with
  ``{document, count, source: 'mongoDb'}`` (or one item with a
  ``documents`` array when ``dataMode == 'object'``).
- ``insert``    — insert documents; emit one item per input with
  ``{insertedCount, insertedIds, acknowledged, source: 'mongoDb'}``.
- ``update``    — update documents; emit one item per input with
  ``{matchedCount, modifiedCount, upsertedId, acknowledged,
  source: 'mongoDb'}``.
- ``delete``    — delete documents; emit one item per input with
  ``{deletedCount, acknowledged, source: 'mongoDb'}``.
- ``aggregate`` — run an aggregation pipeline; emit one item per result
  with ``{result, source: 'mongoDb'}`` (or one item with a ``results``
  array when ``dataMode == 'object'``).

When a ``mongoDb`` (or ``mongoDbApi``) credential is attached and no
mock is present, real calls are made via the ``motor`` async driver.
Otherwise the executor is mock-driven with an offline synthetic
fallback.

Parameters honored:

- ``operation``   (``"find"`` / ``"insert"`` / ``"update"`` / ``"delete"``
  / ``"aggregate"``; default ``"find"``)
- ``collection``  (string; ``$json.collection`` /
  ``$json.collectionName`` fallback; required)
- ``database``    (string; ``$json.database`` / ``$json.databaseName``
  fallback; echoed only)
- ``dataMode``    (``"array"`` / ``"object"``; default ``"array"``;
  find/aggregate only)
- For ``find``:
  - ``query``     (JSON filter dict; ``$json.query`` fallback; default ``{}``)
  - ``limit``     (int; default 10)
  - ``projection``(dict; optional)
  - ``sort``      (dict; optional)
- For ``insert``:
  - ``documents`` (list of docs; ``$json.documents`` / ``$json.data``
    fallback; wraps ``$json`` as a single doc when absent)
- For ``update``:
  - ``query``     (filter dict; ``$json.query`` fallback; default ``{}``)
  - ``update``    (update doc; ``$json.update`` fallback)
  - ``upsert``    (bool; default False)
  - ``multi``     (bool; default False)
- For ``delete``:
  - ``query``     (filter dict; ``$json.query`` fallback; default ``{}``)
  - ``limit``     (int; default 0 = all)
- For ``aggregate``:
  - ``pipeline``  (list of stages; ``$json.pipeline`` fallback)

Behavior precedence:

1. ``ctx.mocks['mongodb_response']`` — when present, the value drives
   the executor. A dict is used as the operation-specific response
   envelope; a callable is invoked as
   ``mock(operation, collection, params, item, ctx)`` and may return a
   dict (normalized per operation) or a non-dict value (replaced by a
   synthetic envelope).
2. ``ctx.mocks['db_response']`` — generic database-response fallback
   (dict envelope or a ``body`` sub-dict).
3. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the MongoDb envelope.
4. If a ``mongoDb`` (or ``mongoDbApi``) credential resolves, a real
   MongoDB call is made via ``motor`` (async driver); the result is
   normalized into the operation envelope.
5. Offline synthetic response with deterministic-looking ids.

Items with an empty resolved ``collection`` are skipped (no item emitted).
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


MONGODB_OPERATIONS: tuple[str, ...] = (
    "find",
    "insert",
    "update",
    "delete",
    "aggregate",
)
MONGODB_DEFAULT_OPERATION: str = "find"
MONGODB_DEFAULT_LIMIT: int = 10
MONGODB_DEFAULT_DATA_MODE: str = "array"
MONGODB_DATA_MODES: tuple[str, ...] = ("array", "object")


def _ectx(item: ExecutionItem, ctx: "EngineContext") -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_coerce_str(v) for v in value if v is not None)
    if isinstance(value, dict):
        for key in ("value", "name", "id", "text", "content"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_int(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                return default
    return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _resolve_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> Any:
    """Return ``params[key]`` (evaluated) or the first present ``$json`` fallback."""
    raw = params.get(key)
    if raw is not None:
        return evaluate(raw, ectx)
    for fk in json_fallbacks:
        if fk in item.json:
            return item.json[fk]
    return None


def _resolve_str_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> str:
    return _coerce_str(_resolve_param(params, key, item, ectx, json_fallbacks))


def _new_object_id() -> str:
    return f"obj_{uuid.uuid4().hex[:12]}"


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_find_response(limit: int) -> dict[str, Any]:
    """Offline fallback: a fake MongoDb find response."""
    count = min(limit, 3)
    documents = [
        {"_id": f"obj_{i}", "name": f"Mock Doc {i}", "value": i * 10}
        for i in range(1, count + 1)
    ]
    return {"documents": documents, "count": count}


def _synthesize_insert_response(doc_count: int) -> dict[str, Any]:
    """Offline fallback: a fake MongoDb insert response."""
    n = max(doc_count, 1)
    return {
        "insertedCount": n,
        "insertedIds": [_new_object_id()],
        "acknowledged": True,
    }


def _synthesize_update_response() -> dict[str, Any]:
    """Offline fallback: a fake MongoDb update response."""
    return {
        "matchedCount": 1,
        "modifiedCount": 1,
        "upsertedId": None,
        "acknowledged": True,
    }


def _synthesize_delete_response() -> dict[str, Any]:
    """Offline fallback: a fake MongoDb delete response."""
    return {"deletedCount": 1, "acknowledged": True}


def _synthesize_aggregate_response() -> dict[str, Any]:
    """Offline fallback: a fake MongoDb aggregate response."""
    return {
        "result": [{"_id": "group1", "count": 5, "total": 150}],
        "ok": 1,
    }


def _synthesize_response(
    operation: str, *, limit: int = 0, doc_count: int = 0
) -> dict[str, Any]:
    if operation == "find":
        return _synthesize_find_response(limit)
    if operation == "insert":
        return _synthesize_insert_response(doc_count)
    if operation == "update":
        return _synthesize_update_response()
    if operation == "delete":
        return _synthesize_delete_response()
    return _synthesize_aggregate_response()


# ── Response normalization ─────────────────────────────────────────────


def _normalize_find_response(raw: dict[str, Any]) -> dict[str, Any]:
    docs_raw = raw.get("documents")
    if not isinstance(docs_raw, list):
        docs_raw = []
    documents: list[dict[str, Any]] = []
    for d in docs_raw:
        if isinstance(d, dict):
            documents.append(d)
        else:
            documents.append({"value": d})
    count = raw.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        count = len(documents)
    return {"documents": documents, "count": count}


def _normalize_insert_response(raw: dict[str, Any]) -> dict[str, Any]:
    inserted_count = raw.get("insertedCount")
    if not isinstance(inserted_count, int) or isinstance(inserted_count, bool):
        inserted_count = 1
    inserted_ids_raw = raw.get("insertedIds")
    if isinstance(inserted_ids_raw, list):
        inserted_ids = list(inserted_ids_raw)
    else:
        inserted_ids = [_new_object_id()]
    acknowledged = raw.get("acknowledged")
    if not isinstance(acknowledged, bool):
        acknowledged = True
    return {
        "insertedCount": inserted_count,
        "insertedIds": inserted_ids,
        "acknowledged": acknowledged,
    }


def _normalize_update_response(raw: dict[str, Any]) -> dict[str, Any]:
    matched = raw.get("matchedCount")
    if not isinstance(matched, int) or isinstance(matched, bool):
        matched = 1
    modified = raw.get("modifiedCount")
    if not isinstance(modified, int) or isinstance(modified, bool):
        modified = 1
    acknowledged = raw.get("acknowledged")
    if not isinstance(acknowledged, bool):
        acknowledged = True
    return {
        "matchedCount": matched,
        "modifiedCount": modified,
        "upsertedId": raw.get("upsertedId"),
        "acknowledged": acknowledged,
    }


def _normalize_delete_response(raw: dict[str, Any]) -> dict[str, Any]:
    deleted = raw.get("deletedCount")
    if not isinstance(deleted, int) or isinstance(deleted, bool):
        deleted = 1
    acknowledged = raw.get("acknowledged")
    if not isinstance(acknowledged, bool):
        acknowledged = True
    return {"deletedCount": deleted, "acknowledged": acknowledged}


def _normalize_aggregate_response(raw: dict[str, Any]) -> dict[str, Any]:
    result_raw = raw.get("result")
    if not isinstance(result_raw, list):
        result_raw = []
    results: list[dict[str, Any]] = []
    for r in result_raw:
        if isinstance(r, dict):
            results.append(r)
        else:
            results.append({"value": r})
    ok = raw.get("ok")
    if not isinstance(ok, int) or isinstance(ok, bool):
        ok = 1
    return {"result": results, "ok": ok}


def _normalize_response(
    raw: dict[str, Any], operation: str
) -> dict[str, Any]:
    if operation == "find":
        return _normalize_find_response(raw)
    if operation == "insert":
        return _normalize_insert_response(raw)
    if operation == "update":
        return _normalize_update_response(raw)
    if operation == "delete":
        return _normalize_delete_response(raw)
    return _normalize_aggregate_response(raw)


def _looks_like_envelope(mock: dict[str, Any], operation: str) -> bool:
    if operation == "find":
        return "documents" in mock or "count" in mock
    if operation == "insert":
        return "insertedCount" in mock or "insertedIds" in mock
    if operation == "update":
        return "matchedCount" in mock or "modifiedCount" in mock
    if operation == "delete":
        return "deletedCount" in mock
    if operation == "aggregate":
        return "result" in mock or "ok" in mock
    return False


def _response_from_http_mock(
    mock: Any, operation: str
) -> dict[str, Any] | None:
    """Extract a MongoDb-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        return _normalize_response(body, operation)
    return None


def _response_from_db_mock(
    mock: Any, operation: str
) -> dict[str, Any] | None:
    """Extract a MongoDb-style envelope from a generic ``db_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        return _normalize_response(body, operation)
    if _looks_like_envelope(mock, operation):
        return _normalize_response(mock, operation)
    return None


# ── Real driver ────────────────────────────────────────────────────────


def _jsonify_mongo(value: Any) -> Any:
    """Convert BSON ObjectId values to strings for JSON serialization."""
    try:
        from bson import ObjectId
    except ImportError:
        return value
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: _jsonify_mongo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify_mongo(v) for v in value]
    return value


def _build_mongodb_config(cred: dict[str, Any]) -> dict[str, Any] | None:
    """Build a MongoDB connection config from a credential dict.

    Returns a dict with ``connectionString`` and ``database`` keys, or
    ``None`` when no usable connection info is present.
    """
    conn_str = str(cred.get("connectionString") or cred.get("url") or "").strip()
    database = str(cred.get("database") or cred.get("db") or "").strip()

    if conn_str:
        config: dict[str, Any] = {"connectionString": conn_str}
        if database:
            config["database"] = database
        return config

    host = str(cred.get("host") or "").strip()
    if not host:
        return None

    port = _coerce_int(cred.get("port"), 27017)
    username = cred.get("username")
    password = cred.get("password")
    ssl = _coerce_bool(cred.get("ssl"), False)

    parts: list[str] = ["mongodb://"]
    if username:
        user = str(username)
        if password:
            parts.append(f"{quote_plus(user)}:{quote_plus(str(password))}@")
        else:
            parts.append(f"{user}@")
    parts.append(host)
    if port and port != 27017:
        parts.append(f":{port}")
    if database:
        parts.append(f"/{database}")
    if ssl:
        parts.append("?ssl=true")

    return {"connectionString": "".join(parts), "database": database}


async def _execute_mongodb_operation(
    conn_params: dict[str, Any],
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    collection: str,
) -> dict[str, Any] | None:
    """Connect to MongoDB and run a single operation.

    Returns a result dict shaped for ``_normalize_response``, or ``None``
    if the operation cannot be performed (e.g. missing database).
    """
    ectx = _ectx(item, ctx)
    database = conn_params.get("database") or _resolve_str_param(
        params, "database", item, ectx, ("database", "databaseName")
    )
    if not database:
        return None

    conn_str = conn_params["connectionString"]
    client = AsyncIOMotorClient(conn_str)
    try:
        coll = client[database][collection]

        if operation == "find":
            query = _resolve_param(params, "query", item, ectx, ("query",))
            if query is None:
                query = {}
            limit = _coerce_int(
                _resolve_param(params, "limit", item, ectx), MONGODB_DEFAULT_LIMIT
            )
            projection = _resolve_param(params, "projection", item, ectx)
            sort = _resolve_param(params, "sort", item, ectx)

            cursor = coll.find(query)
            if sort:
                if isinstance(sort, dict):
                    cursor = cursor.sort(list(sort.items()))
                else:
                    cursor = cursor.sort(sort)
            if projection:
                cursor = cursor.projection(projection)
            cursor = cursor.limit(limit)
            documents = await cursor.to_list(length=limit)
            return {
                "documents": _jsonify_mongo(documents),
                "count": len(documents),
            }

        if operation == "insert":
            documents = _resolve_param(
                params, "documents", item, ectx, ("documents", "data")
            )
            if documents is None:
                documents = [dict(item.json)]
            elif not isinstance(documents, list):
                documents = [documents]
            result = await coll.insert_many(documents)
            return {
                "insertedCount": len(result.inserted_ids),
                "insertedIds": [str(_id) for _id in result.inserted_ids],
                "acknowledged": result.acknowledged,
            }

        if operation == "update":
            query = _resolve_param(params, "query", item, ectx, ("query",))
            if query is None:
                query = {}
            update = _resolve_param(params, "update", item, ectx, ("update",))
            upsert = _coerce_bool(
                _resolve_param(params, "upsert", item, ectx), False
            )
            multi = _coerce_bool(
                _resolve_param(params, "multi", item, ectx), False
            )

            if multi:
                result = await coll.update_many(query, update, upsert=upsert)
            else:
                result = await coll.update_one(query, update, upsert=upsert)
            return {
                "matchedCount": result.matched_count,
                "modifiedCount": result.modified_count,
                "upsertedId": (
                    str(result.upserted_id) if result.upserted_id else None
                ),
                "acknowledged": result.acknowledged,
            }

        if operation == "delete":
            query = _resolve_param(params, "query", item, ectx, ("query",))
            if query is None:
                query = {}
            delete_limit = _coerce_int(
                _resolve_param(params, "limit", item, ectx), 0
            )
            if delete_limit == 1:
                result = await coll.delete_one(query)
            else:
                result = await coll.delete_many(query)
            return {
                "deletedCount": result.deleted_count,
                "acknowledged": result.acknowledged,
            }

        # aggregate
        pipeline = _resolve_param(params, "pipeline", item, ectx, ("pipeline",))
        if pipeline is None:
            pipeline = []
        cursor = coll.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        return {"result": _jsonify_mongo(results), "ok": 1}
    finally:
        client.close()


# ── Response resolution ────────────────────────────────────────────────


async def _resolve_mongodb_response(
    *,
    operation: str,
    collection: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
    limit: int,
    doc_count: int,
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"mongodb_response"``, ``"db_response"``,
    ``"http_response"``, ``"mongodb_api"``, ``"offline"`` so downstream
    observers can tell where the result came from.
    """
    mocks = ctx.mocks or {}
    mmock = mocks.get("mongodb_response")
    if mmock is not None:
        if callable(mmock):
            raw = mmock(operation, collection, params, item, ctx)
        else:
            raw = mmock
        if isinstance(raw, dict):
            return _normalize_response(raw, operation), "mongodb_response"
        return (
            _synthesize_response(operation, limit=limit, doc_count=doc_count),
            "mongodb_response",
        )

    dbmock = mocks.get("db_response")
    if dbmock is not None:
        env = _response_from_db_mock(dbmock, operation)
        if env is not None:
            return env, "db_response"

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _response_from_http_mock(hmock, operation)
        if env is not None:
            return env, "http_response"

    cred = resolve_credential(node, ctx, "mongoDb") or resolve_credential(
        node, ctx, "mongoDbApi"
    )
    if cred:
        conn_params = _build_mongodb_config(cred)
        if conn_params is not None:
            logger.info(
                "mongoDb real call database=%s collection=%s operation=%s",
                conn_params.get("database", ""),
                collection[:80],
                operation,
            )
            try:
                result = await _execute_mongodb_operation(
                    conn_params, operation, params, item, ctx, collection
                )
                if result is not None:
                    return (
                        _normalize_response(result, operation),
                        "mongodb_api",
                    )
            except Exception as exc:
                logger.warning("mongoDb real call failed: %s", exc)

    return (
        _synthesize_response(operation, limit=limit, doc_count=doc_count),
        "offline",
    )


# ── Output builders ────────────────────────────────────────────────────


def _build_find_items(
    item: ExecutionItem,
    envelope: dict[str, Any],
    data_mode: str,
    source: str,
) -> list[ExecutionItem]:
    documents = envelope.get("documents") or []
    count = envelope.get("count", len(documents))

    if data_mode == "object":
        payload: dict[str, Any] = {
            "documents": list(documents),
            "count": count,
            "operation": "find",
            "source": "mongoDb",
        }
        if source not in ("mongodb_response", "mongodb_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        return [ni]

    items: list[ExecutionItem] = []
    for doc in documents:
        payload = {
            "document": doc,
            "count": count,
            "operation": "find",
            "source": "mongoDb",
        }
        if source not in ("mongodb_response", "mongodb_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        items.append(ni)
    return items


def _build_insert_item(
    item: ExecutionItem,
    envelope: dict[str, Any],
    source: str,
) -> ExecutionItem:
    payload: dict[str, Any] = {
        "insertedCount": envelope.get("insertedCount", 1),
        "insertedIds": envelope.get("insertedIds", []),
        "acknowledged": envelope.get("acknowledged", True),
        "operation": "insert",
        "source": "mongoDb",
    }
    if source != "mongodb_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


def _build_update_item(
    item: ExecutionItem,
    envelope: dict[str, Any],
    source: str,
) -> ExecutionItem:
    payload: dict[str, Any] = {
        "matchedCount": envelope.get("matchedCount", 1),
        "modifiedCount": envelope.get("modifiedCount", 1),
        "upsertedId": envelope.get("upsertedId"),
        "acknowledged": envelope.get("acknowledged", True),
        "operation": "update",
        "source": "mongoDb",
    }
    if source != "mongodb_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


def _build_delete_item(
    item: ExecutionItem,
    envelope: dict[str, Any],
    source: str,
) -> ExecutionItem:
    payload: dict[str, Any] = {
        "deletedCount": envelope.get("deletedCount", 1),
        "acknowledged": envelope.get("acknowledged", True),
        "operation": "delete",
        "source": "mongoDb",
    }
    if source != "mongodb_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


def _build_aggregate_items(
    item: ExecutionItem,
    envelope: dict[str, Any],
    data_mode: str,
    source: str,
) -> list[ExecutionItem]:
    results = envelope.get("result") or []
    ok = envelope.get("ok", 1)

    if data_mode == "object":
        payload: dict[str, Any] = {
            "results": list(results),
            "ok": ok,
            "operation": "aggregate",
            "source": "mongoDb",
        }
        if source not in ("mongodb_response", "mongodb_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        return [ni]

    items: list[ExecutionItem] = []
    for r in results:
        payload = {
            "result": r,
            "operation": "aggregate",
            "source": "mongoDb",
        }
        if source not in ("mongodb_response", "mongodb_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        items.append(ni)
    return items


# ── Main executor ──────────────────────────────────────────────────────


async def exec_mongodb(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """MongoDb node — find/insert/update/delete/aggregate per input item.

    - ``find``      → emits one item per document (or one item with a
      ``documents`` array when ``dataMode == 'object'``).
    - ``insert``    → emits one item per input with ``insertedCount,
      insertedIds, acknowledged``.
    - ``update``    → emits one item per input with ``matchedCount,
      modifiedCount, upsertedId, acknowledged``.
    - ``delete``    → emits one item per input with ``deletedCount,
      acknowledged``.
    - ``aggregate`` → emits one item per result (or one item with a
      ``results`` array when ``dataMode == 'object'``).

    Items with an empty resolved ``collection`` are skipped.
    """
    params = node.parameters or {}
    operation = str(
        params.get("operation") or MONGODB_DEFAULT_OPERATION
    ).strip().lower()
    if operation not in MONGODB_OPERATIONS:
        raise ValueError(
            f"mongoDb: unsupported operation {operation!r}; "
            f"expected one of {MONGODB_OPERATIONS}"
        )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)

        collection = _resolve_str_param(
            params, "collection", item, ectx, ("collection", "collectionName")
        ).strip()
        if not collection:
            logger.info(
                "mongoDb %s skipped: empty collection on node %r",
                operation,
                node.name,
            )
            continue

        database = _resolve_str_param(
            params, "database", item, ectx, ("database", "databaseName")
        )

        data_mode = str(
            params.get("dataMode") or MONGODB_DEFAULT_DATA_MODE
        ).strip().lower()
        if data_mode not in MONGODB_DATA_MODES:
            data_mode = MONGODB_DEFAULT_DATA_MODE

        if operation == "find":
            query = _resolve_param(params, "query", item, ectx, ("query",))
            if query is None:
                query = {}
            limit = _coerce_int(
                _resolve_param(params, "limit", item, ectx),
                MONGODB_DEFAULT_LIMIT,
            )
            _projection = _resolve_param(params, "projection", item, ectx)
            _sort = _resolve_param(params, "sort", item, ectx)

            envelope, source = await _resolve_mongodb_response(
                operation=operation,
                collection=collection,
                params=params,
                item=item,
                node=node,
                ctx=ctx,
                limit=limit,
                doc_count=0,
            )
            out.extend(_build_find_items(item, envelope, data_mode, source))
            logger.info(
                "mongoDb find database=%r collection=%r count=%d source=%s",
                database[:80],
                collection[:80],
                envelope.get("count", 0),
                source,
            )
            continue

        if operation == "insert":
            documents = _resolve_param(
                params, "documents", item, ectx, ("documents", "data")
            )
            if documents is None:
                documents = [dict(item.json)]
            elif not isinstance(documents, list):
                documents = [documents]
            doc_count = len(documents)

            envelope, source = await _resolve_mongodb_response(
                operation=operation,
                collection=collection,
                params=params,
                item=item,
                node=node,
                ctx=ctx,
                limit=0,
                doc_count=doc_count,
            )
            out.append(_build_insert_item(item, envelope, source))
            logger.info(
                "mongoDb insert database=%r collection=%r inserted=%d source=%s",
                database[:80],
                collection[:80],
                envelope.get("insertedCount", 0),
                source,
            )
            continue

        if operation == "update":
            query = _resolve_param(params, "query", item, ectx, ("query",))
            if query is None:
                query = {}
            _update = _resolve_param(params, "update", item, ectx, ("update",))
            _upsert = _coerce_bool(
                _resolve_param(params, "upsert", item, ectx), False
            )
            _multi = _coerce_bool(
                _resolve_param(params, "multi", item, ectx), False
            )

            envelope, source = await _resolve_mongodb_response(
                operation=operation,
                collection=collection,
                params=params,
                item=item,
                node=node,
                ctx=ctx,
                limit=0,
                doc_count=0,
            )
            out.append(_build_update_item(item, envelope, source))
            logger.info(
                "mongoDb update database=%r collection=%r matched=%d source=%s",
                database[:80],
                collection[:80],
                envelope.get("matchedCount", 0),
                source,
            )
            continue

        if operation == "delete":
            query = _resolve_param(params, "query", item, ectx, ("query",))
            if query is None:
                query = {}
            _limit = _coerce_int(
                _resolve_param(params, "limit", item, ectx), 0
            )

            envelope, source = await _resolve_mongodb_response(
                operation=operation,
                collection=collection,
                params=params,
                item=item,
                node=node,
                ctx=ctx,
                limit=0,
                doc_count=0,
            )
            out.append(_build_delete_item(item, envelope, source))
            logger.info(
                "mongoDb delete database=%r collection=%r deleted=%d source=%s",
                database[:80],
                collection[:80],
                envelope.get("deletedCount", 0),
                source,
            )
            continue

        # aggregate
        _pipeline = _resolve_param(
            params, "pipeline", item, ectx, ("pipeline",)
        )
        if _pipeline is None:
            _pipeline = []

        envelope, source = await _resolve_mongodb_response(
            operation=operation,
            collection=collection,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
            limit=0,
            doc_count=0,
        )
        out.extend(_build_aggregate_items(item, envelope, data_mode, source))
        logger.info(
            "mongoDb aggregate database=%r collection=%r results=%d source=%s",
            database[:80],
            collection[:80],
            len(envelope.get("result") or []),
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_mongodb",
    "MONGODB_OPERATIONS",
    "MONGODB_DEFAULT_OPERATION",
    "MONGODB_DEFAULT_LIMIT",
    "MONGODB_DEFAULT_DATA_MODE",
    "MONGODB_DATA_MODES",
]