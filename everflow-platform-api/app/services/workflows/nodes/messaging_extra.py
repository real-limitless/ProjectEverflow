"""Messaging notification executors (clean-room n8n-nodes-base.*).

v1 covers:

- ``mattermost``   — send messages to Mattermost channels.
- ``matrix``       — send messages to Matrix rooms.
- ``rocketchat``   — send messages to Rocket.Chat channels.
- ``gotify``       — send push notifications via Gotify.
- ``pushover``     — send push notifications via Pushover.
- ``pushbullet``   — send pushes via Pushbullet.
- ``messageBird``  — send SMS/messages via MessageBird.
- ``sms77``        — send SMS via SMS77.

All API calls are mock-driven — no real network I/O is performed.

Behavior precedence (all nodes):

1. ``ctx.mocks['<node>_response']`` — callable invoked as
   ``mock(operation, params, item, ctx)`` or dict used directly.
2. ``ctx.mocks['http_response']`` — generic fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used.
3. Offline synthetic response.
"""

from __future__ import annotations

import json
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

MATTERMOST_OPERATIONS: tuple[str, ...] = (
    "sendMessage",
    "sendFile",
    "createChannel",
    "createPost",
)
MATRIX_OPERATIONS: tuple[str, ...] = (
    "sendMessage",
    "createRoom",
    "joinRoom",
    "leaveRoom",
    "inviteUser",
)
ROCKETCHAT_OPERATIONS: tuple[str, ...] = (
    "sendMessage",
    "createChannel",
    "createPrivateGroup",
    "postMessage",
)
GOTIFY_OPERATIONS: tuple[str, ...] = ("createMessage", "createApp", "deleteMessage")
PUSHOVER_OPERATIONS: tuple[str, ...] = ("push",)
PUSHBULLET_OPERATIONS: tuple[str, ...] = ("push", "createPush", "deletePush")
MESSAGEBIRD_OPERATIONS: tuple[str, ...] = ("sendSms", "sendVoice", "verify", "lookup")
SMS77_OPERATIONS: tuple[str, ...] = ("sendSms", "sendVoice", "lookup", "status")


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


def _resolve_int_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    default: int,
    json_fallbacks: tuple[str, ...] = (),
) -> int:
    raw = _resolve_param(params, key, item, ectx, json_fallbacks)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _iso(ctx: "EngineContext") -> str:
    now = ctx.now if ctx.now else datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _mock_item(items: list[ExecutionItem]) -> ExecutionItem:
    return items[0] if items else ExecutionItem(json={})


def _resolve_mock_response(
    ctx: "EngineContext",
    mock_key: str,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
) -> tuple[Any, str]:
    """Return ``(value, source)`` from ``ctx.mocks[mock_key]`` or http_response.

    A callable mock is invoked as ``mock(operation, params, item, ctx)``; a
    non-callable is used as-is.  If the callable returns ``None`` the call is
    treated as a miss and the http_response fallback is tried.
    """
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is not None:
        if callable(mock):
            val = mock(operation, params, item, ctx)
            if val is not None:
                return val, mock_key
        else:
            return mock, mock_key
    http = mocks.get("http_response")
    if http is not None:
        if isinstance(http, dict):
            body = http.get("body", http)
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except (ValueError, TypeError):
                    return http, "http_response"
            return body, "http_response"
        return http, "http_response"
    return None, ""


def _add_mock_source(payload: dict[str, Any], src: str, mock_key: str) -> None:
    if src and src != mock_key:
        payload["mockSource"] = src


def _resolve_operation(
    params: dict[str, Any],
    default: str,
    allowed: tuple[str, ...],
    node_name: str,
) -> str:
    raw = params.get("operation")
    if raw is None:
        return default
    op = _coerce_str(raw).strip() or default
    if op not in allowed:
        raise ValueError(
            f"{node_name}: unsupported operation {op!r}; "
            f"expected one of {allowed}"
        )
    return op


def _new_id() -> str:
    return uuid.uuid4().hex


# ── 1. Mattermost ─────────────────────────────────────────────────────


def _synthesize_mattermost(
    operation: str, channel_id: str, message: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "messageId": _new_id(),
        "channelId": channel_id,
        "message": message,
        "createdAt": _iso(ctx),
        "source": "mattermost",
    }


async def exec_mattermost(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Mattermost — send messages to Mattermost channels.

    Operations: ``sendMessage`` (default), ``sendFile``, ``createChannel``,
    ``createPost``.  Emits one item per input with
    ``{messageId, channelId, message, createdAt, source: 'mattermost'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "sendMessage", MATTERMOST_OPERATIONS, "mattermost"
    )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        channel_id = _resolve_str_param(
            params, "channelId", item, ectx, ("channelId", "channel_id", "channel")
        )
        message = _resolve_str_param(
            params, "message", item, ectx, ("message", "text")
        )

        mock_val, src = _resolve_mock_response(
            ctx, "mattermost_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_mattermost(operation, channel_id, message, ctx)
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "messageId": mock_val.get("messageId", _new_id()),
                "channelId": mock_val.get("channelId", channel_id),
                "message": mock_val.get("message", message),
                "createdAt": mock_val.get("createdAt", _iso(ctx)),
                "source": "mattermost",
            }
        else:
            payload = _synthesize_mattermost(operation, channel_id, message, ctx)
            src = "offline"

        _add_mock_source(payload, src, "mattermost_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("mattermost %s source=%s", operation, src)

    return [(0, out)]


# ── 2. Matrix ─────────────────────────────────────────────────────────


def _synthesize_matrix(
    operation: str, room_id: str, message: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "eventId": "$" + _new_id() + ":" + (room_id.split(":")[-1] if ":" in room_id else "server"),
        "roomId": room_id,
        "message": message,
        "source": "matrix",
    }


async def exec_matrix(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Matrix — send messages to Matrix rooms.

    Operations: ``sendMessage`` (default), ``createRoom``, ``joinRoom``,
    ``leaveRoom``, ``inviteUser``.  Emits one item per input with
    ``{eventId, roomId, message, source: 'matrix'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "sendMessage", MATRIX_OPERATIONS, "matrix"
    )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        room_id = _resolve_str_param(
            params, "roomId", item, ectx, ("roomId", "room_id", "room")
        )
        message = _resolve_str_param(
            params, "message", item, ectx, ("message", "text")
        )

        mock_val, src = _resolve_mock_response(
            ctx, "matrix_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_matrix(operation, room_id, message, ctx)
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "eventId": mock_val.get("eventId", _new_id()),
                "roomId": mock_val.get("roomId", room_id),
                "message": mock_val.get("message", message),
                "source": "matrix",
            }
        else:
            payload = _synthesize_matrix(operation, room_id, message, ctx)
            src = "offline"

        _add_mock_source(payload, src, "matrix_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("matrix %s source=%s", operation, src)

    return [(0, out)]


# ── 3. Rocket.Chat ────────────────────────────────────────────────────


def _synthesize_rocketchat(
    operation: str, channel: str, message: str, alias: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "messageId": _new_id(),
        "channel": channel,
        "message": message,
        "alias": alias,
        "createdAt": _iso(ctx),
        "source": "rocketchat",
    }


async def exec_rocket_chat(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Rocket.Chat — send messages to Rocket.Chat.

    Operations: ``sendMessage`` (default), ``createChannel``,
    ``createPrivateGroup``, ``postMessage``.  Emits one item per input with
    ``{messageId, channel, message, source: 'rocketchat'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "sendMessage", ROCKETCHAT_OPERATIONS, "rocketchat"
    )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        channel = _resolve_str_param(
            params, "channel", item, ectx, ("channel", "channelName")
        )
        message = _resolve_str_param(
            params, "message", item, ectx, ("message", "text")
        )
        alias = _resolve_str_param(params, "alias", item, ectx, ("alias",))

        mock_val, src = _resolve_mock_response(
            ctx, "rocketchat_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_rocketchat(operation, channel, message, alias, ctx)
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "messageId": mock_val.get("messageId", _new_id()),
                "channel": mock_val.get("channel", channel),
                "message": mock_val.get("message", message),
                "source": "rocketchat",
            }
        else:
            payload = _synthesize_rocketchat(operation, channel, message, alias, ctx)
            src = "offline"

        _add_mock_source(payload, src, "rocketchat_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("rocketchat %s source=%s", operation, src)

    return [(0, out)]


# ── 4. Gotify ─────────────────────────────────────────────────────────


def _synthesize_gotify(
    operation: str, title: str, message: str, priority: int, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "messageId": _new_id(),
        "title": title,
        "message": message,
        "priority": priority,
        "createdAt": _iso(ctx),
        "source": "gotify",
    }


async def exec_gotify(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Gotify — send push notifications via Gotify.

    Operations: ``createMessage`` (default), ``createApp``,
    ``deleteMessage``.  Emits one item per input with
    ``{messageId, title, message, priority, source: 'gotify'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "createMessage", GOTIFY_OPERATIONS, "gotify"
    )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        title = _resolve_str_param(params, "title", item, ectx, ("title",))
        message = _resolve_str_param(
            params, "message", item, ectx, ("message", "text", "body")
        )
        priority = _resolve_int_param(params, "priority", item, ectx, 5, ("priority",))

        mock_val, src = _resolve_mock_response(
            ctx, "gotify_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_gotify(operation, title, message, priority, ctx)
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "messageId": mock_val.get("messageId", _new_id()),
                "title": mock_val.get("title", title),
                "message": mock_val.get("message", message),
                "priority": mock_val.get("priority", priority),
                "source": "gotify",
            }
        else:
            payload = _synthesize_gotify(operation, title, message, priority, ctx)
            src = "offline"

        _add_mock_source(payload, src, "gotify_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("gotify %s source=%s", operation, src)

    return [(0, out)]


# ── 5. Pushover ───────────────────────────────────────────────────────


def _synthesize_pushover(
    operation: str,
    title: str,
    message: str,
    device: str,
    priority: int,
    sound: str,
    ctx: "EngineContext",
) -> dict[str, Any]:
    return {
        "requestId": _new_id(),
        "status": 1,
        "title": title,
        "message": message,
        "device": device,
        "priority": priority,
        "sound": sound,
        "source": "pushover",
    }


async def exec_pushover(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Pushover — send push notifications via Pushover.

    Operations: ``push`` (default).  Emits one item per input with
    ``{requestId, status: 1, title, message, source: 'pushover'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "push", PUSHOVER_OPERATIONS, "pushover"
    )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        title = _resolve_str_param(params, "title", item, ectx, ("title",))
        message = _resolve_str_param(
            params, "message", item, ectx, ("message", "text", "body")
        )
        device = _resolve_str_param(params, "device", item, ectx, ("device",))
        priority = _resolve_int_param(params, "priority", item, ectx, 0, ("priority",))
        sound = _resolve_str_param(params, "sound", item, ectx, ("sound",))

        mock_val, src = _resolve_mock_response(
            ctx, "pushover_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_pushover(
                operation, title, message, device, priority, sound, ctx
            )
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "requestId": mock_val.get("requestId", _new_id()),
                "status": mock_val.get("status", 1),
                "title": mock_val.get("title", title),
                "message": mock_val.get("message", message),
                "priority": mock_val.get("priority", priority),
                "source": "pushover",
            }
        else:
            payload = _synthesize_pushover(
                operation, title, message, device, priority, sound, ctx
            )
            src = "offline"

        _add_mock_source(payload, src, "pushover_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("pushover %s source=%s", operation, src)

    return [(0, out)]


# ── 6. Pushbullet ─────────────────────────────────────────────────────


def _synthesize_pushbullet(
    operation: str,
    push_type: str,
    title: str,
    body: str,
    device: str,
    ctx: "EngineContext",
) -> dict[str, Any]:
    return {
        "iden": _new_id(),
        "active": True,
        "title": title,
        "body": body,
        "type": push_type,
        "device": device,
        "createdAt": _iso(ctx),
        "source": "pushbullet",
    }


async def exec_pushbullet(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Pushbullet — send pushes via Pushbullet.

    Operations: ``push`` (default), ``createPush``, ``deletePush``.  Emits
    one item per input with
    ``{iden, active: true, title, body, type, source: 'pushbullet'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "push", PUSHBULLET_OPERATIONS, "pushbullet"
    )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        push_type = _coerce_str(
            evaluate(params.get("type", "note"), ectx)
        ).strip() or "note"
        title = _resolve_str_param(params, "title", item, ectx, ("title",))
        body = _resolve_str_param(params, "body", item, ectx, ("body", "message", "text"))
        device = _resolve_str_param(params, "device", item, ectx, ("device",))

        mock_val, src = _resolve_mock_response(
            ctx, "pushbullet_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_pushbullet(
                operation, push_type, title, body, device, ctx
            )
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "iden": mock_val.get("iden", _new_id()),
                "active": mock_val.get("active", True),
                "title": mock_val.get("title", title),
                "body": mock_val.get("body", body),
                "type": mock_val.get("type", push_type),
                "source": "pushbullet",
            }
        else:
            payload = _synthesize_pushbullet(
                operation, push_type, title, body, device, ctx
            )
            src = "offline"

        _add_mock_source(payload, src, "pushbullet_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("pushbullet %s source=%s", operation, src)

    return [(0, out)]


# ── 7. MessageBird ────────────────────────────────────────────────────


def _synthesize_messagebird(
    operation: str, to: str, from_: str, body: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "messageId": _new_id(),
        "to": to,
        "from": from_,
        "body": body,
        "status": "sent",
        "createdAt": _iso(ctx),
        "source": "messagebird",
    }


async def exec_message_bird(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """MessageBird — send SMS/messages via MessageBird.

    Operations: ``sendSms`` (default), ``sendVoice``, ``verify``, ``lookup``.
    Emits one item per input with
    ``{messageId, to, from, body, status: 'sent', source: 'messagebird'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "sendSms", MESSAGEBIRD_OPERATIONS, "messageBird"
    )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        to = _resolve_str_param(params, "to", item, ectx, ("to", "recipient"))
        from_ = _resolve_str_param(
            params, "from", item, ectx, ("from", "fromNumber", "sender")
        )
        body = _resolve_str_param(
            params, "body", item, ectx, ("body", "message", "text")
        )

        mock_val, src = _resolve_mock_response(
            ctx, "messagebird_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_messagebird(operation, to, from_, body, ctx)
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "messageId": mock_val.get("messageId", _new_id()),
                "to": mock_val.get("to", to),
                "from": mock_val.get("from", from_),
                "body": mock_val.get("body", body),
                "status": mock_val.get("status", "sent"),
                "source": "messagebird",
            }
        else:
            payload = _synthesize_messagebird(operation, to, from_, body, ctx)
            src = "offline"

        _add_mock_source(payload, src, "messagebird_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("messageBird %s source=%s", operation, src)

    return [(0, out)]


# ── 8. SMS77 ──────────────────────────────────────────────────────────


def _synthesize_sms77(
    operation: str, to: str, from_: str, text: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "messageId": _new_id(),
        "to": to,
        "from": from_,
        "text": text,
        "status": "sent",
        "createdAt": _iso(ctx),
        "source": "sms77",
    }


async def exec_sms77(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """SMS77 — send SMS via SMS77.

    Operations: ``sendSms`` (default), ``sendVoice``, ``lookup``, ``status``.
    Emits one item per input with
    ``{messageId, to, from, text, status: 'sent', source: 'sms77'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "sendSms", SMS77_OPERATIONS, "sms77"
    )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        to = _resolve_str_param(params, "to", item, ectx, ("to", "recipient"))
        from_ = _resolve_str_param(
            params, "from", item, ectx, ("from", "fromNumber", "sender")
        )
        text = _resolve_str_param(
            params, "text", item, ectx, ("text", "message", "body")
        )

        mock_val, src = _resolve_mock_response(
            ctx, "sms77_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_sms77(operation, to, from_, text, ctx)
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "messageId": mock_val.get("messageId", _new_id()),
                "to": mock_val.get("to", to),
                "from": mock_val.get("from", from_),
                "text": mock_val.get("text", text),
                "status": mock_val.get("status", "sent"),
                "source": "sms77",
            }
        else:
            payload = _synthesize_sms77(operation, to, from_, text, ctx)
            src = "offline"

        _add_mock_source(payload, src, "sms77_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("sms77 %s source=%s", operation, src)

    return [(0, out)]


__all__ = [
    "exec_mattermost",
    "exec_matrix",
    "exec_rocket_chat",
    "exec_gotify",
    "exec_pushover",
    "exec_pushbullet",
    "exec_message_bird",
    "exec_sms77",
    "MATTERMOST_OPERATIONS",
    "MATRIX_OPERATIONS",
    "ROCKETCHAT_OPERATIONS",
    "GOTIFY_OPERATIONS",
    "PUSHOVER_OPERATIONS",
    "PUSHBULLET_OPERATIONS",
    "MESSAGEBIRD_OPERATIONS",
    "SMS77_OPERATIONS",
]