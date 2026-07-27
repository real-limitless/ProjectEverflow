"""Shared helper for credential-aware HTTP dispatch in integration nodes.

Provides a canonical precedence chain that all integration executors
should use:

1. ``ctx.mocks['<node>_response']`` — callable or dict (test/dry-run)
2. ``ctx.mocks['http_response']`` — generic HTTP mock fallback
3. ``ctx.mocks['http']`` — URL-keyed mock used by ``execute_http_request``
4. **If credentials resolve AND no mock** → real HTTP via
   :func:`execute_http_request`
5. Offline synthetic response (clearly tagged with ``source``)

This lets the same executor work in three modes:

- **Tests/dry-run**: inject ``ctx.mocks['<node>_response']``
- **Live with credentials**: attach credentials, no mock → real API call
- **Offline without credentials**: no mock, no creds → synthetic response
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from app.services.workflows.http_client import HttpRequestConfig, HttpResponse, execute_http_request
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


def resolve_credential(
    node: "ExecNode",
    ctx: "EngineContext",
    cred_type: str,
) -> dict[str, Any]:
    """Resolve a credential by type, with fallback to first attached."""
    cred = ctx.resolve_credential(node, cred_type) or {}
    if not cred and node.credentials:
        for v in node.credentials.values():
            if isinstance(v, dict):
                cred = v
                break
    return cred


def check_mock(
    ctx: "EngineContext",
    mock_key: str,
) -> Any:
    """Return the mock value for ``mock_key`` if present, else None."""
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    return mocks.get(mock_key)


def check_http_response_mock(
    ctx: "EngineContext",
) -> dict[str, Any] | None:
    """Return the ``http_response`` mock body if present."""
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    hr = mocks.get("http_response")
    if isinstance(hr, dict):
        body = hr.get("body")
        if isinstance(body, dict):
            return body
    return None


async def maybe_real_http(
    cfg: HttpRequestConfig,
    ctx: "EngineContext",
) -> dict[str, Any] | None:
    """Execute a real HTTP request if no mock intercepts it.

    Returns the parsed response body as a dict, or None if the request
    was intercepted by a mock (``ctx.mocks['http']``).
    """
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    if mocks.get("http") is not None:
        resp = await execute_http_request(cfg, ctx=ctx)
        if isinstance(resp.body, dict):
            return resp.body
        if isinstance(resp.body, str):
            import json
            try:
                return json.loads(resp.body)
            except Exception:
                return {"_raw": resp.body, "status_code": resp.status_code}
        return {"_raw": resp.body, "status_code": resp.status_code}
    if not cfg.url:
        return None
    try:
        resp = await execute_http_request(cfg, ctx=ctx)
        if isinstance(resp.body, dict):
            return resp.body
        if isinstance(resp.body, str):
            import json
            try:
                return json.loads(resp.body)
            except Exception:
                return {"_raw": resp.body, "status_code": resp.status_code}
        return {"_raw": resp.body, "status_code": resp.status_code}
    except Exception as exc:
        logger.warning("Real HTTP call to %s failed: %s", cfg.url, exc)
        return None


async def resolve_response(
    ctx: "EngineContext",
    mock_key: str,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    *,
    build_request: Callable[[dict[str, Any], dict[str, Any], ExecutionItem, "EngineContext"], HttpRequestConfig | None] | None = None,
    cred_type: str = "",
    offline: Callable[[str, dict[str, Any], ExecutionItem, "EngineContext"], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Canonical credential-aware response resolution.

    Precedence:
    1. ``ctx.mocks[mock_key]`` (callable or dict)
    2. ``ctx.mocks['http_response']`` (generic HTTP mock body)
    3. Real HTTP if ``build_request`` returns a config and credentials resolve
    4. Offline synthetic (calls ``offline`` or returns ``{source: mock_key}``)
    """
    mock_val = check_mock(ctx, mock_key)
    if mock_val is not None:
        if callable(mock_val):
            result = mock_val(operation, params, item, ctx)
            if isinstance(result, dict):
                return result
        elif isinstance(mock_val, dict):
            return mock_val

    http_mock = check_http_response_mock(ctx)
    if http_mock is not None:
        return http_mock

    if build_request is not None and cred_type:
        cred = resolve_credential(node, ctx, cred_type)
        if cred:
            cfg = build_request(cred, params, item, ctx)
            if cfg is not None:
                result = await maybe_real_http(cfg, ctx)
                if result is not None:
                    return result

    if offline is not None:
        return offline(operation, params, item, ctx)

    return {"source": mock_key.replace("_response", ""), "operation": operation}