"""Discord executors (clean-room n8n ``@n8n/n8n-nodes-base.discord``).

v1 covers the operations most commonly used in n8n templates:

- ``discord``        — send a message to a Discord channel via the bot
  API / webhook, emitting one item per input with
  ``{messageId, channelId, content, username, embeds, tts, ok, source: 'discord'}``.
- ``discordTrigger``  — emit one item per received Discord Gateway
  event; items carry
  ``{eventType, messageId, channelId, guildId, authorId,
  authorUsername, content, timestamp, source: 'discordTrigger'}``.

All API calls are mock-driven — no real network I/O is performed.

Parameters honored by ``discord``:

- ``channelId`` (string; ``$json.channelId`` / ``$json.channel_id`` fallback)
- ``content``   (string; ``$json.content`` / ``$json.text`` /
  ``$json.message`` fallback)
- ``username``  (override the bot's display name; default empty)
- ``tts``       (bool; default ``False``)
- ``embeds``    (list of embed dicts; optional)

Behavior precedence for ``discord``:

1. ``ctx.mocks['discord_response']`` — when present, the value drives
   the executor. A dict with ``{id, channel_id, content, author}`` is
   used directly; a callable is invoked as
   ``mock(channelId, content, params, item, ctx)`` and may return
   either a dict (used as-is) or any other truthy value (wrapped in
   a synthetic envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Discord envelope.
3. Offline synthetic response with a random ``id``, echoed
   ``channel_id``/``content``, a ``MOCK_BOT_ID`` ``author``, current
   ISO timestamp, ``tts`` and ``embeds``.

Items with an empty resolved ``content`` and no ``embeds`` are skipped
(no item emitted).

Behavior precedence for ``discordTrigger``:

1. ``ctx.mocks['discord_event']`` — when present, the value drives the
   trigger. A dict is used as the raw Discord Gateway event payload
   (with ``t``/``d``/``s``/``op`` fields); a callable is invoked as
   ``mock(node, ctx)``.
2. ``ctx.mocks['trigger_payload']`` — generic trigger payload fallback.
3. Offline synthetic event:
   ``{t: 'MESSAGE_CREATE', d: {id, channel_id, guild_id, author,
   content, timestamp}, s: 1, op: 0}``.
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


DISCORD_DEFAULT_EVENT: str = "MESSAGE_CREATE"
MOCK_BOT_ID: str = "MOCK_BOT_ID"


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
        for key in ("value", "name", "id"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_channel_id(value: Any) -> str:
    """Normalize a ``channelId`` value to a string Discord channel identifier."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        # Discord snowflakes are integers; preserve the digits.
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return ", ".join(
            _coerce_channel_id(v) for v in value if v is not None
        )
    if isinstance(value, dict):
        for key in ("id", "value", "name", "channelId", "channel_id"):
            if key in value and value[key] is not None:
                return _coerce_channel_id(value[key])
    return str(value)


def _resolve_channel_id(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("channelId")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_channel_id(resolved)
        if s:
            return s
    return _coerce_channel_id(
        item.json.get("channelId") or item.json.get("channel_id")
    )


def _resolve_content(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("content")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    return _coerce_str(
        item.json.get("content")
        or item.json.get("text")
        or item.json.get("message")
    )


def _resolve_username(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("username")
    if raw is None:
        return ""
    resolved = evaluate(raw, ectx)
    return _coerce_str(resolved).strip()


def _resolve_tts(params: dict[str, Any]) -> bool:
    raw = params.get("tts")
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off", ""):
            return False
    return False


def _resolve_embeds(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> list[Any]:
    raw = params.get("embeds")
    if raw is None:
        return []
    resolved = evaluate(raw, ectx)
    if resolved is None:
        return []
    if isinstance(resolved, (list, tuple)):
        return list(resolved)
    if isinstance(resolved, dict):
        return [resolved]
    return []


def _now_iso() -> str:
    """Return a Discord-style ISO-8601 UTC timestamp with a ``Z`` suffix."""
    return datetime.utcnow().isoformat() + "Z"


def _new_message_id() -> str:
    """Random Discord-style snowflake id (string of up to 18 digits)."""
    return str(uuid.uuid4().int)[:18]


def _synthesize_response(
    *, channel_id: str, content: str, tts: bool, embeds: list[Any]
) -> dict[str, Any]:
    """Offline fallback: a fake Discord message response."""
    return {
        "id": _new_message_id(),
        "channel_id": channel_id,
        "content": content,
        "author": {
            "id": MOCK_BOT_ID,
            "username": "mock-bot",
            "bot": True,
        },
        "timestamp": _now_iso(),
        "tts": tts,
        "embeds": list(embeds) if embeds else [],
    }


def _discord_response_from_http_mock(mock: Any) -> dict[str, Any] | None:
    """Extract a Discord-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if "id" in body or "channel_id" in body or "content" in body:
            return {
                "id": body.get("id") or _new_message_id(),
                "channel_id": body.get("channel_id") or "",
                "content": body.get("content", ""),
                "author": body.get("author")
                or {
                    "id": MOCK_BOT_ID,
                    "username": "mock-bot",
                    "bot": True,
                },
                "timestamp": body.get("timestamp") or _now_iso(),
                "tts": bool(body.get("tts", False)),
                "embeds": body.get("embeds", []) or [],
            }
        # arbitrary body → wrap as content payload
        return {
            "id": _new_message_id(),
            "channel_id": "",
            "content": "",
            "author": {
                "id": MOCK_BOT_ID,
                "username": "mock-bot",
                "bot": True,
            },
            "timestamp": _now_iso(),
            "tts": False,
            "embeds": [],
            "raw": body,
        }
    if isinstance(body, str) and body.strip():
        return {
            "id": _new_message_id(),
            "channel_id": "",
            "content": body,
            "author": {
                "id": MOCK_BOT_ID,
                "username": "mock-bot",
                "bot": True,
            },
            "timestamp": _now_iso(),
            "tts": False,
            "embeds": [],
        }
    return None


def _resolve_discord_response(
    *,
    channel_id: str,
    content: str,
    tts: bool,
    embeds: list[Any],
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"discord_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result
    came from.
    """
    mocks = ctx.mocks or {}
    dmock = mocks.get("discord_response")
    if dmock is not None:
        if callable(dmock):
            raw = dmock(channel_id, content, params, item, ctx)
        else:
            raw = dmock
        if isinstance(raw, dict):
            envelope = {
                "id": raw.get("id") or _new_message_id(),
                "channel_id": raw.get("channel_id") or channel_id,
                "content": raw.get("content", content),
                "author": raw.get("author")
                or {
                    "id": MOCK_BOT_ID,
                    "username": "mock-bot",
                    "bot": True,
                },
                "timestamp": raw.get("timestamp") or _now_iso(),
                "tts": bool(raw.get("tts", tts)),
                "embeds": list(raw.get("embeds", embeds) or []),
            }
            return envelope, "discord_response"
        # Non-dict truthy → wrap as synthetic
        return (
            {
                "id": _new_message_id(),
                "channel_id": channel_id,
                "content": content,
                "author": {
                    "id": MOCK_BOT_ID,
                    "username": "mock-bot",
                    "bot": True,
                },
                "timestamp": _now_iso(),
                "tts": tts,
                "embeds": list(embeds) if embeds else [],
                "raw": raw,
            },
            "discord_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _discord_response_from_http_mock(hmock)
        if env is not None:
            return env, "http_response"

    return (
        _synthesize_response(
            channel_id=channel_id, content=content, tts=tts, embeds=embeds
        ),
        "offline",
    )


async def exec_discord(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Discord node — send a message per input item.

    Emits one item per input with
    ``{messageId, channelId, content, username, embeds, tts, ok,
    source: 'discord'}``. Items with an empty ``content`` and no
    ``embeds`` are skipped.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        channel_id = _resolve_channel_id(params, item, ectx)
        content = _resolve_content(params, item, ectx)
        username = _resolve_username(params, item, ectx)
        tts = _resolve_tts(params)
        embeds = _resolve_embeds(params, item, ectx)

        if not content.strip() and not embeds:
            logger.info(
                "discord skipped: empty content and no embeds on node %r",
                node.name,
            )
            continue

        envelope, source = _resolve_discord_response(
            channel_id=channel_id,
            content=content,
            tts=tts,
            embeds=embeds,
            params=params,
            item=item,
            ctx=ctx,
        )

        author = envelope.get("author") if isinstance(envelope, dict) else None
        author_username = ""
        if isinstance(author, dict):
            author_username = _coerce_str(author.get("username", ""))

        payload: dict[str, Any] = {
            "messageId": envelope.get("id") if isinstance(envelope, dict) else None,
            "channelId": envelope.get("channel_id", channel_id) if isinstance(envelope, dict) else channel_id,
            "content": envelope.get("content", content) if isinstance(envelope, dict) else content,
            "username": username,
            "embeds": list(envelope.get("embeds", []) or []) if isinstance(envelope, dict) else list(embeds),
            "tts": bool(envelope.get("tts", tts)) if isinstance(envelope, dict) else tts,
            "ok": True,
            "source": "discord",
        }
        if isinstance(envelope, dict) and envelope.get("timestamp"):
            payload["timestamp"] = envelope["timestamp"]
        if isinstance(author, dict):
            payload["author"] = author
        elif author_username:
            payload["author"] = {"id": MOCK_BOT_ID, "username": author_username, "bot": True}
        if source != "discord_response":
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "discord send channelId=%s username=%r tts=%s embeds=%d source=%s",
            channel_id,
            username,
            tts,
            len(embeds),
            source,
        )

    return [(0, out)]


# ── Trigger ────────────────────────────────────────────────────────────


def _synthesize_event() -> dict[str, Any]:
    """Offline fallback: a fake Discord Gateway ``MESSAGE_CREATE`` event."""
    return {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": _new_message_id(),
            "channel_id": "12345",
            "guild_id": "67890",
            "author": {
                "id": "11111",
                "username": "mockuser",
                "bot": False,
            },
            "content": "Mock Discord message",
            "timestamp": _now_iso(),
        },
        "s": 1,
        "op": 0,
    }


def _resolve_event(node: "ExecNode", ctx: "EngineContext") -> dict[str, Any]:
    """Pick the Discord event payload from mocks or fall back to the
    synthetic one."""
    if isinstance(ctx.mocks, dict):
        mock = ctx.mocks.get("discord_event")
        if mock is not None:
            if callable(mock):
                result = mock(node, ctx)
                if isinstance(result, dict):
                    return dict(result)
            elif isinstance(mock, dict):
                return dict(mock)
        fallback = ctx.mocks.get("trigger_payload")
        if isinstance(fallback, dict):
            return dict(fallback)
    return _synthesize_event()


def _extract_d(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the inner ``d`` dict of a Discord Gateway event, or ``{}``."""
    if not isinstance(payload, dict):
        return {}
    d = payload.get("d")
    return d if isinstance(d, dict) else {}


def _extract_author(message: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {}
    raw = message.get("author")
    return raw if isinstance(raw, dict) else {}


def _resolve_event_name(
    params: dict[str, Any], ectx: ExpressionContext
) -> str:
    raw = params.get("event")
    if raw is None:
        return DISCORD_DEFAULT_EVENT
    resolved = evaluate(raw, ectx)
    s = _coerce_str(resolved).strip()
    return s or DISCORD_DEFAULT_EVENT


async def exec_discord_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Discord Trigger — emit one item per received Discord Gateway event.

    Resolution order:

    1. ``ctx.mocks['discord_event']`` (dict or callable ``(node, ctx)``)
    2. ``ctx.mocks['trigger_payload']`` (dict)
    3. Offline synthetic ``MESSAGE_CREATE`` event.

    The emitted item carries flat fields downstream nodes typically read
    (``eventType``, ``messageId``, ``channelId``, ``guildId``,
    ``authorId``, ``authorUsername``, ``content``, ``timestamp``) plus
    the original ``event`` envelope and a
    ``source: 'discordTrigger'`` marker.

    If items list is non-empty (upstream pre-seeded), each existing item
    is passed through with the trigger context fields merged in.
    """
    params = node.parameters or {}
    ectx = ExpressionContext(
        item=items[0] if items else ExecutionItem(),
        node_outputs=ctx.node_outputs,
        now=ctx.now,
    )
    event = _resolve_event_name(params, ectx)

    payload = _resolve_event(node, ctx)
    message = _extract_d(payload)

    event_type = _coerce_str(payload.get("t")) if isinstance(payload, dict) else ""
    if not event_type:
        event_type = event
    author = _extract_author(message)
    author_id = author.get("id")
    author_username = _coerce_str(author.get("username", ""))
    channel_id = _coerce_str(message.get("channel_id", ""))
    guild_id = _coerce_str(message.get("guild_id", ""))
    content = _coerce_str(message.get("content", ""))
    timestamp = _coerce_str(message.get("timestamp", ""))
    message_id = message.get("id")

    base: dict[str, Any] = {
        "eventType": event_type,
        "messageId": message_id,
        "channelId": channel_id,
        "guildId": guild_id,
        "authorId": author_id,
        "authorUsername": author_username,
        "content": content,
        "timestamp": timestamp,
        "event": dict(payload) if isinstance(payload, dict) else {},
        "source": "discordTrigger",
    }

    if items:
        out: list[ExecutionItem] = []
        for item in items:
            merged = dict(item.json)
            for key, value in base.items():
                merged.setdefault(key, value)
            ni = item.clone()
            ni.json = merged
            out.append(ni)
        return [(0, out)]

    return [(0, [ExecutionItem(json=base)])]


__all__ = [
    "exec_discord",
    "exec_discord_trigger",
    "DISCORD_DEFAULT_EVENT",
    "MOCK_BOT_ID",
]
