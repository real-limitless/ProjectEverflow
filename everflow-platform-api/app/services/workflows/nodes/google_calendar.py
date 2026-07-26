"""Google Calendar executor (clean-room n8n ``n8n-nodes-base.googleCalendar``).

v1 supports the four operations most commonly used in n8n templates:

- ``create`` — create an event on a calendar; emit one item per input with
  ``{eventId, summary, start, end, htmlLink, source: 'googleCalendar'}``.
- ``list``   — list events on a calendar; emit one item per event
  (or one item with an ``items`` array when
  ``parameters.dataMode == 'object'``).
- ``get``    — fetch a single event by id; emit one item per input with
  ``{eventId, summary, start, end, htmlLink, source: 'googleCalendar'}``.
- ``delete`` — delete an event by id; emit one item per input with
  ``{eventId, success, deletedAt, source: 'googleCalendar'}``.

Parameters honored:

- ``operation``  (``"create"`` / ``"list"`` / ``"get"`` / ``"delete"``;
  default ``"list"``)
- ``calendarId`` (string; default ``"primary"``)
- For ``create``:
  - ``summary``     (string; ``$json.summary`` / ``$json.title`` fallback)
  - ``start``       (ISO datetime; ``$json.start`` / ``$json.startTime`` fallback)
  - ``end``         (ISO datetime; ``$json.end`` / ``$json.endTime`` fallback)
  - ``description`` (string; ``$json.description`` fallback; optional)
  - ``location``    (string; ``$json.location`` fallback; optional)
  - ``attendees``   (list of emails; ``$json.attendees`` fallback; optional)
- For ``list``:
  - ``timeMin``     (ISO datetime; default now)
  - ``timeMax``     (ISO datetime; default now + 7d)
  - ``maxResults``  (int; default 10; capped at 3 offline)
  - ``q``           (search query; optional, echoed only offline)
- For ``get`` / ``delete``:
  - ``eventId``     (string; ``$json.eventId`` / ``$json.id`` fallback)
- ``dataMode``     (``"array"`` / ``"object"``; default ``"array"``;
  only meaningful for ``list``)

Behavior precedence:

1. ``ctx.mocks['calendar_response']`` — when present, the value drives the
   executor. A dict is used per operation (or operation-specific shape);
   a callable is invoked as ``mock(operation, params, item, ctx)`` and may
   return a dict (used per operation) or a non-dict truthy value
   (wrapped as the operation's envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the operation envelope.
3. Offline synthetic response with deterministic-looking ids and ISO
   timestamps.

Items with an empty resolved ``calendarId`` are skipped (no item emitted).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


CALENDAR_OPERATIONS: tuple[str, ...] = ("create", "list", "get", "delete")
CALENDAR_DEFAULT_OPERATION: str = "list"
CALENDAR_DEFAULT_CALENDAR_ID: str = "primary"
CALENDAR_DEFAULT_MAX_RESULTS: int = 10
CALENDAR_OFFLINE_MAX_EVENTS: int = 3
CALENDAR_DEFAULT_WINDOW_DAYS: int = 7
CALENDAR_DATA_MODES: tuple[str, ...] = ("array", "object")
CALENDAR_DEFAULT_DATA_MODE: str = "array"


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


def _coerce_attendees(value: Any) -> list[dict[str, str]]:
    """Coerce ``attendees`` to ``[{"email": "..."}, ...]``."""
    if value is None:
        return []
    items: list[Any]
    if isinstance(value, (list, tuple)):
        items = list(value)
    elif isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        items = parts
    else:
        return []
    out: list[dict[str, str]] = []
    for entry in items:
        if entry is None:
            continue
        if isinstance(entry, str):
            e = entry.strip()
            if e:
                out.append({"email": e})
        elif isinstance(entry, dict):
            email = _coerce_str(
                entry.get("email") or entry.get("address") or entry.get("id")
            )
            if email:
                display_name = _coerce_str(
                    entry.get("displayName") or entry.get("name")
                ) or None
                rec: dict[str, str] = {"email": email}
                if display_name:
                    rec["displayName"] = display_name
                out.append(rec)
        else:
            e = _coerce_str(entry)
            if e:
                out.append({"email": e})
    return out


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _now_plus_iso(days: int) -> str:
    return (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"


def _new_event_id() -> str:
    return f"mock_event_{uuid.uuid4().hex[:16]}"


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
        if fk in item.json and item.json[fk] is not None:
            return item.json[fk]
    return None


def _resolve_str_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
    *,
    default: str = "",
) -> str:
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    s = _coerce_str(value).strip()
    return s or default


def _resolve_calendar_id(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    # When ``calendarId`` is explicitly provided (even as an empty string),
    # the caller is opting out of the default — return the empty string so
    # the executor skips the item rather than silently falling back to
    # "primary".
    if "calendarId" in params:
        resolved = evaluate(params.get("calendarId"), ectx)
        return _coerce_str(resolved).strip()
    if "calendarId" in item.json or "calendar_id" in item.json:
        raw = item.json.get("calendarId")
        if raw is None:
            raw = item.json.get("calendar_id")
        return _coerce_str(raw).strip()
    return CALENDAR_DEFAULT_CALENDAR_ID


def _resolve_event_id(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    return _resolve_str_param(
        params, "eventId", item, ectx, ("eventId", "id")
    ).strip()


def _resolve_data_mode(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("dataMode")
    if raw is not None:
        resolved = _coerce_str(evaluate(raw, ectx)).strip().lower()
        if resolved in CALENDAR_DATA_MODES:
            return resolved
    json_mode = item.json.get("dataMode")
    if json_mode is not None:
        s = _coerce_str(json_mode).strip().lower()
        if s in CALENDAR_DATA_MODES:
            return s
    return CALENDAR_DEFAULT_DATA_MODE


def _resolve_max_results(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> int:
    raw = params.get("maxResults")
    if raw is not None:
        return _coerce_int(evaluate(raw, ectx), CALENDAR_DEFAULT_MAX_RESULTS)
    json_max = item.json.get("maxResults")
    if json_max is not None:
        return _coerce_int(json_max, CALENDAR_DEFAULT_MAX_RESULTS)
    return CALENDAR_DEFAULT_MAX_RESULTS


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_create_response(
    *,
    summary: str,
    start_iso: str,
    end_iso: str,
    event_id: str,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "summary": summary,
        "start": {"dateTime": start_iso, "timeZone": "UTC"},
        "end": {"dateTime": end_iso, "timeZone": "UTC"},
        "htmlLink": f"https://calendar.google.com/event?eid={event_id}",
    }


def _synthesize_list_response(max_results: int) -> dict[str, Any]:
    count = min(max_results, CALENDAR_OFFLINE_MAX_EVENTS)
    if count < 0:
        count = 0
    items: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        eid = f"mock_event_{i}_{uuid.uuid4().hex[:8]}"
        start_iso = _now_iso()
        end_iso = _now_plus_iso(1)
        items.append(
            {
                "id": eid,
                "summary": f"Mock Event {i}",
                "start": {"dateTime": start_iso, "timeZone": "UTC"},
                "end": {"dateTime": end_iso, "timeZone": "UTC"},
                "htmlLink": f"https://calendar.google.com/event?eid={eid}",
            }
        )
    return {"items": items, "nextPageToken": None}


def _synthesize_get_response(event_id: str) -> dict[str, Any]:
    eid = event_id or _new_event_id()
    return {
        "id": eid,
        "summary": "Mock Event",
        "start": {"dateTime": _now_iso(), "timeZone": "UTC"},
        "end": {"dateTime": _now_plus_iso(1), "timeZone": "UTC"},
        "htmlLink": f"https://calendar.google.com/event?eid={eid}",
    }


def _synthesize_delete_response(event_id: str) -> dict[str, Any]:
    return {
        "success": True,
        "eventId": event_id,
        "deletedAt": _now_iso(),
    }


# ── Envelope coercion from raw mock dicts ─────────────────────────────


def _coerce_event_envelope(
    raw: dict[str, Any],
    *,
    default_id: str,
    default_summary: str,
    default_start: str,
    default_end: str,
) -> dict[str, Any]:
    eid = _coerce_str(raw.get("id")) or default_id
    summary = _coerce_str(raw.get("summary")) or default_summary
    start_raw = raw.get("start")
    if isinstance(start_raw, dict):
        start_obj = {
            "dateTime": _coerce_str(start_raw.get("dateTime")) or default_start,
            "timeZone": _coerce_str(start_raw.get("timeZone")) or "UTC",
        }
    elif isinstance(start_raw, str) and start_raw:
        start_obj = {"dateTime": start_raw, "timeZone": "UTC"}
    else:
        start_obj = {"dateTime": default_start, "timeZone": "UTC"}
    end_raw = raw.get("end")
    if isinstance(end_raw, dict):
        end_obj = {
            "dateTime": _coerce_str(end_raw.get("dateTime")) or default_end,
            "timeZone": _coerce_str(end_raw.get("timeZone")) or "UTC",
        }
    elif isinstance(end_raw, str) and end_raw:
        end_obj = {"dateTime": end_raw, "timeZone": "UTC"}
    else:
        end_obj = {"dateTime": default_end, "timeZone": "UTC"}
    return {
        "id": eid,
        "summary": summary,
        "start": start_obj,
        "end": end_obj,
        "htmlLink": _coerce_str(raw.get("htmlLink"))
        or f"https://calendar.google.com/event?eid={eid}",
    }


def _coerce_listing_envelope(
    raw: dict[str, Any], *, max_results: int
) -> dict[str, Any]:
    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        items_raw = []
    items: list[dict[str, Any]] = []
    for i, entry in enumerate(items_raw[: max(max_results, 0)]):
        if not isinstance(entry, dict):
            continue
        eid = _coerce_str(entry.get("id")) or f"mock_event_{i}_{uuid.uuid4().hex[:8]}"
        start_obj = entry.get("start")
        if not isinstance(start_obj, dict):
            start_obj = {"dateTime": _now_iso(), "timeZone": "UTC"}
        end_obj = entry.get("end")
        if not isinstance(end_obj, dict):
            end_obj = {"dateTime": _now_plus_iso(1), "timeZone": "UTC"}
        items.append(
            {
                "id": eid,
                "summary": _coerce_str(entry.get("summary")) or f"Mock Event {i + 1}",
                "start": {
                    "dateTime": _coerce_str(start_obj.get("dateTime")) or _now_iso(),
                    "timeZone": _coerce_str(start_obj.get("timeZone")) or "UTC",
                },
                "end": {
                    "dateTime": _coerce_str(end_obj.get("dateTime"))
                    or _now_plus_iso(1),
                    "timeZone": _coerce_str(end_obj.get("timeZone")) or "UTC",
                },
                "htmlLink": _coerce_str(entry.get("htmlLink"))
                or f"https://calendar.google.com/event?eid={eid}",
            }
        )
    return {
        "items": items,
        "nextPageToken": raw.get("nextPageToken")
        if raw.get("nextPageToken") is not None
        else None,
    }


def _coerce_delete_envelope(raw: dict[str, Any], *, event_id: str) -> dict[str, Any]:
    return {
        "success": bool(raw.get("success", True)),
        "eventId": _coerce_str(raw.get("eventId")) or event_id,
        "deletedAt": _coerce_str(raw.get("deletedAt")) or _now_iso(),
    }


# ── HTTP-mock unwrapping ───────────────────────────────────────────────


def _calendar_response_from_http_mock(
    mock: Any, *, operation: str, event_id: str
) -> dict[str, Any] | None:
    """Extract a Calendar-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if operation == "list":
            return _coerce_listing_envelope(
                body, max_results=CALENDAR_OFFLINE_MAX_EVENTS
            )
        if operation == "delete":
            return _coerce_delete_envelope(body, event_id=event_id)
        if operation == "get":
            return _coerce_event_envelope(
                body,
                default_id=event_id or _new_event_id(),
                default_summary="Mock Event",
                default_start=_now_iso(),
                default_end=_now_plus_iso(1),
            )
        # create
        return _coerce_event_envelope(
            body,
            default_id=_new_event_id(),
            default_summary="Mock Event",
            default_start=_now_iso(),
            default_end=_now_plus_iso(1),
        )
    if isinstance(body, str) and body.strip():
        if operation == "list":
            return {"items": [], "nextPageToken": None, "raw": body}
        if operation == "delete":
            return {
                "success": True,
                "eventId": event_id,
                "deletedAt": _now_iso(),
                "raw": body,
            }
        if operation == "get":
            return _synthesize_get_response(event_id) | {"raw": body}
        return _synthesize_create_response(
            summary="Mock Event",
            start_iso=_now_iso(),
            end_iso=_now_plus_iso(1),
            event_id=_new_event_id(),
        ) | {"raw": body}
    return None


# ── Response resolution ────────────────────────────────────────────────


def _resolve_calendar_response(
    *,
    operation: str,
    calendar_id: str,
    event_id: str,
    summary: str,
    start_iso: str,
    end_iso: str,
    max_results: int,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"calendar_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    cmock = mocks.get("calendar_response")
    if cmock is not None:
        if callable(cmock):
            raw = cmock(operation, params, item, ctx)
        else:
            raw = cmock
        if isinstance(raw, dict):
            if operation == "list":
                return (
                    _coerce_listing_envelope(raw, max_results=max_results),
                    "calendar_response",
                )
            if operation == "delete":
                return (
                    _coerce_delete_envelope(raw, event_id=event_id),
                    "calendar_response",
                )
            if operation == "get":
                return (
                    _coerce_event_envelope(
                        raw,
                        default_id=event_id or _new_event_id(),
                        default_summary="Mock Event",
                        default_start=_now_iso(),
                        default_end=_now_plus_iso(1),
                    ),
                    "calendar_response",
                )
            # create
            return (
                _coerce_event_envelope(
                    raw,
                    default_id=_new_event_id(),
                    default_summary=summary,
                    default_start=start_iso,
                    default_end=end_iso,
                ),
                "calendar_response",
            )
        # Non-dict truthy → wrap as a synthetic envelope
        if operation == "list":
            return (
                {"items": [], "nextPageToken": None, "raw": raw},
                "calendar_response",
            )
        if operation == "delete":
            return (
                {
                    "success": True,
                    "eventId": event_id,
                    "deletedAt": _now_iso(),
                    "raw": raw,
                },
                "calendar_response",
            )
        if operation == "get":
            base = _synthesize_get_response(event_id)
            base["raw"] = raw
            return base, "calendar_response"
        base = _synthesize_create_response(
            summary=summary,
            start_iso=start_iso,
            end_iso=end_iso,
            event_id=_new_event_id(),
        )
        base["raw"] = raw
        return base, "calendar_response"

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _calendar_response_from_http_mock(
            hmock, operation=operation, event_id=event_id
        )
        if env is not None:
            return env, "http_response"

    if operation == "list":
        return _synthesize_list_response(max_results), "offline"
    if operation == "delete":
        return _synthesize_delete_response(event_id or _new_event_id()), "offline"
    if operation == "get":
        return _synthesize_get_response(event_id), "offline"
    return _synthesize_create_response(
        summary=summary,
        start_iso=start_iso,
        end_iso=end_iso,
        event_id=_new_event_id(),
    ), "offline"


# ── Main executor ──────────────────────────────────────────────────────


async def exec_google_calendar(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Calendar node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = (
        str(params.get("operation") or CALENDAR_DEFAULT_OPERATION).strip().lower()
    )
    if operation not in CALENDAR_OPERATIONS:
        raise ValueError(
            f"googleCalendar: unsupported operation {operation!r}; "
            f"expected one of {CALENDAR_OPERATIONS}"
        )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)

        calendar_id = _resolve_calendar_id(params, item, ectx)
        if not calendar_id:
            logger.info(
                "googleCalendar %s skipped: empty calendarId on node %r",
                operation,
                node.name,
            )
            continue

        data_mode = (
            _resolve_data_mode(params, item, ectx)
            if operation == "list"
            else CALENDAR_DEFAULT_DATA_MODE
        )

        if operation == "create":
            out.extend(
                _build_create_items(
                    params=params,
                    item=item,
                    ectx=ectx,
                    calendar_id=calendar_id,
                    ctx=ctx,
                )
            )
            continue

        if operation == "list":
            out.extend(
                _build_list_items(
                    params=params,
                    item=item,
                    ectx=ectx,
                    calendar_id=calendar_id,
                    data_mode=data_mode,
                    ctx=ctx,
                )
            )
            continue

        # get / delete
        event_id = _resolve_event_id(params, item, ectx)
        if not event_id:
            logger.info(
                "googleCalendar %s skipped: empty eventId on node %r",
                operation,
                node.name,
            )
            continue
        if operation == "get":
            out.extend(
                _build_get_items(
                    item=item,
                    calendar_id=calendar_id,
                    event_id=event_id,
                    params=params,
                    ctx=ctx,
                )
            )
        else:
            out.extend(
                _build_delete_items(
                    item=item,
                    calendar_id=calendar_id,
                    event_id=event_id,
                    params=params,
                    ctx=ctx,
                )
            )

    return [(0, out)]


# ── Per-operation payload builders ─────────────────────────────────────


def _build_create_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    calendar_id: str,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    summary = _resolve_str_param(
        params, "summary", item, ectx, ("summary", "title")
    ) or "Untitled event"
    start_iso = _resolve_str_param(
        params, "start", item, ectx, ("start", "startTime")
    ) or _now_iso()
    end_iso = _resolve_str_param(
        params, "end", item, ectx, ("end", "endTime")
    ) or _now_plus_iso(1)
    description = _resolve_str_param(
        params, "description", item, ectx, ("description",)
    )
    location = _resolve_str_param(
        params, "location", item, ectx, ("location",)
    )
    attendees = _coerce_attendees(
        _resolve_param(params, "attendees", item, ectx, ("attendees",))
    )
    envelope, source = _resolve_calendar_response(
        operation="create",
        calendar_id=calendar_id,
        event_id="",
        summary=summary,
        start_iso=start_iso,
        end_iso=end_iso,
        max_results=CALENDAR_OFFLINE_MAX_EVENTS,
        params=params,
        item=item,
        ctx=ctx,
    )
    payload: dict[str, Any] = {
        "eventId": envelope.get("id"),
        "summary": envelope.get("summary") or summary,
        "start": envelope.get("start")
        or {"dateTime": start_iso, "timeZone": "UTC"},
        "end": envelope.get("end") or {"dateTime": end_iso, "timeZone": "UTC"},
        "htmlLink": envelope.get("htmlLink")
        or f"https://calendar.google.com/event?eid={envelope.get('id')}",
        "calendarId": calendar_id,
        "operation": "create",
        "ok": True,
        "source": "googleCalendar",
    }
    if description:
        payload["description"] = description
    if location:
        payload["location"] = location
    if attendees:
        payload["attendees"] = attendees
    if source != "calendar_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "googleCalendar create calendar=%s eventId=%s source=%s",
        calendar_id,
        envelope.get("id"),
        source,
    )
    return [ni]


def _build_list_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    calendar_id: str,
    data_mode: str,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    max_results = _resolve_max_results(params, item, ectx)
    time_min = _resolve_str_param(
        params, "timeMin", item, ectx, ("timeMin",)
    ) or _now_iso()
    time_max = _resolve_str_param(
        params, "timeMax", item, ectx, ("timeMax",)
    ) or _now_plus_iso(CALENDAR_DEFAULT_WINDOW_DAYS)
    q = _resolve_str_param(params, "q", item, ectx, ("q", "query", "search"))
    envelope, source = _resolve_calendar_response(
        operation="list",
        calendar_id=calendar_id,
        event_id="",
        summary="",
        start_iso=time_min,
        end_iso=time_max,
        max_results=max_results,
        params=params,
        item=item,
        ctx=ctx,
    )
    events = envelope.get("items") or []
    results: list[ExecutionItem] = []

    if data_mode == "object":
        payload = {
            "items": list(events),
            "calendarId": calendar_id,
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "operation": "list",
            "ok": True,
            "source": "googleCalendar",
        }
        if q:
            payload["q"] = q
        if source != "calendar_response":
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        results.append(ni)
    else:
        if not events:
            payload = {
                "eventId": "",
                "summary": "",
                "start": {},
                "end": {},
                "htmlLink": "",
                "items": [],
                "calendarId": calendar_id,
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": max_results,
                "operation": "list",
                "ok": True,
                "source": "googleCalendar",
            }
            if q:
                payload["q"] = q
            if source != "calendar_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            results.append(ni)
        else:
            for entry in events:
                payload = {
                    "eventId": entry.get("id"),
                    "summary": entry.get("summary"),
                    "start": entry.get("start") or {},
                    "end": entry.get("end") or {},
                    "htmlLink": entry.get("htmlLink") or "",
                    "calendarId": calendar_id,
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "maxResults": max_results,
                    "operation": "list",
                    "ok": True,
                    "source": "googleCalendar",
                }
                if q:
                    payload["q"] = q
                if source != "calendar_response":
                    payload["mockSource"] = source
                ni = item.clone()
                ni.json = {**item.json, **payload}
                results.append(ni)

    logger.info(
        "googleCalendar list calendar=%s maxResults=%s source=%s count=%d",
        calendar_id,
        max_results,
        source,
        len(events),
    )
    return results


def _build_get_items(
    *,
    item: ExecutionItem,
    calendar_id: str,
    event_id: str,
    params: dict[str, Any],
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    envelope, source = _resolve_calendar_response(
        operation="get",
        calendar_id=calendar_id,
        event_id=event_id,
        summary="",
        start_iso="",
        end_iso="",
        max_results=CALENDAR_OFFLINE_MAX_EVENTS,
        params=params,
        item=item,
        ctx=ctx,
    )
    payload = {
        "eventId": envelope.get("id") or event_id,
        "summary": envelope.get("summary") or "Mock Event",
        "start": envelope.get("start")
        or {"dateTime": _now_iso(), "timeZone": "UTC"},
        "end": envelope.get("end")
        or {"dateTime": _now_plus_iso(1), "timeZone": "UTC"},
        "htmlLink": envelope.get("htmlLink")
        or f"https://calendar.google.com/event?eid={envelope.get('id') or event_id}",
        "calendarId": calendar_id,
        "operation": "get",
        "ok": True,
        "source": "googleCalendar",
    }
    if source != "calendar_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "googleCalendar get calendar=%s eventId=%s source=%s",
        calendar_id,
        event_id,
        source,
    )
    return [ni]


def _build_delete_items(
    *,
    item: ExecutionItem,
    calendar_id: str,
    event_id: str,
    params: dict[str, Any],
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    envelope, source = _resolve_calendar_response(
        operation="delete",
        calendar_id=calendar_id,
        event_id=event_id,
        summary="",
        start_iso="",
        end_iso="",
        max_results=CALENDAR_OFFLINE_MAX_EVENTS,
        params=params,
        item=item,
        ctx=ctx,
    )
    payload = {
        "eventId": envelope.get("eventId") or event_id,
        "success": bool(envelope.get("success", True)),
        "deletedAt": envelope.get("deletedAt") or _now_iso(),
        "calendarId": calendar_id,
        "operation": "delete",
        "ok": bool(envelope.get("success", True)),
        "source": "googleCalendar",
    }
    if source != "calendar_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "googleCalendar delete calendar=%s eventId=%s source=%s",
        calendar_id,
        event_id,
        source,
    )
    return [ni]


__all__ = [
    "exec_google_calendar",
    "CALENDAR_OPERATIONS",
    "CALENDAR_DEFAULT_OPERATION",
    "CALENDAR_DEFAULT_CALENDAR_ID",
    "CALENDAR_DEFAULT_MAX_RESULTS",
    "CALENDAR_OFFLINE_MAX_EVENTS",
    "CALENDAR_DEFAULT_WINDOW_DAYS",
    "CALENDAR_DATA_MODES",
    "CALENDAR_DEFAULT_DATA_MODE",
]
