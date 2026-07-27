"""Slack executors (clean-room n8n ``@n8n/n8n-nodes-base.slack``).

v1 covers the operations most commonly used in n8n templates:

- ``slack``        — send a message to a Slack channel via the Web API
  (``chat.postMessage``), emitting one item per input with
  ``{ok, channel, text, ts, message, source: 'slack'}``.
- ``slackTrigger``  — emit one item per received Slack Events API payload;
  items carry ``{type, channel, user, text, ts, source: 'slackTrigger'}``.

All API calls are mock-driven — no real network I/O is performed.

When a ``slackApi`` credential is attached and no mock is present, real
calls are made to the Slack Web API via
:func:`execute_http_request`. Otherwise the executor is mock-driven with
an offline synthetic fallback.

Parameters honored by ``slack``:

- ``channel``   (string; ``$json.channel`` / ``$json.channelId`` fallback;
  accepts ``#channel-name`` or channel id)
- ``text``      (string; ``$json.text`` / ``$json.message`` fallback)
- ``blocks``    (Block Kit JSON; when present, sent in place of ``text``)
- ``asUser``    (bool; default ``False``)
- ``linkNames`` (bool; default ``False``)

Behavior precedence for ``slack``:

1. ``ctx.mocks['slack_response']`` — when present, the value drives the
   executor. A dict with ``{ok, channel, ts, message}`` is used
   directly; a callable is invoked as
   ``mock(channel, text, params, item, ctx)`` and may return either a
   dict (used as-is) or any other truthy value (wrapped in a synthetic
   envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Slack envelope.
3. If a ``slackApi`` credential resolves (``botToken``/``token``
   present), a real ``POST /api/chat.postMessage`` call is made to the
   Slack Web API and the response envelope is used.
4. Offline synthetic response with a floating-point ``ts`` timestamp and
   the resolved channel/text echoed back.

Items with an empty resolved ``text`` and no ``blocks`` are skipped
(no item emitted).

Behavior precedence for ``slackTrigger``:

1. ``ctx.mocks['slack_event']`` — when present, the value drives the
   trigger. A dict is used as the raw Slack event payload; a callable
   is invoked as ``mock(node, ctx)``.
2. ``ctx.mocks['trigger_payload']`` — generic trigger payload fallback.
3. Offline synthetic event:
   ``{type: 'message', channel, user, text, ts, event_ts}``.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


SLACK_DEFAULT_EVENTS: tuple[str, ...] = ("message", "app_mention")


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
        for key in ("value", "name", "id", "channel", "text"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_channel(value: Any) -> str:
    """Normalize a channel id (``C12345``) or name (``#general``) to a string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return ", ".join(_coerce_channel(v) for v in value if v is not None)
    if isinstance(value, dict):
        for key in ("id", "value", "name", "channel", "channelId", "channel_id"):
            if key in value and value[key] is not None:
                return _coerce_channel(value[key])
    return str(value)


def _now_ts() -> str:
    """Slack-style timestamp — a fixed-point string of seconds since epoch."""
    return f"{time.time():.6f}"


def _resolve_channel(params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext) -> str:
    raw = params.get("channel")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_channel(resolved)
        if s:
            return s
    return _coerce_channel(
        item.json.get("channel") or item.json.get("channelId") or item.json.get("channel_id")
    )


def _resolve_text(params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext) -> str:
    raw = params.get("text")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    return _coerce_str(item.json.get("text") or item.json.get("message"))


def _resolve_blocks(params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext) -> Any:
    raw = params.get("blocks")
    if raw is None:
        return None
    resolved = evaluate(raw, ectx)
    if resolved is None:
        return None
    if isinstance(resolved, str):
        s = resolved.strip()
        return s if s else None
    if isinstance(resolved, (list, tuple, dict)):
        return resolved
    return None


def _resolve_bool(params: dict[str, Any], key: str, default: bool = False) -> bool:
    raw = params.get(key)
    if raw is None:
        return default
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
        return default
    return default


def _synthesize_response(channel: str, text: str) -> dict[str, Any]:
    """Offline fallback: a fake Slack ``chat.postMessage`` response."""
    ts = _now_ts()
    return {
        "ok": True,
        "channel": channel,
        "ts": ts,
        "message": {
            "type": "message",
            "text": text,
            "user": "U_MOCK_USER",
            "ts": ts,
        },
    }


def _slack_response_from_http_mock(mock: Any) -> dict[str, Any] | None:
    """Extract a Slack-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if "ok" in body or "channel" in body or "ts" in body:
            return {
                "ok": body.get("ok", True),
                "channel": body.get("channel") or "",
                "ts": body.get("ts") or _now_ts(),
                "message": body.get("message")
                or {
                    "type": "message",
                    "text": body.get("text", ""),
                    "user": body.get("user", "U_MOCK_USER"),
                    "ts": body.get("ts") or _now_ts(),
                },
            }
        return {
            "ok": True,
            "channel": "",
            "ts": _now_ts(),
            "message": {
                "type": "message",
                "text": "",
                "user": "U_MOCK_USER",
                "ts": _now_ts(),
            },
            "raw": body,
        }
    if isinstance(body, str) and body.strip():
        return {
            "ok": True,
            "channel": "",
            "ts": _now_ts(),
            "message": {
                "type": "message",
                "text": body,
                "user": "U_MOCK_USER",
                "ts": _now_ts(),
            },
        }
    return None


def _build_slack_request(
    cred: dict[str, Any],
    channel: str,
    text: str,
    blocks: Any,
    as_user: bool,
    link_names: bool,
) -> HttpRequestConfig | None:
    """Build a real Slack Web API ``chat.postMessage`` request config.

    Returns ``None`` when the credential has no token.
    """
    token = str(cred.get("botToken") or cred.get("token") or cred.get("accessToken") or "")
    if not token:
        return None
    body: dict[str, Any] = {"channel": channel}
    if blocks is not None:
        body["blocks"] = blocks
        if text:
            body["text"] = text
    else:
        body["text"] = text
    if as_user:
        body["as_user"] = True
    if link_names:
        body["link_names"] = True
    return HttpRequestConfig(
        url="https://slack.com/api/chat.postMessage",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        body=body,
        body_mode="json",
        response_mode="json",
        timeout=30.0,
    )


async def _resolve_slack_response(
    *,
    channel: str,
    text: str,
    blocks: Any,
    as_user: bool,
    link_names: bool,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"slack_response"``, ``"http_response"``,
    ``"slack_api"``, ``"offline"`` so downstream observers can tell
    where the result came from.
    """
    mocks = ctx.mocks or {}
    smock = mocks.get("slack_response")
    if smock is not None:
        if callable(smock):
            raw = smock(channel, text, params, item, ctx)
        else:
            raw = smock
        if isinstance(raw, dict):
            envelope = {
                "ok": raw.get("ok", True),
                "channel": raw.get("channel") or channel,
                "ts": raw.get("ts") or _now_ts(),
                "message": raw.get("message")
                or {
                    "type": "message",
                    "text": raw.get("text", text),
                    "user": raw.get("user", "U_MOCK_USER"),
                    "ts": raw.get("ts") or _now_ts(),
                },
            }
            return envelope, "slack_response"
        # Non-dict truthy → wrap as synthetic
        return (
            {
                "ok": True,
                "channel": channel,
                "ts": _now_ts(),
                "message": {
                    "type": "message",
                    "text": text,
                    "user": "U_MOCK_USER",
                    "ts": _now_ts(),
                },
                "raw": raw,
            },
            "slack_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _slack_response_from_http_mock(hmock)
        if env is not None:
            return env, "http_response"

    cred = resolve_credential(node, ctx, "slackApi")
    if cred:
        cfg = _build_slack_request(cred, channel, text, blocks, as_user, link_names)
        if cfg is not None:
            logger.info("slack real HTTP call channel=%s", channel)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return resp.body, "slack_api"
            except Exception as exc:
                logger.warning("slack HTTP call failed: %s", exc)

    return _synthesize_response(channel, text), "offline"


async def exec_slack(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Slack node — send a message per input item.

    Emits one item per input with
    ``{ok, channel, text, ts, message, source: 'slack'}``. Items with
    an empty ``text`` and no ``blocks`` are skipped.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        channel = _resolve_channel(params, item, ectx)
        text = _resolve_text(params, item, ectx)
        blocks = _resolve_blocks(params, item, ectx)
        as_user = _resolve_bool(params, "asUser", False)
        link_names = _resolve_bool(params, "linkNames", False)

        if not text.strip() and blocks is None:
            logger.info(
                "slack skipped: empty text and no blocks on node %r",
                node.name,
            )
            continue

        envelope, source = await _resolve_slack_response(
            channel=channel,
            text=text,
            blocks=blocks,
            as_user=as_user,
            link_names=link_names,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
        )

        message = envelope.get("message") if isinstance(envelope, dict) else None
        message_text = text
        message_user = "U_MOCK_USER"
        message_ts = envelope.get("ts", _now_ts()) if isinstance(envelope, dict) else _now_ts()
        if isinstance(message, dict):
            if isinstance(message.get("text"), str):
                message_text = message["text"]
            if isinstance(message.get("user"), str):
                message_user = message["user"]
            if isinstance(message.get("ts"), str):
                message_ts = message["ts"]

        payload: dict[str, Any] = {
            "ok": bool(envelope.get("ok", True)) if isinstance(envelope, dict) else True,
            "channel": envelope.get("channel", channel) if isinstance(envelope, dict) else channel,
            "text": message_text or text,
            "ts": message_ts,
            "message": message
            if isinstance(message, dict)
            else {
                "type": "message",
                "text": text,
                "user": message_user,
                "ts": message_ts,
            },
            "asUser": as_user,
            "linkNames": link_names,
            "source": "slack",
        }
        if blocks is not None:
            payload["blocks"] = blocks
        if source not in ("slack_response", "slack_api"):
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "slack send channel=%s source=%s asUser=%s linkNames=%s",
            channel,
            source,
            as_user,
            link_names,
        )

    return [(0, out)]


# ── Trigger ────────────────────────────────────────────────────────────


def _synthesize_event(event: str) -> dict[str, Any]:
    """Offline fallback: a fake Slack Events API payload."""
    ts = _now_ts()
    return {
        "type": event,
        "channel": "C12345",
        "user": "U12345",
        "text": "Mock Slack message",
        "ts": ts,
        "event_ts": ts,
    }


def _resolve_event(node: "ExecNode", ctx: "EngineContext", event: str) -> dict[str, Any]:
    """Pick the Slack event payload from mocks or fall back to the
    synthetic one."""
    if isinstance(ctx.mocks, dict):
        mock = ctx.mocks.get("slack_event")
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
    return _synthesize_event(event)


def _resolve_event_name(params: dict[str, Any], ectx: ExpressionContext) -> str:
    raw = params.get("event")
    if raw is None:
        return "message"
    resolved = evaluate(raw, ectx)
    s = _coerce_str(resolved).strip()
    return s or "message"


async def exec_slack_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Slack Trigger — emit one item per received Slack event.

    Resolution order:

    1. ``ctx.mocks['slack_event']`` (dict or callable ``(node, ctx)``)
    2. ``ctx.mocks['trigger_payload']`` (dict)
    3. Offline synthetic event.

    The emitted item carries flat fields downstream nodes typically read
    (``type``, ``channel``, ``user``, ``text``, ``ts``) plus the original
    ``event`` envelope and a ``source: 'slackTrigger'`` marker.

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

    payload = _resolve_event(node, ctx, event)

    event_type = _coerce_str(payload.get("type")) or event
    channel = _coerce_channel(payload.get("channel"))
    user = _coerce_str(payload.get("user"))
    text = _coerce_str(payload.get("text"))
    ts = _coerce_str(payload.get("ts")) or _now_ts()

    base: dict[str, Any] = {
        "type": event_type,
        "channel": channel,
        "user": user,
        "text": text,
        "ts": ts,
        "event": dict(payload) if isinstance(payload, dict) else {},
        "source": "slackTrigger",
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
    "exec_slack",
    "exec_slack_trigger",
    "SLACK_DEFAULT_EVENTS",
]
