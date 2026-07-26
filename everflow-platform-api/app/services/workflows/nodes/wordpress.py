"""WordPress executor (clean-room ``n8n-nodes-base.wordpress``).

v1 supports the operations most commonly used in n8n templates:

- ``create`` — create a post; emit one item per input with
  ``{postId, title, content, status, author, date, link, source: 'wordpress'}``.
- ``get``    — fetch a single post by id; emit one item per input.
- ``update`` — update a post by id; emit one item per input.
- ``list``   — list posts; emit one item per post (or one item with a
  ``posts`` array when ``parameters.dataMode == 'object'``).
- ``delete`` — delete a post by id; emit one item per input with
  ``{postId, deleted, source: 'wordpress'}``.

All API calls are mock-driven — no real network I/O is performed.

Parameters honored:

- ``operation`` (``"create"`` / ``"get"`` / ``"update"`` / ``"list"`` /
  ``"delete"``; default ``"get"``)
- ``postId``   (``$json.postId`` / ``$json.id`` fallback; required for
  get/update/delete)
- For ``create`` / ``update``:
  - ``title``      (string; ``$json.title`` fallback)
  - ``content``    (string; ``$json.content`` / ``$json.body`` fallback)
  - ``status``     (``"publish"`` / ``"draft"`` / ``"pending"`` /
    ``"private"``; default ``"draft"`` for create, ``"publish"`` for
    update)
  - ``author``     (int; optional; default 1)
  - ``categories`` (list; optional)
  - ``tags``       (list; optional)
  - ``excerpt``    (string; optional)
- For ``list``:
  - ``perPage``    (int; default 10; capped at 3 offline)
  - ``page``       (int; default 1)
  - ``search``     (string; optional, echoed only)
  - ``status``     (string; default ``"publish"``)
- ``dataMode``  (``"array"`` / ``"object"``; default ``"array"``; only
  meaningful for ``list``)

Behavior precedence:

1. ``ctx.mocks['wordpress_response']`` — when present, the value drives
   the executor. A callable is invoked as
   ``mock(operation, params, item, ctx)`` and may return a dict (used
   per operation) or a non-dict value (falls back to offline synthesis,
   tagged ``wordpress_response``). A non-callable dict is used directly
   as the response.
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response (a JSON ``body`` list is wrapped as ``{posts: body}``
   for list).
3. Offline synthetic response with deterministic-looking ids and ISO
   timestamps.

Items with an empty resolved ``postId`` for get/update/delete are
skipped (no item emitted).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


WORDPRESS_OPERATIONS: tuple[str, ...] = ("create", "get", "update", "list", "delete")
WORDPRESS_DEFAULT_OPERATION: str = "get"
WORDPRESS_STATUSES: tuple[str, ...] = ("publish", "draft", "pending", "private")
WORDPRESS_DEFAULT_STATUS_CREATE: str = "draft"
WORDPRESS_DEFAULT_STATUS_UPDATE: str = "publish"
WORDPRESS_DEFAULT_STATUS_LIST: str = "publish"
WORDPRESS_DEFAULT_PER_PAGE: int = 10
WORDPRESS_DEFAULT_PAGE: int = 1
WORDPRESS_OFFLINE_MAX_POSTS: int = 3
WORDPRESS_DEFAULT_AUTHOR: int = 1
WORDPRESS_DATA_MODES: tuple[str, ...] = ("array", "object")
WORDPRESS_DEFAULT_DATA_MODE: str = "array"


# ── Helpers ───────────────────────────────────────────────────────────


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
        for key in ("value", "name", "id", "title", "content", "rendered"):
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


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_coerce_str(v).strip() for v in value if _coerce_str(v).strip()]
    s = _coerce_str(value).strip()
    if not s:
        return []
    return [part.strip() for part in s.split(",") if part.strip()]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_int() -> int:
    return random.randint(1000, 99999)


def _rendered_str(value: Any) -> str:
    """Extract the rendered string from a WP REST API field or pass through."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        rendered = value.get("rendered")
        if rendered is not None:
            return _coerce_str(rendered)
    return _coerce_str(value)


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
) -> str:
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    return _coerce_str(value)


def _resolve_list_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> list[str]:
    raw = params.get(key)
    if raw is not None:
        resolved = evaluate(raw, ectx)
    else:
        resolved = None
        for fk in json_fallbacks:
            if fk in item.json and item.json[fk] is not None:
                resolved = item.json[fk]
                break
    return _coerce_str_list(resolved)


def _resolve_post_id(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> Any:
    raw = params.get("postId")
    if raw is not None:
        return evaluate(raw, ectx)
    if "postId" in item.json and item.json["postId"] is not None:
        return item.json["postId"]
    if "id" in item.json and item.json["id"] is not None:
        return item.json["id"]
    return None


def _is_empty_post_id(post_id: Any) -> bool:
    if post_id is None:
        return True
    if isinstance(post_id, str):
        return not post_id.strip()
    return False


def _resolve_data_mode(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("dataMode")
    if raw is not None:
        resolved = _coerce_str(evaluate(raw, ectx)).strip().lower()
        if resolved in WORDPRESS_DATA_MODES:
            return resolved
    json_mode = item.json.get("dataMode")
    if json_mode is not None:
        s = _coerce_str(json_mode).strip().lower()
        if s in WORDPRESS_DATA_MODES:
            return s
    return WORDPRESS_DEFAULT_DATA_MODE


def _resolve_per_page(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> int:
    raw = params.get("perPage")
    if raw is not None:
        return _coerce_int(evaluate(raw, ectx), WORDPRESS_DEFAULT_PER_PAGE)
    json_per = item.json.get("perPage")
    if json_per is not None:
        return _coerce_int(json_per, WORDPRESS_DEFAULT_PER_PAGE)
    return WORDPRESS_DEFAULT_PER_PAGE


def _resolve_page(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> int:
    raw = params.get("page")
    if raw is not None:
        return _coerce_int(evaluate(raw, ectx), WORDPRESS_DEFAULT_PAGE)
    json_page = item.json.get("page")
    if json_page is not None:
        return _coerce_int(json_page, WORDPRESS_DEFAULT_PAGE)
    return WORDPRESS_DEFAULT_PAGE


# ── Offline synthesis ─────────────────────────────────────────────────


def _synthesize_create(
    *,
    title: str,
    content: str,
    status: str,
    author: Any,
    excerpt: str,
) -> dict[str, Any]:
    post_id = _random_int()
    return {
        "id": post_id,
        "title": {"rendered": title},
        "content": {"rendered": content},
        "status": status,
        "author": author if author else WORDPRESS_DEFAULT_AUTHOR,
        "date": _now_iso(),
        "link": f"https://example.com/?p={post_id}",
        "type": "post",
        "excerpt": {"rendered": excerpt or content[:100]},
    }


def _synthesize_get(*, post_id: Any) -> dict[str, Any]:
    return {
        "id": post_id,
        "title": {"rendered": "Mock Post"},
        "content": {"rendered": "Mock post content here."},
        "status": "publish",
        "author": 1,
        "date": _now_iso(),
        "link": f"https://example.com/?p={post_id}",
        "type": "post",
    }


def _synthesize_update(
    *,
    post_id: Any,
    title: str,
    content: str,
    status: str,
) -> dict[str, Any]:
    return {
        "id": post_id,
        "title": {"rendered": title or "Mock Post"},
        "content": {"rendered": content or "Mock content"},
        "status": status or "publish",
        "modified": _now_iso(),
        "link": f"https://example.com/?p={post_id}",
        "type": "post",
    }


def _synthesize_list(*, per_page: int) -> dict[str, Any]:
    count = min(per_page, WORDPRESS_OFFLINE_MAX_POSTS)
    if count < 0:
        count = 0
    date_iso = _now_iso()
    posts: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        posts.append(
            {
                "id": i,
                "title": {"rendered": f"Mock Post {i}"},
                "content": {"rendered": f"Content {i}"},
                "status": "publish",
                "date": date_iso,
                "link": f"https://example.com/?p={i}",
                "author": 1,
            }
        )
    return {
        "posts": posts,
        "totalPosts": min(per_page, WORDPRESS_OFFLINE_MAX_POSTS),
        "totalPages": 1,
    }


def _synthesize_delete(*, post_id: Any) -> dict[str, Any]:
    return {
        "deleted": True,
        "previous": {
            "id": post_id,
            "title": {"rendered": "Deleted Post"},
            "status": "trash",
        },
    }


# ── Mock resolution ───────────────────────────────────────────────────


def _resolve_wordpress_response(
    *,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    synth: Any,
) -> tuple[dict[str, Any], str]:
    """Return ``(response, source)`` for the current call.

    ``source`` is one of ``"wordpress_response"``, ``"http_response"``,
    ``"offline"``.
    """
    mocks = ctx.mocks or {}
    wmock = mocks.get("wordpress_response")
    if wmock is not None:
        if callable(wmock):
            raw = wmock(operation, params, item, ctx)
        else:
            raw = wmock
        if isinstance(raw, dict):
            return raw, "wordpress_response"
        return synth(), "wordpress_response"

    hmock = mocks.get("http_response")
    if hmock is not None and isinstance(hmock, dict):
        body = hmock.get("body")
        if isinstance(body, dict):
            return body, "http_response"
        if isinstance(body, list) and operation == "list":
            return (
                {"posts": body, "totalPosts": len(body), "totalPages": 1},
                "http_response",
            )

    return synth(), "offline"


# ── Post field extraction ─────────────────────────────────────────────


def _extract_post(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract flattened post fields from a WP REST API post object."""
    author = raw.get("author")
    if author is None or author == "":
        author = WORDPRESS_DEFAULT_AUTHOR
    return {
        "postId": raw.get("id"),
        "title": _rendered_str(raw.get("title")),
        "content": _rendered_str(raw.get("content")),
        "status": _coerce_str(raw.get("status")),
        "author": author,
        "date": _coerce_str(raw.get("date")) or _coerce_str(raw.get("modified")),
        "link": _coerce_str(raw.get("link")),
    }


def _extract_list_post(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract flattened list-post fields (no author) for list emission."""
    return {
        "postId": raw.get("id"),
        "title": _rendered_str(raw.get("title")),
        "content": _rendered_str(raw.get("content")),
        "status": _coerce_str(raw.get("status")),
        "date": _coerce_str(raw.get("date")) or _coerce_str(raw.get("modified")),
        "link": _coerce_str(raw.get("link")),
    }


# ── Main executor ─────────────────────────────────────────────────────


async def exec_wordpress(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """WordPress node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = (
        str(params.get("operation") or WORDPRESS_DEFAULT_OPERATION).strip().lower()
    )
    if operation not in WORDPRESS_OPERATIONS:
        raise ValueError(
            f"wordpress: unsupported operation {operation!r}; "
            f"expected one of {WORDPRESS_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        if operation == "create":
            out.extend(_build_create_items(params=params, item=item, ectx=ectx, ctx=ctx))
        elif operation == "list":
            out.extend(_build_list_items(params=params, item=item, ectx=ectx, ctx=ctx))
        elif operation == "delete":
            post_id = _resolve_post_id(params, item, ectx)
            if _is_empty_post_id(post_id):
                logger.info(
                    "wordpress %s skipped: empty postId on node %r",
                    operation,
                    node.name,
                )
                continue
            out.extend(
                _build_delete_items(params=params, item=item, ctx=ctx, post_id=post_id)
            )
        elif operation == "get":
            post_id = _resolve_post_id(params, item, ectx)
            if _is_empty_post_id(post_id):
                logger.info(
                    "wordpress %s skipped: empty postId on node %r",
                    operation,
                    node.name,
                )
                continue
            out.extend(
                _build_get_items(params=params, item=item, ctx=ctx, post_id=post_id)
            )
        else:  # update
            post_id = _resolve_post_id(params, item, ectx)
            if _is_empty_post_id(post_id):
                logger.info(
                    "wordpress %s skipped: empty postId on node %r",
                    operation,
                    node.name,
                )
                continue
            out.extend(
                _build_update_items(
                    params=params, item=item, ectx=ectx, ctx=ctx, post_id=post_id
                )
            )

    return [(0, out)]


# ── Per-operation builders ────────────────────────────────────────────


def _build_create_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    title = _resolve_str_param(params, "title", item, ectx, ("title",))
    content = _resolve_str_param(
        params, "content", item, ectx, ("content", "body")
    )
    status_raw = _resolve_str_param(params, "status", item, ectx, ("status",))
    status = (
        status_raw if status_raw in WORDPRESS_STATUSES else WORDPRESS_DEFAULT_STATUS_CREATE
    )
    author = _resolve_param(params, "author", item, ectx, ("author",))
    categories = _resolve_list_param(params, "categories", item, ectx, ("categories",))
    tags = _resolve_list_param(params, "tags", item, ectx, ("tags",))
    excerpt = _resolve_str_param(params, "excerpt", item, ectx, ("excerpt",))

    def _synth() -> dict[str, Any]:
        return _synthesize_create(
            title=title, content=content, status=status, author=author, excerpt=excerpt
        )

    response, source = _resolve_wordpress_response(
        operation="create",
        params=params,
        item=item,
        ctx=ctx,
        synth=_synth,
    )

    post = _extract_post(response)
    payload: dict[str, Any] = {
        "postId": post["postId"],
        "title": post["title"] or title,
        "content": post["content"] or content,
        "status": post["status"] or status,
        "author": post["author"],
        "date": post["date"],
        "link": post["link"],
        "operation": "create",
        "source": "wordpress",
    }
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags
    if excerpt:
        payload["excerpt"] = excerpt
    if source != "wordpress_response":
        payload["mockSource"] = source

    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "wordpress create postId=%s status=%s source=%s",
        post["postId"],
        status,
        source,
    )
    return [ni]


def _build_get_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    post_id: Any,
) -> list[ExecutionItem]:
    def _synth() -> dict[str, Any]:
        return _synthesize_get(post_id=post_id)

    response, source = _resolve_wordpress_response(
        operation="get",
        params=params,
        item=item,
        ctx=ctx,
        synth=_synth,
    )

    post = _extract_post(response)
    payload: dict[str, Any] = {
        "postId": post["postId"] if post["postId"] is not None else post_id,
        "title": post["title"] or "Mock Post",
        "content": post["content"] or "Mock post content here.",
        "status": post["status"] or "publish",
        "author": post["author"],
        "date": post["date"],
        "link": post["link"],
        "operation": "get",
        "source": "wordpress",
    }
    if source != "wordpress_response":
        payload["mockSource"] = source

    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "wordpress get postId=%s source=%s",
        post_id,
        source,
    )
    return [ni]


def _build_update_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    ctx: "EngineContext",
    post_id: Any,
) -> list[ExecutionItem]:
    title = _resolve_str_param(params, "title", item, ectx, ("title",))
    content = _resolve_str_param(
        params, "content", item, ectx, ("content", "body")
    )
    status_raw = _resolve_str_param(params, "status", item, ectx, ("status",))
    status = (
        status_raw if status_raw in WORDPRESS_STATUSES else WORDPRESS_DEFAULT_STATUS_UPDATE
    )
    author = _resolve_param(params, "author", item, ectx, ("author",))
    categories = _resolve_list_param(params, "categories", item, ectx, ("categories",))
    tags = _resolve_list_param(params, "tags", item, ectx, ("tags",))
    excerpt = _resolve_str_param(params, "excerpt", item, ectx, ("excerpt",))

    def _synth() -> dict[str, Any]:
        return _synthesize_update(
            post_id=post_id, title=title, content=content, status=status
        )

    response, source = _resolve_wordpress_response(
        operation="update",
        params=params,
        item=item,
        ctx=ctx,
        synth=_synth,
    )

    post = _extract_post(response)
    payload: dict[str, Any] = {
        "postId": post["postId"] if post["postId"] is not None else post_id,
        "title": post["title"] or title or "Mock Post",
        "content": post["content"] or content or "Mock content",
        "status": post["status"] or status or "publish",
        "author": post["author"] if author else post["author"],
        "date": post["date"],
        "link": post["link"],
        "operation": "update",
        "source": "wordpress",
    }
    if categories:
        payload["categories"] = categories
    if tags:
        payload["tags"] = tags
    if excerpt:
        payload["excerpt"] = excerpt
    if source != "wordpress_response":
        payload["mockSource"] = source

    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "wordpress update postId=%s status=%s source=%s",
        post_id,
        status,
        source,
    )
    return [ni]


def _build_list_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ectx: ExpressionContext,
    ctx: "EngineContext",
) -> list[ExecutionItem]:
    per_page = _resolve_per_page(params, item, ectx)
    page = _resolve_page(params, item, ectx)
    search = _resolve_str_param(params, "search", item, ectx, ("search",))
    status_raw = _resolve_str_param(params, "status", item, ectx, ("status",))
    list_status = status_raw if status_raw else WORDPRESS_DEFAULT_STATUS_LIST
    data_mode = _resolve_data_mode(params, item, ectx)

    def _synth() -> dict[str, Any]:
        return _synthesize_list(per_page=per_page)

    response, source = _resolve_wordpress_response(
        operation="list",
        params=params,
        item=item,
        ctx=ctx,
        synth=_synth,
    )

    raw_posts = response.get("posts")
    if not isinstance(raw_posts, list):
        raw_posts = []
    total_posts = response.get("totalPosts")
    if total_posts is None:
        total_posts = len(raw_posts)

    results: list[ExecutionItem] = []

    if data_mode == "object":
        posts = [_extract_list_post(entry) for entry in raw_posts if isinstance(entry, dict)]
        payload: dict[str, Any] = {
            "posts": posts,
            "totalPosts": total_posts,
            "operation": "list",
            "source": "wordpress",
        }
        if search:
            payload["search"] = search
        if source != "wordpress_response":
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        results.append(ni)
    else:
        for entry in raw_posts:
            if not isinstance(entry, dict):
                continue
            post = _extract_list_post(entry)
            payload = {
                "postId": post["postId"],
                "title": post["title"],
                "content": post["content"],
                "status": post["status"],
                "date": post["date"],
                "link": post["link"],
                "operation": "list",
                "source": "wordpress",
            }
            if search:
                payload["search"] = search
            if source != "wordpress_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            results.append(ni)

    logger.info(
        "wordpress list perPage=%s page=%s source=%s count=%d",
        per_page,
        page,
        source,
        len(raw_posts),
    )
    return results


def _build_delete_items(
    *,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    post_id: Any,
) -> list[ExecutionItem]:
    def _synth() -> dict[str, Any]:
        return _synthesize_delete(post_id=post_id)

    response, source = _resolve_wordpress_response(
        operation="delete",
        params=params,
        item=item,
        ctx=ctx,
        synth=_synth,
    )

    deleted = bool(response.get("deleted", True))
    payload: dict[str, Any] = {
        "postId": post_id,
        "deleted": deleted,
        "operation": "delete",
        "source": "wordpress",
    }
    if source != "wordpress_response":
        payload["mockSource"] = source

    ni = item.clone()
    ni.json = {**item.json, **payload}
    logger.info(
        "wordpress delete postId=%s source=%s",
        post_id,
        source,
    )
    return [ni]


__all__ = [
    "exec_wordpress",
    "WORDPRESS_OPERATIONS",
    "WORDPRESS_DEFAULT_OPERATION",
    "WORDPRESS_STATUSES",
    "WORDPRESS_DEFAULT_STATUS_CREATE",
    "WORDPRESS_DEFAULT_STATUS_UPDATE",
    "WORDPRESS_DEFAULT_STATUS_LIST",
    "WORDPRESS_DEFAULT_PER_PAGE",
    "WORDPRESS_DEFAULT_PAGE",
    "WORDPRESS_OFFLINE_MAX_POSTS",
    "WORDPRESS_DEFAULT_AUTHOR",
    "WORDPRESS_DATA_MODES",
    "WORDPRESS_DEFAULT_DATA_MODE",
]