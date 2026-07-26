"""Social media executors (clean-room n8n ``@n8n/n8n-nodes-base``).

v1 covers the operations most commonly used in n8n templates:

- ``twitter``  — post a tweet / retweet / reply via the X (Twitter) API v2.
  Emits one item per input with
  ``{tweetId, text, operation, authorId, createdAt, source: 'twitter'}``.
- ``linkedIn`` — post an update via the LinkedIn Share API.
  Emits one item per input with
  ``{shareId, text, visibility, author, createdAt, source: 'linkedIn'}``.
- ``reddit``   — post to a subreddit via the Reddit API.
  Emits one item per input with
  ``{postId, title, text, subreddit, kind, author, createdAt, permalink,
  source: 'reddit'}``.

All API calls are mock-driven — no real network I/O is performed.

Parameters honored by ``twitter``:

- ``operation`` (one of ``tweet`` / ``retweet`` / ``reply``; default ``tweet``)
- ``text``      (string; ``$json.text`` / ``$json.message`` / ``$json.tweet``
  fallback; used by ``tweet`` and ``reply``)
- ``tweetId``   (string; ``$json.tweetId`` / ``$json.id`` fallback; used by
  ``retweet`` and ``reply``)

Parameters honored by ``linkedIn``:

- ``text``       (string; ``$json.text`` / ``$json.message`` /
  ``$json.content`` fallback)
- ``visibility`` (one of ``PUBLIC`` / ``CONNECTIONS`` / ``LOGGED_IN_MEMBERS``;
  default ``PUBLIC``)
- ``author``     (URN, e.g. ``urn:li:person:xxx``; ``$json.author`` /
  ``$json.authorUrn`` fallback; default ``urn:li:person:mock_person``)

Parameters honored by ``reddit``:

- ``title``     (string; ``$json.title`` / ``$json.name`` fallback)
- ``text``      (string; ``$json.text`` / ``$json.body`` / ``$json.content``
  fallback)
- ``subreddit`` (string; ``$json.subreddit`` / ``$json.sub`` fallback)
- ``kind``      (one of ``self`` / ``link``; default ``self``)
- ``url``       (string; ``$json.url`` fallback; used by ``link``)

Behavior precedence (all three nodes):

1. ``ctx.mocks['<provider>_response']`` — when present, the value drives the
   executor. A callable is invoked with provider-specific args and may return
   a dict (used as the response) or any other value (falls back to offline
   synthesis, tagged ``<provider>_response``). A non-callable dict is used
   directly as the response.
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as the
   response.
3. Offline synthetic response.

Items with an empty resolved ``text`` (twitter tweet/reply, linkedIn) or
empty ``title``/``subreddit`` (reddit) are skipped (no item emitted).
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


TWITTER_OPERATIONS: tuple[str, ...] = ("tweet", "retweet", "reply")
LINKEDIN_VISIBILITIES: tuple[str, ...] = ("PUBLIC", "CONNECTIONS", "LOGGED_IN_MEMBERS")
REDDIT_KINDS: tuple[str, ...] = ("self", "link")


# ── Shared helpers ────────────────────────────────────────────────────


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
        for key in ("value", "name", "id", "text", "title"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _resolve_mock(
    ctx: "EngineContext",
    mock_key: str,
    *args: Any,
) -> tuple[Any, str]:
    """Return ``(value, source)`` from ``ctx.mocks[mock_key]`` or empty.

    A callable mock is invoked with ``*args``; a non-callable is used as-is.
    """
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is None:
        return None, ""
    if callable(mock):
        return mock(*args), mock_key
    return mock, mock_key


def _http_fallback(ctx: "EngineContext") -> tuple[Any, str]:
    """Return ``(body, 'http_response')`` from a generic ``http_response`` mock."""
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    http = mocks.get("http_response")
    if http is None:
        return None, ""
    if isinstance(http, dict):
        body = http.get("body", http)
        if isinstance(body, str):
            import json

            try:
                body = json.loads(body)
            except (ValueError, TypeError):
                return http, "http_response"
        return body, "http_response"
    return http, "http_response"


# ── Twitter ───────────────────────────────────────────────────────────


def _synthesize_twitter(
    operation: str,
    text: str,
    tweet_id: str,
) -> dict[str, Any]:
    """Offline fallback: a fake X/Twitter API v2 response."""
    return {
        "data": {
            "id": tweet_id,
            "text": text,
            "edit_history_tweet_ids": [str(random.randint(10**18, 10**19 - 1))],
            "author_id": "mock_user_id",
            "created_at": _now_iso(),
        },
        "operation": operation,
        "source": "twitter",
    }


async def exec_twitter(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Twitter node — post a tweet / retweet / reply per input item.

    Emits one item per input with
    ``{tweetId, text, operation, authorId, createdAt, source: 'twitter'}``.
    Items with an empty ``text`` are skipped for ``tweet`` and ``reply``.
    """
    params = node.parameters or {}
    operation = _coerce_str(params.get("operation")).strip() or "tweet"
    if operation not in TWITTER_OPERATIONS:
        raise ValueError(
            f"twitter: unsupported operation {operation!r}; "
            f"expected one of {TWITTER_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        text = _resolve_str_param(
            params, "text", item, ectx, ("text", "message", "tweet")
        )
        tweet_id_param = _resolve_str_param(
            params, "tweetId", item, ectx, ("tweetId", "id")
        )

        if not text.strip() and operation in ("tweet", "reply"):
            logger.info(
                "twitter %s skipped: empty text on node %r",
                operation,
                node.name,
            )
            continue

        tweet_id = str(random.randint(10**18, 10**19 - 1))
        author_id = "mock_user_id"
        created_at = _now_iso()

        mock_val, src = _resolve_mock(
            ctx, "twitter_response", operation, text, params, item, ctx
        )
        if mock_val is None:
            mock_val, src = _http_fallback(ctx)
        if mock_val is None:
            mock_val = _synthesize_twitter(operation, text, tweet_id)
            src = "offline"

        data = (
            mock_val.get("data", mock_val)
            if isinstance(mock_val, dict)
            else {}
        )
        if not isinstance(data, dict):
            data = {}

        payload: dict[str, Any] = {
            "tweetId": data.get("id", tweet_id),
            "text": data.get("text", text),
            "operation": data.get("operation", operation),
            "authorId": data.get("author_id", author_id),
            "createdAt": data.get("created_at", created_at),
            "source": "twitter",
        }
        if src and src != "twitter_response":
            payload["mockSource"] = src
        if tweet_id_param and operation in ("retweet", "reply"):
            payload["replyToId"] = tweet_id_param

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "twitter %s tweetId=%s source=%s",
            operation,
            payload["tweetId"],
            src or "offline",
        )

    return [(0, out)]


# ── LinkedIn ──────────────────────────────────────────────────────────


def _synthesize_linkedin(
    text: str,
    visibility: str,
    author: str,
) -> dict[str, Any]:
    """Offline fallback: a fake LinkedIn Share API response."""
    return {
        "id": f"urn:li:share:{random.randint(10**10, 10**11 - 1)}",
        "activity": str(random.randint(10**10, 10**11 - 1)),
        "text": text,
        "visibility": visibility,
        "author": author,
        "created_at": _now_iso(),
        "source": "linkedIn",
    }


async def exec_linkedin(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """LinkedIn node — post an update per input item.

    Emits one item per input with
    ``{shareId, text, visibility, author, createdAt, source: 'linkedIn'}``.
    Items with an empty ``text`` are skipped.
    """
    params = node.parameters or {}

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        text = _resolve_str_param(
            params, "text", item, ectx, ("text", "message", "content")
        )
        if not text.strip():
            logger.info(
                "linkedIn skipped: empty text on node %r", node.name
            )
            continue

        visibility = _resolve_str_param(
            params, "visibility", item, ectx, ("visibility",)
        ).strip().upper() or "PUBLIC"
        if visibility not in LINKEDIN_VISIBILITIES:
            visibility = "PUBLIC"

        author = _resolve_str_param(
            params, "author", item, ectx, ("author", "authorUrn")
        ).strip() or "urn:li:person:mock_person"

        share_id = f"urn:li:share:{random.randint(10**10, 10**11 - 1)}"
        created_at = _now_iso()

        mock_val, src = _resolve_mock(
            ctx, "linkedin_response", text, params, item, ctx
        )
        if mock_val is None:
            mock_val, src = _http_fallback(ctx)
        if mock_val is None:
            mock_val = _synthesize_linkedin(text, visibility, author)
            src = "offline"

        if isinstance(mock_val, dict):
            share_id = mock_val.get("id", share_id)
            text = mock_val.get("text", text)
            visibility = mock_val.get("visibility", visibility)
            author = mock_val.get("author", author)
            created_at = mock_val.get("created_at", created_at)

        payload: dict[str, Any] = {
            "shareId": share_id,
            "text": text,
            "visibility": visibility,
            "author": author,
            "createdAt": created_at,
            "source": "linkedIn",
        }
        if src and src != "linkedin_response":
            payload["mockSource"] = src

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "linkedIn shareId=%s visibility=%s source=%s",
            share_id,
            visibility,
            src or "offline",
        )

    return [(0, out)]


# ── Reddit ────────────────────────────────────────────────────────────


def _synthesize_reddit(
    title: str,
    text: str,
    subreddit: str,
    kind: str,
    url: str,
) -> dict[str, Any]:
    """Offline fallback: a fake Reddit API response."""
    short = uuid.uuid4().hex[:6]
    permalink = f"/r/{subreddit}/comments/mock/{title[:20].replace(' ', '_')}/"
    return {
        "id": f"t3_{short}",
        "name": f"t3_{short}",
        "title": title,
        "selftext": text,
        "subreddit": subreddit,
        "kind": kind,
        "author": "mock_reddit_user",
        "created_utc": time.time(),
        "permalink": permalink,
        "url": url if kind == "link" else "",
        "source": "reddit",
    }


async def exec_reddit(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Reddit node — post to a subreddit per input item.

    Emits one item per input with
    ``{postId, title, text, subreddit, kind, author, createdAt, permalink,
    source: 'reddit'}``.
    Items with an empty ``title`` or ``subreddit`` are skipped.
    """
    params = node.parameters or {}
    kind = _coerce_str(params.get("kind")).strip() or "self"
    if kind not in REDDIT_KINDS:
        raise ValueError(
            f"reddit: unsupported kind {kind!r}; "
            f"expected one of {REDDIT_KINDS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        title = _resolve_str_param(
            params, "title", item, ectx, ("title", "name")
        )
        subreddit = _resolve_str_param(
            params, "subreddit", item, ectx, ("subreddit", "sub")
        )

        if not title.strip() or not subreddit.strip():
            logger.info(
                "reddit skipped: empty title or subreddit on node %r",
                node.name,
            )
            continue

        text = _resolve_str_param(
            params, "text", item, ectx, ("text", "body", "content")
        )
        url = ""
        if kind == "link":
            url = _resolve_str_param(
                params, "url", item, ectx, ("url",)
            )

        author = "mock_reddit_user"
        created_utc = time.time()
        permalink = f"/r/{subreddit}/comments/mock/{title[:20].replace(' ', '_')}/"
        post_id = f"t3_{uuid.uuid4().hex[:6]}"

        mock_val, src = _resolve_mock(
            ctx, "reddit_response", title, text, subreddit, params, item, ctx
        )
        if mock_val is None:
            mock_val, src = _http_fallback(ctx)
        if mock_val is None:
            mock_val = _synthesize_reddit(title, text, subreddit, kind, url)
            src = "offline"

        if isinstance(mock_val, dict):
            post_id = mock_val.get("id", post_id)
            title = mock_val.get("title", title)
            text = mock_val.get("selftext", mock_val.get("text", text))
            subreddit = mock_val.get("subreddit", subreddit)
            kind = mock_val.get("kind", kind)
            author = mock_val.get("author", author)
            created_utc = mock_val.get("created_utc", created_utc)
            permalink = mock_val.get("permalink", permalink)
            url = mock_val.get("url", url)

        payload: dict[str, Any] = {
            "postId": post_id,
            "title": title,
            "text": text,
            "subreddit": subreddit,
            "kind": kind,
            "author": author,
            "createdAt": created_utc,
            "permalink": permalink,
            "source": "reddit",
        }
        if kind == "link":
            payload["url"] = url
        if src and src != "reddit_response":
            payload["mockSource"] = src

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "reddit postId=%s subreddit=%s kind=%s source=%s",
            post_id,
            subreddit,
            kind,
            src or "offline",
        )

    return [(0, out)]


__all__ = [
    "exec_twitter",
    "exec_linkedin",
    "exec_reddit",
    "TWITTER_OPERATIONS",
    "LINKEDIN_VISIBILITIES",
    "REDDIT_KINDS",
]