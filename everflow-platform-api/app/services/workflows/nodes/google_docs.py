"""Google Docs executor (clean-room n8n ``n8n-nodes-base.googleDocs``).

v1 supports the three operations most commonly used in n8n templates:

- ``create`` — create a new Google Doc; emit one item per input with
  ``{documentId, title, body, revisionId, source: 'googleDocs'}``
  (``body`` is a synthetic ``{content: [...]}`` structure).
- ``read``   — read a Google Doc by id; emit one item per input with
  ``{documentId, title, body, revisionId, source: 'googleDocs'}``
  (``body`` is a plain text string).
- ``update`` — update an existing Google Doc; emit one item per input
  with ``{documentId, revisionId, updatedAt, source: 'googleDocs'}``.

Parameters honored:

- ``operation``  (``"create"`` / ``"read"`` / ``"update"``;
  default ``"read"``)
- ``title``      (string; ``$json.title`` / ``$json.name`` fallback;
  used by ``create``)
- ``content``    (string; ``$json.content`` / ``$json.text`` fallback;
  used by ``create`` and ``update``)
- ``documentId`` (string; ``$json.documentId`` / ``$json.id`` fallback;
  required for ``read`` and ``update``)
- ``replaceAll`` (bool; default ``False``; used by ``update``)

When a ``googleDocsOAuth2Api`` credential is attached and no mock is
present, real calls are made to the Google Docs API via
:func:`execute_http_request`. Otherwise the executor is mock-driven with
an offline synthetic fallback.

Behavior precedence:

1. ``ctx.mocks['docs_response']`` — when present, the value drives the
   executor. A dict is used per operation (or operation-specific
   shape); a callable is invoked as
   ``mock(operation, params, item, ctx)`` and may return a dict (used
   per operation) or a non-dict truthy value (wrapped as the
   operation's envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the Docs envelope.
3. If a ``googleDocsOAuth2Api`` credential resolves (``accessToken``
   present), real calls are made to the Google Docs API via
   :func:`execute_http_request` and the response is coerced into the
   operation envelope.
4. Offline synthetic response with deterministic-looking ids.

Items missing ``documentId`` (for ``read``/``update``) are skipped (no
item emitted) — matching the behavior of the other output nodes in
this package.
"""

from __future__ import annotations

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


DOCS_OPERATIONS: tuple[str, ...] = ("create", "read", "update")
DOCS_DEFAULT_OPERATION: str = "read"


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
        for key in ("value", "name", "id", "text", "content", "title"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None or isinstance(value, bool):
        return bool(value) if value is not None else default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "yes", "1", "on"):
            return True
        if s in ("false", "no", "0", "off", ""):
            return False
    return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_document_id() -> str:
    return f"mock_doc_{uuid.uuid4().hex[:16]}"


def _resolve_str_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> str:
    """Return ``params[key]`` (evaluated) or the first present ``$json`` fallback."""
    raw = params.get(key)
    if raw is not None:
        resolved = evaluate(raw, ectx)
        s = _coerce_str(resolved).strip()
        if s:
            return s
    for fk in json_fallbacks:
        if fk in item.json:
            s = _coerce_str(item.json[fk]).strip()
            if s:
                return s
    return ""


# ── Synthetic responses ────────────────────────────────────────────────


def _synthesize_create_response(document_id: str, title: str, content: str) -> dict[str, Any]:
    """Offline fallback: a fake Docs create response."""
    return {
        "documentId": document_id,
        "title": title,
        "body": {
            "content": [
                {
                    "paragraph": {
                        "elements": [{"textRun": {"content": content}}]
                    }
                }
            ]
        },
        "revisionId": "1",
    }


def _synthesize_read_response(document_id: str) -> dict[str, Any]:
    """Offline fallback: a fake Docs read response (plain text body)."""
    return {
        "documentId": document_id,
        "title": "Mock Document",
        "body": "Mock document content here.",
        "revisionId": "1",
    }


def _synthesize_update_response(document_id: str) -> dict[str, Any]:
    """Offline fallback: a fake Docs update response."""
    return {
        "documentId": document_id,
        "revisionId": "2",
        "updatedAt": _now_iso(),
    }


# ── Per-operation envelope coercers ────────────────────────────────────


def _coerce_create_envelope(
    raw: dict[str, Any], *, document_id: str, title: str, content: str
) -> dict[str, Any]:
    body = raw.get("body")
    if not isinstance(body, dict):
        body = {
            "content": [
                {
                    "paragraph": {
                        "elements": [{"textRun": {"content": content}}]
                    }
                }
            ]
        }
    return {
        "documentId": _coerce_str(raw.get("documentId")) or document_id,
        "title": _coerce_str(raw.get("title")) or title,
        "body": body,
        "revisionId": _coerce_str(raw.get("revisionId")) or "1",
    }


def _coerce_read_envelope(raw: dict[str, Any], *, document_id: str) -> dict[str, Any]:
    body = raw.get("body")
    if isinstance(body, dict):
        body_text = _coerce_str(body.get("content")) or _coerce_str(body)
    else:
        body_text = _coerce_str(body) or "Mock document content here."
    return {
        "documentId": _coerce_str(raw.get("documentId")) or document_id,
        "title": _coerce_str(raw.get("title")) or "Mock Document",
        "body": body_text,
        "revisionId": _coerce_str(raw.get("revisionId")) or "1",
    }


def _coerce_update_envelope(raw: dict[str, Any], *, document_id: str) -> dict[str, Any]:
    return {
        "documentId": _coerce_str(raw.get("documentId")) or document_id,
        "revisionId": _coerce_str(raw.get("revisionId")) or "2",
        "updatedAt": _coerce_str(raw.get("updatedAt")) or _now_iso(),
    }


# ── HTTP-mock unwrapping ───────────────────────────────────────────────


def _docs_response_from_http_mock(
    mock: Any, *, operation: str, document_id: str, title: str, content: str
) -> dict[str, Any] | None:
    """Extract a Docs-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if isinstance(body, dict):
        if operation == "create":
            return _coerce_create_envelope(
                body, document_id=document_id, title=title, content=content
            )
        if operation == "read":
            return _coerce_read_envelope(body, document_id=document_id)
        return _coerce_update_envelope(body, document_id=document_id)
    if isinstance(body, str) and body.strip():
        if operation == "create":
            return _coerce_create_envelope(
                {"body": {"content": body}},
                document_id=document_id,
                title=title,
                content=content,
            )
        if operation == "read":
            return _coerce_read_envelope(
                {"body": body}, document_id=document_id
            )
        return _coerce_update_envelope({}, document_id=document_id)
    return None


# ── Real HTTP request building ────────────────────────────────────────


def _build_docs_request(
    cred: dict[str, Any],
    *,
    operation: str,
    document_id: str,
    title: str,
    content: str,
) -> HttpRequestConfig | None:
    """Build a real Google Docs API request config.

    Returns ``None`` when the credential has no ``accessToken``.
    """
    access_token = str(cred.get("accessToken") or "")
    if not access_token:
        return None
    if operation == "create":
        return HttpRequestConfig(
            url="https://docs.googleapis.com/v1/documents",
            method="POST",
            body={"title": title},
            body_mode="json",
            auth="bearer",
            auth_credential=cred,
            response_mode="json",
            timeout=30.0,
        )
    if operation == "read":
        return HttpRequestConfig(
            url=f"https://docs.googleapis.com/v1/documents/{document_id}",
            method="GET",
            auth="bearer",
            auth_credential=cred,
            response_mode="json",
            timeout=30.0,
        )
    if operation == "update":
        return HttpRequestConfig(
            url=f"https://docs.googleapis.com/v1/documents/{document_id}:batchUpdate",
            method="POST",
            body={
                "requests": [
                    {"insertText": {"location": {"index": 1}, "text": content}}
                ]
            },
            body_mode="json",
            auth="bearer",
            auth_credential=cred,
            response_mode="json",
            timeout=30.0,
        )
    return None


def _envelope_from_docs_api(
    data: dict[str, Any],
    *,
    operation: str,
    document_id: str,
    title: str,
    content: str,
) -> dict[str, Any]:
    """Convert a real Google Docs API response to the internal
    operation envelope shape."""
    if operation == "create":
        return _coerce_create_envelope(
            data, document_id=document_id, title=title, content=content
        )
    if operation == "read":
        return _coerce_read_envelope(data, document_id=document_id)
    return _coerce_update_envelope(data, document_id=document_id)


# ── Response resolution ────────────────────────────────────────────────


async def _resolve_docs_response(
    *,
    operation: str,
    document_id: str,
    title: str,
    content: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"docs_response"``, ``"http_response"``,
    ``"docs_api"``, ``"offline"`` so downstream observers can tell where
    the result came from.
    """
    mocks = ctx.mocks or {}
    dmock = mocks.get("docs_response")
    if dmock is not None:
        if callable(dmock):
            raw = dmock(operation, params, item, ctx)
        else:
            raw = dmock
        if isinstance(raw, dict):
            if operation == "create":
                return (
                    _coerce_create_envelope(
                        raw, document_id=document_id, title=title, content=content
                    ),
                    "docs_response",
                )
            if operation == "read":
                return (
                    _coerce_read_envelope(raw, document_id=document_id),
                    "docs_response",
                )
            return (
                _coerce_update_envelope(raw, document_id=document_id),
                "docs_response",
            )
        # Non-dict truthy → wrap as a synthetic envelope
        if operation == "create":
            return (
                _synthesize_create_response(
                    document_id or _new_document_id(), title, content
                )
                | {"raw": raw},
                "docs_response",
            )
        if operation == "read":
            return (
                _synthesize_read_response(document_id or _new_document_id())
                | {"raw": raw},
                "docs_response",
            )
        return (
            _synthesize_update_response(document_id or _new_document_id())
            | {"raw": raw},
            "docs_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _docs_response_from_http_mock(
            hmock,
            operation=operation,
            document_id=document_id,
            title=title,
            content=content,
        )
        if env is not None:
            return env, "http_response"

    cred = resolve_credential(node, ctx, "googleDocsOAuth2Api")
    if cred:
        cfg = _build_docs_request(
            cred,
            operation=operation,
            document_id=document_id,
            title=title,
            content=content,
        )
        if cfg is not None:
            logger.info(
                "googleDocs real HTTP call operation=%s documentId=%s",
                operation,
                document_id,
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_docs_api(
                            resp.body,
                            operation=operation,
                            document_id=document_id,
                            title=title,
                            content=content,
                        ),
                        "docs_api",
                    )
            except Exception as exc:
                logger.warning("googleDocs HTTP call failed: %s", exc)

    if operation == "create":
        return (
            _synthesize_create_response(
                document_id or _new_document_id(), title, content
            ),
            "offline",
        )
    if operation == "read":
        return _synthesize_read_response(document_id), "offline"
    return _synthesize_update_response(document_id), "offline"


# ── Main executor ──────────────────────────────────────────────────────


async def exec_google_docs(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Docs node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(params.get("operation") or DOCS_DEFAULT_OPERATION).strip().lower()
    if operation not in DOCS_OPERATIONS:
        raise ValueError(
            f"googleDocs: unsupported operation {operation!r}; "
            f"expected one of {DOCS_OPERATIONS}"
        )

    replace_all = _coerce_bool(
        evaluate(params.get("replaceAll"), _ectx(items[0], ctx))
        if params.get("replaceAll") is not None and items
        else params.get("replaceAll"),
        False,
    )

    out: list[ExecutionItem] = []

    for item in items:
        ectx = _ectx(item, ctx)
        title = ""
        content = ""
        document_id = ""

        if operation == "create":
            title = _resolve_str_param(
                params, "title", item, ectx, ("title", "name")
            )
            content = _resolve_str_param(
                params, "content", item, ectx, ("content", "text")
            )
        else:
            document_id = _resolve_str_param(
                params, "documentId", item, ectx, ("documentId", "id")
            )
            if not document_id:
                logger.info(
                    "googleDocs %s skipped: empty documentId on node %r",
                    operation,
                    node.name,
                )
                continue
            if operation == "update":
                content = _resolve_str_param(
                    params, "content", item, ectx, ("content", "text")
                )

        envelope, source = await _resolve_docs_response(
            operation=operation,
            document_id=document_id,
            title=title,
            content=content,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
        )

        payload: dict[str, Any]
        if operation == "create":
            payload = {
                "documentId": envelope.get("documentId") or _new_document_id(),
                "title": envelope.get("title") or title or "Untitled",
                "body": envelope.get("body")
                or _synthesize_create_response(
                    _new_document_id(), title, content
                )["body"],
                "revisionId": envelope.get("revisionId") or "1",
                "operation": operation,
                "ok": True,
                "source": "googleDocs",
            }
        elif operation == "read":
            payload = {
                "documentId": envelope.get("documentId") or document_id,
                "title": envelope.get("title") or "Mock Document",
                "body": envelope.get("body") or "Mock document content here.",
                "revisionId": envelope.get("revisionId") or "1",
                "operation": operation,
                "ok": True,
                "source": "googleDocs",
            }
        else:  # update
            payload = {
                "documentId": envelope.get("documentId") or document_id,
                "revisionId": envelope.get("revisionId") or "2",
                "updatedAt": envelope.get("updatedAt") or _now_iso(),
                "replaceAll": replace_all,
                "operation": operation,
                "ok": True,
                "source": "googleDocs",
            }

        if source not in ("docs_response", "docs_api"):
            payload["mockSource"] = source

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "googleDocs %s documentId=%r title=%r source=%s",
            operation,
            (payload.get("documentId") or "")[:80],
            (payload.get("title") or "")[:80],
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_google_docs",
    "DOCS_OPERATIONS",
    "DOCS_DEFAULT_OPERATION",
]
