"""Postgres executor (clean-room n8n ``n8n-nodes-base.postgres``).

v1 supports the four operations most commonly used in n8n templates:

- ``execute`` — run an arbitrary SQL query; emit one item per row with
  ``{row, rowCount, command, source: 'postgres'}`` (or one item with a
  ``rows`` array when ``dataMode == 'object'``).
- ``insert``  — insert rows into a table; emit one item per input with
  ``{affectedRows, command, lastInsertId, source: 'postgres'}``.
- ``update``  — update rows in a table; emit one item per input with
  ``{affectedRows, command, source: 'postgres'}``.
- ``upsert``  — upsert rows in a table; emit one item per input with
  ``{affectedRows, command, lastInsertId, upserted, source: 'postgres'}``.

All database calls are mock-driven — no real Postgres connection is made.

Parameters honored:

- ``operation``        (``"execute"`` / ``"insert"`` / ``"update"`` /
  ``"upsert"``; default ``"execute"``)
- ``database``         (string; ``$json.database`` /
  ``$json.databaseId`` fallback; echoed only)
- For ``execute``:
  - ``query``          (SQL string; ``$json.query`` / ``$json.sql``
    fallback; required)
  - ``queryParameters``(list of values; optional)
  - ``dataMode``       (``"array"`` / ``"object"``; default ``"array"``)
- For ``insert`` / ``update`` / ``upsert``:
  - ``table``          (string; ``$json.table`` / ``$json.tableName``
    fallback; required)
  - ``schema``         (string; default ``"public"``)
  - ``columns``        (list of column names; ``$json.columns`` fallback)
  - ``values``         (list of row value lists; ``$json.values`` /
    ``$json.data`` fallback)
  - ``where``          (SQL WHERE clause; ``$json.where`` fallback;
    update/upsert only)
  - ``idColumn``       (string; default ``"id"``; update/upsert only)

Behavior precedence:

1. ``ctx.mocks['postgres_response']`` — when present, the value drives
   the executor. A dict is used as the operation-specific response (with
   ``rows`` for execute or ``affectedRows`` for insert/update/upsert);
   a callable is invoked as
   ``mock(operation, query_or_table, params, item, ctx)`` and may return
   a dict (used per operation) or a non-dict truthy value (wrapped in a
   synthetic envelope).
2. ``ctx.mocks['db_response']`` — generic database-response fallback
   (dict with ``rows`` / ``affectedRows`` / ``body``).
3. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Postgres envelope.
4. Offline synthetic response with deterministic-looking ids.

Items with an empty resolved ``query`` (execute) or ``table``
(insert/update/upsert) are skipped (no item emitted).
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


POSTGRES_OPERATIONS: tuple[str, ...] = ("execute", "insert", "update", "upsert")
POSTGRES_DEFAULT_OPERATION: str = "execute"
POSTGRES_DEFAULT_SCHEMA: str = "public"
POSTGRES_DEFAULT_ID_COLUMN: str = "id"
POSTGRES_DEFAULT_DATA_MODE: str = "array"
POSTGRES_DATA_MODES: tuple[str, ...] = ("array", "object")


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


def _new_insert_id() -> int:
    return random.randint(1, 2_000_000_000)


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_execute_response() -> dict[str, Any]:
    """Offline fallback: a fake Postgres SELECT response."""
    return {
        "rows": [
            {"id": 1, "name": "Mock Row 1", "value": 100},
            {"id": 2, "name": "Mock Row 2", "value": 200},
        ],
        "rowCount": 2,
        "command": "SELECT",
    }


def _synthesize_insert_response(row_count: int) -> dict[str, Any]:
    """Offline fallback: a fake Postgres INSERT response."""
    return {
        "affectedRows": max(row_count, 1),
        "command": "INSERT",
        "lastInsertId": _new_insert_id(),
    }


def _synthesize_update_response() -> dict[str, Any]:
    """Offline fallback: a fake Postgres UPDATE response."""
    return {
        "affectedRows": 1,
        "command": "UPDATE",
    }


def _synthesize_upsert_response() -> dict[str, Any]:
    """Offline fallback: a fake Postgres UPSERT response."""
    return {
        "affectedRows": 1,
        "command": "INSERT",
        "lastInsertId": _new_insert_id(),
        "upserted": True,
    }


def _synthesize_response(
    operation: str, row_count: int = 0
) -> dict[str, Any]:
    if operation == "execute":
        return _synthesize_execute_response()
    if operation == "insert":
        return _synthesize_insert_response(row_count)
    if operation == "update":
        return _synthesize_update_response()
    return _synthesize_upsert_response()


# ── Response normalization ─────────────────────────────────────────────


def _normalize_execute_response(raw: dict[str, Any]) -> dict[str, Any]:
    rows_raw = raw.get("rows")
    if not isinstance(rows_raw, list):
        rows_raw = []
    rows: list[dict[str, Any]] = []
    for r in rows_raw:
        if isinstance(r, dict):
            rows.append(r)
        else:
            rows.append({"value": r})
    row_count = raw.get("rowCount")
    if not isinstance(row_count, int) or isinstance(row_count, bool):
        row_count = len(rows)
    command = _coerce_str(raw.get("command")).strip().upper() or "SELECT"
    return {"rows": rows, "rowCount": row_count, "command": command}


def _normalize_write_response(
    raw: dict[str, Any], operation: str
) -> dict[str, Any]:
    affected = raw.get("affectedRows")
    if not isinstance(affected, int) or isinstance(affected, bool):
        affected = 1
    if operation == "insert":
        command = _coerce_str(raw.get("command")).strip().upper() or "INSERT"
        last_id = raw.get("lastInsertId")
        if not isinstance(last_id, int) or isinstance(last_id, bool):
            last_id = _new_insert_id()
        return {
            "affectedRows": affected,
            "command": command,
            "lastInsertId": last_id,
        }
    if operation == "update":
        command = _coerce_str(raw.get("command")).strip().upper() or "UPDATE"
        return {"affectedRows": affected, "command": command}
    # upsert
    command = _coerce_str(raw.get("command")).strip().upper() or "INSERT"
    last_id = raw.get("lastInsertId")
    if not isinstance(last_id, int) or isinstance(last_id, bool):
        last_id = _new_insert_id()
    upserted = raw.get("upserted")
    if not isinstance(upserted, bool):
        upserted = True
    return {
        "affectedRows": affected,
        "command": command,
        "lastInsertId": last_id,
        "upserted": upserted,
    }


def _normalize_response(
    raw: dict[str, Any], operation: str
) -> dict[str, Any]:
    if operation == "execute":
        return _normalize_execute_response(raw)
    return _normalize_write_response(raw, operation)


def _response_from_http_mock(
    mock: Any, operation: str
) -> dict[str, Any] | None:
    """Extract a Postgres-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        return _normalize_response(body, operation)
    return None


def _response_from_db_mock(
    mock: Any, operation: str
) -> dict[str, Any] | None:
    """Extract a Postgres-style envelope from a generic ``db_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        return _normalize_response(body, operation)
    if "rows" in mock or "affectedRows" in mock or "command" in mock:
        return _normalize_response(mock, operation)
    return None


# ── Response resolution ────────────────────────────────────────────────


def _resolve_postgres_response(
    *,
    operation: str,
    query_or_table: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    row_count: int,
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"postgres_response"``, ``"db_response"``,
    ``"http_response"``, ``"offline"`` so downstream observers can tell
    where the result came from.
    """
    mocks = ctx.mocks or {}
    pmock = mocks.get("postgres_response")
    if pmock is not None:
        if callable(pmock):
            raw = pmock(operation, query_or_table, params, item, ctx)
        else:
            raw = pmock
        if isinstance(raw, dict):
            return _normalize_response(raw, operation), "postgres_response"
        return _synthesize_response(operation, row_count), "postgres_response"

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

    return _synthesize_response(operation, row_count), "offline"


# ── Output builders ────────────────────────────────────────────────────


def _build_execute_items(
    item: ExecutionItem,
    envelope: dict[str, Any],
    data_mode: str,
    source: str,
) -> list[ExecutionItem]:
    rows = envelope.get("rows") or []
    row_count = envelope.get("rowCount", len(rows))
    command = envelope.get("command", "SELECT")

    if data_mode == "object":
        payload: dict[str, Any] = {
            "rows": list(rows),
            "rowCount": row_count,
            "command": command,
            "source": "postgres",
        }
        if source != "postgres_response":
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        return [ni]

    items: list[ExecutionItem] = []
    for row in rows:
        payload = {
            "row": row,
            "rowCount": row_count,
            "command": command,
            "source": "postgres",
        }
        if source != "postgres_response":
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
        "affectedRows": envelope.get("affectedRows", 1),
        "command": envelope.get("command"),
        "source": "postgres",
    }
    if "lastInsertId" in envelope:
        payload["lastInsertId"] = envelope["lastInsertId"]
    if operation == "upsert":
        payload["upserted"] = envelope.get("upserted", True)
    if source != "postgres_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


# ── Main executor ──────────────────────────────────────────────────────


async def exec_postgres(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Postgres node — execute/insert/update/upsert per input item.

    - ``execute`` → emits one item per row (or one item with a ``rows``
      array when ``dataMode == 'object'``).
    - ``insert``  → emits one item per input with ``affectedRows,
      command, lastInsertId``.
    - ``update``  → emits one item per input with ``affectedRows,
      command``.
    - ``upsert``  → emits one item per input with ``affectedRows,
      command, lastInsertId, upserted``.

    Items with an empty resolved ``query`` (execute) or ``table``
    (insert/update/upsert) are skipped.
    """
    params = node.parameters or {}
    operation = str(
        params.get("operation") or POSTGRES_DEFAULT_OPERATION
    ).strip().lower()
    if operation not in POSTGRES_OPERATIONS:
        raise ValueError(
            f"postgres: unsupported operation {operation!r}; "
            f"expected one of {POSTGRES_OPERATIONS}"
        )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)

        if operation == "execute":
            query = _resolve_str_param(
                params, "query", item, ectx, ("query", "sql")
            ).strip()
            if not query:
                logger.info(
                    "postgres execute skipped: empty query on node %r",
                    node.name,
                )
                continue
            query_params = _resolve_param(
                params, "queryParameters", item, ectx
            )
            data_mode = str(
                params.get("dataMode") or POSTGRES_DEFAULT_DATA_MODE
            ).strip().lower()
            if data_mode not in POSTGRES_DATA_MODES:
                data_mode = POSTGRES_DEFAULT_DATA_MODE

            envelope, source = _resolve_postgres_response(
                operation=operation,
                query_or_table=query,
                params=params,
                item=item,
                ctx=ctx,
                row_count=0,
            )
            out.extend(
                _build_execute_items(item, envelope, data_mode, source)
            )
            logger.info(
                "postgres execute query=%r rows=%d source=%s",
                query[:80],
                envelope.get("rowCount", 0),
                source,
            )
            continue

        # insert / update / upsert
        table = _resolve_str_param(
            params, "table", item, ectx, ("table", "tableName")
        ).strip()
        if not table:
            logger.info(
                "postgres %s skipped: empty table on node %r",
                operation,
                node.name,
            )
            continue

        schema = _resolve_str_param(
            params, "schema", item, ectx
        ).strip() or POSTGRES_DEFAULT_SCHEMA
        columns = _resolve_param(params, "columns", item, ectx, ("columns",))
        values = _resolve_param(
            params, "values", item, ectx, ("values", "data")
        )

        row_count = 0
        if isinstance(values, list):
            row_count = len(values)
        elif values is not None:
            row_count = 1

        if operation in ("update", "upsert"):
            _where = _resolve_str_param(
                params, "where", item, ectx, ("where",)
            ).strip()
            _id_column = _resolve_str_param(
                params, "idColumn", item, ectx
            ).strip() or POSTGRES_DEFAULT_ID_COLUMN

        envelope, source = _resolve_postgres_response(
            operation=operation,
            query_or_table=table,
            params=params,
            item=item,
            ctx=ctx,
            row_count=row_count,
        )
        out.append(_build_write_item(item, envelope, operation, source))
        logger.info(
            "postgres %s schema=%r table=%r affected=%d source=%s",
            operation,
            schema,
            table[:80],
            envelope.get("affectedRows", 0),
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_postgres",
    "POSTGRES_OPERATIONS",
    "POSTGRES_DEFAULT_OPERATION",
    "POSTGRES_DEFAULT_SCHEMA",
    "POSTGRES_DEFAULT_ID_COLUMN",
    "POSTGRES_DEFAULT_DATA_MODE",
    "POSTGRES_DATA_MODES",
]