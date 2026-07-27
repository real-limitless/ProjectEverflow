"""Supabase executor (clean-room n8n ``n8n-nodes-base.supabase``).

v1 supports the four operations most commonly used in n8n templates:

- ``select`` — select rows from a Supabase table via PostgREST; emit one
  item per row with ``{row, count, source: 'supabase'}`` (or one item
  with a ``data`` array when ``dataMode == 'object'``).
- ``insert`` — insert rows into a table; emit one item per input with
  ``{data, count, status, source: 'supabase'}``.
- ``update`` — update rows in a table; emit one item per input with
  ``{data, count, status, source: 'supabase'}``.
- ``upsert`` — upsert rows in a table; emit one item per input with
  ``{data, count, status, upserted, source: 'supabase'}``.

When a ``supabaseApi`` credential is attached and no mock is present,
real calls are made to the Supabase PostgREST API via
:func:`execute_http_request`. Otherwise the executor is mock-driven with
an offline synthetic fallback.

Parameters honored:

- ``operation``        (``"select"`` / ``"insert"`` / ``"update"`` /
  ``"upsert"``; default ``"select"``)
- ``table``            (string; ``$json.table`` / ``$json.tableName``
  fallback; required)
- ``schema``           (string; default ``"public"``)
- For ``select``:
  - ``columns``        (string; default ``"*"``)
  - ``limit``          (int; default 10)
  - ``filter``         (dict of column → value; optional)
  - ``order``          (dict with ``column``, ``ascending``; optional)
  - ``dataMode``       (``"array"`` / ``"object"``; default ``"array"``)
- For ``insert``:
  - ``records``        (list of dicts; ``$json.records`` /
    ``$json.data`` fallback; or wrap ``$json`` as single record)
- For ``update`` / ``upsert``:
  - ``records``        (list of dicts; ``$json.records`` /
    ``$json.data`` fallback)
  - ``match``          (dict of column → value for WHERE;
    ``$json.match`` fallback)
  - ``onConflict``     (column name; default ``"id"``; upsert only)

Behavior precedence:

1. ``ctx.mocks['supabase_response']`` — when present, the value drives
   the executor. A dict is used as the operation-specific response; a
   callable is invoked as
   ``mock(operation, table, params, item, ctx)`` and may return a dict
   (used per operation) or a non-dict truthy value (wrapped in a
   synthetic envelope).
2. ``ctx.mocks['db_response']`` — generic database-response fallback
   (dict with ``data`` / ``count`` / ``status`` / ``body``).
3. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Supabase envelope.
4. If a ``supabaseApi`` credential resolves (``url`` and ``apiKey``
   present), a real call is made to the Supabase PostgREST API and the
   response is normalized into the operation envelope.
5. Offline synthetic response with deterministic-looking ids.

Items with an empty resolved ``table`` are skipped (no item emitted).
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


SUPABASE_OPERATIONS: tuple[str, ...] = ("select", "insert", "update", "upsert")
SUPABASE_DEFAULT_OPERATION: str = "select"
SUPABASE_DEFAULT_SCHEMA: str = "public"
SUPABASE_DEFAULT_COLUMNS: str = "*"
SUPABASE_DEFAULT_LIMIT: int = 10
SUPABASE_DEFAULT_ON_CONFLICT: str = "id"
SUPABASE_DEFAULT_DATA_MODE: str = "array"
SUPABASE_DATA_MODES: tuple[str, ...] = ("array", "object")
SUPABASE_OFFLINE_MAX_ROWS: int = 3


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


def _new_id() -> int:
    return random.randint(1, 2_000_000_000)


def _resolve_records(
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    *,
    wrap_json: bool,
) -> list[dict[str, Any]]:
    """Resolve the ``records`` parameter with ``$json`` fallbacks.

    For ``insert``, if no records are found, ``$json`` is wrapped as a
    single record (``wrap_json=True``). For ``update``/``upsert``, an
    empty list is returned.
    """
    raw = _resolve_param(params, "records", item, ectx, ("records", "data"))
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        return [raw]
    if wrap_json:
        return [dict(item.json)]
    return []


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_select(limit: int) -> dict[str, Any]:
    """Offline fallback: a fake Supabase select response."""
    limit = max(0, limit)
    upper = min(limit + 1, SUPABASE_OFFLINE_MAX_ROWS + 1)
    data = [
        {"id": i, "name": f"Mock Row {i}", "value": i * 10}
        for i in range(1, upper)
    ]
    return {
        "data": data,
        "count": min(limit, SUPABASE_OFFLINE_MAX_ROWS),
        "status": 200,
    }


def _synthesize_insert(first_record: dict[str, Any]) -> dict[str, Any]:
    """Offline fallback: a fake Supabase insert response."""
    fields = dict(first_record) if isinstance(first_record, dict) else {}
    return {"data": [{"id": _new_id(), **fields}], "count": 1, "status": 201}


def _synthesize_update(
    match_id: Any, updated_fields: dict[str, Any]
) -> dict[str, Any]:
    """Offline fallback: a fake Supabase update response."""
    fields = dict(updated_fields) if isinstance(updated_fields, dict) else {}
    mid = match_id if match_id is not None else 1
    return {"data": [{"id": mid, **fields}], "count": 1, "status": 200}


def _synthesize_upsert(
    match_id: Any, fields: dict[str, Any]
) -> dict[str, Any]:
    """Offline fallback: a fake Supabase upsert response."""
    f = dict(fields) if isinstance(fields, dict) else {}
    mid = match_id if match_id is not None else _new_id()
    return {
        "data": [{"id": mid, **f}],
        "count": 1,
        "status": 201,
        "upserted": True,
    }


def _synthesize_response(
    operation: str,
    limit: int,
    records: list[dict[str, Any]],
    match: dict[str, Any],
) -> dict[str, Any]:
    if operation == "select":
        return _synthesize_select(limit)
    if operation == "insert":
        first = records[0] if records else {}
        return _synthesize_insert(first)
    if operation == "update":
        match_id = match.get("id") if isinstance(match, dict) else None
        first = records[0] if records else {}
        return _synthesize_update(match_id, first)
    # upsert
    match_id = match.get("id") if isinstance(match, dict) else None
    first = records[0] if records else {}
    return _synthesize_upsert(match_id, first)


# ── Response normalization ─────────────────────────────────────────────


def _default_status(operation: str) -> int:
    if operation == "select":
        return 200
    if operation in ("insert", "upsert"):
        return 201
    return 200


def _normalize_response(raw: dict[str, Any], operation: str) -> dict[str, Any]:
    data_raw = raw.get("data")
    if not isinstance(data_raw, list):
        data_raw = []
    count = raw.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        count = len(data_raw)
    status = raw.get("status")
    if not isinstance(status, int) or isinstance(status, bool):
        status = _default_status(operation)
    envelope: dict[str, Any] = {"data": data_raw, "count": count, "status": status}
    if operation == "upsert":
        upserted = raw.get("upserted")
        if not isinstance(upserted, bool):
            upserted = True
        envelope["upserted"] = upserted
    return envelope


def _response_from_db_mock(
    mock: Any, operation: str
) -> dict[str, Any] | None:
    """Extract a Supabase-style envelope from a generic ``db_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        return _normalize_response(body, operation)
    if "data" in mock or "count" in mock or "status" in mock:
        return _normalize_response(mock, operation)
    return None


def _response_from_http_mock(
    mock: Any, operation: str
) -> dict[str, Any] | None:
    """Extract a Supabase-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        return _normalize_response(body, operation)
    return None


# ── Response resolution ────────────────────────────────────────────────


def _build_supabase_request(
    cred: dict[str, Any],
    operation: str,
    table: str,
    schema: str,
    params: dict[str, Any],
    limit: int,
    records: list[dict[str, Any]],
    match: dict[str, Any],
) -> HttpRequestConfig | None:
    """Build a real Supabase PostgREST request config.

    Returns ``None`` when the credential has no ``url`` or ``apiKey``.
    """
    url = str(
        cred.get("url") or cred.get("baseUrl") or cred.get("host") or ""
    ).rstrip("/")
    api_key = str(
        cred.get("apiKey")
        or cred.get("api_key")
        or cred.get("anonKey")
        or cred.get("serviceKey")
        or ""
    )
    if not url or not api_key:
        return None
    rest_base = f"{url}/rest/v1"
    headers: dict[str, str] = {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
    }
    if schema and schema != SUPABASE_DEFAULT_SCHEMA:
        headers["Accept-Profile"] = schema

    if operation == "select":
        columns = str(params.get("columns") or SUPABASE_DEFAULT_COLUMNS)
        query_parts: list[str] = [f"select={columns}"]
        filter_dict = params.get("filter")
        if isinstance(filter_dict, dict):
            for col, val in filter_dict.items():
                query_parts.append(f"{col}=eq.{val}")
        order = params.get("order")
        if isinstance(order, dict):
            col = order.get("column")
            if col:
                ascending = order.get("ascending", True)
                direction = "asc" if ascending else "desc"
                query_parts.append(f"order={col}.{direction}")
        query_parts.append(f"limit={limit}")
        qs = "&".join(query_parts)
        return HttpRequestConfig(
            url=f"{rest_base}/{table}?{qs}",
            method="GET",
            headers=headers,
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    if operation == "insert":
        headers["Prefer"] = "return=representation"
        body: Any = records if records else []
        return HttpRequestConfig(
            url=f"{rest_base}/{table}",
            method="POST",
            headers=headers,
            body=body,
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    if operation == "update":
        headers["Prefer"] = "return=representation"
        match_filters: list[str] = []
        if isinstance(match, dict):
            for col, val in match.items():
                match_filters.append(f"{col}=eq.{val}")
        body = records[0] if records else {}
        request_url = f"{rest_base}/{table}"
        if match_filters:
            request_url = f"{request_url}?{'&'.join(match_filters)}"
        return HttpRequestConfig(
            url=request_url,
            method="PATCH",
            headers=headers,
            body=body,
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    # upsert
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"
    on_conflict = str(
        params.get("onConflict") or SUPABASE_DEFAULT_ON_CONFLICT
    )
    body = records if records else []
    return HttpRequestConfig(
        url=f"{rest_base}/{table}?on_conflict={on_conflict}",
        method="POST",
        headers=headers,
        body=body,
        body_mode="json",
        response_mode="json",
        timeout=30.0,
    )


def _envelope_from_supabase_api(
    data: Any,
    operation: str,
) -> dict[str, Any]:
    """Convert a real Supabase PostgREST response to the internal
    envelope shape.

    PostgREST returns a bare JSON array for most operations; this wraps
    it into the ``{data, count, status}`` envelope the executor uses.
    """
    if isinstance(data, list):
        raw: dict[str, Any] = {"data": data, "count": len(data)}
    elif isinstance(data, dict):
        raw = data
    else:
        raw = {"data": []}
    return _normalize_response(raw, operation)


async def _resolve_supabase_response(
    *,
    operation: str,
    table: str,
    schema: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
    limit: int,
    records: list[dict[str, Any]],
    match: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"supabase_response"``, ``"db_response"``,
    ``"http_response"``, ``"supabase_api"``, ``"offline"`` so downstream
    observers can tell where the result came from.
    """
    mocks = ctx.mocks or {}
    smock = mocks.get("supabase_response")
    if smock is not None:
        if callable(smock):
            raw = smock(operation, table, params, item, ctx)
        else:
            raw = smock
        if isinstance(raw, dict):
            return _normalize_response(raw, operation), "supabase_response"
        return (
            _synthesize_response(operation, limit, records, match),
            "supabase_response",
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

    cred = resolve_credential(node, ctx, "supabaseApi")
    if cred:
        cfg = _build_supabase_request(
            cred, operation, table, schema, params, limit, records, match
        )
        if cfg is not None:
            logger.info(
                "supabase real HTTP call operation=%s table=%s",
                operation,
                table,
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, (dict, list)):
                    return (
                        _envelope_from_supabase_api(resp.body, operation),
                        "supabase_api",
                    )
            except Exception as exc:
                logger.warning("supabase HTTP call failed: %s", exc)

    return (
        _synthesize_response(operation, limit, records, match),
        "offline",
    )


# ── Output builders ────────────────────────────────────────────────────


def _build_select_items(
    item: ExecutionItem,
    envelope: dict[str, Any],
    data_mode: str,
    source: str,
) -> list[ExecutionItem]:
    data = envelope.get("data") or []
    count = envelope.get("count", len(data))

    if data_mode == "object":
        payload: dict[str, Any] = {
            "data": list(data),
            "count": count,
            "source": "supabase",
        }
        if source not in ("supabase_response", "supabase_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        return [ni]

    items: list[ExecutionItem] = []
    for row in data:
        payload = {
            "row": row,
            "count": count,
            "source": "supabase",
        }
        if source not in ("supabase_response", "supabase_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        items.append(ni)
    return items


def _build_write_item(
    item: ExecutionItem,
    envelope: dict[str, Any],
    operation: str,
    source: str,
) -> ExecutionItem:
    payload: dict[str, Any] = {
        "data": envelope.get("data") or [],
        "count": envelope.get("count", 1),
        "status": envelope.get("status", _default_status(operation)),
        "source": "supabase",
    }
    if operation == "upsert":
        payload["upserted"] = envelope.get("upserted", True)
    if source not in ("supabase_response", "supabase_api"):
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


# ── Main executor ──────────────────────────────────────────────────────


async def exec_supabase(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Supabase node — select/insert/update/upsert per input item.

    - ``select`` → emits one item per row (or one item with a ``data``
      array when ``dataMode == 'object'``).
    - ``insert``  → emits one item per input with ``data, count, status``.
    - ``update``  → emits one item per input with ``data, count, status``.
    - ``upsert``  → emits one item per input with ``data, count, status,
      upserted``.

    Items with an empty resolved ``table`` are skipped.
    """
    params = node.parameters or {}
    operation = str(
        params.get("operation") or SUPABASE_DEFAULT_OPERATION
    ).strip().lower()
    if operation not in SUPABASE_OPERATIONS:
        raise ValueError(
            f"supabase: unsupported operation {operation!r}; "
            f"expected one of {SUPABASE_OPERATIONS}"
        )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        table = _resolve_str_param(
            params, "table", item, ectx, ("table", "tableName")
        ).strip()
        if not table:
            logger.info(
                "supabase %s skipped: empty table on node %r",
                operation,
                node.name,
            )
            continue

        schema = _resolve_str_param(
            params, "schema", item, ectx
        ).strip() or SUPABASE_DEFAULT_SCHEMA

        limit = SUPABASE_DEFAULT_LIMIT
        records: list[dict[str, Any]] = []
        match: dict[str, Any] = {}
        data_mode = SUPABASE_DEFAULT_DATA_MODE

        if operation == "select":
            limit = _coerce_int(
                _resolve_param(params, "limit", item, ectx),
                SUPABASE_DEFAULT_LIMIT,
            )
            data_mode = str(
                params.get("dataMode") or SUPABASE_DEFAULT_DATA_MODE
            ).strip().lower()
            if data_mode not in SUPABASE_DATA_MODES:
                data_mode = SUPABASE_DEFAULT_DATA_MODE
        elif operation == "insert":
            records = _resolve_records(params, item, ectx, wrap_json=True)
        else:  # update / upsert
            records = _resolve_records(params, item, ectx, wrap_json=False)
            match_resolved = _resolve_param(
                params, "match", item, ectx, ("match",)
            )
            match = match_resolved if isinstance(match_resolved, dict) else {}

        envelope, source = await _resolve_supabase_response(
            operation=operation,
            table=table,
            schema=schema,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
            limit=limit,
            records=records,
            match=match,
        )

        if operation == "select":
            out.extend(_build_select_items(item, envelope, data_mode, source))
        else:
            out.append(_build_write_item(item, envelope, operation, source))

        logger.info(
            "supabase %s schema=%r table=%r count=%d source=%s",
            operation,
            schema,
            table[:80],
            envelope.get("count", 0),
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_supabase",
    "SUPABASE_OPERATIONS",
    "SUPABASE_DEFAULT_OPERATION",
    "SUPABASE_DEFAULT_SCHEMA",
    "SUPABASE_DEFAULT_COLUMNS",
    "SUPABASE_DEFAULT_LIMIT",
    "SUPABASE_DEFAULT_ON_CONFLICT",
    "SUPABASE_DEFAULT_DATA_MODE",
    "SUPABASE_DATA_MODES",
]