"""YouTube executor (clean-room n8n ``n8n-nodes-base.youTube``).

v1 supports the four operations most commonly used in n8n templates:

- ``search``  — search for videos; emit one item per result with
  ``{videoId, title, description, channelId, publishedAt, source: 'youTube'}``
  (or one item with an ``items`` array when
  ``parameters.dataMode == 'object'``).
- ``get``     — fetch a single video by id; emit one item per input with
  ``{videoId, title, description, channelId, publishedAt, viewCount,
  likeCount, commentCount, source: 'youTube'}``.
- ``list``    — list videos for a channel; emit one item per result with
  ``{videoId, title, publishedAt, source: 'youTube'}``.
- ``upload``  — upload a video; emit one item per input with
  ``{videoId, title, description, privacyStatus, uploadStatus,
  source: 'youTube'}``.

Parameters honored:

- ``operation``  (``"search"`` / ``"get"`` / ``"list"`` / ``"upload"``;
  default ``"search"``)
- For ``search``:
  - ``q``          (string; ``$json.q`` / ``$json.query`` / ``$json.search``
    fallback)
  - ``maxResults`` (int; default 5; capped at 3 offline)
  - ``order``      (string; default ``"relevance"``)
  - ``type``       (string; default ``"video"``)
- For ``get``:
  - ``videoId``    (string; ``$json.videoId`` / ``$json.id`` fallback)
- For ``list``:
  - ``channelId``  (string; ``$json.channelId`` fallback)
  - ``maxResults`` (int; default 5; capped at 3 offline)
- For ``upload``:
  - ``title``         (string; ``$json.title`` fallback)
  - ``description``   (string; ``$json.description`` fallback)
  - ``privacyStatus`` (string; default ``"private"``)
- ``dataMode``     (``"array"`` / ``"object"``; default ``"array"``;
  only meaningful for ``search``)

Behavior precedence:

1. ``ctx.mocks['youtube_response']`` — when present, the value drives the
   executor. A dict is used per operation (or operation-specific shape);
   a callable is invoked as ``mock(operation, params, item, ctx)`` and may
   return a dict (used per operation) or a non-dict truthy value
   (wrapped as the operation's envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the operation envelope.
3. Offline synthetic response with deterministic-looking ids and ISO
   timestamps.

Items with an empty resolved ``videoId`` for ``get`` are skipped, and items
with an empty resolved ``channelId`` for ``list`` are skipped (no item
emitted) — matching the behavior of the other output nodes in this
package.
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


YOUTUBE_OPERATIONS: tuple[str, ...] = ("search", "get", "list", "upload")
YOUTUBE_DEFAULT_OPERATION: str = "search"
YOUTUBE_DEFAULT_MAX_RESULTS: int = 5
YOUTUBE_OFFLINE_MAX_VIDEOS: int = 3
YOUTUBE_DEFAULT_ORDER: str = "relevance"
YOUTUBE_DEFAULT_TYPE: str = "video"
YOUTUBE_DEFAULT_PRIVACY_STATUS: str = "private"
YOUTUBE_DATA_MODES: tuple[str, ...] = ("array", "object")
YOUTUBE_DEFAULT_DATA_MODE: str = "array"


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
        for key in ("value", "name", "id", "title", "text", "content", "message"):
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
    return datetime.utcnow().isoformat() + "Z"


def _new_video_id() -> str:
    return f"mock_upload_{uuid.uuid4().hex[:16]}"


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


def _resolve_data_mode(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("dataMode")
    if raw is not None:
        resolved = _coerce_str(evaluate(raw, ectx)).strip().lower()
        if resolved in YOUTUBE_DATA_MODES:
            return resolved
    json_mode = item.json.get("dataMode")
    if json_mode is not None:
        s = _coerce_str(json_mode).strip().lower()
        if s in YOUTUBE_DATA_MODES:
            return s
    return YOUTUBE_DEFAULT_DATA_MODE


def _resolve_max_results(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> int:
    raw = params.get("maxResults")
    if raw is not None:
        return _coerce_int(evaluate(raw, ectx), YOUTUBE_DEFAULT_MAX_RESULTS)
    json_max = item.json.get("maxResults")
    if json_max is not None:
        return _coerce_int(json_max, YOUTUBE_DEFAULT_MAX_RESULTS)
    return YOUTUBE_DEFAULT_MAX_RESULTS


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_search_response(max_results: int) -> dict[str, Any]:
    count = min(max_results, YOUTUBE_OFFLINE_MAX_VIDEOS)
    if count < 0:
        count = 0
    items: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        items.append(
            {
                "id": {"videoId": f"mock_vid_{i}"},
                "snippet": {
                    "title": f"Mock Video {i}",
                    "description": f"Mock description {i}",
                    "channelId": "mock_channel",
                    "publishedAt": _now_iso(),
                    "thumbnails": {
                        "default": {"url": "https://i.ytimg.com/vi/mock/default.jpg"}
                    },
                },
            }
        )
    return {
        "items": items,
        "pageInfo": {
            "totalResults": min(max_results, YOUTUBE_OFFLINE_MAX_VIDEOS),
            "resultsPerPage": min(max_results, YOUTUBE_OFFLINE_MAX_VIDEOS),
        },
    }


def _synthesize_get_response(video_id: str) -> dict[str, Any]:
    return {
        "id": video_id,
        "snippet": {
            "title": "Mock Video",
            "description": "Mock description",
            "channelId": "mock_channel",
            "publishedAt": _now_iso(),
        },
        "statistics": {
            "viewCount": "1000",
            "likeCount": "100",
            "commentCount": "10",
        },
    }


def _synthesize_list_response(max_results: int) -> dict[str, Any]:
    count = min(max_results, YOUTUBE_OFFLINE_MAX_VIDEOS)
    if count < 0:
        count = 0
    items: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        items.append(
            {
                "id": f"mock_vid_{i}",
                "snippet": {
                    "title": f"Channel Video {i}",
                    "publishedAt": _now_iso(),
                },
            }
        )
    return {
        "items": items,
        "pageInfo": {"totalResults": min(max_results, YOUTUBE_OFFLINE_MAX_VIDEOS)},
    }


def _synthesize_upload_response(
    *, title: str, description: str, privacy_status: str
) -> dict[str, Any]:
    return {
        "id": _new_video_id(),
        "snippet": {
            "title": title,
            "description": description,
            "channelId": "mock_channel",
            "publishedAt": _now_iso(),
        },
        "status": {
            "uploadStatus": "uploaded",
            "privacyStatus": privacy_status,
        },
    }


# ── Envelope coercion from raw mock dicts ─────────────────────────────


def _coerce_search_entry(entry: Any, index: int) -> dict[str, Any]:
    """Coerce a single search result into a flat {videoId, snippet} dict."""
    if not isinstance(entry, dict):
        return {
            "id": {"videoId": f"mock_vid_{index}"},
            "snippet": {
                "title": f"Mock Video {index}",
                "description": "",
                "channelId": "mock_channel",
                "publishedAt": _now_iso(),
            },
        }
    id_raw = entry.get("id")
    if isinstance(id_raw, dict):
        video_id = _coerce_str(id_raw.get("videoId")) or f"mock_vid_{index}"
    else:
        video_id = _coerce_str(id_raw) or f"mock_vid_{index}"
    snippet_raw = entry.get("snippet")
    if not isinstance(snippet_raw, dict):
        snippet_raw = {}
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": _coerce_str(snippet_raw.get("title")) or f"Mock Video {index}",
            "description": _coerce_str(snippet_raw.get("description")),
            "channelId": _coerce_str(snippet_raw.get("channelId")) or "mock_channel",
            "publishedAt": _coerce_str(snippet_raw.get("publishedAt")) or _now_iso(),
            "thumbnails": snippet_raw.get("thumbnails")
            if isinstance(snippet_raw.get("thumbnails"), dict)
            else {"default": {"url": "https://i.ytimg.com/vi/mock/default.jpg"}},
        },
    }


def _coerce_search_envelope(
    raw: dict[str, Any], *, max_results: int
) -> dict[str, Any]:
    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        items_raw = []
    items: list[dict[str, Any]] = []
    for i, entry in enumerate(items_raw[: max(max_results, 0)], start=1):
        items.append(_coerce_search_entry(entry, i))
    page_info = raw.get("pageInfo")
    if not isinstance(page_info, dict):
        page_info = {
            "totalResults": len(items),
            "resultsPerPage": len(items),
        }
    return {"items": items, "pageInfo": page_info}


def _coerce_get_envelope(raw: dict[str, Any], *, video_id: str) -> dict[str, Any]:
    eid = _coerce_str(raw.get("id")) or video_id
    snippet_raw = raw.get("snippet")
    if not isinstance(snippet_raw, dict):
        snippet_raw = {}
    stats_raw = raw.get("statistics")
    if not isinstance(stats_raw, dict):
        stats_raw = {}
    return {
        "id": eid,
        "snippet": {
            "title": _coerce_str(snippet_raw.get("title")) or "Mock Video",
            "description": _coerce_str(snippet_raw.get("description"))
            or "Mock description",
            "channelId": _coerce_str(snippet_raw.get("channelId")) or "mock_channel",
            "publishedAt": _coerce_str(snippet_raw.get("publishedAt")) or _now_iso(),
        },
        "statistics": {
            "viewCount": _coerce_str(stats_raw.get("viewCount")) or "1000",
            "likeCount": _coerce_str(stats_raw.get("likeCount")) or "100",
            "commentCount": _coerce_str(stats_raw.get("commentCount")) or "10",
        },
    }


def _coerce_list_entry(entry: Any, index: int) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {
            "id": f"mock_vid_{index}",
            "snippet": {
                "title": f"Channel Video {index}",
                "publishedAt": _now_iso(),
            },
        }
    snippet_raw = entry.get("snippet")
    if not isinstance(snippet_raw, dict):
        snippet_raw = {}
    return {
        "id": _coerce_str(entry.get("id")) or f"mock_vid_{index}",
        "snippet": {
            "title": _coerce_str(snippet_raw.get("title"))
            or f"Channel Video {index}",
            "publishedAt": _coerce_str(snippet_raw.get("publishedAt")) or _now_iso(),
        },
    }


def _coerce_list_envelope(
    raw: dict[str, Any], *, max_results: int
) -> dict[str, Any]:
    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        items_raw = []
    items: list[dict[str, Any]] = []
    for i, entry in enumerate(items_raw[: max(max_results, 0)], start=1):
        items.append(_coerce_list_entry(entry, i))
    page_info = raw.get("pageInfo")
    if not isinstance(page_info, dict):
        page_info = {"totalResults": len(items)}
    return {"items": items, "pageInfo": page_info}


def _coerce_upload_envelope(
    raw: dict[str, Any],
    *,
    title: str,
    description: str,
    privacy_status: str,
) -> dict[str, Any]:
    eid = _coerce_str(raw.get("id")) or _new_video_id()
    snippet_raw = raw.get("snippet")
    if not isinstance(snippet_raw, dict):
        snippet_raw = {}
    status_raw = raw.get("status")
    if not isinstance(status_raw, dict):
        status_raw = {}
    return {
        "id": eid,
        "snippet": {
            "title": _coerce_str(snippet_raw.get("title")) or title,
            "description": _coerce_str(snippet_raw.get("description")) or description,
            "channelId": _coerce_str(snippet_raw.get("channelId")) or "mock_channel",
            "publishedAt": _coerce_str(snippet_raw.get("publishedAt")) or _now_iso(),
        },
        "status": {
            "uploadStatus": _coerce_str(status_raw.get("uploadStatus")) or "uploaded",
            "privacyStatus": _coerce_str(status_raw.get("privacyStatus"))
            or privacy_status,
        },
    }


# ── HTTP-mock unwrapping ───────────────────────────────────────────────


def _youtube_response_from_http_mock(
    mock: Any,
    *,
    operation: str,
    video_id: str,
    title: str,
    description: str,
    privacy_status: str,
    max_results: int,
) -> dict[str, Any] | None:
    """Extract a YouTube-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if operation == "search":
            return _coerce_search_envelope(body, max_results=max_results)
        if operation == "get":
            return _coerce_get_envelope(body, video_id=video_id)
        if operation == "list":
            return _coerce_list_envelope(body, max_results=max_results)
        return _coerce_upload_envelope(
            body,
            title=title,
            description=description,
            privacy_status=privacy_status,
        )
    if isinstance(body, str) and body.strip():
        if operation == "search":
            return {"items": [], "pageInfo": {"totalResults": 0}, "raw": body}
        if operation == "get":
            base = _synthesize_get_response(video_id)
            base["raw"] = body
            return base
        if operation == "list":
            return {"items": [], "pageInfo": {"totalResults": 0}, "raw": body}
        base = _synthesize_upload_response(
            title=title, description=description, privacy_status=privacy_status
        )
        base["raw"] = body
        return base
    return None


# ── Response resolution ────────────────────────────────────────────────


def _resolve_youtube_response(
    *,
    operation: str,
    video_id: str,
    title: str,
    description: str,
    privacy_status: str,
    max_results: int,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"youtube_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    ymock = mocks.get("youtube_response")
    if ymock is not None:
        if callable(ymock):
            raw = ymock(operation, params, item, ctx)
        else:
            raw = ymock
        if isinstance(raw, dict):
            if operation == "search":
                return (
                    _coerce_search_envelope(raw, max_results=max_results),
                    "youtube_response",
                )
            if operation == "get":
                return (
                    _coerce_get_envelope(raw, video_id=video_id),
                    "youtube_response",
                )
            if operation == "list":
                return (
                    _coerce_list_envelope(raw, max_results=max_results),
                    "youtube_response",
                )
            return (
                _coerce_upload_envelope(
                    raw,
                    title=title,
                    description=description,
                    privacy_status=privacy_status,
                ),
                "youtube_response",
            )
        # Non-dict truthy → wrap as a synthetic envelope
        if operation == "search":
            return (
                {"items": [], "pageInfo": {"totalResults": 0}, "raw": raw},
                "youtube_response",
            )
        if operation == "get":
            base = _synthesize_get_response(video_id)
            base["raw"] = raw
            return base, "youtube_response"
        if operation == "list":
            return (
                {"items": [], "pageInfo": {"totalResults": 0}, "raw": raw},
                "youtube_response",
            )
        base = _synthesize_upload_response(
            title=title, description=description, privacy_status=privacy_status
        )
        base["raw"] = raw
        return base, "youtube_response"

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _youtube_response_from_http_mock(
            hmock,
            operation=operation,
            video_id=video_id,
            title=title,
            description=description,
            privacy_status=privacy_status,
            max_results=max_results,
        )
        if env is not None:
            return env, "http_response"

    if operation == "search":
        return _synthesize_search_response(max_results), "offline"
    if operation == "get":
        return _synthesize_get_response(video_id), "offline"
    if operation == "list":
        return _synthesize_list_response(max_results), "offline"
    return (
        _synthesize_upload_response(
            title=title, description=description, privacy_status=privacy_status
        ),
        "offline",
    )


# ── Main executor ──────────────────────────────────────────────────────


async def exec_youtube(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """YouTube node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = (
        str(params.get("operation") or YOUTUBE_DEFAULT_OPERATION).strip().lower()
    )
    if operation not in YOUTUBE_OPERATIONS:
        raise ValueError(
            f"youTube: unsupported operation {operation!r}; "
            f"expected one of {YOUTUBE_OPERATIONS}"
        )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)

        if operation == "search":
            out.extend(
                _build_search_items(
                    params=params,
                    item=item,
                    ectx=ectx,
                    ctx=ctx,
                )
            )
            continue

        if operation == "get":
            video_id = _resolve_str_param(
                params, "videoId", item, ectx, ("videoId", "id")
            ).strip()
            if not video_id:
                logger.info(
                    "youTube get skipped: empty videoId on node %r",
                    node.name,
                )
                continue
            out.extend(
                _build_get_items(
                    item=item,
                    video_id=video_id,
                    params=params,
                    ctx=ctx,
                )
            )
            continue

        if operation == "list":
            channel_id = _resolve_str_param(
                params, "channelId", item, ectx, ("channelId",)
            ).strip()
            if not channel_id:
                logger.info(
                    "youTube list skipped: empty channelId on node %r",
                    node.name,
                )
                continue
            out.extend(
                _build_list_items(
                    params=params,
                    item=item,
                    ectx=ectx,
                    channel_id=channel_id,
                    ctx=ctx,
                )
            )
            continue

        # upload
        out.extend(
            _build_upload_items(
                params=params,
                item=item,
                ectx=ectx,
                ctx=ctx,
            )
        )

    return [(0, out)]


# ── Per-operation payload builders ─────────────────────────────────────


def _build_search_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    q = _resolve_str_param(params, "q", item, ectx, ("q", "query", "search"))
    max_results = _resolve_max_results(params, item, ectx)
    order = _resolve_str_param(
        params, "order", item, ectx, ("order",), default=YOUTUBE_DEFAULT_ORDER
    )
    type_ = _resolve_str_param(
        params, "type", item, ectx, ("type",), default=YOUTUBE_DEFAULT_TYPE
    )
    data_mode = _resolve_data_mode(params, item, ectx)

    envelope, source = _resolve_youtube_response(
        operation="search",
        video_id="",
        title="",
        description="",
        privacy_status=YOUTUBE_DEFAULT_PRIVACY_STATUS,
        max_results=max_results,
        params=params,
        item=item,
        ctx=ctx,
    )
    raw_items = envelope.get("items") or []
    results: list[ExecutionItem] = []

    if data_mode == "object":
        payload: dict[str, Any] = {
            "items": list(raw_items),
            "q": q,
            "maxResults": max_results,
            "order": order,
            "type": type_,
            "operation": "search",
            "ok": True,
            "source": "youTube",
        }
        if source != "youtube_response":
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        results.append(ni)
    else:
        if not raw_items:
            payload = {
                "videoId": "",
                "title": "",
                "description": "",
                "channelId": "",
                "publishedAt": "",
                "items": [],
                "q": q,
                "maxResults": max_results,
                "order": order,
                "type": type_,
                "operation": "search",
                "ok": True,
                "source": "youTube",
            }
            if source != "youtube_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            results.append(ni)
        else:
            for entry in raw_items:
                id_obj = entry.get("id") if isinstance(entry, dict) else None
                vid = (
                    _coerce_str(id_obj.get("videoId"))
                    if isinstance(id_obj, dict)
                    else _coerce_str(entry.get("videoId") if isinstance(entry, dict) else "")
                )
                snippet = entry.get("snippet") if isinstance(entry, dict) else None
                if not isinstance(snippet, dict):
                    snippet = {}
                payload = {
                    "videoId": vid,
                    "title": _coerce_str(snippet.get("title")),
                    "description": _coerce_str(snippet.get("description")),
                    "channelId": _coerce_str(snippet.get("channelId")),
                    "publishedAt": _coerce_str(snippet.get("publishedAt")),
                    "q": q,
                    "maxResults": max_results,
                    "order": order,
                    "type": type_,
                    "operation": "search",
                    "ok": True,
                    "source": "youTube",
                }
                if source != "youtube_response":
                    payload["mockSource"] = source
                ni = item.clone()
                ni.json = {**item.json, **payload}
                results.append(ni)

    logger.info(
        "youTube search q=%r maxResults=%s order=%s type=%s source=%s count=%d",
        q[:80],
        max_results,
        order,
        type_,
        source,
        len(raw_items),
    )
    return results


def _build_get_items(
    *,
    item: ExecutionItem,
    video_id: str,
    params: dict[str, Any],
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    envelope, source = _resolve_youtube_response(
        operation="get",
        video_id=video_id,
        title="",
        description="",
        privacy_status=YOUTUBE_DEFAULT_PRIVACY_STATUS,
        max_results=YOUTUBE_OFFLINE_MAX_VIDEOS,
        params=params,
        item=item,
        ctx=ctx,
    )
    snippet = envelope.get("snippet") if isinstance(envelope.get("snippet"), dict) else {}
    stats = (
        envelope.get("statistics")
        if isinstance(envelope.get("statistics"), dict)
        else {}
    )
    payload = {
        "videoId": _coerce_str(envelope.get("id")) or video_id,
        "title": _coerce_str(snippet.get("title")) or "Mock Video",
        "description": _coerce_str(snippet.get("description")) or "Mock description",
        "channelId": _coerce_str(snippet.get("channelId")) or "mock_channel",
        "publishedAt": _coerce_str(snippet.get("publishedAt")) or _now_iso(),
        "viewCount": _coerce_str(stats.get("viewCount")) or "1000",
        "likeCount": _coerce_str(stats.get("likeCount")) or "100",
        "commentCount": _coerce_str(stats.get("commentCount")) or "10",
        "operation": "get",
        "ok": True,
        "source": "youTube",
    }
    if source != "youtube_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "youTube get videoId=%s source=%s",
        video_id,
        source,
    )
    return [ni]


def _build_list_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    channel_id: str,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    max_results = _resolve_max_results(params, item, ectx)
    envelope, source = _resolve_youtube_response(
        operation="list",
        video_id="",
        title="",
        description="",
        privacy_status=YOUTUBE_DEFAULT_PRIVACY_STATUS,
        max_results=max_results,
        params=params,
        item=item,
        ctx=ctx,
    )
    raw_items = envelope.get("items") or []
    results: list[ExecutionItem] = []

    if not raw_items:
        payload = {
            "videoId": "",
            "title": "",
            "publishedAt": "",
            "items": [],
            "channelId": channel_id,
            "maxResults": max_results,
            "operation": "list",
            "ok": True,
            "source": "youTube",
        }
        if source != "youtube_response":
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        results.append(ni)
    else:
        for entry in raw_items:
            snippet = entry.get("snippet") if isinstance(entry, dict) else None
            if not isinstance(snippet, dict):
                snippet = {}
            payload = {
                "videoId": _coerce_str(entry.get("id")) if isinstance(entry, dict) else "",
                "title": _coerce_str(snippet.get("title")),
                "publishedAt": _coerce_str(snippet.get("publishedAt")),
                "channelId": channel_id,
                "maxResults": max_results,
                "operation": "list",
                "ok": True,
                "source": "youTube",
            }
            if source != "youtube_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            results.append(ni)

    logger.info(
        "youTube list channelId=%s maxResults=%s source=%s count=%d",
        channel_id,
        max_results,
        source,
        len(raw_items),
    )
    return results


def _build_upload_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    title = _resolve_str_param(
        params, "title", item, ectx, ("title",), default="Untitled video"
    )
    description = _resolve_str_param(
        params, "description", item, ectx, ("description",)
    )
    privacy_status = _resolve_str_param(
        params, "privacyStatus", item, ectx, ("privacyStatus",),
        default=YOUTUBE_DEFAULT_PRIVACY_STATUS,
    )
    envelope, source = _resolve_youtube_response(
        operation="upload",
        video_id="",
        title=title,
        description=description,
        privacy_status=privacy_status,
        max_results=YOUTUBE_OFFLINE_MAX_VIDEOS,
        params=params,
        item=item,
        ctx=ctx,
    )
    snippet = envelope.get("snippet") if isinstance(envelope.get("snippet"), dict) else {}
    status = envelope.get("status") if isinstance(envelope.get("status"), dict) else {}
    payload = {
        "videoId": _coerce_str(envelope.get("id")),
        "title": _coerce_str(snippet.get("title")) or title,
        "description": _coerce_str(snippet.get("description")) or description,
        "privacyStatus": _coerce_str(status.get("privacyStatus")) or privacy_status,
        "uploadStatus": _coerce_str(status.get("uploadStatus")) or "uploaded",
        "operation": "upload",
        "ok": True,
        "source": "youTube",
    }
    if source != "youtube_response":
        payload["mockSource"] = source
    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "youTube upload title=%r privacyStatus=%s source=%s",
        title[:80],
        privacy_status,
        source,
    )
    return [ni]


__all__ = [
    "exec_youtube",
    "YOUTUBE_OPERATIONS",
    "YOUTUBE_DEFAULT_OPERATION",
    "YOUTUBE_DEFAULT_MAX_RESULTS",
    "YOUTUBE_OFFLINE_MAX_VIDEOS",
    "YOUTUBE_DEFAULT_ORDER",
    "YOUTUBE_DEFAULT_TYPE",
    "YOUTUBE_DEFAULT_PRIVACY_STATUS",
    "YOUTUBE_DATA_MODES",
    "YOUTUBE_DEFAULT_DATA_MODE",
]