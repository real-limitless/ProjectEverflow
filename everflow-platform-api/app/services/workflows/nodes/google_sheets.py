"""Google Sheets executor (clean-room n8n ``n8n-nodes-base.googleSheets``).

v1 supports the three operations most commonly used in n8n templates:

- ``read``   — read rows from a sheet (Sheets API
  ``GET /v4/spreadsheets/{spreadsheetId}/values/{range}``), emitting one
  item per row with ``{range, majorDimension, values, rowCount,
  source: 'googleSheets'}`` (or one item carrying all values when no
  values are returned).
- ``append`` — append rows to a sheet
  (``POST /v4/spreadsheets/{spreadsheetId}/values/{range}:append``),
  emitting one item per input with
  ``{spreadsheetId, updatedRange, updatedRows, updatedColumns,
  source: 'googleSheets'}``.
- ``update`` — update rows in a sheet
  (``PUT /v4/spreadsheets/{spreadsheetId}/values/{range}``), emitting
  one item per input with
  ``{spreadsheetId, updatedRange, updatedRows, updatedColumns,
  updatedCells, source: 'googleSheets'}``.

When a ``googleSheetsOAuth2Api`` credential is attached and no mock is
present, real calls are made to the Google Sheets API via
:func:`execute_http_request`. Otherwise the executor is mock-driven with
an offline synthetic fallback.

Parameters honored:

- ``operation``     (``"read"`` / ``"append"`` / ``"update"``;
  default ``"read"``)
- ``sheetId``       (string; ``$json.sheetId`` /
  ``$json.spreadsheetId`` fallback; required)
- ``range``         (string; default ``"A1:Z1000"``)
- ``dataMode``      (``"auto"`` / ``"array"`` / ``"object"``;
  default ``"array"``)
- ``majorDimension``(``"ROWS"`` / ``"COLUMNS"``; default ``"ROWS"``;
  used by ``read``)
- ``data``          (list of rows or dict; default from
  ``$json.data`` / ``$json.values``; used by ``append`` / ``update``)

Behavior precedence:

1. ``ctx.mocks['sheets_response']`` — when present, the value drives the
   executor. A dict with ``{range, majorDimension, values}`` (for
   ``read``) or ``{updates: {spreadsheetId, updatedRange, updatedRows,
   updatedColumns, updatedCells}}`` (for ``append``/``update``) is used
   directly; a callable is invoked as
   ``mock(operation, sheetId, range, params, item, ctx)`` and may return
   either a dict (used as-is) or any other truthy value (wrapped in a
   synthetic envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Sheets envelope.
3. If a ``googleSheetsOAuth2Api`` credential resolves (``accessToken`` /
   ``token`` present), a real Sheets API call is made and the response
   envelope is used.
4. Offline synthetic response:
   - ``read``:   ``{range, majorDimension: 'ROWS',
     values: [['mock', 'row1', 'data'], ['mock', 'row2', 'data']]}``
   - ``append``: ``{updates: {spreadsheetId: sheetId, updatedRange:
     range, updatedRows: 1, updatedColumns: 3, updatedCells: 3}}``
   - ``update``: ``{spreadsheetId: sheetId, updatedRange: range,
     updatedRows: 1, updatedColumns: 3, updatedCells: 3}``

Items with an empty resolved ``sheetId`` are skipped (no item emitted).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


SHEETS_OPERATIONS: tuple[str, ...] = ("read", "append", "update")
SHEETS_DATA_MODES: tuple[str, ...] = ("auto", "array", "object")
SHEETS_MAJOR_DIMENSIONS: tuple[str, ...] = ("ROWS", "COLUMNS")
SHEETS_DEFAULT_RANGE: str = "A1:Z1000"
SHEETS_DEFAULT_MAJOR_DIMENSION: str = "ROWS"
SHEETS_DEFAULT_DATA_MODE: str = "array"


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
        for key in ("value", "name", "id", "text", "content", "message"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_data(value: Any) -> list[list[Any]]:
    """Coerce ``data`` to a list-of-rows (list[list[Any]]).

    Accepts:

    - ``[[1, 2], [3, 4]]``                → ``[[1, 2], [3, 4]]``
    - ``[{"a": 1, "b": 2}, ...]``         → rows from the union of keys
    - ``{"values": [...]}``                → recurse into the values key
    - ``"a,b\nc,d"``                       → split on ``\n`` then ``,``
    - scalar → wrapped as a single cell
    """
    if value is None:
        return []
    if isinstance(value, str):
        lines = [ln for ln in value.splitlines() if ln.strip()]
        if not lines:
            return []
        rows: list[list[Any]] = []
        for line in lines:
            rows.append([_coerce_cell(c) for c in line.split(",")])
        return rows
    if isinstance(value, dict):
        if "values" in value and value["values"] is not None:
            return _coerce_data(value["values"])
        if "data" in value and value["data"] is not None:
            return _coerce_data(value["data"])
        # Dict-of-dicts → wrap in a single cell
        if value and all(isinstance(v, (str, int, float, bool)) for v in value.values()):
            return [[_coerce_cell(v) for v in value.values()]]
        return [value]
    if isinstance(value, (list, tuple)):
        if not value:
            return []
        first = value[0]
        # list[dict] → object mode
        if isinstance(first, dict):
            keys: list[str] = []
            for entry in value:
                if isinstance(entry, dict):
                    for k in entry.keys():
                        if k not in keys:
                            keys.append(k)
            rows = []
            for entry in value:
                if isinstance(entry, dict):
                    rows.append([entry.get(k) for k in keys])
                else:
                    rows.append([entry])
            return rows
        # list[list[...]] → array mode
        if isinstance(first, (list, tuple)):
            return [
                [_coerce_cell(c) for c in (row if isinstance(row, (list, tuple)) else [row])]
                for row in value
            ]
        # list of scalars → single row
        return [[_coerce_cell(c) for c in value]]
    # Scalar → single cell
    return [[_coerce_cell(value)]]


def _coerce_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return ", ".join(_coerce_str(v) for v in value if v is not None)
    if isinstance(value, dict):
        return _coerce_str(value)
    return str(value)


def _resolve_sheet_id(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("sheetId")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved).strip()
        if s:
            return s
    return _coerce_str(
        item.json.get("sheetId") or item.json.get("spreadsheetId")
    ).strip()


def _resolve_range(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("range")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved).strip()
        if s:
            return s
    json_range = item.json.get("range")
    if json_range is not None and str(json_range).strip():
        return _coerce_str(json_range).strip()
    return SHEETS_DEFAULT_RANGE


def _resolve_data_mode(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("dataMode")
    if raw is not None:
        resolved = _coerce_str(evaluate(raw, ectx)).strip().lower()
        if resolved in SHEETS_DATA_MODES:
            return resolved
    json_mode = item.json.get("dataMode")
    if json_mode is not None:
        s = _coerce_str(json_mode).strip().lower()
        if s in SHEETS_DATA_MODES:
            return s
    return SHEETS_DEFAULT_DATA_MODE


def _resolve_major_dimension(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("majorDimension")
    if raw is not None:
        resolved = _coerce_str(evaluate(raw, ectx)).strip().upper()
        if resolved in SHEETS_MAJOR_DIMENSIONS:
            return resolved
    json_dim = item.json.get("majorDimension")
    if json_dim is not None:
        s = _coerce_str(json_dim).strip().upper()
        if s in SHEETS_MAJOR_DIMENSIONS:
            return s
    return SHEETS_DEFAULT_MAJOR_DIMENSION


def _resolve_data(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> list[list[Any]]:
    raw = params.get("data")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        if resolved is not None:
            coerced = _coerce_data(resolved)
            if coerced:
                return coerced
    json_data = item.json.get("data")
    if json_data is not None:
        coerced = _coerce_data(json_data)
        if coerced:
            return coerced
    json_values = item.json.get("values")
    if json_values is not None:
        coerced = _coerce_data(json_values)
        if coerced:
            return coerced
    return []


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_read_response(
    range_str: str, major_dimension: str
) -> dict[str, Any]:
    """Offline fallback: a fake Sheets values response."""
    return {
        "range": range_str,
        "majorDimension": major_dimension or "ROWS",
        "values": [
            ["mock", "row1", "data"],
            ["mock", "row2", "data"],
        ],
    }


def _synthesize_append_response(
    sheet_id: str, range_str: str
) -> dict[str, Any]:
    """Offline fallback: a fake Sheets append response."""
    return {
        "spreadsheetId": sheet_id,
        "updates": {
            "spreadsheetId": sheet_id,
            "updatedRange": f"{range_str}",
            "updatedRows": 1,
            "updatedColumns": 3,
            "updatedCells": 3,
        },
    }


def _synthesize_update_response(
    sheet_id: str, range_str: str
) -> dict[str, Any]:
    """Offline fallback: a fake Sheets update response."""
    return {
        "spreadsheetId": sheet_id,
        "updatedRange": f"{range_str}",
        "updatedRows": 1,
        "updatedColumns": 3,
        "updatedCells": 3,
    }


# ── HTTP-mock unwrapping ───────────────────────────────────────────────


def _sheets_response_from_http_mock(
    mock: Any, *, operation: str, sheet_id: str, range_str: str
) -> dict[str, Any] | None:
    """Extract a Sheets-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if operation == "read":
            if "values" in body or "range" in body:
                return {
                    "range": body.get("range") or range_str,
                    "majorDimension": body.get("majorDimension") or "ROWS",
                    "values": body.get("values") or [],
                }
            return {
                "range": range_str,
                "majorDimension": "ROWS",
                "values": [],
                "raw": body,
            }
        # append / update
        updates = body.get("updates")
        if isinstance(updates, dict):
            return {
                "spreadsheetId": body.get("spreadsheetId")
                or (updates.get("spreadsheetId") if isinstance(updates, dict) else None)
                or sheet_id,
                "updates": {
                    "spreadsheetId": updates.get("spreadsheetId") or sheet_id,
                    "updatedRange": updates.get("updatedRange")
                    or f"{range_str}",
                    "updatedRows": updates.get("updatedRows", 1),
                    "updatedColumns": updates.get("updatedColumns", 0),
                    "updatedCells": updates.get("updatedCells", 0),
                },
            }
        if (
            "updatedRange" in body
            or "updatedRows" in body
            or "updatedCells" in body
        ):
            return {
                "spreadsheetId": body.get("spreadsheetId") or sheet_id,
                "updatedRange": body.get("updatedRange") or f"{range_str}",
                "updatedRows": body.get("updatedRows", 1),
                "updatedColumns": body.get("updatedColumns", 0),
                "updatedCells": body.get("updatedCells", 0),
            }
        return {
            "spreadsheetId": sheet_id,
            "updatedRange": f"{range_str}",
            "updatedRows": 1,
            "updatedColumns": 0,
            "updatedCells": 0,
            "raw": body,
        }
    if isinstance(body, str) and body.strip():
        if operation == "read":
            return {
                "range": range_str,
                "majorDimension": "ROWS",
                "values": [],
            }
        return {
            "spreadsheetId": sheet_id,
            "updatedRange": f"{range_str}",
            "updatedRows": 1,
            "updatedColumns": 0,
            "updatedCells": 0,
            "raw": body,
        }
    return None


# ── Real HTTP request builders ─────────────────────────────────────────


def _sheets_token(cred: dict[str, Any]) -> str:
    return str(cred.get("accessToken") or cred.get("token") or cred.get("access_token") or "")


def _build_sheets_request(
    cred: dict[str, Any],
    *,
    operation: str,
    sheet_id: str,
    range_str: str,
    major_dimension: str,
    data: list[list[Any]],
) -> HttpRequestConfig | None:
    """Build a real Google Sheets API request config.

    Returns ``None`` when the credential has no access token.
    """
    token = _sheets_token(cred)
    if not token:
        return None
    encoded_range = quote(range_str, safe="")
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(sheet_id, safe='')}/values"
    headers = {"Authorization": f"Bearer {token}"}
    if operation == "read":
        url = f"{base}/{encoded_range}"
        if major_dimension and major_dimension != "ROWS":
            url = f"{url}?majorDimension={quote(major_dimension, safe='')}"
        return HttpRequestConfig(
            url=url,
            method="GET",
            headers=headers,
            body_mode="none",
            response_mode="json",
            timeout=30.0,
        )
    if operation == "append":
        return HttpRequestConfig(
            url=f"{base}/{encoded_range}:append?valueInputOption=USER_ENTERED",
            method="POST",
            headers={**headers, "Content-Type": "application/json"},
            body={"values": data},
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )
    # update
    return HttpRequestConfig(
        url=f"{base}/{encoded_range}?valueInputOption=USER_ENTERED",
        method="PUT",
        headers={**headers, "Content-Type": "application/json"},
        body={"values": data},
        body_mode="json",
        response_mode="json",
        timeout=30.0,
    )


def _envelope_from_sheets_api(
    data: dict[str, Any],
    *,
    operation: str,
    sheet_id: str,
    range_str: str,
    major_dimension: str,
) -> dict[str, Any]:
    """Normalize a real Sheets API response into the internal envelope shape."""
    return _normalize_sheets_envelope(
        data,
        operation=operation,
        sheet_id=sheet_id,
        range_str=range_str,
        major_dimension=major_dimension,
    )


# ── Response resolution ────────────────────────────────────────────────


async def _resolve_sheets_response(
    *,
    operation: str,
    sheet_id: str,
    range_str: str,
    major_dimension: str,
    data: list[list[Any]],
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"sheets_response"``, ``"http_response"``,
    ``"google_sheets_api"``, ``"offline"`` so downstream observers can
    tell where the result came from.
    """
    mocks = ctx.mocks or {}
    smock = mocks.get("sheets_response")
    if smock is not None:
        if callable(smock):
            raw = smock(operation, sheet_id, range_str, params, item, ctx)
        else:
            raw = smock
        if isinstance(raw, dict):
            return _normalize_sheets_envelope(
                raw,
                operation=operation,
                sheet_id=sheet_id,
                range_str=range_str,
                major_dimension=major_dimension,
            ), "sheets_response"
        # Non-dict truthy → wrap as synthetic
        if operation == "read":
            return (
                _synthesize_read_response(range_str, major_dimension) | {"raw": raw},
                "sheets_response",
            )
        if operation == "append":
            return (
                _synthesize_append_response(sheet_id, range_str) | {"raw": raw},
                "sheets_response",
            )
        return (
            _synthesize_update_response(sheet_id, range_str) | {"raw": raw},
            "sheets_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _sheets_response_from_http_mock(
            hmock, operation=operation, sheet_id=sheet_id, range_str=range_str
        )
        if env is not None:
            return env, "http_response"

    cred = resolve_credential(node, ctx, "googleSheetsOAuth2Api")
    if cred:
        cfg = _build_sheets_request(
            cred,
            operation=operation,
            sheet_id=sheet_id,
            range_str=range_str,
            major_dimension=major_dimension,
            data=data,
        )
        if cfg is not None:
            logger.info(
                "googleSheets real HTTP call op=%s sheet=%s range=%s",
                operation,
                sheet_id,
                range_str,
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_sheets_api(
                            resp.body,
                            operation=operation,
                            sheet_id=sheet_id,
                            range_str=range_str,
                            major_dimension=major_dimension,
                        ),
                        "google_sheets_api",
                    )
            except Exception as exc:
                logger.warning("googleSheets HTTP call failed: %s", exc)

    if operation == "read":
        return _synthesize_read_response(range_str, major_dimension), "offline"
    if operation == "append":
        return _synthesize_append_response(sheet_id, range_str), "offline"
    return _synthesize_update_response(sheet_id, range_str), "offline"


def _normalize_sheets_envelope(
    raw: dict[str, Any],
    *,
    operation: str,
    sheet_id: str,
    range_str: str,
    major_dimension: str,
) -> dict[str, Any]:
    """Normalize a mock envelope into the canonical operation shape."""
    if operation == "read":
        return {
            "range": raw.get("range") or range_str,
            "majorDimension": raw.get("majorDimension") or major_dimension or "ROWS",
            "values": raw.get("values") or [],
        }
    if operation == "append":
        updates = raw.get("updates")
        if isinstance(updates, dict):
            return {
                "spreadsheetId": raw.get("spreadsheetId")
                or updates.get("spreadsheetId")
                or sheet_id,
                "updates": {
                    "spreadsheetId": updates.get("spreadsheetId") or sheet_id,
                    "updatedRange": updates.get("updatedRange") or f"{range_str}",
                    "updatedRows": updates.get("updatedRows", 1),
                    "updatedColumns": updates.get("updatedColumns", 0),
                    "updatedCells": updates.get("updatedCells", 0),
                },
            }
        return {
            "spreadsheetId": raw.get("spreadsheetId") or sheet_id,
            "updates": {
                "spreadsheetId": raw.get("spreadsheetId") or sheet_id,
                "updatedRange": raw.get("updatedRange") or f"{range_str}",
                "updatedRows": raw.get("updatedRows", 1),
                "updatedColumns": raw.get("updatedColumns", 0),
                "updatedCells": raw.get("updatedCells", 0),
            },
        }
    # update
    return {
        "spreadsheetId": raw.get("spreadsheetId") or sheet_id,
        "updatedRange": raw.get("updatedRange") or f"{range_str}",
        "updatedRows": raw.get("updatedRows", 1),
        "updatedColumns": raw.get("updatedColumns", 0),
        "updatedCells": raw.get("updatedCells", 0),
    }


# ── Main executor ──────────────────────────────────────────────────────


async def exec_google_sheets(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Sheets node — read/append/update per input item.

    - ``read``  → emits one item per row, or one item with the full
      ``values`` list when the response has no values.
    - ``append``→ emits one item per input with ``spreadsheetId,
      updatedRange, updatedRows, updatedColumns``.
    - ``update``→ emits one item per input with ``spreadsheetId,
      updatedRange, updatedRows, updatedColumns, updatedCells``.

    Items with an empty resolved ``sheetId`` are skipped.
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or "read").strip().lower()
    if operation not in SHEETS_OPERATIONS:
        raise ValueError(
            f"googleSheets: unsupported operation {operation!r}; "
            f"expected one of {SHEETS_OPERATIONS}"
        )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        sheet_id = _resolve_sheet_id(params, item, ectx)
        range_str = _resolve_range(params, item, ectx)
        data_mode = _resolve_data_mode(params, item, ectx)
        major_dimension = (
            _resolve_major_dimension(params, item, ectx)
            if operation == "read"
            else SHEETS_DEFAULT_MAJOR_DIMENSION
        )

        if not sheet_id:
            logger.info(
                "googleSheets %s skipped: empty sheetId on node %r",
                operation,
                node.name,
            )
            continue

        data = _resolve_data(params, item, ectx) if operation != "read" else []
        envelope, source = await _resolve_sheets_response(
            operation=operation,
            sheet_id=sheet_id,
            range_str=range_str,
            major_dimension=major_dimension,
            data=data,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
        )

        if operation == "read":
            out.extend(
                _build_read_items(
                    item=item,
                    envelope=envelope,
                    sheet_id=sheet_id,
                    range_str=range_str,
                    major_dimension=major_dimension,
                    data_mode=data_mode,
                    source=source,
                )
            )
            continue

        if operation == "append":
            payload = _build_append_payload(
                envelope=envelope,
                sheet_id=sheet_id,
                range_str=range_str,
                data=data,
                source=source,
            )
        else:
            payload = _build_update_payload(
                envelope=envelope,
                sheet_id=sheet_id,
                range_str=range_str,
                data=data,
                source=source,
            )

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "googleSheets %s sheet=%s range=%s source=%s",
            operation,
            sheet_id,
            range_str,
            source,
        )

    return [(0, out)]


# ── Per-operation payload builders ─────────────────────────────────────


def _build_read_items(
    *,
    item: ExecutionItem,
    envelope: dict[str, Any],
    sheet_id: str,
    range_str: str,
    major_dimension: str,
    data_mode: str,
    source: str,
) -> list[ExecutionItem]:
    """Build output items for a ``read`` operation.

    Emits one item per row when the envelope has values, otherwise a
    single item carrying the (empty) values list.
    """
    values = envelope.get("values") or []
    resolved_range = envelope.get("range") or range_str
    resolved_dim = envelope.get("majorDimension") or major_dimension or "ROWS"

    if not values:
        payload: dict[str, Any] = {
            "range": resolved_range,
            "majorDimension": resolved_dim,
            "values": [],
            "rowCount": 0,
            "sheetId": sheet_id,
            "dataMode": data_mode,
            "source": "googleSheets",
        }
        if source not in ("sheets_response", "google_sheets_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        return [ni]

    items: list[ExecutionItem] = []
    for row in values:
        row_list = list(row) if isinstance(row, (list, tuple)) else [row]
        payload = {
            "range": resolved_range,
            "majorDimension": resolved_dim,
            "values": row_list,
            "rowCount": 1,
            "sheetId": sheet_id,
            "dataMode": data_mode,
            "source": "googleSheets",
        }
        if source not in ("sheets_response", "google_sheets_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        items.append(ni)
    return items


def _build_append_payload(
    *,
    envelope: dict[str, Any],
    sheet_id: str,
    range_str: str,
    data: list[list[Any]],
    source: str,
) -> dict[str, Any]:
    updates = envelope.get("updates") if isinstance(envelope, dict) else None
    if not isinstance(updates, dict):
        updates = {}
    payload = {
        "spreadsheetId": (
            (envelope.get("spreadsheetId") if isinstance(envelope, dict) else None)
            or updates.get("spreadsheetId")
            or sheet_id
        ),
        "updatedRange": (
            updates.get("updatedRange")
            or (envelope.get("updatedRange") if isinstance(envelope, dict) else None)
            or f"{range_str}"
        ),
        "updatedRows": updates.get("updatedRows", 1),
        "updatedColumns": updates.get("updatedColumns", 0),
        "source": "googleSheets",
    }
    if source not in ("sheets_response", "google_sheets_api"):
        payload["mockSource"] = source
    return payload


def _build_update_payload(
    *,
    envelope: dict[str, Any],
    sheet_id: str,
    range_str: str,
    data: list[list[Any]],
    source: str,
) -> dict[str, Any]:
    payload = {
        "spreadsheetId": (
            (envelope.get("spreadsheetId") if isinstance(envelope, dict) else None)
            or sheet_id
        ),
        "updatedRange": (
            (envelope.get("updatedRange") if isinstance(envelope, dict) else None)
            or f"{range_str}"
        ),
        "updatedRows": (
            (envelope.get("updatedRows") if isinstance(envelope, dict) else None)
            if (isinstance(envelope, dict) and "updatedRows" in envelope)
            else 0
        ) or 0,
        "updatedColumns": (
            envelope.get("updatedColumns") if isinstance(envelope, dict) else None
        )
        or 0,
        "updatedCells": (
            envelope.get("updatedCells") if isinstance(envelope, dict) else None
        )
        or 0,
        "source": "googleSheets",
    }
    if payload["updatedRows"] == 0:
        payload["updatedRows"] = 1
    if source not in ("sheets_response", "google_sheets_api"):
        payload["mockSource"] = source
    return payload


__all__ = [
    "exec_google_sheets",
    "SHEETS_OPERATIONS",
    "SHEETS_DATA_MODES",
    "SHEETS_MAJOR_DIMENSIONS",
    "SHEETS_DEFAULT_RANGE",
    "SHEETS_DEFAULT_MAJOR_DIMENSION",
    "SHEETS_DEFAULT_DATA_MODE",
]
