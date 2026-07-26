"""Facebook Graph API executor (clean-room ``n8n-nodes-base.facebookGraphApi``).

v1 covers the operations most commonly used in n8n templates:

- ``facebookGraphApi`` — make Graph API calls (GET/POST/DELETE) to
  Facebook/Meta endpoints. Emits one item per input with
  ``{operation, node, version, <response fields>, source: 'facebookGraphApi'}``.

All API calls are mock-driven — no real network I/O is performed.

Parameters honored by ``facebookGraphApi``:

- ``operation``   (one of ``get`` / ``post`` / ``delete``; default ``get``)
- ``node``        (the Graph API node/path, e.g. ``me``, ``me/feed``,
  ``{page-id}/posts``; ``$json.node`` / ``$json.path`` fallback)
- ``fields``      (list of field names; optional, for GET)
- ``parameters``  (dict of query/body params; ``$json.parameters``
  fallback; default ``{}``)
- ``version``     (API version; default ``v18.0``)

Behavior precedence:

1. ``ctx.mocks['facebook_response']`` — when present, the value drives
   the executor. A callable is invoked as
   ``mock(operation, node, params, item, ctx)`` and may return a dict
   (used as the response) or any other value (falls back to offline
   synthesis, tagged ``facebook_response``). A non-callable dict is used
   directly as the response.
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response.
3. Offline synthetic response.

Items with an empty resolved ``node`` are skipped (no item emitted).
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


FACEBOOK_OPERATIONS: tuple[str, ...] = ("get", "post", "delete")
FACEBOOK_DEFAULT_OPERATION: str = "get"
FACEBOOK_DEFAULT_VERSION: str = "v18.0"


# ── Helpers ───────────────────────────────────────────────────────────


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
        for key in ("value", "name", "id", "path"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_coerce_str(v).strip() for v in value if _coerce_str(v).strip()]
    s = _coerce_str(value).strip()
    if not s:
        return []
    return [part.strip() for part in s.split(",") if part.strip()]


def _resolve_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> Any:
    """Return ``params[key]`` (evaluated) or the first present ``$json`` fallback."""
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
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    return _coerce_str(value)


def _resolve_list_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> list[str]:
    raw = params.get(key)
    if raw is not None:
        resolved = evaluate(raw, ectx)
    else:
        resolved = None
        for fk in json_fallbacks:
            if fk in item.json:
                resolved = item.json[fk]
                break
    return _coerce_str_list(resolved)


def _resolve_dict_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> dict[str, Any]:
    raw = params.get(key)
    if raw is not None:
        resolved = evaluate(raw, ectx)
    else:
        resolved = None
        for fk in json_fallbacks:
            if fk in item.json:
                resolved = item.json[fk]
                break
    if isinstance(resolved, dict):
        return resolved
    return {}


# ── Offline synthesis ─────────────────────────────────────────────────


def _synthesize_get(graph_node: str, version: str) -> dict[str, Any]:
    return {
        "id": "mock_fb_id",
        "name": "Mock Facebook Object",
        "data": [],
        "paging": {
            "cursors": {"before": "mock_before", "after": "mock_after"}
        },
        "version": version,
        "node": graph_node,
    }


def _synthesize_post(graph_node: str, version: str) -> dict[str, Any]:
    return {
        "id": f"mock_post_{uuid.uuid4().hex[:16]}",
        "success": True,
        "node": graph_node,
        "version": version,
    }


def _synthesize_delete(graph_node: str, version: str) -> dict[str, Any]:
    return {
        "success": True,
        "node": graph_node,
        "version": version,
    }


def _synthesize_offline(
    operation: str,
    *,
    graph_node: str,
    version: str,
) -> dict[str, Any]:
    if operation == "get":
        return _synthesize_get(graph_node, version)
    if operation == "post":
        return _synthesize_post(graph_node, version)
    return _synthesize_delete(graph_node, version)


# ── Mock resolution ───────────────────────────────────────────────────


def _resolve_facebook_response(
    *,
    operation: str,
    graph_node: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    synth: Any,
) -> tuple[dict[str, Any], str]:
    """Return ``(response, source)`` for the current call.

    ``source`` is one of ``"facebook_response"``, ``"http_response"``,
    ``"offline"``.
    """
    mocks = ctx.mocks or {}
    fmock = mocks.get("facebook_response")
    if fmock is not None:
        if callable(fmock):
            raw = fmock(operation, graph_node, params, item, ctx)
        else:
            raw = fmock
        if isinstance(raw, dict):
            return raw, "facebook_response"
        return synth(), "facebook_response"

    hmock = mocks.get("http_response")
    if hmock is not None and isinstance(hmock, dict):
        body = hmock.get("body")
        if isinstance(body, dict):
            return body, "http_response"

    return synth(), "offline"


# ── Action executor ───────────────────────────────────────────────────


async def exec_facebook_graph_api(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Facebook Graph API node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(params.get("operation") or FACEBOOK_DEFAULT_OPERATION)
    if operation not in FACEBOOK_OPERATIONS:
        raise ValueError(
            f"facebookGraphApi: unsupported operation {operation!r}; "
            f"expected one of {FACEBOOK_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        graph_node = _resolve_str_param(
            params, "node", item, ectx, ("node", "path")
        )

        # Version
        version_raw = params.get("version")
        if version_raw is not None:
            version = _coerce_str(evaluate(version_raw, ectx))
        else:
            version = FACEBOOK_DEFAULT_VERSION
        if not version:
            version = FACEBOOK_DEFAULT_VERSION

        # Fields (list; optional; for GET)
        fields = _resolve_list_param(
            params, "fields", item, ectx, ("fields",)
        )

        # Call parameters (dict of query/body params)
        call_params = _resolve_dict_param(
            params, "parameters", item, ectx, ("parameters",)
        )

        # Empty node → no item
        if not graph_node:
            logger.info(
                "facebookGraphApi %s skipped: empty node on node %r",
                operation,
                node.name,
            )
            continue

        def _synth() -> dict[str, Any]:
            return _synthesize_offline(
                operation,
                graph_node=graph_node,
                version=version,
            )

        response, source = _resolve_facebook_response(
            operation=operation,
            graph_node=graph_node,
            params=call_params,
            item=item,
            ctx=ctx,
            synth=_synth,
        )

        payload: dict[str, Any] = {
            "operation": operation,
            "node": graph_node,
            "version": version,
            **response,
            "source": "facebookGraphApi",
        }
        if source != "facebook_response":
            payload["mockSource"] = source

        # Echo fields for GET when provided
        if operation == "get" and fields:
            payload["fields"] = fields

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)

        logger.info(
            "facebookGraphApi %s node=%s version=%s source=%s",
            operation,
            graph_node,
            version,
            source,
        )

    return [(0, out)]


__all__ = [
    "exec_facebook_graph_api",
    "FACEBOOK_OPERATIONS",
    "FACEBOOK_DEFAULT_OPERATION",
    "FACEBOOK_DEFAULT_VERSION",
]