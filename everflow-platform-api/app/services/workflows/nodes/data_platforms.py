"""Data platform executors (clean-room ``n8n-nodes-base.*``).

Implements Baserow, NocoDB, Dropbox, Nextcloud.
All mock-driven — no real network I/O.
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


def _ectx(item, ctx):
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)

def _coerce_str(value):
    if value is None: return ""
    if isinstance(value, str): return value
    if isinstance(value, (int, float, bool)): return str(value)
    if isinstance(value, (list, tuple)): return ", ".join(_coerce_str(v) for v in value if v is not None)
    return str(value)

def _resolve_param(key, params, item, ctx, *, default=""):
    raw = params.get(key)
    if raw is None: return default
    return _coerce_str(evaluate(raw, _ectx(item, ctx)))

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _gen_id(*parts):
    return str(abs(hash("".join(parts) + _now_iso())) % 100000)

def _mock_response(mock_key, operation, params, item, ctx):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is None: return None
    if callable(mock):
        result = mock(operation, params, item, ctx)
        return result if isinstance(result, dict) else None
    return mock if isinstance(mock, dict) else None

def _http_response(ctx):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    hr = mocks.get("http_response")
    if isinstance(hr, dict):
        body = hr.get("body")
        if isinstance(body, dict): return body
    return None


BASEROW_OPERATIONS = ("create", "get", "update", "delete", "list")
BASEROW_DEFAULT_OPERATION = "create"

async def exec_baserow(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", BASEROW_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("baserow_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={"rowId": _gen_id("baserow", name), "name": name, "operation": operation, "source": "baserow", "updatedAt": _now_iso()}))
    return [(0, out)]


NOCODB_OPERATIONS = ("create", "get", "update", "delete", "list")
NOCODB_DEFAULT_OPERATION = "create"

async def exec_nocodb(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", NOCODB_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("nocodb_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={"rowId": _gen_id("nocodb", name), "name": name, "operation": operation, "source": "nocodb", "updatedAt": _now_iso()}))
    return [(0, out)]


DROPBOX_OPERATIONS = ("download", "upload", "list", "delete", "createFolder", "move")
DROPBOX_DEFAULT_OPERATION = "download"

async def exec_dropbox(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", DROPBOX_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("dropbox_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        path = _resolve_param("path", params, item, ctx)
        out.append(ExecutionItem(json={"path": path, "fileSize": 1024, "operation": operation, "source": "dropbox", "updatedAt": _now_iso()}))
    return [(0, out)]


NEXTCLOUD_OPERATIONS = ("download", "upload", "list", "delete", "createFolder", "share")
NEXTCLOUD_DEFAULT_OPERATION = "download"

async def exec_nextcloud(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", NEXTCLOUD_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("nextcloud_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        path = _resolve_param("path", params, item, ctx)
        out.append(ExecutionItem(json={"path": path, "fileSize": 2048, "operation": operation, "source": "nextcloud", "updatedAt": _now_iso()}))
    return [(0, out)]