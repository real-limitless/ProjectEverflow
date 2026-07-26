"""Gmail executor (clean-room n8n ``@n8n/n8n-nodes-langchain.gmail``).

v1 supports the two operations most commonly used in n8n templates:

- ``send`` — send an email and emit one item per input describing the
  resulting Gmail message (``messageId``, ``threadId``, ``to``, ``subject``,
  ``body``, ``labelIds``).
- ``sendAndWait`` — same payload as ``send`` but the workflow pauses for
  an external reply; since this is a dry-run / mock-driven environment
  the executor just echoes the operation so downstream nodes can
  branch on it.

Parameters honored:

- ``to``        (string or list; ``$json.to`` fallback)
- ``subject``   (string; ``$json.subject`` fallback)
- ``message``   (string; ``$json.message`` / ``$json.body`` / ``$json.text`` fallback)
- ``cc``        (string or list; optional)
- ``bcc``       (string or list; optional)
- ``html``      (bool; default ``False``)
- ``operation`` (``"send"`` or ``"sendAndWait"``; default ``"send"``)

Behavior precedence:

1. ``ctx.mocks['gmail_response']`` — when present, the value drives the
   executor. A dict with ``{id, threadId, labelIds}`` is used directly;
   a callable is invoked as
   ``mock(to, subject, body, params, item, ctx)`` and may return either a
   dict (used as-is) or any other truthy value (wrapped in a synthetic
   envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the message envelope.
3. Offline synthetic response with deterministic-looking
   ``<fake-…@mail.gmail.com>`` id and ``thread-…`` thread id.

Items with an empty resolved ``subject`` are skipped (no item emitted).
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


GMAIL_OPERATIONS: tuple[str, ...] = ("send", "sendAndWait")


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
        # accept {"value": "..."} or {"name": "..."} shapes
        for key in ("value", "name", "address", "email"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_recipients(value: Any) -> str:
    """Normalize a string-or-list ``to``/``cc``/``bcc`` field to a CSV string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for entry in value:
            s = _coerce_str(entry).strip()
            if s:
                parts.append(s)
        return ", ".join(parts)
    return _coerce_str(value)


def _resolve_body(item: ExecutionItem, params: dict[str, Any], ectx: ExpressionContext) -> str:
    """Resolve the message body with multiple fallback paths."""
    raw = params.get("message")
    if raw is not None:
        evaluated = evaluate(raw, ectx)
        if evaluated is not None and str(evaluated).strip() != "":
            return _coerce_str(evaluated)
    # Fall back to $json.message / $json.body / $json.text
    for key in ("message", "body", "text"):
        v = item.json.get(key)
        if v is not None and str(v).strip() != "":
            return _coerce_str(v)
    return ""


def _synthesize_response() -> dict[str, Any]:
    """Offline fallback: a fake Gmail message envelope."""
    return {
        "id": f"<fake-{uuid.uuid4().hex[:16]}@mail.gmail.com>",
        "threadId": f"<thread-{uuid.uuid4().hex[:8]}>",
        "labelIds": ["SENT"],
    }


def _gmail_response_from_http_mock(mock: Any) -> dict[str, Any] | None:
    """Extract a Gmail-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        # already a Gmail envelope
        if "id" in body or "threadId" in body:
            return {
                "id": body.get("id") or f"<fake-{uuid.uuid4().hex[:16]}@mail.gmail.com>",
                "threadId": body.get("threadId")
                or f"<thread-{uuid.uuid4().hex[:8]}>",
                "labelIds": body.get("labelIds") or ["SENT"],
            }
        # otherwise wrap the body as a synthetic id-less payload
        return {
            "id": f"<fake-{uuid.uuid4().hex[:16]}@mail.gmail.com>",
            "threadId": f"<thread-{uuid.uuid4().hex[:8]}>",
            "labelIds": ["SENT"],
            "raw": body,
        }
    if isinstance(body, str) and body.strip():
        return {
            "id": f"<fake-{uuid.uuid4().hex[:16]}@mail.gmail.com>",
            "threadId": f"<thread-{uuid.uuid4().hex[:8]}>",
            "labelIds": ["SENT"],
            "raw": body,
        }
    return None


def _resolve_gmail_response(
    *,
    to: str,
    subject: str,
    body: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"gmail_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    gmock = mocks.get("gmail_response")
    if gmock is not None:
        if callable(gmock):
            raw = gmock(to, subject, body, params, item, ctx)
        else:
            raw = gmock
        if isinstance(raw, dict):
            return (
                {
                    "id": raw.get("id")
                    or f"<fake-{uuid.uuid4().hex[:16]}@mail.gmail.com>",
                    "threadId": raw.get("threadId")
                    or f"<thread-{uuid.uuid4().hex[:8]}>",
                    "labelIds": raw.get("labelIds") or ["SENT"],
                },
                "gmail_response",
            )
        # Non-dict truthy → wrap as synthetic
        return (
            {
                "id": f"<fake-{uuid.uuid4().hex[:16]}@mail.gmail.com>",
                "threadId": f"<thread-{uuid.uuid4().hex[:8]}>",
                "labelIds": ["SENT"],
                "raw": raw,
            },
            "gmail_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _gmail_response_from_http_mock(hmock)
        if env is not None:
            return env, "http_response"

    return _synthesize_response(), "offline"


async def exec_gmail(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Gmail node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(params.get("operation") or "send")
    if operation not in GMAIL_OPERATIONS:
        raise ValueError(
            f"gmail: unsupported operation {operation!r}; "
            f"expected one of {GMAIL_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        # to
        if params.get("to") is not None:
            to = _coerce_recipients(evaluate(params.get("to"), ectx))
        else:
            to = _coerce_recipients(item.json.get("to"))

        # subject
        subject_raw = params.get("subject")
        if subject_raw is not None:
            subject = _coerce_str(evaluate(subject_raw, ectx))
        else:
            subject = _coerce_str(item.json.get("subject"))

        # Empty subject → skip emitting any item
        if not subject.strip():
            logger.info(
                "gmail %s skipped: empty subject on node %r",
                operation,
                node.name,
            )
            continue

        # message body
        body = _resolve_body(item, params, ectx)

        # cc / bcc (optional)
        cc = _coerce_recipients(evaluate(params.get("cc"), ectx)) if params.get("cc") is not None else ""
        bcc = _coerce_recipients(evaluate(params.get("bcc"), ectx)) if params.get("bcc") is not None else ""

        # html flag
        html_raw = params.get("html")
        html = bool(evaluate(html_raw, ectx)) if html_raw is not None else False

        envelope, source = _resolve_gmail_response(
            to=to,
            subject=subject,
            body=body,
            params=params,
            item=item,
            ctx=ctx,
        )

        payload: dict[str, Any] = {
            "messageId": envelope.get("id"),
            "threadId": envelope.get("threadId"),
            "to": to,
            "subject": subject,
            "body": body,
            "labelIds": envelope.get("labelIds") or ["SENT"],
            "ok": True,
            "source": "gmail",
            "operation": operation,
        }
        if cc:
            payload["cc"] = cc
        if bcc:
            payload["bcc"] = bcc
        payload["html"] = html
        if source != "gmail_response":
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "gmail %s to=%s subject=%s source=%s",
            operation,
            to[:80],
            subject[:80],
            source,
        )
    return [(0, out)]


__all__ = ["exec_gmail", "GMAIL_OPERATIONS"]
