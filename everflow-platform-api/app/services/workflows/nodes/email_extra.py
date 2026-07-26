"""Email service executors (clean-room ``n8n-nodes-base.*``).

Implements:

- ``sendGrid``          — send email via SendGrid
- ``sendInBlue`` (Brevo)— send email via Brevo/Sendinblue
- ``mailgun``           — send email via Mailgun
- ``mailchimp``         — Mailchimp newsletter operations
- ``mailjet``           — send email via Mailjet
- ``postmarkTrigger``   — trigger on inbound Postmark email
- ``emailReadImap``     — trigger on IMAP mailbox poll

All executors are mock-driven — no real network I/O is performed.

Behavior precedence for action nodes:

1. ``ctx.mocks['<node>_response']`` — callable or dict. A callable is
   invoked as ``mock(operation, params, item, ctx)``.
2. ``ctx.mocks['http_response']`` — generic fallback.
3. Offline synthetic response.

For trigger nodes:

1. ``ctx.mocks['<node>_trigger_payload']``
2. ``ctx.mocks['trigger_payload']``
3. Offline synthetic payload.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


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
    return str(value)


def _resolve_param(
    key: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    *,
    default: str = "",
) -> str:
    raw = params.get(key)
    if raw is None:
        return default
    evaluated = evaluate(raw, _ectx(item, ctx))
    return _coerce_str(evaluated)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mock_response(
    mock_key: str,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> dict[str, Any] | None:
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is None:
        return None
    if callable(mock):
        result = mock(operation, params, item, ctx)
        if isinstance(result, dict):
            return result
        return None
    if isinstance(mock, dict):
        return mock
    return None


def _http_response(ctx: "EngineContext") -> dict[str, Any] | None:
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    hr = mocks.get("http_response")
    if isinstance(hr, dict):
        body = hr.get("body")
        if isinstance(body, dict):
            return body
    return None


# ── SendGrid ─────────────────────────────────────────────────────────


SENDGRID_OPERATIONS: tuple[str, ...] = ("send", "sendBulk")
SENDGRID_DEFAULT_OPERATION: str = "send"


async def exec_sendgrid(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """SendGrid — send email via SendGrid API."""
    params = node.parameters or {}
    operation = params.get("operation", SENDGRID_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("sendgrid_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        out.append(
            ExecutionItem(
                json={
                    "messageId": f"sg-{abs(hash(to + subject)) % 100000}",
                    "status": "sent",
                    "to": to,
                    "subject": subject,
                    "source": "sendgrid",
                    "operation": operation,
                    "sentAt": _now_iso(),
                }
            )
        )
    return [(0, out)]


# ── Brevo (Sendinblue) ───────────────────────────────────────────────


BREVO_OPERATIONS: tuple[str, ...] = ("send", "sendTemplate")
BREVO_DEFAULT_OPERATION: str = "send"


async def exec_brevo(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Brevo (Sendinblue) — send email via Brevo API."""
    params = node.parameters or {}
    operation = params.get("operation", BREVO_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("brevo_response", operation, params, item, ctx)
        if mock is None:
            mock = _mock_response("sendinblue_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        out.append(
            ExecutionItem(
                json={
                    "messageId": f"brevo-{abs(hash(to + subject)) % 100000}",
                    "status": "sent",
                    "to": to,
                    "subject": subject,
                    "source": "brevo",
                    "operation": operation,
                    "sentAt": _now_iso(),
                }
            )
        )
    return [(0, out)]


# ── Mailgun ──────────────────────────────────────────────────────────


MAILGUN_OPERATIONS: tuple[str, ...] = ("send",)
MAILGUN_DEFAULT_OPERATION: str = "send"


async def exec_mailgun(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Mailgun — send email via Mailgun API."""
    params = node.parameters or {}
    operation = params.get("operation", MAILGUN_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("mailgun_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        out.append(
            ExecutionItem(
                json={
                    "messageId": f"mg-{abs(hash(to + subject)) % 100000}",
                    "status": "sent",
                    "to": to,
                    "subject": subject,
                    "source": "mailgun",
                    "operation": operation,
                    "sentAt": _now_iso(),
                }
            )
        )
    return [(0, out)]


# ── Mailchimp ────────────────────────────────────────────────────────


MAILCHIMP_OPERATIONS: tuple[str, ...] = (
    "subscribe",
    "unsubscribe",
    "addMember",
    "updateMember",
    "getMember",
    "createCampaign",
    "sendCampaign",
)
MAILCHIMP_DEFAULT_OPERATION: str = "subscribe"


async def exec_mailchimp(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Mailchimp — newsletter / list member operations."""
    params = node.parameters or {}
    operation = params.get("operation", MAILCHIMP_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("mailchimp_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        email = _resolve_param("email", params, item, ctx)
        list_id = _resolve_param("listId", params, item, ctx)
        status = "subscribed" if operation in ("subscribe", "addMember") else "unsubscribed"
        out.append(
            ExecutionItem(
                json={
                    "email": email,
                    "listId": list_id,
                    "status": status,
                    "operation": operation,
                    "source": "mailchimp",
                    "updatedAt": _now_iso(),
                }
            )
        )
    return [(0, out)]


# ── Mailjet ──────────────────────────────────────────────────────────


MAILJET_OPERATIONS: tuple[str, ...] = ("send", "sendTemplate")
MAILJET_DEFAULT_OPERATION: str = "send"


async def exec_mailjet(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Mailjet — send email via Mailjet API."""
    params = node.parameters or {}
    operation = params.get("operation", MAILJET_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("mailjet_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        out.append(
            ExecutionItem(
                json={
                    "messageId": f"mj-{abs(hash(to + subject)) % 100000}",
                    "status": "sent",
                    "to": to,
                    "subject": subject,
                    "source": "mailjet",
                    "operation": operation,
                    "sentAt": _now_iso(),
                }
            )
        )
    return [(0, out)]


# ── Postmark Trigger ─────────────────────────────────────────────────


def _trigger_payload(ctx: "EngineContext", *keys: str) -> dict[str, Any] | None:
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    for key in keys:
        val = mocks.get(key)
        if isinstance(val, dict):
            return val
        if callable(val):
            result = val()
            if isinstance(result, dict):
                return result
    return None


async def exec_postmark_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Postmark Trigger — fires on inbound email."""
    payload = _trigger_payload(ctx, "postmark_trigger_payload", "trigger_payload")
    if payload is not None:
        return [(0, [ExecutionItem(json=payload)])]
    return [
        (
            0,
            [
                ExecutionItem(
                    json={
                        "from": "sender@example.com",
                        "to": "recipient@example.com",
                        "subject": "Inbound Postmark email",
                        "body": "This is a synthetic Postmark trigger payload.",
                        "date": _now_iso(),
                        "messageId": f"postmark-{abs(hash(_now_iso())) % 100000}",
                        "source": "postmark",
                    }
                )
            ],
        )
    ]


# ── Email IMAP Trigger ───────────────────────────────────────────────


async def exec_email_read_imap(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Email IMAP Trigger — polls an IMAP mailbox."""
    params = node.parameters or {}
    mailbox = params.get("mailbox", "INBOX")
    payload = _trigger_payload(ctx, "imap_trigger_payload", "trigger_payload")
    if payload is not None:
        if "mailbox" not in payload:
            payload = {**payload, "mailbox": mailbox}
        return [(0, [ExecutionItem(json=payload)])]
    return [
        (
            0,
            [
                ExecutionItem(
                    json={
                        "from": "sender@example.com",
                        "to": "recipient@example.com",
                        "subject": "Inbound IMAP email",
                        "body": "This is a synthetic IMAP trigger payload.",
                        "date": _now_iso(),
                        "uid": abs(hash(_now_iso())) % 1000000,
                        "mailbox": mailbox,
                        "source": "imap",
                    }
                )
            ],
        )
    ]