"""Airtable executor (clean-room n8n ``n8n-nodes-base.airtable``).

v1 supports the five operations most commonly used in n8n templates:

- ``list``   — list records from a table; emit one item per record (or
  one item with a ``records`` array when ``dataMode == 'object'``).
- ``create`` — create records in a table; emit one item per input with
  ``{recordId, fields, createdTime, source: 'airtable'}``.
- ``read``   — read a single record by id; emit one item per input with
  ``{recordId, fields, createdTime, source: 'airtable'}``.
- ``update`` — update a single record by id; emit one item per input
  with ``{recordId, fields, createdTime, source: 'airtable'}``.
- ``upsert`` — upsert a single record by id; emit one item per input
  with ``{recordId, fields, createdTime, updatedRecords,
  createdRecords, source: 'airtable'}``.

All API calls are mock-driven — no real network I/O is performed.

Parameters honored:

- ``operation``      (``"list"`` / ``"create"`` / ``"read"`` /
  ``"update"`` / ``"upsert"``; default ``"list"``)
- ``base``           (base ID; ``$json.base`` / ``$json.baseId``
  fallback; required)
- ``table``          (table name or ID; ``$json.table`` /
  ``$json.tableId`` / ``$json.tableName`` fallback; required)
- ``view``           (string; default ``"Grid view"``; list only)
- ``maxRecords``     (int; default 10; capped at 3 offline; list only)
- ``filterByFormula``(string; optional; list only)
- ``sort``           (list of ``{field, direction}``; optional; list only)
- ``records``        (list of ``{fields: {...}}``; default
  ``$json.records`` / ``$json.data``; create only)
- ``useItemFields``  (bool; default False; create only — use item json
  as the record fields)
- ``recordId``       (string; ``$json.recordId`` / ``$json.id``
  fallback; required for read/update; optional for upsert)
- ``fields``         (dict; default ``$json.fields``; update/upsert)
- ``dataMode``       (``"array"`` / ``"object"``; default ``"array"``;
  list only)

Behavior precedence:

1. ``ctx.mocks['airtable_response']`` — when present, the value drives
   the executor. A dict is used as the operation-specific response; a
   callable is invoked as
   ``mock(operation, base, table, params, item, ctx)`` and may return
   a dict (used per operation) or a non-dict truthy value (wrapped in a
   synthetic envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the operation envelope.
3. Offline synthetic response with deterministic-looking ids and
   timestamps.

Items with an empty resolved ``base`` or ``table`` are skipped (no item
emitted). Items with an empty ``recordId`` on read/update are also
skipped.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


AIRTABLE_OPERATIONS: tuple[str, ...] = ("list", "create", "read", "update", "upsert")
AIRTABLE_DEFAULT_OPERATION: str = "list"
AIRTABLE_DEFAULT_VIEW: str = "Grid view"
AIRTABLE_DEFAULT_MAX_RECORDS: int = 10
AIRTABLE_DEFAULT_DATA_MODE: str = "array"
AIRTABLE_OFFLINE_MAX_RECORDS: int = 3


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


def _coerce_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_record_id() -> str:
    return f"rec{uuid.uuid4().hex[:8]}"


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


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_list(max_records: int) -> dict[str, Any]:
    """Offline fallback: a fake Airtable list-records response."""
    count = min(max(max_records, 0) + 1, AIRTABLE_OFFLINE_MAX_RECORDS + 1)
    records: list[dict[str, Any]] = []
    for i in range(1, count):
        records.append(
            {
                "id": f"rec{i}",
                "fields": {
                    "Name": f"Mock Record {i}",
                    "Status": "Active",
                    "Value": i * 10,
                },
                "createdTime": _now_iso(),
            }
        )
    return {"records": records}


def _synthesize_create(fields: dict[str, Any]) -> dict[str, Any]:
    """Offline fallback: a fake Airtable create-records response."""
    return {
        "records": [
            {
                "id": _new_record_id(),
                "fields": fields or {},
                "createdTime": _now_iso(),
            }
        ]
    }


def _synthesize_read(record_id: str) -> dict[str, Any]:
    """Offline fallback: a fake Airtable get-record response."""
    return {
        "id": record_id,
        "fields": {"Name": "Mock Record", "Status": "Active"},
        "createdTime": _now_iso(),
    }


def _synthesize_update(record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Offline fallback: a fake Airtable update-record response."""
    return {
        "id": record_id,
        "fields": fields or {},
        "createdTime": _now_iso(),
    }


def _synthesize_upsert(record_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Offline fallback: a fake Airtable upsert response."""
    return {
        "records": [
            {
                "id": record_id,
                "fields": fields or {},
                "createdTime": _now_iso(),
            }
        ],
        "updatedRecords": 1,
        "createdRecords": 0,
    }


# ── Response normalization ─────────────────────────────────────────────


def _normalize_list_response(raw: dict[str, Any]) -> dict[str, Any]:
    records_raw = raw.get("records")
    if not isinstance(records_raw, list):
        records_raw = []
    records: list[dict[str, Any]] = []
    for i, rec in enumerate(records_raw):
        if not isinstance(rec, dict):
            continue
        records.append(
            {
                "id": _coerce_str(rec.get("id")) or f"rec{i + 1}",
                "fields": rec.get("fields") if isinstance(rec.get("fields"), dict) else {},
                "createdTime": _coerce_str(rec.get("createdTime")) or _now_iso(),
            }
        )
    return {"records": records}


def _normalize_create_response(
    raw: dict[str, Any], fields: dict[str, Any]
) -> dict[str, Any]:
    records_raw = raw.get("records")
    if isinstance(records_raw, list) and records_raw:
        rec = records_raw[0] if isinstance(records_raw[0], dict) else {}
        return {
            "records": [
                {
                    "id": _coerce_str(rec.get("id")) or _new_record_id(),
                    "fields": rec.get("fields")
                    if isinstance(rec.get("fields"), dict)
                    else fields or {},
                    "createdTime": _coerce_str(rec.get("createdTime")) or _now_iso(),
                }
            ]
        }
    if "id" in raw or "fields" in raw:
        return {
            "records": [
                {
                    "id": _coerce_str(raw.get("id")) or _new_record_id(),
                    "fields": raw.get("fields")
                    if isinstance(raw.get("fields"), dict)
                    else fields or {},
                    "createdTime": _coerce_str(raw.get("createdTime")) or _now_iso(),
                }
            ]
        }
    return _synthesize_create(fields)


def _normalize_read_response(
    raw: dict[str, Any], record_id: str
) -> dict[str, Any]:
    return {
        "id": _coerce_str(raw.get("id")) or record_id,
        "fields": raw.get("fields") if isinstance(raw.get("fields"), dict) else {},
        "createdTime": _coerce_str(raw.get("createdTime")) or _now_iso(),
    }


def _normalize_update_response(
    raw: dict[str, Any], record_id: str, fields: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": _coerce_str(raw.get("id")) or record_id,
        "fields": raw.get("fields")
        if isinstance(raw.get("fields"), dict)
        else fields or {},
        "createdTime": _coerce_str(raw.get("createdTime")) or _now_iso(),
    }


def _normalize_upsert_response(
    raw: dict[str, Any], record_id: str, fields: dict[str, Any]
) -> dict[str, Any]:
    records_raw = raw.get("records")
    if isinstance(records_raw, list) and records_raw:
        rec = records_raw[0] if isinstance(records_raw[0], dict) else {}
        first_rec = {
            "id": _coerce_str(rec.get("id")) or record_id,
            "fields": rec.get("fields")
            if isinstance(rec.get("fields"), dict)
            else fields or {},
            "createdTime": _coerce_str(rec.get("createdTime")) or _now_iso(),
        }
    else:
        first_rec = {
            "id": _coerce_str(raw.get("id")) or record_id,
            "fields": raw.get("fields")
            if isinstance(raw.get("fields"), dict)
            else fields or {},
            "createdTime": _coerce_str(raw.get("createdTime")) or _now_iso(),
        }
    updated = raw.get("updatedRecords")
    created = raw.get("createdRecords")
    return {
        "records": [first_rec],
        "updatedRecords": int(updated)
        if isinstance(updated, (int, float)) and not isinstance(updated, bool)
        else 1,
        "createdRecords": int(created)
        if isinstance(created, (int, float)) and not isinstance(created, bool)
        else 0,
    }


def _normalize_response(
    raw: dict[str, Any],
    operation: str,
    record_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    if operation == "list":
        return _normalize_list_response(raw)
    if operation == "create":
        return _normalize_create_response(raw, fields)
    if operation == "read":
        return _normalize_read_response(raw, record_id)
    if operation == "update":
        return _normalize_update_response(raw, record_id, fields)
    return _normalize_upsert_response(raw, record_id, fields)


def _response_from_http_mock(
    mock: Any,
    operation: str,
    record_id: str,
    fields: dict[str, Any],
) -> dict[str, Any] | None:
    """Extract an Airtable-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if not isinstance(body, dict):
        return None
    return _normalize_response(body, operation, record_id, fields)


def _synthesize_response(
    operation: str,
    max_records: int,
    record_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    if operation == "list":
        return _synthesize_list(max_records)
    if operation == "create":
        return _synthesize_create(fields)
    if operation == "read":
        return _synthesize_read(record_id)
    if operation == "update":
        return _synthesize_update(record_id, fields)
    return _synthesize_upsert(record_id, fields)


# ── Response resolution ────────────────────────────────────────────────


def _resolve_airtable_response(
    *,
    operation: str,
    base: str,
    table: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    max_records: int,
    record_id: str,
    fields: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"airtable_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    amock = mocks.get("airtable_response")
    if amock is not None:
        if callable(amock):
            raw = amock(operation, base, table, params, item, ctx)
        else:
            raw = amock
        if isinstance(raw, dict):
            return (
                _normalize_response(raw, operation, record_id, fields),
                "airtable_response",
            )
        return (
            _synthesize_response(operation, max_records, record_id, fields),
            "airtable_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _response_from_http_mock(hmock, operation, record_id, fields)
        if env is not None:
            return env, "http_response"

    return (
        _synthesize_response(operation, max_records, record_id, fields),
        "offline",
    )


# ── Output builders ────────────────────────────────────────────────────


def _build_list_items(
    item: ExecutionItem,
    envelope: dict[str, Any],
    data_mode: str,
    source: str,
) -> list[ExecutionItem]:
    records = envelope.get("records") or []
    if data_mode == "object":
        payload: dict[str, Any] = {
            "records": list(records),
            "operation": "list",
            "source": "airtable",
        }
        if source != "airtable_response":
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        return [ni]

    items: list[ExecutionItem] = []
    for rec in records:
        payload = {
            "recordId": rec.get("id"),
            "fields": rec.get("fields") or {},
            "createdTime": rec.get("createdTime") or _now_iso(),
            "operation": "list",
            "source": "airtable",
        }
        if source != "airtable_response":
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        items.append(ni)
    return items


def _build_create_item(
    item: ExecutionItem, envelope: dict[str, Any], source: str
) -> ExecutionItem:
    records = envelope.get("records") or []
    rec = records[0] if records else {}
    payload = {
        "recordId": rec.get("id"),
        "fields": rec.get("fields") or {},
        "createdTime": rec.get("createdTime") or _now_iso(),
        "operation": "create",
        "source": "airtable",
    }
    if source != "airtable_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


def _build_read_item(
    item: ExecutionItem, envelope: dict[str, Any], source: str
) -> ExecutionItem:
    payload = {
        "recordId": envelope.get("id"),
        "fields": envelope.get("fields") or {},
        "createdTime": envelope.get("createdTime") or _now_iso(),
        "operation": "read",
        "source": "airtable",
    }
    if source != "airtable_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


def _build_update_item(
    item: ExecutionItem, envelope: dict[str, Any], source: str
) -> ExecutionItem:
    payload = {
        "recordId": envelope.get("id"),
        "fields": envelope.get("fields") or {},
        "createdTime": envelope.get("createdTime") or _now_iso(),
        "operation": "update",
        "source": "airtable",
    }
    if source != "airtable_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


def _build_upsert_item(
    item: ExecutionItem, envelope: dict[str, Any], source: str
) -> ExecutionItem:
    records = envelope.get("records") or []
    rec = records[0] if records else {}
    payload = {
        "recordId": rec.get("id"),
        "fields": rec.get("fields") or {},
        "createdTime": rec.get("createdTime") or _now_iso(),
        "updatedRecords": envelope.get("updatedRecords", 1),
        "createdRecords": envelope.get("createdRecords", 0),
        "operation": "upsert",
        "source": "airtable",
    }
    if source != "airtable_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    return ni


# ── Main executor ──────────────────────────────────────────────────────


async def exec_airtable(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Airtable node — list/create/read/update/upsert per input item.

    - ``list``   → emits one item per record (or one item with a
      ``records`` array when ``dataMode == 'object'``).
    - ``create`` → emits one item per input with ``recordId, fields,
      createdTime``.
    - ``read``   → emits one item per input with ``recordId, fields,
      createdTime``.
    - ``update`` → emits one item per input with ``recordId, fields,
      createdTime``.
    - ``upsert`` → emits one item per input with ``recordId, fields,
      createdTime, updatedRecords, createdRecords``.

    Items with an empty resolved ``base`` or ``table`` are skipped.
    Items with an empty ``recordId`` on read/update are also skipped.
    """
    params = node.parameters or {}
    operation = str(
        params.get("operation") or AIRTABLE_DEFAULT_OPERATION
    ).strip().lower()
    if operation not in AIRTABLE_OPERATIONS:
        raise ValueError(
            f"airtable: unsupported operation {operation!r}; "
            f"expected one of {AIRTABLE_OPERATIONS}"
        )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        base = _resolve_str_param(
            params, "base", item, ectx, ("base", "baseId")
        ).strip()
        table = _resolve_str_param(
            params, "table", item, ectx, ("table", "tableId", "tableName")
        ).strip()

        if not base or not table:
            logger.info(
                "airtable %s skipped: empty base or table on node %r",
                operation,
                node.name,
            )
            continue

        # Operation-specific params and gating
        max_records = AIRTABLE_DEFAULT_MAX_RECORDS
        record_id = ""
        fields: dict[str, Any] = {}
        data_mode = AIRTABLE_DEFAULT_DATA_MODE

        if operation == "list":
            max_records = _coerce_int(
                _resolve_param(params, "maxRecords", item, ectx),
                AIRTABLE_DEFAULT_MAX_RECORDS,
            )
            data_mode = str(
                params.get("dataMode") or AIRTABLE_DEFAULT_DATA_MODE
            ).strip().lower()
            if data_mode not in ("array", "object"):
                data_mode = AIRTABLE_DEFAULT_DATA_MODE

        elif operation == "create":
            use_item_fields = _coerce_bool(
                _resolve_param(params, "useItemFields", item, ectx)
            )
            if use_item_fields:
                create_fields = dict(item.json)
            else:
                records_data = _resolve_param(
                    params, "records", item, ectx, ("records", "data")
                )
                create_fields = {}
                if isinstance(records_data, list) and records_data:
                    first = records_data[0]
                    if isinstance(first, dict):
                        rf = first.get("fields")
                        if isinstance(rf, dict):
                            create_fields = rf
            fields = create_fields

        else:  # read / update / upsert
            record_id = _resolve_str_param(
                params, "recordId", item, ectx, ("recordId", "id")
            ).strip()
            if operation in ("read", "update") and not record_id:
                logger.info(
                    "airtable %s skipped: empty recordId on node %r",
                    operation,
                    node.name,
                )
                continue
            if operation in ("update", "upsert"):
                resolved_fields = _resolve_param(
                    params, "fields", item, ectx, ("fields",)
                )
                fields = resolved_fields if isinstance(resolved_fields, dict) else {}

        envelope, source = _resolve_airtable_response(
            operation=operation,
            base=base,
            table=table,
            params=params,
            item=item,
            ctx=ctx,
            max_records=max_records,
            record_id=record_id,
            fields=fields,
        )

        if operation == "list":
            out.extend(_build_list_items(item, envelope, data_mode, source))
        elif operation == "create":
            out.append(_build_create_item(item, envelope, source))
        elif operation == "read":
            out.append(_build_read_item(item, envelope, source))
        elif operation == "update":
            out.append(_build_update_item(item, envelope, source))
        else:  # upsert
            out.append(_build_upsert_item(item, envelope, source))

        logger.info(
            "airtable %s base=%r table=%r recordId=%r source=%s",
            operation,
            base[:80],
            table[:80],
            record_id[:80],
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_airtable",
    "AIRTABLE_OPERATIONS",
    "AIRTABLE_DEFAULT_OPERATION",
    "AIRTABLE_DEFAULT_VIEW",
    "AIRTABLE_DEFAULT_MAX_RECORDS",
    "AIRTABLE_DEFAULT_DATA_MODE",
]