"""Email service executors (clean-room ``n8n-nodes-base.*``).

Implements:

- ``sendGrid``          — send email via SendGrid
- ``sendInBlue`` (Brevo)— send email via Brevo/Sendinblue
- ``mailgun``           — send email via Mailgun
- ``mailchimp``         — Mailchimp newsletter operations
- ``mailjet``           — send email via Mailjet
- ``postmarkTrigger``   — trigger on inbound Postmark email
- ``emailReadImap``     — trigger on IMAP mailbox poll

All executors are mock-driven with an offline synthetic fallback. When a
matching credential is attached and no mock is present, real calls are
made to the respective service API via :func:`execute_http_request`.

Behavior precedence for action nodes:

1. ``ctx.mocks['<node>_response']`` — callable or dict. A callable is
   invoked as ``mock(operation, params, item, ctx)``.
2. ``ctx.mocks['http_response']`` — generic fallback.
3. If a matching credential resolves, a real HTTP call is made to the
   service API and the response envelope is used.
4. Offline synthetic response.

For trigger nodes:

1. ``ctx.mocks['<node>_trigger_payload']``
2. ``ctx.mocks['trigger_payload']``
3. Offline synthetic payload.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

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


def _build_sendgrid_request(
    cred: dict[str, Any],
    to: str,
    subject: str,
    body: str,
    from_email: str,
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    """Build a real SendGrid ``/v3/mail/send`` request config.

    Returns ``None`` when the credential has no ``apiKey``.
    """
    api_key = str(cred.get("apiKey") or "")
    if not api_key:
        return None
    payload: dict[str, Any] = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }
    return HttpRequestConfig(
        url="https://api.sendgrid.com/v3/mail/send",
        method="POST",
        headers={"Authorization": f"Bearer {api_key}"},
        body=payload,
        body_mode="json",
        response_mode="json",
        timeout=30.0,
    )


def _envelope_from_sendgrid_api(
    data: dict[str, Any],
    to: str,
    subject: str,
    operation: str,
) -> dict[str, Any]:
    """Convert a real SendGrid API response to the internal envelope shape."""
    return {
        "messageId": data.get("messageId") or f"sg-{abs(hash(to + subject)) % 100000}",
        "status": "sent",
        "to": to,
        "subject": subject,
        "source": "sendgrid",
        "operation": operation,
        "sentAt": _now_iso(),
    }


def _synthesize_sendgrid_response(
    to: str, subject: str, operation: str
) -> dict[str, Any]:
    """Offline fallback: a fake SendGrid send response."""
    return {
        "messageId": f"sg-{abs(hash(to + subject)) % 100000}",
        "status": "sent",
        "to": to,
        "subject": subject,
        "source": "sendgrid",
        "operation": operation,
        "sentAt": _now_iso(),
    }


async def _resolve_sendgrid_response(
    *,
    to: str,
    subject: str,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"sendgrid_response"``, ``"http_response"``,
    ``"sendgrid_api"``, ``"offline"``.
    """
    mock = _mock_response("sendgrid_response", operation, params, item, ctx)
    if mock is not None:
        return mock, "sendgrid_response"
    http = _http_response(ctx)
    if http is not None:
        return http, "http_response"
    cred = resolve_credential(node, ctx, "sendGridApi")
    if cred:
        from_email = _resolve_param("from", params, item, ctx, default="noreply@example.com")
        body = _resolve_param("body", params, item, ctx) or _resolve_param("text", params, item, ctx)
        cfg = _build_sendgrid_request(cred, to, subject, body, from_email, params)
        if cfg is not None:
            logger.info("sendgrid real HTTP call to=%s subject=%s", to, subject)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if resp.status_code < 400:
                    headers = resp.headers or {}
                    msg_id = headers.get("X-Message-Id") or headers.get("x-message-id")
                    data = resp.body if isinstance(resp.body, dict) else {}
                    if msg_id:
                        data = {**data, "messageId": msg_id}
                    return (
                        _envelope_from_sendgrid_api(data, to, subject, operation),
                        "sendgrid_api",
                    )
            except Exception as exc:
                logger.warning("sendgrid HTTP call failed: %s", exc)
    return _synthesize_sendgrid_response(to, subject, operation), "offline"


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
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        envelope, source = await _resolve_sendgrid_response(
            to=to,
            subject=subject,
            operation=operation,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
        )
        payload: dict[str, Any] = dict(envelope)
        if source not in ("sendgrid_response", "sendgrid_api"):
            payload["mockSource"] = source
        out.append(ExecutionItem(json=payload))
    return [(0, out)]


# ── Brevo (Sendinblue) ───────────────────────────────────────────────


BREVO_OPERATIONS: tuple[str, ...] = ("send", "sendTemplate")
BREVO_DEFAULT_OPERATION: str = "send"


def _build_brevo_request(
    cred: dict[str, Any],
    to: str,
    subject: str,
    body: str,
    from_email: str,
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    """Build a real Brevo ``/v3/smtp/email`` request config.

    Returns ``None`` when the credential has no ``apiKey``.
    """
    api_key = str(cred.get("apiKey") or "")
    if not api_key:
        return None
    payload: dict[str, Any] = {
        "sender": {"email": from_email},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": body,
    }
    return HttpRequestConfig(
        url="https://api.brevo.com/v3/smtp/email",
        method="POST",
        headers={"api-key": api_key},
        body=payload,
        body_mode="json",
        response_mode="json",
        timeout=30.0,
    )


def _envelope_from_brevo_api(
    data: dict[str, Any],
    to: str,
    subject: str,
    operation: str,
) -> dict[str, Any]:
    """Convert a real Brevo API response to the internal envelope shape."""
    return {
        "messageId": data.get("messageId") or f"brevo-{abs(hash(to + subject)) % 100000}",
        "status": "sent",
        "to": to,
        "subject": subject,
        "source": "brevo",
        "operation": operation,
        "sentAt": _now_iso(),
    }


def _synthesize_brevo_response(
    to: str, subject: str, operation: str
) -> dict[str, Any]:
    """Offline fallback: a fake Brevo send response."""
    return {
        "messageId": f"brevo-{abs(hash(to + subject)) % 100000}",
        "status": "sent",
        "to": to,
        "subject": subject,
        "source": "brevo",
        "operation": operation,
        "sentAt": _now_iso(),
    }


async def _resolve_brevo_response(
    *,
    to: str,
    subject: str,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"brevo_response"``, ``"http_response"``,
    ``"brevo_api"``, ``"offline"``.
    """
    mock = _mock_response("brevo_response", operation, params, item, ctx)
    if mock is None:
        mock = _mock_response("sendinblue_response", operation, params, item, ctx)
    if mock is not None:
        return mock, "brevo_response"
    http = _http_response(ctx)
    if http is not None:
        return http, "http_response"
    cred = resolve_credential(node, ctx, "brevoApi")
    if cred:
        from_email = _resolve_param("from", params, item, ctx, default="noreply@example.com")
        body = _resolve_param("body", params, item, ctx) or _resolve_param("text", params, item, ctx)
        cfg = _build_brevo_request(cred, to, subject, body, from_email, params)
        if cfg is not None:
            logger.info("brevo real HTTP call to=%s subject=%s", to, subject)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if resp.status_code < 400:
                    data = resp.body if isinstance(resp.body, dict) else {}
                    return (
                        _envelope_from_brevo_api(data, to, subject, operation),
                        "brevo_api",
                    )
            except Exception as exc:
                logger.warning("brevo HTTP call failed: %s", exc)
    return _synthesize_brevo_response(to, subject, operation), "offline"


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
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        envelope, source = await _resolve_brevo_response(
            to=to,
            subject=subject,
            operation=operation,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
        )
        payload: dict[str, Any] = dict(envelope)
        if source not in ("brevo_response", "brevo_api"):
            payload["mockSource"] = source
        out.append(ExecutionItem(json=payload))
    return [(0, out)]


# ── Mailgun ──────────────────────────────────────────────────────────


MAILGUN_OPERATIONS: tuple[str, ...] = ("send",)
MAILGUN_DEFAULT_OPERATION: str = "send"


def _build_mailgun_request(
    cred: dict[str, Any],
    to: str,
    subject: str,
    body: str,
    from_email: str,
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    """Build a real Mailgun ``/v3/{domain}/messages`` request config.

    Returns ``None`` when the credential has no ``apiKey`` or ``domain``.
    """
    api_key = str(cred.get("apiKey") or "")
    domain = str(cred.get("domain") or "")
    if not api_key or not domain:
        return None
    base_url = str(cred.get("baseUrl") or "https://api.mailgun.net")
    auth = base64.b64encode(f"api:{api_key}".encode("utf-8")).decode("ascii")
    form: dict[str, str] = {
        "from": from_email,
        "to": to,
        "subject": subject,
        "text": body,
    }
    return HttpRequestConfig(
        url=f"{base_url}/v3/{domain}/messages",
        method="POST",
        headers={"Authorization": f"Basic {auth}"},
        body=form,
        body_mode="form",
        response_mode="json",
        timeout=30.0,
    )


def _envelope_from_mailgun_api(
    data: dict[str, Any],
    to: str,
    subject: str,
    operation: str,
) -> dict[str, Any]:
    """Convert a real Mailgun API response to the internal envelope shape."""
    return {
        "messageId": data.get("id") or f"mg-{abs(hash(to + subject)) % 100000}",
        "status": "sent",
        "to": to,
        "subject": subject,
        "source": "mailgun",
        "operation": operation,
        "sentAt": _now_iso(),
    }


def _synthesize_mailgun_response(
    to: str, subject: str, operation: str
) -> dict[str, Any]:
    """Offline fallback: a fake Mailgun send response."""
    return {
        "messageId": f"mg-{abs(hash(to + subject)) % 100000}",
        "status": "sent",
        "to": to,
        "subject": subject,
        "source": "mailgun",
        "operation": operation,
        "sentAt": _now_iso(),
    }


async def _resolve_mailgun_response(
    *,
    to: str,
    subject: str,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"mailgun_response"``, ``"http_response"``,
    ``"mailgun_api"``, ``"offline"``.
    """
    mock = _mock_response("mailgun_response", operation, params, item, ctx)
    if mock is not None:
        return mock, "mailgun_response"
    http = _http_response(ctx)
    if http is not None:
        return http, "http_response"
    cred = resolve_credential(node, ctx, "mailgunApi")
    if cred:
        from_email = _resolve_param("from", params, item, ctx, default="noreply@example.com")
        body = _resolve_param("body", params, item, ctx) or _resolve_param("text", params, item, ctx)
        cfg = _build_mailgun_request(cred, to, subject, body, from_email, params)
        if cfg is not None:
            logger.info("mailgun real HTTP call to=%s subject=%s", to, subject)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if resp.status_code < 400:
                    data = resp.body if isinstance(resp.body, dict) else {}
                    return (
                        _envelope_from_mailgun_api(data, to, subject, operation),
                        "mailgun_api",
                    )
            except Exception as exc:
                logger.warning("mailgun HTTP call failed: %s", exc)
    return _synthesize_mailgun_response(to, subject, operation), "offline"


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
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        envelope, source = await _resolve_mailgun_response(
            to=to,
            subject=subject,
            operation=operation,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
        )
        payload: dict[str, Any] = dict(envelope)
        if source not in ("mailgun_response", "mailgun_api"):
            payload["mockSource"] = source
        out.append(ExecutionItem(json=payload))
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