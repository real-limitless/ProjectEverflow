"""WhatsApp executors (clean-room n8n ``@n8n/n8n-nodes-base.whatsApp``).

v1 covers the operations most commonly used in n8n templates:

- ``whatsApp``        — send a message to a phone number via the
  WhatsApp Business Cloud API, emitting one item per input with
  ``{messageId, phoneNumber, text, messageType, ok, contacts, source}``.
- ``whatsAppTrigger``  — emit one item per incoming WhatsApp webhook
  payload; items carry ``{object, phoneNumberId, from, messageId, text,
  timestamp, source}``.

All API calls are mock-driven — no real network I/O is performed.

Parameters honored by ``whatsApp``:

- ``phoneNumber``  (string; ``$json.phoneNumber`` / ``$json.from`` /
  ``$json.to`` fallback; non-digits are stripped for the API call but
  the original value is preserved in the emitted ``phoneNumber`` field)
- ``text``         (string; ``$json.text`` / ``$json.message`` /
  ``$json.body`` fallback)
- ``messageType``  (``text`` / ``template``; default ``text``)

Behavior precedence for ``whatsApp``:

1. ``ctx.mocks['whatsapp_response']`` — when present, the value drives
   the executor. A dict with ``{messaging_product, contacts, messages}``
   is used directly; a callable is invoked as
   ``mock(phoneNumber, text, params, item, ctx)``.
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the WhatsApp envelope.
3. Offline synthetic response: ``{messaging_product, contacts,
   messages}`` with a random ``wamid.<hex>`` message id and current
   timestamp.

Items with an empty resolved ``text`` are skipped (no item emitted).

Behavior precedence for ``whatsAppTrigger``:

1. ``ctx.mocks['whatsapp_webhook']`` — when present, the value drives the
   trigger. A dict is used as the raw WhatsApp webhook payload; a
   callable is invoked as ``mock(node, ctx)``.
2. ``ctx.mocks['trigger_payload']`` — generic trigger payload fallback.
3. Offline synthetic webhook: ``{object: 'whatsapp_business_account',
   entry: [{id, changes: [{value: {messaging_product, metadata,
   messages: [...]}, field: 'messages'}]}]}``.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


WHATSAPP_MESSAGE_TYPES: tuple[str, ...] = ("text", "template")


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
        for key in ("value", "name", "id", "phone", "phoneNumber"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_phone(value: Any) -> str:
    """Normalize a phone-number value to a string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        # Ints often represent the raw digit string; coerce without
        # scientific notation surprises.
        if isinstance(value, float) and not value.is_integer():
            return str(value)
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return ", ".join(_coerce_phone(v) for v in value if v is not None)
    if isinstance(value, dict):
        for key in (
            "phoneNumber",
            "phone_number",
            "wa_id",
            "from",
            "to",
            "id",
            "value",
            "name",
        ):
            if key in value and value[key] is not None:
                return _coerce_phone(value[key])
    return str(value)


def _digits_only(value: str) -> str:
    """Strip everything except digits from a phone-number string."""
    return "".join(ch for ch in value if ch.isdigit())


def _resolve_phone_number(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("phoneNumber")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_phone(resolved)
        if s:
            return s
    return _coerce_phone(
        item.json.get("phoneNumber")
        or item.json.get("from")
        or item.json.get("to")
    )


def _resolve_text(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("text")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    return _coerce_str(
        item.json.get("text") or item.json.get("message") or item.json.get("body")
    )


def _resolve_message_type(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("messageType")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved).strip().lower()
        if s in WHATSAPP_MESSAGE_TYPES:
            return s
    return "text"


def _synthesize_response(phone: str, phone_digits: str) -> dict[str, Any]:
    """Offline fallback: a fake WhatsApp ``sendMessage`` response."""
    return {
        "messaging_product": "whatsapp",
        "contacts": [
            {"input": phone, "wa_id": phone_digits},
        ],
        "messages": [
            {
                "id": f"wamid.{uuid.uuid4().hex[:16]}",
                "from": phone_digits,
                "timestamp": int(time.time()),
            }
        ],
    }


def _response_from_http_mock(mock: Any, phone: str, phone_digits: str) -> dict[str, Any] | None:
    """Extract a WhatsApp-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if (
            "messaging_product" in body
            or "contacts" in body
            or "messages" in body
        ):
            messages = body.get("messages")
            if not isinstance(messages, list) or not messages:
                messages = [
                    {
                        "id": body.get("id")
                        or f"wamid.{uuid.uuid4().hex[:16]}",
                        "from": body.get("from", phone_digits),
                        "timestamp": body.get("timestamp") or int(time.time()),
                    }
                ]
            contacts = body.get("contacts")
            if not isinstance(contacts, list) or not contacts:
                contacts = [
                    {
                        "input": body.get("input", phone),
                        "wa_id": body.get("wa_id", phone_digits),
                    }
                ]
            return {
                "messaging_product": body.get("messaging_product", "whatsapp"),
                "contacts": contacts,
                "messages": messages,
            }
        # arbitrary body → wrap as raw
        return {
            "messaging_product": "whatsapp",
            "contacts": [
                {"input": phone, "wa_id": phone_digits},
            ],
            "messages": [
                {
                    "id": f"wamid.{uuid.uuid4().hex[:16]}",
                    "from": phone_digits,
                    "timestamp": int(time.time()),
                }
            ],
            "raw": body,
        }
    return None


def _resolve_whatsapp_response(
    *,
    phone: str,
    phone_digits: str,
    text: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"whatsapp_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    wmock = mocks.get("whatsapp_response")
    if wmock is not None:
        if callable(wmock):
            raw = wmock(phone, text, params, item, ctx)
        else:
            raw = wmock
        if isinstance(raw, dict):
            messages = raw.get("messages")
            if not isinstance(messages, list) or not messages:
                messages = [
                    {
                        "id": f"wamid.{uuid.uuid4().hex[:16]}",
                        "from": phone_digits,
                        "timestamp": int(time.time()),
                    }
                ]
            contacts = raw.get("contacts")
            if not isinstance(contacts, list) or not contacts:
                contacts = [
                    {"input": phone, "wa_id": phone_digits},
                ]
            return (
                {
                    "messaging_product": raw.get("messaging_product", "whatsapp"),
                    "contacts": contacts,
                    "messages": messages,
                },
                "whatsapp_response",
            )
        # Non-dict truthy → wrap as synthetic
        return _synthesize_response(phone, phone_digits), "whatsapp_response"

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _response_from_http_mock(hmock, phone, phone_digits)
        if env is not None:
            return env, "http_response"

    return _synthesize_response(phone, phone_digits), "offline"


def _extract_message_id(envelope: dict[str, Any]) -> Any:
    messages = envelope.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict):
            return first.get("id")
    return None


def _extract_contacts(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    contacts = envelope.get("contacts")
    if isinstance(contacts, list):
        return [c for c in contacts if isinstance(c, dict)]
    return []


async def exec_whatsapp(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """WhatsApp node — send a message per input item.

    Emits one item per input with
    ``{messageId, phoneNumber, text, messageType, ok, contacts,
    source: 'whatsApp'}``. Items with an empty ``text`` are skipped.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        phone = _resolve_phone_number(params, item, ectx)
        text = _resolve_text(params, item, ectx)
        message_type = _resolve_message_type(params, item, ectx)

        if not text.strip():
            logger.info(
                "whatsapp skipped: empty text on node %r", node.name
            )
            continue

        phone_digits = _digits_only(phone)

        envelope, source = _resolve_whatsapp_response(
            phone=phone,
            phone_digits=phone_digits,
            text=text,
            params=params,
            item=item,
            ctx=ctx,
        )

        payload: dict[str, Any] = {
            "messageId": _extract_message_id(envelope),
            "phoneNumber": phone,
            "text": text,
            "messageType": message_type,
            "ok": True,
            "contacts": _extract_contacts(envelope),
            "source": "whatsApp",
        }
        if source != "whatsapp_response":
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "whatsapp send phoneNumber=%s messageType=%s source=%s",
            phone,
            message_type,
            source,
        )

    return [(0, out)]


# ── Trigger ────────────────────────────────────────────────────────────


def _synthesize_webhook() -> dict[str, Any]:
    """Offline fallback: a fake WhatsApp webhook payload."""
    ts = int(time.time())
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "12345",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "12345",
                            },
                            "messages": [
                                {
                                    "from": "15559876543",
                                    "id": f"wamid.{uuid.uuid4().hex[:12]}",
                                    "timestamp": str(ts),
                                    "text": {"body": "Mock WhatsApp message"},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def _resolve_webhook_payload(node: "ExecNode", ctx: "EngineContext") -> dict[str, Any]:
    """Pick the WhatsApp webhook payload from mocks or fall back to the
    synthetic one."""
    if isinstance(ctx.mocks, dict):
        mock = ctx.mocks.get("whatsapp_webhook")
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
    return _synthesize_webhook()


def _extract_first_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of the first message dict from a WhatsApp
    webhook payload."""
    if not isinstance(payload, dict):
        return {}
    entry = payload.get("entry")
    if not isinstance(entry, list) or not entry:
        return {}
    first_entry = entry[0]
    if not isinstance(first_entry, dict):
        return {}
    changes = first_entry.get("changes")
    if not isinstance(changes, list) or not changes:
        return {}
    first_change = changes[0]
    if not isinstance(first_change, dict):
        return {}
    value = first_change.get("value")
    if not isinstance(value, dict):
        return {}
    messages = value.get("messages")
    if not isinstance(messages, list) or not messages:
        return {}
    first = messages[0]
    return first if isinstance(first, dict) else {}


def _extract_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    entry = payload.get("entry")
    if not isinstance(entry, list) or not entry:
        return {}
    first_entry = entry[0]
    if not isinstance(first_entry, dict):
        return {}
    changes = first_entry.get("changes")
    if not isinstance(changes, list) or not changes:
        return {}
    first_change = changes[0]
    if not isinstance(first_change, dict):
        return {}
    value = first_change.get("value")
    if not isinstance(value, dict):
        return {}
    metadata = value.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _extract_text_body(message: dict[str, Any]) -> str:
    """Best-effort string extraction of a WhatsApp message body."""
    if not isinstance(message, dict):
        return ""
    direct = message.get("text")
    if isinstance(direct, dict):
        body = direct.get("body")
        if isinstance(body, str) and body:
            return body
    for key in ("body", "caption", "text"):
        val = message.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict):
            inner = val.get("body")
            if isinstance(inner, str) and inner:
                return inner
    return ""


def _resolve_webhook_url(
    params: dict[str, Any], ectx: ExpressionContext
) -> str:
    raw = params.get("webhookUrl")
    if raw is None:
        return ""
    return _coerce_str(evaluate(raw, ectx))


async def exec_whatsapp_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """WhatsApp Trigger — emit one item per received WhatsApp webhook.

    Resolution order:

    1. ``ctx.mocks['whatsapp_webhook']`` (dict or callable ``(node, ctx)``)
    2. ``ctx.mocks['trigger_payload']`` (dict)
    3. Offline synthetic webhook.

    The emitted item carries flat fields downstream nodes typically read
    (``object``, ``phoneNumberId``, ``from``, ``messageId``, ``text``,
    ``timestamp``) plus the original ``payload`` envelope and a
    ``source: 'whatsAppTrigger'`` marker.

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

    payload = _resolve_webhook_payload(node, ctx)
    message = _extract_first_message(payload)
    metadata = _extract_metadata(payload)

    object_kind = (
        _coerce_str(payload.get("object"))
        if isinstance(payload, dict)
        else ""
    ) or "whatsapp_business_account"
    phone_number_id = _coerce_str(metadata.get("phone_number_id"))
    display_phone = _coerce_str(metadata.get("display_phone_number"))
    sender = _coerce_str(message.get("from"))
    message_id = message.get("id") if isinstance(message, dict) else None
    raw_ts = message.get("timestamp") if isinstance(message, dict) else None
    timestamp = _coerce_str(raw_ts)
    text = _extract_text_body(message)

    base: dict[str, Any] = {
        "object": object_kind,
        "phoneNumberId": phone_number_id,
        "displayPhoneNumber": display_phone,
        "from": sender,
        "messageId": message_id,
        "text": text,
        "timestamp": timestamp,
        "webhookUrl": webhook_url,
        "payload": dict(payload) if isinstance(payload, dict) else {},
        "source": "whatsAppTrigger",
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
    "exec_whatsapp",
    "exec_whatsapp_trigger",
    "WHATSAPP_MESSAGE_TYPES",
]
