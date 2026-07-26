"""Notion executor (clean-room n8n ``n8n-nodes-base.notion``).

v1 supports the five operations most commonly used in n8n templates:

- ``search``       — search pages/databases; emit one item per result
  (or one item with a ``results`` array when ``dataMode == 'object'``)
  carrying ``{pageId, title, url, object, createdTime, source: 'notion'}``.
- ``createPage``   — create a page under a database or page parent;
  emit one item per input with
  ``{pageId, url, parentId, properties, createdTime, source: 'notion'}``.
- ``getPage``      — read a page by id; emit one item per input with
  ``{pageId, title, url, properties, createdTime, source: 'notion'}``.
- ``updatePage``   — update a page's properties; emit one item per input
  with ``{pageId, url, properties, lastEditedTime, source: 'notion'}``.
- ``queryDatabase``— query a database; emit one item per result with
  ``{pageId, title, createdTime, source: 'notion'}``.

Parameters honored:

- ``operation``   (``"search"`` / ``"createPage"`` / ``"getPage"`` /
  ``"updatePage"`` / ``"queryDatabase"``; default ``"search"``)
- ``query``       (string; ``$json.query`` / ``$json.search`` fallback;
  used by ``search``)
- ``filter``      (dict with ``property`` / ``value``; optional; used by
  ``search`` and ``queryDatabase``)
- ``pageSize``    (int; default 10; capped at 3 in offline mode)
- ``parentId``    (string; ``$json.parentId`` / ``$json.databaseId``
  fallback; used by ``createPage``)
- ``properties``  (dict of property name → value; ``$json.properties``
  fallback; used by ``createPage`` and ``updatePage``)
- ``children``    (list of block objects; optional; used by ``createPage``)
- ``pageId``      (string; ``$json.pageId`` / ``$json.id`` fallback;
  required for ``getPage`` and ``updatePage``)
- ``databaseId``  (string; ``$json.databaseId`` fallback; required for
  ``queryDatabase``)
- ``sorts``       (list; optional; used by ``queryDatabase``)
- ``dataMode``    (``"array"`` / ``"object"``; default ``"array"``; only
  meaningful for ``search``)

Behavior precedence:

1. ``ctx.mocks['notion_response']`` — when present, the value drives the
   executor. A dict is used per operation (or operation-specific shape);
   a callable is invoked as
   ``mock(operation, params, item, ctx)`` and may return a dict (used
   per operation) or a non-dict truthy value (wrapped as the
   operation's envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the operation envelope.
3. Offline synthetic response with deterministic-looking ids and
   timestamps.

Items missing ``pageId`` (for ``getPage``/``updatePage``) or
``databaseId`` (for ``queryDatabase``) are skipped (no item emitted) —
matching the behavior of the other output nodes in this package.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


NOTION_OPERATIONS: tuple[str, ...] = (
    "search",
    "createPage",
    "getPage",
    "updatePage",
    "queryDatabase",
)
NOTION_DEFAULT_OPERATION: str = "search"
NOTION_DEFAULT_PAGE_SIZE: int = 10
NOTION_OFFLINE_MAX_RESULTS: int = 3


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
        for key in ("value", "name", "id", "text", "content", "title"):
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_page_id() -> str:
    return f"mock_page_{uuid.uuid4().hex[:12]}"


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
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    return _coerce_str(value)


def _resolve_dict_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> dict[str, Any]:
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    if isinstance(value, dict):
        return value
    return {}


def _resolve_list_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> list[Any]:
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    if isinstance(value, list):
        return value
    return []


def _extract_title(properties: dict[str, Any] | None) -> str:
    """Extract a plain-text title from a Notion properties dict.

    Notion stores titles as ``{title: [{text: {content: "..."}}]}`` under
    a property whose type is ``title``. We scan for the first such
    property and join the text runs.
    """
    if not isinstance(properties, dict):
        return ""
    for prop in properties.values():
        if not isinstance(prop, dict):
            continue
        title_arr = prop.get("title")
        if isinstance(title_arr, list):
            parts: list[str] = []
            for run in title_arr:
                if isinstance(run, dict):
                    text = run.get("text")
                    if isinstance(text, dict) and isinstance(text.get("content"), str):
                        parts.append(text["content"])
                    elif isinstance(run.get("plain_text"), str):
                        parts.append(run["plain_text"])
            if parts:
                return "".join(parts)
    return ""


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_search_response(page_size: int) -> dict[str, Any]:
    count = min(page_size, NOTION_OFFLINE_MAX_RESULTS)
    now = _now_iso()
    results: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        results.append(
            {
                "id": f"mock_page_{i}",
                "object": "page",
                "url": f"https://notion.so/mock_page_{i}",
                "properties": {
                    "title": {
                        "title": [
                            {"text": {"content": f"Mock Page {i}"}}
                        ]
                    }
                },
                "created_time": now,
                "last_edited_time": now,
            }
        )
    return {"results": results, "has_more": False, "next_cursor": None}


def _synthesize_create_page_response(
    parent_id: str, properties: dict[str, Any]
) -> dict[str, Any]:
    now = _now_iso()
    return {
        "id": _new_page_id(),
        "object": "page",
        "url": "https://notion.so/mock_page",
        "parent": {"type": "database_id", "database_id": parent_id},
        "properties": properties or {},
        "created_time": now,
        "last_edited_time": now,
    }


def _synthesize_get_page_response(page_id: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "id": page_id,
        "object": "page",
        "url": f"https://notion.so/{page_id}",
        "properties": {
            "title": {
                "title": [{"text": {"content": "Mock Page"}}]
            }
        },
        "created_time": now,
        "last_edited_time": now,
    }


def _synthesize_update_page_response(
    page_id: str, properties: dict[str, Any]
) -> dict[str, Any]:
    now = _now_iso()
    return {
        "id": page_id,
        "object": "page",
        "url": f"https://notion.so/{page_id}",
        "properties": properties or {},
        "last_edited_time": now,
        "archived": False,
    }


def _synthesize_query_database_response(page_size: int) -> dict[str, Any]:
    count = min(page_size, NOTION_OFFLINE_MAX_RESULTS)
    now = _now_iso()
    results: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        results.append(
            {
                "id": f"mock_record_{i}",
                "object": "page",
                "properties": {
                    "Name": {
                        "title": [
                            {"text": {"content": f"Record {i}"}}
                        ]
                    }
                },
                "created_time": now,
            }
        )
    return {"results": results, "has_more": False, "next_cursor": None}


# ── Per-operation envelope coercers ────────────────────────────────────


def _coerce_search_envelope(raw: dict[str, Any], *, page_size: int) -> dict[str, Any]:
    results_raw = raw.get("results")
    if not isinstance(results_raw, list):
        results_raw = []
    results: list[dict[str, Any]] = []
    for i, entry in enumerate(results_raw[: max(page_size, 1)]):
        if not isinstance(entry, dict):
            continue
        rid = _coerce_str(entry.get("id")) or f"mock_page_{i + 1}"
        now = _now_iso()
        results.append(
            {
                "id": rid,
                "object": _coerce_str(entry.get("object")) or "page",
                "url": _coerce_str(entry.get("url"))
                or f"https://notion.so/{rid}",
                "properties": entry.get("properties")
                if isinstance(entry.get("properties"), dict)
                else {
                    "title": {
                        "title": [
                            {"text": {"content": f"Mock Page {i + 1}"}}
                        ]
                    }
                },
                "created_time": _coerce_str(entry.get("created_time")) or now,
                "last_edited_time": _coerce_str(entry.get("last_edited_time"))
                or now,
            }
        )
    return {
        "results": results,
        "has_more": bool(raw.get("has_more", False)),
        "next_cursor": raw.get("next_cursor"),
    }


def _coerce_create_page_envelope(
    raw: dict[str, Any], *, parent_id: str, properties: dict[str, Any]
) -> dict[str, Any]:
    now = _now_iso()
    rid = _coerce_str(raw.get("id")) or _new_page_id()
    parent = raw.get("parent")
    if not isinstance(parent, dict):
        parent = {"type": "database_id", "database_id": parent_id}
    return {
        "id": rid,
        "object": _coerce_str(raw.get("object")) or "page",
        "url": _coerce_str(raw.get("url")) or "https://notion.so/mock_page",
        "parent": parent,
        "properties": raw.get("properties")
        if isinstance(raw.get("properties"), dict)
        else (properties or {}),
        "created_time": _coerce_str(raw.get("created_time")) or now,
        "last_edited_time": _coerce_str(raw.get("last_edited_time")) or now,
    }


def _coerce_get_page_envelope(raw: dict[str, Any], *, page_id: str) -> dict[str, Any]:
    now = _now_iso()
    rid = _coerce_str(raw.get("id")) or page_id
    props = raw.get("properties")
    if not isinstance(props, dict):
        props = {"title": {"title": [{"text": {"content": "Mock Page"}}]}}
    return {
        "id": rid,
        "object": _coerce_str(raw.get("object")) or "page",
        "url": _coerce_str(raw.get("url")) or f"https://notion.so/{rid}",
        "properties": props,
        "created_time": _coerce_str(raw.get("created_time")) or now,
        "last_edited_time": _coerce_str(raw.get("last_edited_time")) or now,
    }


def _coerce_update_page_envelope(
    raw: dict[str, Any], *, page_id: str, properties: dict[str, Any]
) -> dict[str, Any]:
    now = _now_iso()
    rid = _coerce_str(raw.get("id")) or page_id
    props = raw.get("properties")
    if not isinstance(props, dict):
        props = properties or {}
    return {
        "id": rid,
        "object": _coerce_str(raw.get("object")) or "page",
        "url": _coerce_str(raw.get("url")) or f"https://notion.so/{rid}",
        "properties": props,
        "last_edited_time": _coerce_str(raw.get("last_edited_time")) or now,
        "archived": bool(raw.get("archived", False)),
    }


def _coerce_query_database_envelope(
    raw: dict[str, Any], *, page_size: int
) -> dict[str, Any]:
    results_raw = raw.get("results")
    if not isinstance(results_raw, list):
        results_raw = []
    results: list[dict[str, Any]] = []
    for i, entry in enumerate(results_raw[: max(page_size, 1)]):
        if not isinstance(entry, dict):
            continue
        rid = _coerce_str(entry.get("id")) or f"mock_record_{i + 1}"
        now = _now_iso()
        props = entry.get("properties")
        if not isinstance(props, dict):
            props = {
                "Name": {
                    "title": [{"text": {"content": f"Record {i + 1}"}}]
                }
            }
        results.append(
            {
                "id": rid,
                "object": _coerce_str(entry.get("object")) or "page",
                "properties": props,
                "created_time": _coerce_str(entry.get("created_time")) or now,
            }
        )
    return {
        "results": results,
        "has_more": bool(raw.get("has_more", False)),
        "next_cursor": raw.get("next_cursor"),
    }


# ── HTTP-mock unwrapping ───────────────────────────────────────────────


def _notion_response_from_http_mock(
    mock: Any,
    *,
    operation: str,
    page_size: int,
    parent_id: str,
    properties: dict[str, Any],
    page_id: str,
) -> dict[str, Any] | None:
    """Extract a Notion-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if not isinstance(body, dict):
        if isinstance(body, str) and body.strip():
            if operation == "search":
                return _coerce_search_envelope(
                    {"results": [], "raw": body}, page_size=page_size
                )
            if operation == "queryDatabase":
                return _coerce_query_database_envelope(
                    {"results": [], "raw": body}, page_size=page_size
                )
            if operation == "createPage":
                return _coerce_create_page_envelope(
                    {"raw": body}, parent_id=parent_id, properties=properties
                )
            if operation == "getPage":
                return _coerce_get_page_envelope(
                    {"raw": body}, page_id=page_id
                )
            return _coerce_update_page_envelope(
                {"raw": body}, page_id=page_id, properties=properties
            )
        return None
    if operation == "search":
        return _coerce_search_envelope(body, page_size=page_size)
    if operation == "createPage":
        return _coerce_create_page_envelope(
            body, parent_id=parent_id, properties=properties
        )
    if operation == "getPage":
        return _coerce_get_page_envelope(body, page_id=page_id)
    if operation == "updatePage":
        return _coerce_update_page_envelope(
            body, page_id=page_id, properties=properties
        )
    return _coerce_query_database_envelope(body, page_size=page_size)


# ── Response resolution ────────────────────────────────────────────────


def _resolve_notion_response(
    *,
    operation: str,
    params: dict[str, Any],
    page_size: int,
    parent_id: str,
    properties: dict[str, Any],
    page_id: str,
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"notion_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    nmock = mocks.get("notion_response")
    if nmock is not None:
        if callable(nmock):
            raw = nmock(operation, params, item, ctx)
        else:
            raw = nmock
        if isinstance(raw, dict):
            if operation == "search":
                return _coerce_search_envelope(raw, page_size=page_size), "notion_response"
            if operation == "createPage":
                return (
                    _coerce_create_page_envelope(
                        raw, parent_id=parent_id, properties=properties
                    ),
                    "notion_response",
                )
            if operation == "getPage":
                return _coerce_get_page_envelope(raw, page_id=page_id), "notion_response"
            if operation == "updatePage":
                return (
                    _coerce_update_page_envelope(
                        raw, page_id=page_id, properties=properties
                    ),
                    "notion_response",
                )
            return (
                _coerce_query_database_envelope(raw, page_size=page_size),
                "notion_response",
            )
        # Non-dict truthy → wrap as a synthetic envelope
        if operation == "search":
            return (
                _synthesize_search_response(page_size) | {"raw": raw},
                "notion_response",
            )
        if operation == "createPage":
            return (
                _synthesize_create_page_response(parent_id, properties)
                | {"raw": raw},
                "notion_response",
            )
        if operation == "getPage":
            return (
                _synthesize_get_page_response(page_id) | {"raw": raw},
                "notion_response",
            )
        if operation == "updatePage":
            return (
                _synthesize_update_page_response(page_id, properties)
                | {"raw": raw},
                "notion_response",
            )
        return (
            _synthesize_query_database_response(page_size) | {"raw": raw},
            "notion_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _notion_response_from_http_mock(
            hmock,
            operation=operation,
            page_size=page_size,
            parent_id=parent_id,
            properties=properties,
            page_id=page_id,
        )
        if env is not None:
            return env, "http_response"

    if operation == "search":
        return _synthesize_search_response(page_size), "offline"
    if operation == "createPage":
        return _synthesize_create_page_response(parent_id, properties), "offline"
    if operation == "getPage":
        return _synthesize_get_page_response(page_id), "offline"
    if operation == "updatePage":
        return _synthesize_update_page_response(page_id, properties), "offline"
    return _synthesize_query_database_response(page_size), "offline"


# ── Main executor ──────────────────────────────────────────────────────


async def exec_notion(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Notion node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(
        params.get("operation") or NOTION_DEFAULT_OPERATION
    ).strip()
    if operation not in NOTION_OPERATIONS:
        raise ValueError(
            f"notion: unsupported operation {operation!r}; "
            f"expected one of {NOTION_OPERATIONS}"
        )

    data_mode = str(params.get("dataMode") or "array").strip().lower()
    if data_mode not in ("array", "object"):
        data_mode = "array"

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)

        # Shared resolution
        page_size = NOTION_DEFAULT_PAGE_SIZE
        if params.get("pageSize") is not None:
            page_size = _coerce_int(
                evaluate(params.get("pageSize"), ectx), NOTION_DEFAULT_PAGE_SIZE
            )
        elif "pageSize" in item.json:
            page_size = _coerce_int(
                item.json.get("pageSize"), NOTION_DEFAULT_PAGE_SIZE
            )
        if page_size < 1:
            page_size = NOTION_DEFAULT_PAGE_SIZE

        # Operation-specific param resolution + gating
        query = ""
        filter_dict: dict[str, Any] = {}
        sorts_list: list[Any] = []
        parent_id = ""
        properties: dict[str, Any] = {}
        children: list[Any] = []
        page_id = ""
        database_id = ""

        if operation == "search":
            query = _resolve_str_param(
                params, "query", item, ectx, ("query", "search")
            )
            filter_dict = _resolve_dict_param(params, "filter", item, ectx, ("filter",))

        elif operation == "createPage":
            parent_id = _resolve_str_param(
                params, "parentId", item, ectx, ("parentId", "databaseId")
            )
            properties = _resolve_dict_param(
                params, "properties", item, ectx, ("properties",)
            )
            children = _resolve_list_param(
                params, "children", item, ectx, ("children",)
            )

        elif operation in ("getPage", "updatePage"):
            page_id = _resolve_str_param(
                params, "pageId", item, ectx, ("pageId", "id")
            )
            if not page_id:
                logger.info(
                    "notion %s skipped: empty pageId on node %r",
                    operation,
                    node.name,
                )
                continue
            if operation == "updatePage":
                properties = _resolve_dict_param(
                    params, "properties", item, ectx, ("properties",)
                )

        else:  # queryDatabase
            database_id = _resolve_str_param(
                params, "databaseId", item, ectx, ("databaseId",)
            )
            if not database_id:
                logger.info(
                    "notion queryDatabase skipped: empty databaseId on node %r",
                    node.name,
                )
                continue
            filter_dict = _resolve_dict_param(params, "filter", item, ectx, ("filter",))
            sorts_list = _resolve_list_param(params, "sorts", item, ectx, ("sorts",))

        envelope, source = _resolve_notion_response(
            operation=operation,
            params=params,
            page_size=page_size,
            parent_id=parent_id,
            properties=properties,
            page_id=page_id,
            item=item,
            ctx=ctx,
        )

        if operation == "search":
            results = envelope.get("results") or []
            if data_mode == "object":
                payload: dict[str, Any] = {
                    "results": list(results),
                    "hasMore": bool(envelope.get("has_more", False)),
                    "nextCursor": envelope.get("next_cursor"),
                    "query": query,
                    "pageSize": page_size,
                    "operation": operation,
                    "ok": True,
                    "source": "notion",
                }
                if filter_dict:
                    payload["filter"] = filter_dict
                if source != "notion_response":
                    payload["mockSource"] = source
                ni = item.clone()
                ni.json = {**item.json, **payload}
                out.append(ni)
            else:
                for entry in results:
                    entry_props = entry.get("properties")
                    title = _extract_title(entry_props) if isinstance(entry_props, dict) else ""
                    payload = {
                        "pageId": entry.get("id"),
                        "title": title,
                        "url": entry.get("url"),
                        "object": entry.get("object"),
                        "createdTime": entry.get("created_time"),
                        "operation": operation,
                        "ok": True,
                        "source": "notion",
                    }
                    if source != "notion_response":
                        payload["mockSource"] = source
                    ni = item.clone()
                    ni.json = {**item.json, **payload}
                    out.append(ni)

        elif operation == "createPage":
            parent_obj = envelope.get("parent")
            echoed_parent = ""
            if isinstance(parent_obj, dict):
                echoed_parent = _coerce_str(
                    parent_obj.get("database_id")
                    or parent_obj.get("page_id")
                ) or parent_id
            payload = {
                "pageId": envelope.get("id"),
                "url": envelope.get("url"),
                "parentId": echoed_parent or parent_id,
                "properties": envelope.get("properties") or properties or {},
                "createdTime": envelope.get("created_time"),
                "operation": operation,
                "ok": True,
                "source": "notion",
            }
            if children:
                payload["children"] = children
            if source != "notion_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        elif operation == "getPage":
            props = envelope.get("properties")
            title = _extract_title(props) if isinstance(props, dict) else ""
            payload = {
                "pageId": envelope.get("id") or page_id,
                "title": title,
                "url": envelope.get("url"),
                "properties": props or {},
                "createdTime": envelope.get("created_time"),
                "operation": operation,
                "ok": True,
                "source": "notion",
            }
            if source != "notion_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        elif operation == "updatePage":
            payload = {
                "pageId": envelope.get("id") or page_id,
                "url": envelope.get("url"),
                "properties": envelope.get("properties") or properties or {},
                "lastEditedTime": envelope.get("last_edited_time"),
                "archived": bool(envelope.get("archived", False)),
                "operation": operation,
                "ok": True,
                "source": "notion",
            }
            if source != "notion_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        else:  # queryDatabase
            results = envelope.get("results") or []
            for entry in results:
                entry_props = entry.get("properties")
                title = _extract_title(entry_props) if isinstance(entry_props, dict) else ""
                payload = {
                    "pageId": entry.get("id"),
                    "title": title,
                    "createdTime": entry.get("created_time"),
                    "databaseId": database_id,
                    "operation": operation,
                    "ok": True,
                    "source": "notion",
                }
                if source != "notion_response":
                    payload["mockSource"] = source
                ni = item.clone()
                ni.json = {**item.json, **payload}
                out.append(ni)

        logger.info(
            "notion %s pageId=%r parentId=%r databaseId=%r pageSize=%s source=%s",
            operation,
            page_id[:80],
            parent_id[:80],
            database_id[:80],
            page_size,
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_notion",
    "NOTION_OPERATIONS",
    "NOTION_DEFAULT_OPERATION",
]