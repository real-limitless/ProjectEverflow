"""Microsoft executors (clean-room n8n ``@n8n/n8n-nodes-base.microsoftTeams``
and ``@n8n/n8n-nodes-base.microsoftOutlook``).

v1 covers the operations most commonly used in n8n templates:

- ``microsoftTeams``   — send a message to a Microsoft Teams channel
  (Graph API ``POST /teams/{team-id}/channels/{channel-id}/messages``),
  emitting one item per input with
  ``{messageId, teamId, channelId, message, contentType, createdDateTime,
  ok, source: 'microsoftTeams'}``.
- ``microsoftOutlook`` — send an email via Microsoft Graph
  (``POST /me/sendMail`` or ``POST /users/{id}/sendMail``), emitting one
  item per input with
  ``{messageId, internetMessageId, to, subject, body, bodyContentType,
  sentDateTime, ok, source: 'microsoftOutlook'}``.

All API calls are mock-driven — no real network I/O is performed.

Parameters honored by ``microsoftTeams``:

- ``teamId``      (string; ``$json.teamId`` / ``$json.team_id`` fallback)
- ``channelId``   (string; ``$json.channelId`` / ``$json.channel_id`` fallback)
- ``message``     (string; ``$json.message`` / ``$json.text`` / ``$json.content`` fallback)
- ``contentType`` (``text`` / ``html``; default ``text``)

Behavior precedence for ``microsoftTeams``:

1. ``ctx.mocks['teams_response']`` — when present, the value drives the
   executor. A dict with ``{id, createdDateTime, from, body}`` is used
   directly; a callable is invoked as
   ``mock(channelId, message, params, item, ctx)`` and may return either
   a dict (used as-is) or any other truthy value (wrapped in a synthetic
   envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Teams envelope.
3. Offline synthetic response with a random UUID ``id``, an
   ``createdDateTime`` ISO timestamp, and the resolved message echoed.

Items with an empty resolved ``message`` are skipped (no item emitted).

Parameters honored by ``microsoftOutlook``:

- ``to``             (string or list; ``$json.to`` fallback)
- ``subject``        (string; ``$json.subject`` fallback)
- ``body``           (string; ``$json.body`` / ``$json.message`` / ``$json.text`` fallback)
- ``bodyContentType``(``Text`` / ``HTML``; default ``Text``)
- ``cc``             (string or list; optional)
- ``bcc``            (string or list; optional)

Behavior precedence for ``microsoftOutlook``:

1. ``ctx.mocks['outlook_response']`` — when present, the value drives
   the executor. A dict with ``{id, conversationId, internetMessageId,
   from, toRecipients}`` is used directly; a callable is invoked as
   ``mock(to, subject, body, params, item, ctx)`` and may return either
   a dict (used as-is) or any other truthy value (wrapped in a synthetic
   envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Outlook envelope.
3. Offline synthetic response with random UUIDs for ``id`` and
   ``conversationId``, a ``<…@outlook.com>`` ``internetMessageId``, and
   the resolved recipients/subject/body echoed.

Items with an empty resolved ``subject`` or ``body`` are skipped (no
item emitted).
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


MICROSOFT_TEAMS_CONTENT_TYPES: tuple[str, ...] = ("text", "html")
MICROSOFT_OUTLOOK_BODY_CONTENT_TYPES: tuple[str, ...] = ("Text", "HTML")


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
        for key in ("value", "name", "id", "text", "message", "content"):
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


def _normalize_content_type(value: Any, *, default: str) -> str:
    """Normalize a content-type value to one of the allowed tokens."""
    if value is None:
        return default
    s = _coerce_str(value).strip()
    if not s:
        return default
    lowered = s.lower()
    if default == "text":
        if lowered in ("text", "html"):
            return lowered
        return default
    # Outlook body content type: "Text" or "HTML"
    if s in ("Text", "HTML"):
        return s
    if lowered == "html":
        return "HTML"
    if lowered == "text":
        return "Text"
    return default


def _now_iso_z() -> str:
    """ISO-8601 UTC timestamp ending in ``Z`` (Graph API style)."""
    return datetime.utcnow().isoformat() + "Z"


# ── microsoftTeams ────────────────────────────────────────────────────


def _resolve_team_id(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("teamId")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved).strip()
        if s:
            return s
    return _coerce_str(item.json.get("teamId") or item.json.get("team_id"))


def _resolve_channel_id(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("channelId")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved).strip()
        if s:
            return s
    return _coerce_str(
        item.json.get("channelId") or item.json.get("channel_id")
    )


def _resolve_message(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("message")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    for key in ("message", "text", "content"):
        v = item.json.get(key)
        if v is not None and str(v).strip():
            return _coerce_str(v)
    return ""


def _synthesize_teams_response(
    channel_id: str, message: str, content_type: str
) -> dict[str, Any]:
    """Offline fallback: a fake Graph API chatMessage envelope."""
    return {
        "id": str(uuid.uuid4()),
        "createdDateTime": _now_iso_z(),
        "from": {
            "user": {
                "id": "MOCK_USER_ID",
                "displayName": "Mock User",
            }
        },
        "body": {
            "contentType": content_type,
            "content": message,
        },
        "channelId": channel_id,
    }


def _teams_response_from_http_mock(mock: Any) -> dict[str, Any] | None:
    """Extract a Teams-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if "id" in body or "createdDateTime" in body or "body" in body:
            return {
                "id": body.get("id") or str(uuid.uuid4()),
                "createdDateTime": body.get("createdDateTime") or _now_iso_z(),
                "from": body.get("from")
                or {
                    "user": {
                        "id": "MOCK_USER_ID",
                        "displayName": "Mock User",
                    }
                },
                "body": body.get("body")
                or {
                    "contentType": "text",
                    "content": "",
                },
            }
        # otherwise wrap the body as a synthetic id-less payload
        return {
            "id": str(uuid.uuid4()),
            "createdDateTime": _now_iso_z(),
            "from": {
                "user": {
                    "id": "MOCK_USER_ID",
                    "displayName": "Mock User",
                }
            },
            "body": {"contentType": "text", "content": ""},
            "raw": body,
        }
    if isinstance(body, str) and body.strip():
        return {
            "id": str(uuid.uuid4()),
            "createdDateTime": _now_iso_z(),
            "from": {
                "user": {
                    "id": "MOCK_USER_ID",
                    "displayName": "Mock User",
                }
            },
            "body": {"contentType": "text", "content": body},
        }
    return None


def _resolve_teams_response(
    *,
    channel_id: str,
    message: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    content_type: str,
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"teams_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    tmock = mocks.get("teams_response")
    if tmock is not None:
        if callable(tmock):
            raw = tmock(channel_id, message, params, item, ctx)
        else:
            raw = tmock
        if isinstance(raw, dict):
            envelope = {
                "id": raw.get("id") or str(uuid.uuid4()),
                "createdDateTime": raw.get("createdDateTime") or _now_iso_z(),
                "from": raw.get("from")
                or {
                    "user": {
                        "id": "MOCK_USER_ID",
                        "displayName": "Mock User",
                    }
                },
                "body": raw.get("body")
                or {
                    "contentType": content_type,
                    "content": message,
                },
                "channelId": raw.get("channelId") or channel_id,
            }
            return envelope, "teams_response"
        # Non-dict truthy → wrap as synthetic
        return (
            _synthesize_teams_response(channel_id, message, content_type) | {"raw": raw},
            "teams_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _teams_response_from_http_mock(hmock)
        if env is not None:
            env.setdefault("channelId", channel_id)
            if isinstance(env.get("body"), dict):
                env["body"].setdefault("contentType", content_type)
                if not env["body"].get("content"):
                    env["body"]["content"] = message
            return env, "http_response"

    return (
        _synthesize_teams_response(channel_id, message, content_type),
        "offline",
    )


async def exec_microsoft_teams(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Microsoft Teams node — send a message to a channel per input item.

    Emits one item per input with
    ``{messageId, teamId, channelId, message, contentType,
    createdDateTime, ok, source: 'microsoftTeams'}``. Items with an
    empty ``message`` are skipped.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        team_id = _resolve_team_id(params, item, ectx)
        channel_id = _resolve_channel_id(params, item, ectx)
        message = _resolve_message(params, item, ectx)
        content_type = _normalize_content_type(
            params.get("contentType"), default="text"
        )

        if not message.strip():
            logger.info(
                "microsoftTeams skipped: empty message on node %r",
                node.name,
            )
            continue

        envelope, source = _resolve_teams_response(
            channel_id=channel_id,
            message=message,
            params=params,
            item=item,
            ctx=ctx,
            content_type=content_type,
        )

        body = envelope.get("body") if isinstance(envelope, dict) else None
        if not isinstance(body, dict):
            body = {"contentType": content_type, "content": message}

        payload: dict[str, Any] = {
            "messageId": envelope.get("id") if isinstance(envelope, dict) else None,
            "teamId": team_id,
            "channelId": envelope.get("channelId", channel_id) if isinstance(envelope, dict) else channel_id,
            "message": body.get("content", message),
            "contentType": body.get("contentType", content_type),
            "createdDateTime": envelope.get("createdDateTime")
            if isinstance(envelope, dict)
            else _now_iso_z(),
            "ok": True,
            "source": "microsoftTeams",
        }
        if source != "teams_response":
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "microsoftTeams send team=%s channel=%s source=%s",
            team_id,
            channel_id,
            source,
        )

    return [(0, out)]


# ── microsoftOutlook ──────────────────────────────────────────────────


def _resolve_to(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("to")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_recipients(resolved)
        if s.strip():
            return s
    return _coerce_recipients(item.json.get("to"))


def _resolve_subject(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("subject")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved)
        if s.strip():
            return s
    return _coerce_str(item.json.get("subject"))


def _resolve_outlook_body(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> str:
    raw = params.get("body")
    if raw is not None:
        resolved = evaluate(raw, ectx)
        if resolved is not None and str(resolved).strip() != "":
            return _coerce_str(resolved)
    for key in ("body", "message", "text"):
        v = item.json.get(key)
        if v is not None and str(v).strip() != "":
            return _coerce_str(v)
    return ""


def _synthesize_outlook_response(
    to_list: str, subject: str, body: str
) -> dict[str, Any]:
    """Offline fallback: a fake Graph API sendMail response."""
    message_id = str(uuid.uuid4())
    return {
        "id": message_id,
        "conversationId": str(uuid.uuid4()),
        "internetMessageId": f"<{uuid.uuid4().hex}@outlook.com>",
        "from": {
            "emailAddress": {
                "name": "Mock User",
                "address": "mock@outlook.com",
            }
        },
        "toRecipients": [
            {"emailAddress": {"name": addr.strip(), "address": addr.strip()}}
            for addr in to_list.split(",")
            if addr.strip()
        ],
        "subject": subject,
        "bodyPreview": body[:100],
        "sentDateTime": _now_iso_z(),
    }


def _outlook_response_from_http_mock(mock: Any) -> dict[str, Any] | None:
    """Extract an Outlook-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if (
            "id" in body
            or "conversationId" in body
            or "internetMessageId" in body
        ):
            return {
                "id": body.get("id") or str(uuid.uuid4()),
                "conversationId": body.get("conversationId") or str(uuid.uuid4()),
                "internetMessageId": body.get("internetMessageId")
                or f"<{uuid.uuid4().hex}@outlook.com>",
                "from": body.get("from")
                or {
                    "emailAddress": {
                        "name": "Mock User",
                        "address": "mock@outlook.com",
                    }
                },
                "toRecipients": body.get("toRecipients") or [],
            }
        return {
            "id": str(uuid.uuid4()),
            "conversationId": str(uuid.uuid4()),
            "internetMessageId": f"<{uuid.uuid4().hex}@outlook.com>",
            "from": {
                "emailAddress": {
                    "name": "Mock User",
                    "address": "mock@outlook.com",
                }
            },
            "toRecipients": [],
            "raw": body,
        }
    if isinstance(body, str) and body.strip():
        return {
            "id": str(uuid.uuid4()),
            "conversationId": str(uuid.uuid4()),
            "internetMessageId": f"<{uuid.uuid4().hex}@outlook.com>",
            "from": {
                "emailAddress": {
                    "name": "Mock User",
                    "address": "mock@outlook.com",
                }
            },
            "toRecipients": [],
            "raw": body,
        }
    return None


def _resolve_outlook_response(
    *,
    to: str,
    subject: str,
    body: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"outlook_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    omock = mocks.get("outlook_response")
    if omock is not None:
        if callable(omock):
            raw = omock(to, subject, body, params, item, ctx)
        else:
            raw = omock
        if isinstance(raw, dict):
            envelope = {
                "id": raw.get("id") or str(uuid.uuid4()),
                "conversationId": raw.get("conversationId") or str(uuid.uuid4()),
                "internetMessageId": raw.get("internetMessageId")
                or f"<{uuid.uuid4().hex}@outlook.com>",
                "from": raw.get("from")
                or {
                    "emailAddress": {
                        "name": "Mock User",
                        "address": "mock@outlook.com",
                    }
                },
                "toRecipients": raw.get("toRecipients")
                or [
                    {"emailAddress": {"name": addr.strip(), "address": addr.strip()}}
                    for addr in to.split(",")
                    if addr.strip()
                ],
                "subject": raw.get("subject", subject),
                "bodyPreview": raw.get("bodyPreview", body[:100]),
                "sentDateTime": raw.get("sentDateTime") or _now_iso_z(),
            }
            return envelope, "outlook_response"
        # Non-dict truthy → wrap as synthetic
        return (
            _synthesize_outlook_response(to, subject, body) | {"raw": raw},
            "outlook_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _outlook_response_from_http_mock(hmock)
        if env is not None:
            env.setdefault("subject", subject)
            env.setdefault("bodyPreview", body[:100])
            env.setdefault("sentDateTime", _now_iso_z())
            if not env.get("toRecipients"):
                env["toRecipients"] = [
                    {"emailAddress": {"name": addr.strip(), "address": addr.strip()}}
                    for addr in to.split(",")
                    if addr.strip()
                ]
            return env, "http_response"

    return _synthesize_outlook_response(to, subject, body), "offline"


async def exec_microsoft_outlook(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Microsoft Outlook node — send an email via Graph API per input item.

    Emits one item per input with
    ``{messageId, internetMessageId, to, subject, body, bodyContentType,
    sentDateTime, ok, source: 'microsoftOutlook'}``. Items with an empty
    ``subject`` or empty ``body`` are skipped.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)

        to = _resolve_to(params, item, ectx)
        subject = _resolve_subject(params, item, ectx)
        body = _resolve_outlook_body(params, item, ectx)
        body_content_type = _normalize_content_type(
            params.get("bodyContentType"), default="Text"
        )

        if not subject.strip():
            logger.info(
                "microsoftOutlook skipped: empty subject on node %r",
                node.name,
            )
            continue
        if not body.strip():
            logger.info(
                "microsoftOutlook skipped: empty body on node %r",
                node.name,
            )
            continue

        cc = (
            _coerce_recipients(evaluate(params.get("cc"), ectx))
            if params.get("cc") is not None
            else ""
        )
        bcc = (
            _coerce_recipients(evaluate(params.get("bcc"), ectx))
            if params.get("bcc") is not None
            else ""
        )

        envelope, source = _resolve_outlook_response(
            to=to,
            subject=subject,
            body=body,
            params=params,
            item=item,
            ctx=ctx,
        )

        payload: dict[str, Any] = {
            "messageId": envelope.get("id"),
            "internetMessageId": envelope.get("internetMessageId"),
            "to": to,
            "subject": envelope.get("subject", subject),
            "body": body,
            "bodyContentType": body_content_type,
            "sentDateTime": envelope.get("sentDateTime") or _now_iso_z(),
            "ok": True,
            "source": "microsoftOutlook",
        }
        if cc:
            payload["cc"] = cc
        if bcc:
            payload["bcc"] = bcc
        if source != "outlook_response":
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "microsoftOutlook send to=%s subject=%s source=%s",
            to[:80],
            subject[:80],
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_microsoft_teams",
    "exec_microsoft_outlook",
    "MICROSOFT_TEAMS_CONTENT_TYPES",
    "MICROSOFT_OUTLOOK_BODY_CONTENT_TYPES",
]
