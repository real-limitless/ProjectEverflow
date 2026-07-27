"""Data platform executors (clean-room ``n8n-nodes-base.*``).

Implements Baserow, NocoDB, Dropbox, Nextcloud.

When the appropriate credential (``baserowApi``, ``nocodbApi``, ``dropboxApi``,
``nextcloudApi``) is attached and no mock is present, real calls are made to
the respective API via :func:`execute_http_request`. Otherwise the executor is
mock-driven with an offline synthetic fallback.
"""

from __future__ import annotations

import json
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


# ── Baserow ─────────────────────────────────────────────────────────────

BASEROW_OPERATIONS = ("create", "get", "update", "delete", "list")
BASEROW_DEFAULT_OPERATION = "create"


def _build_baserow_request(cred, operation, params, item, ctx):
    """Build a real Baserow API request. Returns ``None`` when auth or
    required parameters are missing."""
    base_url = str(cred.get("baseUrl") or "").rstrip("/")
    api_key = str(cred.get("apiKey") or "")
    if not base_url or not api_key:
        return None
    table_id = _resolve_param("tableId", params, item, ctx)
    if not table_id:
        return None
    headers = {"Authorization": f"Token {api_key}"}
    url = f"{base_url}/api/database/rows/table/{table_id}/"
    if operation == "create":
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=item.json, body_mode="json", response_mode="json", timeout=30.0)
    if operation == "list":
        return HttpRequestConfig(url=url, method="GET", headers=headers, response_mode="json", timeout=30.0)
    if operation in ("get", "update", "delete"):
        row_id = _resolve_param("rowId", params, item, ctx)
        if not row_id:
            return None
        row_url = f"{url}{row_id}/"
        if operation == "get":
            return HttpRequestConfig(url=row_url, method="GET", headers=headers, response_mode="json", timeout=30.0)
        if operation == "update":
            return HttpRequestConfig(url=row_url, method="PATCH", headers=headers, body=item.json, body_mode="json", response_mode="json", timeout=30.0)
        if operation == "delete":
            return HttpRequestConfig(url=row_url, method="DELETE", headers=headers, response_mode="json", timeout=30.0)
    return None


def _envelope_from_baserow_api(data, operation, params, item, ctx):
    name = _resolve_param("name", params, item, ctx)
    return {
        "rowId": data.get("id") or _gen_id("baserow", name),
        "name": name,
        "operation": operation,
        "source": "baserow_api",
        "updatedAt": _now_iso(),
        "raw": data,
    }


async def exec_baserow(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", BASEROW_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("baserow_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "baserowApi")
        if cred:
            cfg = _build_baserow_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_baserow_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("baserow HTTP call failed: %s", exc)
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={"rowId": _gen_id("baserow", name), "name": name, "operation": operation, "source": "baserow", "updatedAt": _now_iso()}))
    return [(0, out)]


# ── NocoDB ──────────────────────────────────────────────────────────────

NOCODB_OPERATIONS = ("create", "get", "update", "delete", "list")
NOCODB_DEFAULT_OPERATION = "create"


def _build_nocodb_request(cred, operation, params, item, ctx):
    """Build a real NocoDB API request. Returns ``None`` when auth or
    required parameters are missing."""
    base_url = str(cred.get("baseUrl") or "").rstrip("/")
    api_key = str(cred.get("apiKey") or "")
    if not base_url or not api_key:
        return None
    table_id = _resolve_param("tableId", params, item, ctx)
    if not table_id:
        return None
    headers = {"xc-token": api_key}
    url = f"{base_url}/api/v2/tables/{table_id}/records"
    if operation == "create":
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=item.json, body_mode="json", response_mode="json", timeout=30.0)
    if operation == "list":
        return HttpRequestConfig(url=url, method="GET", headers=headers, response_mode="json", timeout=30.0)
    if operation in ("get", "update", "delete"):
        row_id = _resolve_param("rowId", params, item, ctx)
        if not row_id:
            return None
        row_url = f"{url}/{row_id}"
        if operation == "get":
            return HttpRequestConfig(url=row_url, method="GET", headers=headers, response_mode="json", timeout=30.0)
        if operation == "update":
            return HttpRequestConfig(url=row_url, method="PATCH", headers=headers, body=item.json, body_mode="json", response_mode="json", timeout=30.0)
        if operation == "delete":
            return HttpRequestConfig(url=row_url, method="DELETE", headers=headers, response_mode="json", timeout=30.0)
    return None


def _envelope_from_nocodb_api(data, operation, params, item, ctx):
    name = _resolve_param("name", params, item, ctx)
    return {
        "rowId": data.get("Id") or data.get("id") or _gen_id("nocodb", name),
        "name": name,
        "operation": operation,
        "source": "nocodb_api",
        "updatedAt": _now_iso(),
        "raw": data,
    }


async def exec_nocodb(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", NOCODB_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("nocodb_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "nocodbApi")
        if cred:
            cfg = _build_nocodb_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_nocodb_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("nocodb HTTP call failed: %s", exc)
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={"rowId": _gen_id("nocodb", name), "name": name, "operation": operation, "source": "nocodb", "updatedAt": _now_iso()}))
    return [(0, out)]


# ── Dropbox ─────────────────────────────────────────────────────────────

DROPBOX_OPERATIONS = ("download", "upload", "list", "delete", "createFolder", "move")
DROPBOX_DEFAULT_OPERATION = "download"


def _build_dropbox_request(cred, operation, params, item, ctx):
    """Build a real Dropbox API request. Returns ``None`` when auth or
    required parameters are missing."""
    access_token = str(cred.get("accessToken") or "")
    if not access_token:
        return None
    headers: dict[str, str] = {"Authorization": f"Bearer {access_token}"}
    path = _resolve_param("path", params, item, ctx)
    if operation == "list":
        url = "https://api.dropboxapi.com/2/files/list_folder"
        body: Any = {"path": path or ""}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="json", response_mode="json", timeout=30.0)
    if operation == "upload":
        url = "https://content.dropboxapi.com/2/files/upload"
        api_arg = json.dumps({"path": path, "mode": "overwrite", "autorename": False, "mute": False})
        headers["Dropbox-API-Arg"] = api_arg
        headers["Content-Type"] = "application/octet-stream"
        content = _resolve_param("content", params, item, ctx)
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=content, body_mode="raw", response_mode="json", timeout=30.0)
    if operation == "download":
        url = "https://content.dropboxapi.com/2/files/download"
        headers["Dropbox-API-Arg"] = json.dumps({"path": path})
        return HttpRequestConfig(url=url, method="POST", headers=headers, response_mode="json", timeout=30.0)
    if operation == "delete":
        url = "https://api.dropboxapi.com/2/files/delete_v2"
        body = {"path": path}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="json", response_mode="json", timeout=30.0)
    if operation == "createFolder":
        url = "https://api.dropboxapi.com/2/files/create_folder_v2"
        body = {"path": path}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="json", response_mode="json", timeout=30.0)
    if operation == "move":
        new_path = _resolve_param("newPath", params, item, ctx) or _resolve_param("toPath", params, item, ctx)
        url = "https://api.dropboxapi.com/2/files/move_v2"
        body = {"from_path": path, "to_path": new_path}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="json", response_mode="json", timeout=30.0)
    return None


def _envelope_from_dropbox_api(data, operation, params, item, ctx):
    path = _resolve_param("path", params, item, ctx)
    return {
        "path": path,
        "operation": operation,
        "source": "dropbox_api",
        "updatedAt": _now_iso(),
        "raw": data,
    }


async def exec_dropbox(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", DROPBOX_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("dropbox_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "dropboxApi")
        if cred:
            cfg = _build_dropbox_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_dropbox_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("dropbox HTTP call failed: %s", exc)
        path = _resolve_param("path", params, item, ctx)
        out.append(ExecutionItem(json={"path": path, "fileSize": 1024, "operation": operation, "source": "dropbox", "updatedAt": _now_iso()}))
    return [(0, out)]


# ── Nextcloud ───────────────────────────────────────────────────────────

NEXTCLOUD_OPERATIONS = ("download", "upload", "list", "delete", "createFolder", "share")
NEXTCLOUD_DEFAULT_OPERATION = "download"


def _build_nextcloud_request(cred, operation, params, item, ctx):
    """Build a real Nextcloud WebDAV request. Returns ``None`` when auth or
    required parameters are missing."""
    base_url = str(cred.get("baseUrl") or "").rstrip("/")
    username = str(cred.get("username") or "")
    password = str(cred.get("password") or "")
    if not base_url or not username or not password:
        return None
    path = _resolve_param("path", params, item, ctx).lstrip("/")
    auth_cred = {"username": username, "password": password}
    dav_base = f"{base_url}/remote.php/dav/files/{username}"
    if operation == "download":
        return HttpRequestConfig(url=f"{dav_base}/{path}", method="GET", auth="basic", auth_credential=auth_cred, response_mode="json", timeout=30.0)
    if operation == "upload":
        content = _resolve_param("content", params, item, ctx)
        return HttpRequestConfig(url=f"{dav_base}/{path}", method="PUT", auth="basic", auth_credential=auth_cred, body=content, body_mode="raw", response_mode="json", timeout=30.0)
    if operation == "list":
        return HttpRequestConfig(url=f"{dav_base}/", method="PROPFIND", auth="basic", auth_credential=auth_cred, response_mode="json", timeout=30.0)
    if operation == "delete":
        return HttpRequestConfig(url=f"{dav_base}/{path}", method="DELETE", auth="basic", auth_credential=auth_cred, response_mode="json", timeout=30.0)
    if operation == "createFolder":
        return HttpRequestConfig(url=f"{dav_base}/{path}", method="MKCOL", auth="basic", auth_credential=auth_cred, response_mode="json", timeout=30.0)
    if operation == "share":
        share_url = f"{base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares"
        body: Any = {"path": "/" + path, "shareType": 3}
        return HttpRequestConfig(url=share_url, method="POST", auth="basic", auth_credential=auth_cred, body=body, body_mode="json", response_mode="json", timeout=30.0)
    return None


def _envelope_from_nextcloud_api(data, operation, params, item, ctx):
    path = _resolve_param("path", params, item, ctx)
    return {
        "path": path,
        "operation": operation,
        "source": "nextcloud_api",
        "updatedAt": _now_iso(),
        "raw": data,
    }


async def exec_nextcloud(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", NEXTCLOUD_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("nextcloud_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "nextcloudApi")
        if cred:
            cfg = _build_nextcloud_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_nextcloud_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("nextcloud HTTP call failed: %s", exc)
        path = _resolve_param("path", params, item, ctx)
        out.append(ExecutionItem(json={"path": path, "fileSize": 2048, "operation": operation, "source": "nextcloud", "updatedAt": _now_iso()}))
    return [(0, out)]