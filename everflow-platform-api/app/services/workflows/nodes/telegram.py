"""Telegram executors (clean-room n8n ``@n8n/n8n-nodes-base.telegram``).

v1 covers the operations most commonly used in n8n templates:

- ``telegram``       — send a message to a chat via the Telegram Bot API
  (``sendMessage``), emitting one item per input with ``{messageId,
  chatId, text, parseMode, ok, source}``.
- ``telegramTrigger`` — emit one item per received Telegram update via a
  configured webhook; items carry ``{updateId, messageId, fromId,
  fromName, chatId, text, source}``.

All API calls are mock-driven — no real network I/O is performed.

Parameters honored by ``telegram``:

- ``chatId``    (string; ``$json.chatId`` / ``$json.chat_id`` fallback)
- ``text``      (string; ``$json.text`` / ``$json.message`` fallback)
- ``parseMode`` (``Markdown`` / ``HTML`` / ``MarkdownV2``; default
  ``Markdown``)

Behavior precedence for ``telegram``:

1. ``ctx.mocks['telegram_response']`` — when present, the value drives
   the executor. A dict with ``{message_id, chat, date}`` is used
   directly; a callable is invoked as
   ``mock(chatId, text, params, item, ctx)`` and may return either a
   dict (used as-is) or any other truthy value (wrapped in a synthetic
   envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Telegram envelope.
3. Offline synthetic response with a random ``message_id`` and current
   ``date``/``chat`` echo.

Items with an empty resolved ``text`` are skipped (no item emitted).

Behavior precedence for ``telegramTrigger``:

1. ``ctx.mocks['telegram_update']`` — when present, the value drives the
   trigger. A dict is used as the raw Telegram update payload; a
   callable is invoked as ``mock(node, ctx)``.
2. ``ctx.mocks['trigger_payload']`` — generic trigger payload fallback.
3. Offline synthetic update: ``{update_id, message: {message_id, from,
   chat, date, text}}`` populated with a mock message.
"""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


TELEGRAM_PARSE_MODES: tuple[str, ...] = ("Markdown", "HTML", "MarkdownV2")


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


def _coerce_chat_id(value: Any) -> str:
    """Normalize a ``chatId`` value to a string Telegram chat identifier."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return ", ".join(_coerce_chat_id(v) for v in value if v is not None)
    if isinstance(value, dict):
        for key in ("id", "value", "name", "chatId", "chat_id"):
            if key in value and value[key] is not None:
                return _coerce_chat_id(value[key])
    return str(value)


def _chat_id_to_int(chat_id: str) -> int:
    """Best-effort int conversion of a chat id; falls back to 0."""
    s = _coerce_chat_id(chat_id).strip()
    if not s:
        return 0
    # Channels / groups in Telegram may be negative — keep the sign.
    try:
        return int(s)
    except (TypeError, ValueError):
        # Strip an optional @ prefix for public channel usernames.
        if s.startswith("@"):
            return 0
        return 0


def _resolve_chat_id(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("chatId")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_chat_id(resolved)
        if s:
            return s
    return _coerce_chat_id(item.json.get("chatId") or item.json.get("chat_id"))


def _resolve_text(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("text")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    return _coerce_str(item.json.get("text") or item.json.get("message"))


def _resolve_parse_mode(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("parseMode")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved).strip()
        if s:
            # Be lenient: accept case-insensitive and the common aliases
            aliases = {
                "markdown": "Markdown",
                "md": "Markdown",
                "html": "HTML",
                "markdownv2": "MarkdownV2",
                "markdown2": "MarkdownV2",
                "markdown_v2": "MarkdownV2",
            }
            normalized = aliases.get(s.lower(), s)
            if normalized in TELEGRAM_PARSE_MODES:
                return normalized
    return "Markdown"


def _synthesize_response(chat_id: str, text: str) -> dict[str, Any]:
    """Offline fallback: a fake Telegram ``sendMessage`` response."""
    return {
        "message_id": random.randint(1, 10**9),
        "chat": {"id": _chat_id_to_int(chat_id), "type": "private"},
        "date": int(time.time()),
        "text": text,
    }


def _response_from_http_mock(mock: Any) -> dict[str, Any] | None:
    """Extract a Telegram-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if "message_id" in body or "chat" in body or "text" in body:
            return {
                "message_id": body.get("message_id")
                or random.randint(1, 10**9),
                "chat": body.get("chat")
                or {"id": body.get("chat_id", 0), "type": "private"},
                "date": body.get("date") or int(time.time()),
                "text": body.get("text") or "",
            }
        # arbitrary body → wrap as text payload
        return {
            "message_id": random.randint(1, 10**9),
            "chat": {"id": 0, "type": "private"},
            "date": int(time.time()),
            "text": "",
            "raw": body,
        }
    if isinstance(body, str) and body.strip():
        return {
            "message_id": random.randint(1, 10**9),
            "chat": {"id": 0, "type": "private"},
            "date": int(time.time()),
            "text": body,
        }
    return None


def _resolve_telegram_response(
    *,
    chat_id: str,
    text: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"telegram_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    tmock = mocks.get("telegram_response")
    if tmock is not None:
        if callable(tmock):
            raw = tmock(chat_id, text, params, item, ctx)
        else:
            raw = tmock
        if isinstance(raw, dict):
            return (
                {
                    "message_id": raw.get("message_id")
                    or random.randint(1, 10**9),
                    "chat": raw.get("chat")
                    or {"id": _chat_id_to_int(chat_id), "type": "private"},
                    "date": raw.get("date") or int(time.time()),
                    "text": raw.get("text", text),
                },
                "telegram_response",
            )
        # Non-dict truthy → wrap as synthetic
        return (
            {
                "message_id": random.randint(1, 10**9),
                "chat": {"id": _chat_id_to_int(chat_id), "type": "private"},
                "date": int(time.time()),
                "text": text,
                "raw": raw,
            },
            "telegram_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _response_from_http_mock(hmock)
        if env is not None:
            return env, "http_response"

    return _synthesize_response(chat_id, text), "offline"


async def exec_telegram(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Telegram node — send a message per input item.

    Emits one item per input with
    ``{messageId, chatId, text, parseMode, ok, source: 'telegram'}``.
    Items with an empty ``text`` are skipped.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        chat_id = _resolve_chat_id(params, item, ectx)
        text = _resolve_text(params, item, ectx)
        parse_mode = _resolve_parse_mode(params, item, ectx)

        # Empty text → skip emitting any item
        if not text.strip():
            logger.info(
                "telegram skipped: empty text on node %r", node.name
            )
            continue

        envelope, source = _resolve_telegram_response(
            chat_id=chat_id,
            text=text,
            params=params,
            item=item,
            ctx=ctx,
        )

        payload: dict[str, Any] = {
            "messageId": envelope.get("message_id"),
            "chatId": chat_id,
            "text": envelope.get("text", text),
            "parseMode": parse_mode,
            "ok": True,
            "source": "telegram",
        }
        if isinstance(envelope.get("chat"), dict):
            payload["chat"] = envelope["chat"]
        if source != "telegram_response":
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "telegram send chatId=%s parseMode=%s source=%s",
            chat_id,
            parse_mode,
            source,
        )

    return [(0, out)]


# ── Trigger ────────────────────────────────────────────────────────────


def _synthesize_update() -> dict[str, Any]:
    """Offline fallback: a fake Telegram update payload."""
    return {
        "update_id": random.randint(1, 10**9),
        "message": {
            "message_id": 1,
            "from": {
                "id": 12345,
                "first_name": "Mock",
                "is_bot": False,
            },
            "chat": {"id": 12345, "type": "private"},
            "date": int(time.time()),
            "text": "Mock Telegram message",
        },
    }


def _resolve_update(node: "ExecNode", ctx: "EngineContext") -> dict[str, Any]:
    """Pick the Telegram update payload from mocks or fall back to the
    synthetic one."""
    if isinstance(ctx.mocks, dict):
        mock = ctx.mocks.get("telegram_update")
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
    return _synthesize_update()


def _extract_message(update: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of the inner ``message`` dict from a Telegram
    update. Telegram updates can also carry ``edited_message`` or
    ``channel_post``; we prefer ``message`` then fall back to those."""
    if not isinstance(update, dict):
        return {}
    for key in ("message", "edited_message", "channel_post", "callback_query"):
        val = update.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _extract_text(message: dict[str, Any]) -> str:
    """Best-effort string extraction of a Telegram message body."""
    if not isinstance(message, dict):
        return ""
    direct = message.get("text")
    if isinstance(direct, str) and direct:
        return direct
    for key in ("caption", "message", "body"):
        val = message.get(key)
        if isinstance(val, str) and val:
            return val
    return ""


def _extract_from(message: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {}
    raw = message.get("from")
    return raw if isinstance(raw, dict) else {}


def _extract_chat(message: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {}
    raw = message.get("chat")
    return raw if isinstance(raw, dict) else {}


def _extract_chat_id_str(message: dict[str, Any]) -> str:
    chat = _extract_chat(message)
    val = chat.get("id")
    if val is None:
        return ""
    if isinstance(val, bool):
        return ""
    if isinstance(val, (int, float)):
        return str(int(val))
    return _coerce_str(val)


def _resolve_webhook_url(
    params: dict[str, Any], ectx: ExpressionContext
) -> str:
    raw = params.get("webhookUrl")
    if raw is None:
        return ""
    return _coerce_str(evaluate(raw, ectx))


async def exec_telegram_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Telegram Trigger — emit one item per received Telegram update.

    Resolution order:

    1. ``ctx.mocks['telegram_update']`` (dict or callable ``(node, ctx)``)
    2. ``ctx.mocks['trigger_payload']`` (dict)
    3. Offline synthetic update.

    The emitted item carries flat fields downstream nodes typically read
    (``updateId``, ``messageId``, ``fromId``, ``fromName``, ``chatId``,
    ``text``) plus the original ``update`` envelope and a
    ``source: 'telegramTrigger'`` marker.

    If items list is non-empty (upstream pre-seeded), each existing item
    is passed through with the trigger context fields merged in.
    """
    params = node.parameters or {}
    ectx = ExpressionContext(
        item=items[0] if items else ExecutionItem(),
        node_outputs=ctx.node_outputs,
        now=ctx.now,
    )
    webhook_url = _resolve_webhook_url(params, ectx)

    update = _resolve_update(node, ctx)
    message = _extract_message(update)

    update_id = update.get("update_id") if isinstance(update, dict) else None
    message_id = message.get("message_id") if isinstance(message, dict) else None
    from_user = _extract_from(message)
    from_id = from_user.get("id")
    from_name = (
        from_user.get("first_name")
        or from_user.get("username")
        or from_user.get("name")
        or ""
    )
    chat_id = _extract_chat_id_str(message)
    text = _extract_text(message)

    base: dict[str, Any] = {
        "updateId": update_id,
        "messageId": message_id,
        "fromId": from_id,
        "fromName": _coerce_str(from_name) if from_name else "",
        "chatId": chat_id,
        "text": text,
        "webhookUrl": webhook_url,
        "update": dict(update) if isinstance(update, dict) else {},
        "source": "telegramTrigger",
    }

    if items:
        # Pass-through mode: keep upstream data, just add trigger context.
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
    "exec_telegram",
    "exec_telegram_trigger",
    "TELEGRAM_PARSE_MODES",
]
