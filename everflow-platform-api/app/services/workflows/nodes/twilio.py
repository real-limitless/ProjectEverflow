"""Twilio executor (clean-room n8n ``@n8n/n8n-nodes-base.twilio``).

v1 covers the two operations most commonly used in n8n templates:

- ``send``  — send an SMS via the Twilio API
  (``POST /2010-04-01/Accounts/{AccountSid}/Messages.json``).
- ``call``  — place an outbound call via the Twilio API
  (``POST /2010-04-01/Accounts/{AccountSid}/Calls.json``).

When a ``twilioApi`` credential is attached and no mock is present,
real calls are made to the Twilio API via
:func:`execute_http_request`. Otherwise the executor is mock-driven
with an offline synthetic fallback.

Parameters honored:

- ``operation`` (``"send"`` / ``"call"``; default ``"send"``)
- ``from``      (string; ``$json.from`` / ``$json.fromNumber`` fallback)
- ``to``        (string; ``$json.to`` / ``$json.toNumber`` fallback)
- ``message``   (string; ``$json.message`` / ``$json.body`` / ``$json.text``
  fallback; used for SMS only)
- ``options``   (dict; optional — e.g. ``voiceUrl`` for calls)

Behavior precedence for the API call:

1. ``ctx.mocks['twilio_response']`` — when present, the value drives the
   executor. A dict with at least ``{sid, status, to, from, body?}`` is
   used directly; a callable is invoked as
   ``mock(operation, from_num, to_num, params, item, ctx)``.
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Twilio envelope.
3. If a ``twilioApi`` credential resolves (``accountSid`` and
   ``authToken`` present), a real ``POST`` call is made to the Twilio
   API (``Messages.json`` for SMS, ``Calls.json`` for calls) and the
   response envelope is used.
4. Offline synthetic response (Twilio-shaped):
   - SMS  → ``{sid: "SM<32 hex>", status: 'queued', to, from, body,
     date_created, direction: 'outbound-api', price: None,
     error_code: None, error_message: None}``
   - Call → ``{sid: "CA<32 hex>", status: 'queued', to, from,
     direction: 'outbound-api', date_created}``

Items with an empty resolved ``to`` are skipped. For SMS, items with an
empty ``message`` are also skipped (calls do not require a body).

Emitted per-item payload:

- ``{sid, status, to, from, body, operation, ok, source: 'twilio'}``
  where ``body`` is only set for SMS.
"""

from __future__ import annotations

import base64
import logging
import uuid
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


TWILIO_OPERATIONS: tuple[str, ...] = ("send", "call")


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
        for key in ("value", "name", "number", "phoneNumber", "from", "to"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _resolve_from(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("from")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    return _coerce_str(item.json.get("from") or item.json.get("fromNumber"))


def _resolve_to(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("to")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    return _coerce_str(item.json.get("to") or item.json.get("toNumber"))


def _resolve_message(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("message")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    return _coerce_str(
        item.json.get("message") or item.json.get("body") or item.json.get("text")
    )


def _resolve_options(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> dict[str, Any]:
    raw = params.get("options")
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    evaluated = evaluate(raw, ectx)
    if isinstance(evaluated, dict):
        return dict(evaluated)
    return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _synthesize_sms(to: str, from_num: str, body: str) -> dict[str, Any]:
    return {
        "sid": f"SM{uuid.uuid4().hex[:32]}",
        "status": "queued",
        "to": to,
        "from": from_num,
        "body": body,
        "date_created": _now_iso(),
        "direction": "outbound-api",
        "price": None,
        "error_code": None,
        "error_message": None,
    }


def _synthesize_call(to: str, from_num: str) -> dict[str, Any]:
    return {
        "sid": f"CA{uuid.uuid4().hex[:32]}",
        "status": "queued",
        "to": to,
        "from": from_num,
        "direction": "outbound-api",
        "date_created": _now_iso(),
    }


def _twilio_response_from_http_mock(
    mock: Any, to: str, from_num: str, body: str
) -> dict[str, Any] | None:
    if not isinstance(mock, dict):
        return None
    raw_body = mock.get("body")
    if isinstance(raw_body, dict):
        if "sid" in raw_body or "status" in raw_body:
            return {
                "sid": raw_body.get("sid") or f"SM{uuid.uuid4().hex[:32]}",
                "status": raw_body.get("status") or "queued",
                "to": raw_body.get("to", to),
                "from": raw_body.get("from", from_num),
                "body": raw_body.get("body", body),
                "raw": raw_body,
            }
        return {
            "sid": f"SM{uuid.uuid4().hex[:32]}",
            "status": "queued",
            "to": to,
            "from": from_num,
            "body": body,
            "raw": raw_body,
        }
    return None


def _build_twilio_request(
    cred: dict[str, Any],
    operation: str,
    from_num: str,
    to: str,
    body: str,
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    """Build a real Twilio API request config.

    Returns ``None`` when the credential lacks ``accountSid`` or
    ``authToken``.
    """
    account_sid = str(cred.get("accountSid") or cred.get("account_sid") or "")
    auth_token = str(cred.get("authToken") or cred.get("auth_token") or "")
    if not account_sid or not auth_token:
        return None

    raw = f"{account_sid}:{auth_token}".encode("utf-8")
    auth_header = "Basic " + base64.b64encode(raw).decode("ascii")
    headers = {"Authorization": auth_header}

    if operation == "call":
        options = params.get("options") if isinstance(params.get("options"), dict) else {}
        voice_url = str(options.get("voiceUrl") or "")
        form_body: dict[str, Any] = {"From": from_num, "To": to, "Url": voice_url}
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls.json"
    else:
        form_body = {"From": from_num, "To": to, "Body": body}
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

    return HttpRequestConfig(
        url=url,
        method="POST",
        headers=headers,
        body=form_body,
        body_mode="form",
        response_mode="json",
        timeout=30.0,
    )


def _envelope_from_twilio_api(
    data: dict[str, Any],
    operation: str,
    to: str,
    from_num: str,
    body: str,
) -> dict[str, Any]:
    """Convert a real Twilio API response to the internal envelope
    shape."""
    return {
        "sid": data.get("sid")
        or (
            f"SM{uuid.uuid4().hex[:32]}"
            if operation == "send"
            else f"CA{uuid.uuid4().hex[:32]}"
        ),
        "status": data.get("status") or "queued",
        "to": data.get("to") or to,
        "from": data.get("from") or from_num,
        "body": data.get("body", body) if operation == "send" else "",
    }


async def _resolve_twilio_response(
    *,
    operation: str,
    from_num: str,
    to: str,
    body: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"twilio_response"``, ``"http_response"``,
    ``"twilio_api"``, ``"offline"`` so downstream observers can tell
    where the result came from.
    """
    mocks = ctx.mocks or {}
    tmock = mocks.get("twilio_response")
    if tmock is not None:
        if callable(tmock):
            raw = tmock(operation, from_num, to, params, item, ctx)
        else:
            raw = tmock
        if isinstance(raw, dict):
            return (
                {
                    "sid": raw.get("sid")
                    or (
                        f"SM{uuid.uuid4().hex[:32]}"
                        if operation == "send"
                        else f"CA{uuid.uuid4().hex[:32]}"
                    ),
                    "status": raw.get("status") or "queued",
                    "to": raw.get("to", to),
                    "from": raw.get("from", from_num),
                    "body": raw.get("body", body) if operation == "send" else "",
                },
                "twilio_response",
            )
        # Non-dict truthy → wrap as synthetic
        return (
            _synthesize_sms(to, from_num, body)
            if operation == "send"
            else _synthesize_call(to, from_num),
            "twilio_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _twilio_response_from_http_mock(hmock, to, from_num, body)
        if env is not None:
            return env, "http_response"

    cred = resolve_credential(node, ctx, "twilioApi")
    if cred:
        cfg = _build_twilio_request(cred, operation, from_num, to, body, params)
        if cfg is not None:
            logger.info(
                "twilio real HTTP call operation=%s from=%s to=%s",
                operation,
                from_num[:24],
                to[:24],
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_twilio_api(
                            resp.body, operation, to, from_num, body
                        ),
                        "twilio_api",
                    )
            except Exception as exc:
                logger.warning("twilio HTTP call failed: %s", exc)

    if operation == "call":
        return _synthesize_call(to, from_num), "offline"
    return _synthesize_sms(to, from_num, body), "offline"


async def exec_twilio(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Twilio node — send an SMS or place a call per input item.

    Emits one item per input with
    ``{sid, status, to, from, body (SMS only), operation, ok,
    source: 'twilio'}``. Items with an empty ``to`` are skipped. For SMS,
    items with an empty ``message`` are skipped as well.
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or "send")
    if operation not in TWILIO_OPERATIONS:
        raise ValueError(
            f"twilio: unsupported operation {operation!r}; "
            f"expected one of {TWILIO_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        from_num = _resolve_from(params, item, ectx)
        to = _resolve_to(params, item, ectx)
        message = _resolve_message(params, item, ectx)
        options = _resolve_options(params, item, ectx)

        if not to.strip():
            logger.info(
                "twilio %s skipped: empty 'to' on node %r",
                operation,
                node.name,
            )
            continue

        if operation == "send" and not message.strip():
            logger.info(
                "twilio %s skipped: empty 'message' on node %r",
                operation,
                node.name,
            )
            continue

        envelope, source = await _resolve_twilio_response(
            operation=operation,
            from_num=from_num,
            to=to,
            body=message,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
        )

        payload: dict[str, Any] = {
            "sid": envelope.get("sid"),
            "status": envelope.get("status") or "queued",
            "to": envelope.get("to", to),
            "from": envelope.get("from", from_num),
            "operation": operation,
            "ok": True,
            "source": "twilio",
        }
        if operation == "send":
            payload["body"] = envelope.get("body", message)
        if options:
            payload["options"] = options
        if source not in ("twilio_response", "twilio_api"):
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "twilio %s from=%s to=%s source=%s",
            operation,
            from_num[:24],
            to[:24],
            source,
        )

    return [(0, out)]


__all__ = ["exec_twilio", "TWILIO_OPERATIONS"]
