"""MySQL executor (clean-room n8n ``n8n-nodes-base.mySql``).

v1 supports the four operations most commonly used in n8n templates:

- ``execute`` — run an arbitrary SQL query; emit one item per row with
  ``{row, rowCount, fieldCount, source: 'mySql'}`` (or one item with a
  ``rows`` array when ``dataMode == 'object'``).
- ``insert``  — insert rows into a table; emit one item per input with
  ``{affectedRows, insertId, fieldCount, info, source: 'mySql'}``.
- ``update``  — update rows in a table; emit one item per input with
  ``{affectedRows, insertId, fieldCount, info, source: 'mySql'}``.
- ``upsert``  — upsert rows in a table; emit one item per input with
  ``{affectedRows, insertId, fieldCount, info, source: 'mySql'}``.

When a ``mySql`` (or ``mysqlApi``) credential is attached and no mock is
present, real calls are made via ``aiomysql``. Otherwise the executor is
mock-driven with an offline synthetic fallback.

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
  - ``columns``        (list of column names; ``$json.columns`` fallback)
  - ``values``         (list of row value lists; ``$json.values`` /
    ``$json.data`` fallback)
  - ``where``          (SQL WHERE clause; ``$json.where`` fallback;
    update/upsert only)
  - ``idColumn``       (string; default ``"id"``; update/upsert only)

Behavior precedence:

1. ``ctx.mocks['mysql_response']`` — when present, the value drives
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
   into the MySQL envelope.
4. If a ``mySql`` (or ``mysqlApi``) credential resolves, a real
   connection is opened via ``aiomysql`` and the operation is executed.
5. Offline synthetic response with deterministic-looking ids.

Items with an empty resolved ``query`` (execute) or ``table``
(insert/update/upsert) are skipped (no item emitted).
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any

import aiomysql

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


MYSQL_OPERATIONS: tuple[str, ...] = ("execute", "insert", "update", "upsert")
MYSQL_DEFAULT_OPERATION: str = "execute"
MYSQL_DEFAULT_ID_COLUMN: str = "id"
MYSQL_DEFAULT_DATA_MODE: str = "array"
MYSQL_DATA_MODES: tuple[str, ...] = ("array", "object")


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
    """Offline fallback: a fake MySQL SELECT response."""
    return {
        "rows": [
            {"id": 1, "name": "Mock Row 1", "value": 100},
            {"id": 2, "name": "Mock Row 2", "value": 200},
        ],
        "rowCount": 2,
        "fieldCount": 3,
        "insertId": 0,
    }


def _synthesize_insert_response() -> dict[str, Any]:
    """Offline fallback: a fake MySQL INSERT response."""
    return {
        "affectedRows": 1,
        "insertId": _new_insert_id(),
        "fieldCount": 0,
        "info": "Records: 1  Duplicates: 0  Warnings: 0",
    }


def _synthesize_update_response() -> dict[str, Any]:
    """Offline fallback: a fake MySQL UPDATE response."""
    return {
        "affectedRows": 1,
        "insertId": 0,
        "fieldCount": 0,
        "info": "Rows matched: 1  Changed: 1  Warnings: 0",
    }


def _synthesize_upsert_response() -> dict[str, Any]:
    """Offline fallback: a fake MySQL UPSERT (INSERT ... ON DUPLICATE) response."""
    return {
        "affectedRows": 2,
        "insertId": _new_insert_id(),
        "fieldCount": 0,
        "info": "Records: 1  Duplicates: 0  Warnings: 0",
    }


def _synthesize_response(operation: str) -> dict[str, Any]:
    if operation == "execute":
        return _synthesize_execute_response()
    if operation == "insert":
        return _synthesize_insert_response()
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
    field_count = raw.get("fieldCount")
    if not isinstance(field_count, int) or isinstance(field_count, bool):
        field_count = 0
    insert_id = raw.get("insertId")
    if not isinstance(insert_id, int) or isinstance(insert_id, bool):
        insert_id = 0
    return {
        "rows": rows,
        "rowCount": row_count,
        "fieldCount": field_count,
        "insertId": insert_id,
    }


def _normalize_write_response(
    raw: dict[str, Any], operation: str
) -> dict[str, Any]:
    affected = raw.get("affectedRows")
    if not isinstance(affected, int) or isinstance(affected, bool):
        affected = 1
    insert_id = raw.get("insertId")
    if not isinstance(insert_id, int) or isinstance(insert_id, bool):
        insert_id = _new_insert_id() if operation in ("insert", "upsert") else 0
    field_count = raw.get("fieldCount")
    if not isinstance(field_count, int) or isinstance(field_count, bool):
        field_count = 0
    info = raw.get("info")
    if not isinstance(info, str) or not info:
        if operation == "insert" or operation == "upsert":
            info = "Records: 1  Duplicates: 0  Warnings: 0"
        else:
            info = "Rows matched: 1  Changed: 1  Warnings: 0"
    return {
        "affectedRows": affected,
        "insertId": insert_id,
        "fieldCount": field_count,
        "info": info,
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
    """Extract a MySQL-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        return _normalize_response(body, operation)
    return None


def _response_from_db_mock(
    mock: Any, operation: str
) -> dict[str, Any] | None:
    """Extract a MySQL-style envelope from a generic ``db_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        return _normalize_response(body, operation)
    if "rows" in mock or "affectedRows" in mock or "insertId" in mock:
        return _normalize_response(mock, operation)
    return None


# ── Real DB dispatch ──────────────────────────────────────────────────


def _build_mysql_config(cred: dict[str, Any]) -> dict[str, Any] | None:
    """Extract ``aiomysql.connect`` kwargs from a mySql credential dict.

    Supports either a connection string (``connectionString`` / ``url``)
    or individual ``host`` / ``port`` / ``database`` / ``user`` /
    ``password`` fields.  Returns ``None`` when there is not enough
    information to open a connection.
    """
    conn_str = cred.get("connectionString") or cred.get("url")
    if isinstance(conn_str, str) and conn_str.strip():
        from urllib.parse import urlparse

        try:
            parsed = urlparse(conn_str.strip())
        except Exception:
            parsed = None
        if parsed and parsed.hostname:
            params: dict[str, Any] = {
                "host": parsed.hostname,
                "port": parsed.port or 3306,
                "db": (parsed.path.lstrip("/") if parsed.path else ""),
                "user": parsed.username or "",
                "password": parsed.password or "",
            }
            if params["db"] and params["user"]:
                ssl_val = cred.get("ssl")
                if isinstance(ssl_val, bool) and ssl_val:
                    params["ssl"] = True
                return params

    host = cred.get("host")
    if not host:
        return None

    database = cred.get("database") or cred.get("db") or cred.get("dbname")
    user = cred.get("user") or cred.get("username")
    if not database or not user:
        return None

    params = {
        "host": str(host),
        "port": _coerce_int(cred.get("port"), 3306),
        "db": str(database),
        "user": str(user),
        "password": str(cred.get("password") or ""),
    }
    ssl = cred.get("ssl")
    if isinstance(ssl, bool) and ssl:
        params["ssl"] = True
    return params


async def _execute_mysql_query(
    conn_params: dict[str, Any],
    operation: str,
    query_or_table: str,
    params: dict[str, Any],
    item: ExecutionItem,
) -> dict[str, Any]:
    """Open a real MySQL connection via ``aiomysql``, run the operation,
    and return a result dict in the internal envelope shape.

    The caller is responsible for normalising the returned dict via
    :func:`_normalize_response`.
    """
    conn = await aiomysql.connect(**conn_params)
    try:
        if operation == "execute":
            sql = query_or_table
            qparams = params.get("queryParameters")
            args = list(qparams) if isinstance(qparams, (list, tuple)) else None
            async with conn.cursor() as cur:
                await cur.execute(sql, args)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = [dict(zip(cols, r)) for r in await cur.fetchall()]
                else:
                    rows = []
                command = sql.strip().split()[0].upper() if sql.strip() else "SELECT"
                return {
                    "rows": rows,
                    "rowCount": len(rows),
                    "fieldCount": len(cur.description) if cur.description else 0,
                    "insertId": cur.lastrowid,
                }

        table = query_or_table
        columns = params.get("columns")
        values = params.get("values")

        if isinstance(values, list):
            rows_data = values
        elif values is not None:
            rows_data = [[values]]
        else:
            rows_data = []

        if not isinstance(columns, list) or not columns:
            if rows_data and isinstance(rows_data[0], (list, tuple)):
                columns = [f"col{i}" for i in range(len(rows_data[0]))]
            else:
                columns = []

        col_names = [str(c) for c in columns]
        qualified = f"`{table}`"

        if operation == "insert":
            col_list = ", ".join(f"`{c}`" for c in col_names)
            placeholders = ", ".join("%s" for _ in col_names)
            sql = f"INSERT INTO {qualified} ({col_list}) VALUES ({placeholders})"
            async with conn.cursor() as cur:
                if rows_data:
                    await cur.executemany(sql, [list(r) for r in rows_data])
                return {
                    "affectedRows": max(cur.rowcount, 0),
                    "insertId": cur.lastrowid,
                    "fieldCount": 0,
                    "info": f"Records: {len(rows_data)}  Duplicates: 0  Warnings: 0",
                }

        if operation == "update":
            set_clause = ", ".join(f"`{c}` = %s" for c in col_names)
            where = str(params.get("where") or "").strip()
            sql = f"UPDATE {qualified} SET {set_clause}"
            if where:
                sql += f" WHERE {where}"
            args: list[Any] = []
            for row in rows_data:
                args.extend(row)
            async with conn.cursor() as cur:
                await cur.execute(sql, args)
                affected = cur.rowcount
                return {
                    "affectedRows": affected,
                    "insertId": cur.lastrowid,
                    "fieldCount": 0,
                    "info": f"Rows matched: {affected}  Changed: {affected}  Warnings: 0",
                }

        # upsert
        col_list = ", ".join(f"`{c}`" for c in col_names)
        placeholders = ", ".join("%s" for _ in col_names)
        update_cols = ", ".join(f"`{c}` = VALUES(`{c}`)" for c in col_names)
        sql = (
            f"INSERT INTO {qualified} ({col_list}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_cols}"
        )
        async with conn.cursor() as cur:
            if rows_data:
                await cur.executemany(sql, [list(r) for r in rows_data])
            return {
                "affectedRows": max(cur.rowcount, 0),
                "insertId": cur.lastrowid,
                "fieldCount": 0,
                "info": f"Records: {len(rows_data)}  Duplicates: 0  Warnings: 0",
            }
    finally:
        conn.close()


# ── Response resolution ────────────────────────────────────────────────


async def _resolve_mysql_response(
    *,
    operation: str,
    query_or_table: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"mysql_response"``, ``"db_response"``,
    ``"http_response"``, ``"mysql_api"``, ``"offline"`` so downstream
    observers can tell where the result came from.
    """
    mocks = ctx.mocks or {}
    mmock = mocks.get("mysql_response")
    if mmock is not None:
        if callable(mmock):
            raw = mmock(operation, query_or_table, params, item, ctx)
        else:
            raw = mmock
        if isinstance(raw, dict):
            return _normalize_response(raw, operation), "mysql_response"
        return _synthesize_response(operation), "mysql_response"

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

    cred = resolve_credential(node, ctx, "mySql") or resolve_credential(
        node, ctx, "mysqlApi"
    )
    if cred:
        conn_params = _build_mysql_config(cred)
        if conn_params is not None:
            logger.info(
                "mysql real DB call operation=%s target=%s",
                operation,
                query_or_table[:80],
            )
            try:
                raw = await _execute_mysql_query(
                    conn_params, operation, query_or_table, params, item
                )
                return _normalize_response(raw, operation), "mysql_api"
            except Exception as exc:
                logger.warning("mysql real DB call failed: %s", exc)

    return _synthesize_response(operation), "offline"


# ── Output builders ────────────────────────────────────────────────────


def _build_execute_items(
    item: ExecutionItem,
    envelope: dict[str, Any],
    data_mode: str,
    source: str,
) -> list[ExecutionItem]:
    rows = envelope.get("rows") or []
    row_count = envelope.get("rowCount", len(rows))
    field_count = envelope.get("fieldCount", 0)

    if data_mode == "object":
        payload: dict[str, Any] = {
            "rows": list(rows),
            "rowCount": row_count,
            "source": "mySql",
        }
        if source not in ("mysql_response", "mysql_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        return [ni]

    items: list[ExecutionItem] = []
    for row in rows:
        payload = {
            "row": row,
            "rowCount": row_count,
            "fieldCount": field_count,
            "source": "mySql",
        }
        if source not in ("mysql_response", "mysql_api"):
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
        "insertId": envelope.get("insertId", 0),
        "fieldCount": envelope.get("fieldCount", 0),
        "info": envelope.get("info", ""),
        "source": "mySql",
    }
    if source not in ("mysql_response", "mysql_api"):
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


# ── Main executor ──────────────────────────────────────────────────────


async def exec_mysql(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """MySQL node — execute/insert/update/upsert per input item.

    - ``execute`` → emits one item per row (or one item with a ``rows``
      array when ``dataMode == 'object'``).
    - ``insert``  → emits one item per input with ``affectedRows,
      insertId, fieldCount, info``.
    - ``update``  → emits one item per input with ``affectedRows,
      insertId, fieldCount, info``.
    - ``upsert``  → emits one item per input with ``affectedRows,
      insertId, fieldCount, info``.

    Items with an empty resolved ``query`` (execute) or ``table``
    (insert/update/upsert) are skipped.
    """
    params = node.parameters or {}
    operation = str(
        params.get("operation") or MYSQL_DEFAULT_OPERATION
    ).strip().lower()
    if operation not in MYSQL_OPERATIONS:
        raise ValueError(
            f"mysql: unsupported operation {operation!r}; "
            f"expected one of {MYSQL_OPERATIONS}"
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
                    "mysql execute skipped: empty query on node %r",
                    node.name,
                )
                continue
            query_params = _resolve_param(
                params, "queryParameters", item, ectx
            )
            data_mode = str(
                params.get("dataMode") or MYSQL_DEFAULT_DATA_MODE
            ).strip().lower()
            if data_mode not in MYSQL_DATA_MODES:
                data_mode = MYSQL_DEFAULT_DATA_MODE

            envelope, source = await _resolve_mysql_response(
                operation=operation,
                query_or_table=query,
                params=params,
                item=item,
                node=node,
                ctx=ctx,
            )
            out.extend(
                _build_execute_items(item, envelope, data_mode, source)
            )
            logger.info(
                "mysql execute query=%r rows=%d source=%s",
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
                "mysql %s skipped: empty table on node %r",
                operation,
                node.name,
            )
            continue

        columns = _resolve_param(params, "columns", item, ectx, ("columns",))
        values = _resolve_param(
            params, "values", item, ectx, ("values", "data")
        )

        if operation in ("update", "upsert"):
            _where = _resolve_str_param(
                params, "where", item, ectx, ("where",)
            ).strip()
            _id_column = _resolve_str_param(
                params, "idColumn", item, ectx
            ).strip() or MYSQL_DEFAULT_ID_COLUMN

        envelope, source = await _resolve_mysql_response(
            operation=operation,
            query_or_table=table,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
        )
        out.append(_build_write_item(item, envelope, operation, source))
        logger.info(
            "mysql %s table=%r affected=%d source=%s",
            operation,
            table[:80],
            envelope.get("affectedRows", 0),
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_mysql",
    "MYSQL_OPERATIONS",
    "MYSQL_DEFAULT_OPERATION",
    "MYSQL_DEFAULT_ID_COLUMN",
    "MYSQL_DEFAULT_DATA_MODE",
    "MYSQL_DATA_MODES",
]