"""Microsoft extra executors (clean-room ``n8n-nodes-base.*``).

Implements:

- ``microsoftExcel``        — read/append/update/delete Excel rows
- ``microsoftOneDrive``     — OneDrive file operations
- ``microsoftSharePoint``   — SharePoint file/list operations
- ``microsoftSql``          — MS SQL query execute (TDS; mock-only)
- ``microsoftEntra``        — Azure AD user/group operations
- ``microsoftToDo``         — To Do task operations

All services except ``microsoftSql`` call the Microsoft Graph API
(``https://graph.microsoft.com/v1.0``) when a ``microsoftOutlookOAuth2Api``
credential resolves (``accessToken`` key, sent as
``Authorization: Bearer {accessToken}``). ``microsoftSql`` uses the TDS
protocol and remains mock-only.

Behavior precedence:

1. ``ctx.mocks['<node>_response']`` — callable or dict. A callable is
   invoked as ``mock(operation, params, item, ctx)``.
2. ``ctx.mocks['http_response']`` — generic fallback.
3. Real Microsoft Graph API call when a credential resolves (except
   ``microsoftSql``); on exception, logs a warning and falls through.
4. Offline synthetic response (``source: '<node>'``,
   ``mockSource: 'offline'``).
"""

from __future__ import annotations

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

MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MS_CRED_TYPE = "microsoftOutlookOAuth2Api"


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


def _graph_token(cred: dict[str, Any]) -> str:
    return str(cred.get("accessToken") or cred.get("access_token") or cred.get("token") or "")


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


# ── Microsoft Excel ──────────────────────────────────────────────────


MSEXCEL_OPERATIONS: tuple[str, ...] = ("read", "append", "update", "delete")
MSEXCEL_DEFAULT_OPERATION: str = "read"


def _build_excel_request(
    cred: dict[str, Any],
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> HttpRequestConfig | None:
    """Build a Microsoft Graph request for Excel table-row operations."""
    if not _graph_token(cred):
        return None
    file_id = _resolve_param("fileId", params, item, ctx)
    table_name = _resolve_param("tableName", params, item, ctx)
    if not file_id or not table_name:
        return None
    base = f"{MS_GRAPH_BASE}/me/drive/items/{file_id}/workbook/tables/{table_name}/rows"
    common = {"auth": "bearer", "auth_credential": cred, "response_mode": "json", "timeout": 30.0}
    if operation == "read":
        return HttpRequestConfig(url=base, method="GET", **common)
    if operation == "append":
        values = params.get("values")
        if values is None:
            values = params.get("rows")
        body: dict[str, Any] = {"values": values} if values is not None else {}
        return HttpRequestConfig(url=base, method="POST", body=body, body_mode="json", **common)
    if operation in ("update", "delete"):
        row_index = _resolve_param("rowIndex", params, item, ctx)
        if not row_index:
            return None
        url = f"{base}/{row_index}"
        if operation == "delete":
            return HttpRequestConfig(url=url, method="DELETE", **common)
        values = params.get("values")
        if values is None:
            values = params.get("row")
        body = {"values": values} if values is not None else {}
        return HttpRequestConfig(url=url, method="PATCH", body=body, body_mode="json", **common)
    return None


def _envelope_from_excel_api(
    data: Any,
    operation: str,
    file_id: str,
) -> dict[str, Any]:
    """Convert a Microsoft Graph Excel response to the internal envelope."""
    if operation == "read":
        rows = data.get("value") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            rows = data if isinstance(data, list) else []
        return {
            "rows": rows,
            "operation": operation,
            "fileId": file_id,
            "source": "microsoft_excel_api",
            "readAt": _now_iso(),
        }
    return {
        "operation": operation,
        "fileId": file_id,
        "affectedRows": 1,
        "source": "microsoft_excel_api",
        "updatedAt": _now_iso(),
    }


async def exec_microsoft_excel(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Microsoft Excel — read/append/update/delete Excel spreadsheet rows."""
    params = node.parameters or {}
    operation = params.get("operation", MSEXCEL_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("microsoft_excel_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        file_id = _resolve_param("fileId", params, item, ctx)
        cred = resolve_credential(node, ctx, MS_CRED_TYPE)
        if cred:
            cfg = _build_excel_request(cred, operation, params, item, ctx)
            if cfg is not None:
                logger.info("microsoft_excel real HTTP call op=%s fileId=%s", operation, file_id)
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if resp.status_code < 400:
                        out.append(
                            ExecutionItem(
                                json=_envelope_from_excel_api(resp.body, operation, file_id)
                            )
                        )
                        continue
                except Exception as exc:
                    logger.warning("microsoft_excel HTTP call failed: %s", exc)
        if operation == "read":
            rows = [{"row": i, "col1": f"val-{i}", "col2": i * 10} for i in range(3)]
            out.append(
                ExecutionItem(
                    json={
                        "rows": rows,
                        "operation": operation,
                        "fileId": file_id,
                        "source": "microsoft_excel",
                        "mockSource": "offline",
                        "readAt": _now_iso(),
                    }
                )
            )
        else:
            out.append(
                ExecutionItem(
                    json={
                        "operation": operation,
                        "fileId": file_id,
                        "affectedRows": 1,
                        "source": "microsoft_excel",
                        "mockSource": "offline",
                        "updatedAt": _now_iso(),
                    }
                )
            )
    return [(0, out)]


# ── Microsoft OneDrive ───────────────────────────────────────────────


MSONEDRIVE_OPERATIONS: tuple[str, ...] = (
    "download",
    "upload",
    "list",
    "delete",
    "rename",
    "createFolder",
)
MSONEDRIVE_DEFAULT_OPERATION: str = "download"


def _build_onedrive_request(
    cred: dict[str, Any],
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> HttpRequestConfig | None:
    """Build a Microsoft Graph request for OneDrive file operations."""
    if not _graph_token(cred):
        return None
    common = {"auth": "bearer", "auth_credential": cred, "response_mode": "json", "timeout": 30.0}
    if operation == "download":
        file_id = _resolve_param("fileId", params, item, ctx)
        if not file_id:
            return None
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/me/drive/items/{file_id}/content",
            method="GET",
            auth="bearer",
            auth_credential=cred,
            response_mode="binary",
            timeout=30.0,
        )
    if operation == "upload":
        file_name = _resolve_param("fileName", params, item, ctx)
        if not file_name:
            return None
        content = params.get("content")
        if content is None:
            content = params.get("body") or ""
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/me/drive/root:/{file_name}:/content",
            method="PUT",
            body=content,
            body_mode="raw",
            **common,
        )
    if operation == "list":
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/me/drive/root/children", method="GET", **common
        )
    if operation == "delete":
        file_id = _resolve_param("fileId", params, item, ctx)
        if not file_id:
            return None
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/me/drive/items/{file_id}", method="DELETE", **common
        )
    if operation == "rename":
        file_id = _resolve_param("fileId", params, item, ctx)
        if not file_id:
            return None
        new_name = _resolve_param("name", params, item, ctx) or _resolve_param(
            "newName", params, item, ctx
        )
        body: dict[str, Any] = {"name": new_name} if new_name else {}
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/me/drive/items/{file_id}",
            method="PATCH",
            body=body,
            body_mode="json",
            **common,
        )
    if operation == "createFolder":
        name = _resolve_param("name", params, item, ctx)
        if not name:
            return None
        parent_id = _resolve_param("parentId", params, item, ctx)
        base = (
            f"{MS_GRAPH_BASE}/me/drive/items/{parent_id}/children"
            if parent_id
            else f"{MS_GRAPH_BASE}/me/drive/children"
        )
        body = {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}
        return HttpRequestConfig(url=base, method="POST", body=body, body_mode="json", **common)
    return None


def _envelope_from_onedrive_api(
    data: Any,
    operation: str,
    file_name: str,
) -> dict[str, Any]:
    """Convert a Microsoft Graph OneDrive response to the internal envelope."""
    if operation == "list":
        items = data.get("value") if isinstance(data, dict) else None
        if not isinstance(items, list):
            items = []
        return {
            "items": items,
            "operation": operation,
            "source": "microsoft_onedrive_api",
            "updatedAt": _now_iso(),
        }
    name = data.get("name") if isinstance(data, dict) else None
    return {
        "fileName": name or file_name,
        "operation": operation,
        "source": "microsoft_onedrive_api",
        "updatedAt": _now_iso(),
    }


async def exec_microsoft_onedrive(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Microsoft OneDrive — file operations."""
    params = node.parameters or {}
    operation = params.get("operation", MSONEDRIVE_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("microsoft_onedrive_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        file_name = _resolve_param("fileName", params, item, ctx)
        cred = resolve_credential(node, ctx, MS_CRED_TYPE)
        if cred:
            cfg = _build_onedrive_request(cred, operation, params, item, ctx)
            if cfg is not None:
                logger.info("microsoft_onedrive real HTTP call op=%s", operation)
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if resp.status_code < 400:
                        out.append(
                            ExecutionItem(
                                json=_envelope_from_onedrive_api(resp.body, operation, file_name)
                            )
                        )
                        continue
                except Exception as exc:
                    logger.warning("microsoft_onedrive HTTP call failed: %s", exc)
        out.append(
            ExecutionItem(
                json={
                    "fileName": file_name,
                    "fileSize": 1024,
                    "operation": operation,
                    "source": "microsoft_onedrive",
                    "mockSource": "offline",
                    "updatedAt": _now_iso(),
                }
            )
        )
    return [(0, out)]


# ── Microsoft SharePoint ─────────────────────────────────────────────


MSSHAREPOINT_OPERATIONS: tuple[str, ...] = (
    "download",
    "upload",
    "list",
    "createListItem",
    "updateListItem",
    "deleteListItem",
)
MSSHAREPOINT_DEFAULT_OPERATION: str = "download"


def _build_sharepoint_request(
    cred: dict[str, Any],
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> HttpRequestConfig | None:
    """Build a Microsoft Graph request for SharePoint operations."""
    if not _graph_token(cred):
        return None
    site_id = _resolve_param("siteId", params, item, ctx)
    if not site_id:
        return None
    common = {"auth": "bearer", "auth_credential": cred, "response_mode": "json", "timeout": 30.0}
    if operation == "download":
        item_id = _resolve_param("itemId", params, item, ctx)
        if not item_id:
            return None
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/sites/{site_id}/drive/items/{item_id}/content",
            method="GET",
            auth="bearer",
            auth_credential=cred,
            response_mode="binary",
            timeout=30.0,
        )
    list_id = _resolve_param("listId", params, item, ctx)
    if not list_id:
        return None
    base = f"{MS_GRAPH_BASE}/sites/{site_id}/lists/{list_id}/items"
    if operation == "list":
        return HttpRequestConfig(url=base, method="GET", **common)
    if operation == "createListItem":
        fields = params.get("fields")
        if not isinstance(fields, dict):
            fields = params.get("values") or {}
        body: dict[str, Any] = {"fields": fields}
        return HttpRequestConfig(url=base, method="POST", body=body, body_mode="json", **common)
    item_id = _resolve_param("itemId", params, item, ctx)
    if not item_id:
        return None
    url = f"{base}/{item_id}"
    if operation == "updateListItem":
        fields = params.get("fields")
        if not isinstance(fields, dict):
            fields = params.get("values") or {}
        body = {"fields": fields}
        return HttpRequestConfig(url=url, method="PATCH", body=body, body_mode="json", **common)
    if operation == "deleteListItem":
        return HttpRequestConfig(url=url, method="DELETE", **common)
    return None


def _envelope_from_sharepoint_api(
    data: Any,
    operation: str,
    site_id: str,
    list_id: str,
) -> dict[str, Any]:
    """Convert a Microsoft Graph SharePoint response to the internal envelope."""
    if operation == "list":
        items = data.get("value") if isinstance(data, dict) else None
        if not isinstance(items, list):
            items = []
        return {
            "items": items,
            "siteId": site_id,
            "listId": list_id,
            "operation": operation,
            "source": "microsoft_sharepoint_api",
            "updatedAt": _now_iso(),
        }
    return {
        "siteId": site_id,
        "listId": list_id,
        "operation": operation,
        "source": "microsoft_sharepoint_api",
        "updatedAt": _now_iso(),
    }


async def exec_microsoft_sharepoint(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Microsoft SharePoint — file/list operations."""
    params = node.parameters or {}
    operation = params.get("operation", MSSHAREPOINT_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("microsoft_sharepoint_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        site_id = _resolve_param("siteId", params, item, ctx)
        list_id = _resolve_param("listId", params, item, ctx)
        cred = resolve_credential(node, ctx, MS_CRED_TYPE)
        if cred:
            cfg = _build_sharepoint_request(cred, operation, params, item, ctx)
            if cfg is not None:
                logger.info("microsoft_sharepoint real HTTP call op=%s", operation)
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if resp.status_code < 400:
                        out.append(
                            ExecutionItem(
                                json=_envelope_from_sharepoint_api(
                                    resp.body, operation, site_id, list_id
                                )
                            )
                        )
                        continue
                except Exception as exc:
                    logger.warning("microsoft_sharepoint HTTP call failed: %s", exc)
        out.append(
            ExecutionItem(
                json={
                    "siteId": site_id,
                    "listId": list_id,
                    "operation": operation,
                    "source": "microsoft_sharepoint",
                    "mockSource": "offline",
                    "updatedAt": _now_iso(),
                }
            )
        )
    return [(0, out)]


# ── Microsoft SQL ────────────────────────────────────────────────────


MSSQL_OPERATIONS: tuple[str, ...] = ("executeQuery", "insert", "update", "delete")
MSSQL_DEFAULT_OPERATION: str = "executeQuery"


async def exec_microsoft_sql(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Microsoft SQL — execute SQL queries (TDS; mock-only)."""
    params = node.parameters or {}
    operation = params.get("operation", MSSQL_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("microsoft_sql_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        if operation == "executeQuery":
            rows = [{"id": i, "name": f"row-{i}"} for i in range(3)]
            out.append(
                ExecutionItem(
                    json={
                        "rows": rows,
                        "affectedRows": len(rows),
                        "operation": operation,
                        "source": "microsoft_sql",
                        "executedAt": _now_iso(),
                    }
                )
            )
        else:
            out.append(
                ExecutionItem(
                    json={
                        "affectedRows": 1,
                        "operation": operation,
                        "source": "microsoft_sql",
                        "executedAt": _now_iso(),
                    }
                )
            )
    return [(0, out)]


# ── Microsoft Entra ──────────────────────────────────────────────────


MSENTRA_OPERATIONS: tuple[str, ...] = (
    "getUser",
    "listUsers",
    "createUser",
    "updateUser",
    "deleteUser",
    "getGroup",
    "listGroups",
)
MSENTRA_DEFAULT_OPERATION: str = "getUser"


def _build_entra_request(
    cred: dict[str, Any],
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> HttpRequestConfig | None:
    """Build a Microsoft Graph request for Entra (Azure AD) operations."""
    if not _graph_token(cred):
        return None
    common = {"auth": "bearer", "auth_credential": cred, "response_mode": "json", "timeout": 30.0}
    if operation == "listUsers":
        return HttpRequestConfig(url=f"{MS_GRAPH_BASE}/users", method="GET", **common)
    if operation == "listGroups":
        return HttpRequestConfig(url=f"{MS_GRAPH_BASE}/groups", method="GET", **common)
    if operation == "createUser":
        body = params.get("user")
        if not isinstance(body, dict):
            body = params.get("fields") or params.get("body") or {}
        if not isinstance(body, dict):
            body = {}
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/users", method="POST", body=body, body_mode="json", **common
        )
    if operation in ("getUser", "updateUser", "deleteUser"):
        user_id = _resolve_param("userId", params, item, ctx)
        if not user_id:
            return None
        url = f"{MS_GRAPH_BASE}/users/{user_id}"
        if operation == "getUser":
            return HttpRequestConfig(url=url, method="GET", **common)
        if operation == "deleteUser":
            return HttpRequestConfig(url=url, method="DELETE", **common)
        body = params.get("user")
        if not isinstance(body, dict):
            body = params.get("fields") or params.get("body") or {}
        if not isinstance(body, dict):
            body = {}
        return HttpRequestConfig(url=url, method="PATCH", body=body, body_mode="json", **common)
    if operation == "getGroup":
        group_id = _resolve_param("groupId", params, item, ctx)
        if not group_id:
            return None
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/groups/{group_id}", method="GET", **common
        )
    return None


def _envelope_from_entra_api(data: Any, operation: str) -> dict[str, Any]:
    """Convert a Microsoft Graph Entra response to the internal envelope."""
    if operation == "listUsers":
        users = data.get("value") if isinstance(data, dict) else None
        if not isinstance(users, list):
            users = []
        return {
            "users": users,
            "operation": operation,
            "source": "microsoft_entra_api",
            "queriedAt": _now_iso(),
        }
    if operation == "listGroups":
        groups = data.get("value") if isinstance(data, dict) else None
        if not isinstance(groups, list):
            groups = []
        return {
            "groups": groups,
            "operation": operation,
            "source": "microsoft_entra_api",
            "queriedAt": _now_iso(),
        }
    user_id = data.get("id") if isinstance(data, dict) else None
    display_name = data.get("displayName") if isinstance(data, dict) else None
    email = (data.get("mail") or data.get("userPrincipalName")) if isinstance(data, dict) else None
    return {
        "id": user_id or "",
        "displayName": display_name or "",
        "email": email or "",
        "operation": operation,
        "source": "microsoft_entra_api",
        "updatedAt": _now_iso(),
    }


async def exec_microsoft_entra(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Microsoft Entra — Azure AD user/group operations."""
    params = node.parameters or {}
    operation = params.get("operation", MSENTRA_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("microsoft_entra_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        user_id = _resolve_param("userId", params, item, ctx)
        cred = resolve_credential(node, ctx, MS_CRED_TYPE)
        if cred:
            cfg = _build_entra_request(cred, operation, params, item, ctx)
            if cfg is not None:
                logger.info("microsoft_entra real HTTP call op=%s", operation)
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if resp.status_code < 400:
                        out.append(
                            ExecutionItem(json=_envelope_from_entra_api(resp.body, operation))
                        )
                        continue
                except Exception as exc:
                    logger.warning("microsoft_entra HTTP call failed: %s", exc)
        if operation == "listUsers":
            users = [
                {"id": f"user-{i}", "displayName": f"User {i}", "email": f"user{i}@example.com"}
                for i in range(3)
            ]
            out.append(
                ExecutionItem(
                    json={
                        "users": users,
                        "operation": operation,
                        "source": "microsoft_entra",
                        "mockSource": "offline",
                        "queriedAt": _now_iso(),
                    }
                )
            )
        elif operation == "listGroups":
            groups = [
                {"id": f"group-{i}", "displayName": f"Group {i}"}
                for i in range(3)
            ]
            out.append(
                ExecutionItem(
                    json={
                        "groups": groups,
                        "operation": operation,
                        "source": "microsoft_entra",
                        "mockSource": "offline",
                        "queriedAt": _now_iso(),
                    }
                )
            )
        else:
            out.append(
                ExecutionItem(
                    json={
                        "id": user_id or "user-0",
                        "displayName": "Synthetic User",
                        "email": "user@example.com",
                        "operation": operation,
                        "source": "microsoft_entra",
                        "mockSource": "offline",
                        "updatedAt": _now_iso(),
                    }
                )
            )
    return [(0, out)]


# ── Microsoft To Do ──────────────────────────────────────────────────


MSTODO_OPERATIONS: tuple[str, ...] = (
    "createTask",
    "listTasks",
    "updateTask",
    "deleteTask",
    "createList",
    "listLists",
)
MSTODO_DEFAULT_OPERATION: str = "createTask"


def _build_todo_request(
    cred: dict[str, Any],
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> HttpRequestConfig | None:
    """Build a Microsoft Graph request for To Do operations."""
    if not _graph_token(cred):
        return None
    common = {"auth": "bearer", "auth_credential": cred, "response_mode": "json", "timeout": 30.0}
    if operation == "listLists":
        return HttpRequestConfig(url=f"{MS_GRAPH_BASE}/me/todo/lists", method="GET", **common)
    if operation == "createList":
        body = params.get("list")
        if isinstance(body, str):
            body = {"displayName": body}
        if not isinstance(body, dict):
            body = {}
        return HttpRequestConfig(
            url=f"{MS_GRAPH_BASE}/me/todo/lists",
            method="POST",
            body=body,
            body_mode="json",
            **common,
        )
    list_id = _resolve_param("listId", params, item, ctx)
    if not list_id:
        return None
    base = f"{MS_GRAPH_BASE}/me/todo/lists/{list_id}/tasks"
    if operation == "listTasks":
        return HttpRequestConfig(url=base, method="GET", **common)
    if operation == "createTask":
        body = params.get("task")
        if not isinstance(body, dict):
            body = params.get("fields") or {}
        if not isinstance(body, dict):
            body = {}
        title = _resolve_param("taskTitle", params, item, ctx)
        if title and "title" not in body:
            body = {"title": title, **body}
        return HttpRequestConfig(url=base, method="POST", body=body, body_mode="json", **common)
    task_id = _resolve_param("taskId", params, item, ctx)
    if not task_id:
        return None
    url = f"{base}/{task_id}"
    if operation == "updateTask":
        body = params.get("task")
        if not isinstance(body, dict):
            body = params.get("fields") or {}
        if not isinstance(body, dict):
            body = {}
        return HttpRequestConfig(url=url, method="PATCH", body=body, body_mode="json", **common)
    if operation == "deleteTask":
        return HttpRequestConfig(url=url, method="DELETE", **common)
    return None


def _envelope_from_todo_api(
    data: Any,
    operation: str,
    list_id: str,
    task_title: str,
) -> dict[str, Any]:
    """Convert a Microsoft Graph To Do response to the internal envelope."""
    if operation == "listTasks":
        tasks = data.get("value") if isinstance(data, dict) else None
        if not isinstance(tasks, list):
            tasks = []
        return {
            "tasks": tasks,
            "listId": list_id,
            "operation": operation,
            "source": "microsoft_todo_api",
            "updatedAt": _now_iso(),
        }
    if operation == "listLists":
        lists = data.get("value") if isinstance(data, dict) else None
        if not isinstance(lists, list):
            lists = []
        return {
            "lists": lists,
            "operation": operation,
            "source": "microsoft_todo_api",
            "updatedAt": _now_iso(),
        }
    task_id = data.get("id") if isinstance(data, dict) else None
    title = data.get("title") if isinstance(data, dict) else None
    return {
        "taskId": task_id or "",
        "taskTitle": title or task_title,
        "listId": list_id,
        "operation": operation,
        "source": "microsoft_todo_api",
        "updatedAt": _now_iso(),
    }


async def exec_microsoft_todo(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Microsoft To Do — task operations."""
    params = node.parameters or {}
    operation = params.get("operation", MSTODO_DEFAULT_OPERATION)
    out: list[ExecutionItem] = []

    for item in items:
        mock = _mock_response("microsoft_todo_response", operation, params, item, ctx)
        if mock is not None:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http is not None:
            out.append(ExecutionItem(json=http))
            continue
        task_title = _resolve_param("taskTitle", params, item, ctx)
        list_id = _resolve_param("listId", params, item, ctx, default="default-list")
        cred = resolve_credential(node, ctx, MS_CRED_TYPE)
        if cred:
            cfg = _build_todo_request(cred, operation, params, item, ctx)
            if cfg is not None:
                logger.info("microsoft_todo real HTTP call op=%s", operation)
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if resp.status_code < 400:
                        out.append(
                            ExecutionItem(
                                json=_envelope_from_todo_api(
                                    resp.body, operation, list_id, task_title
                                )
                            )
                        )
                        continue
                except Exception as exc:
                    logger.warning("microsoft_todo HTTP call failed: %s", exc)
        out.append(
            ExecutionItem(
                json={
                    "taskId": f"task-{abs(hash(task_title + _now_iso())) % 100000}",
                    "taskTitle": task_title,
                    "listId": list_id,
                    "operation": operation,
                    "source": "microsoft_todo",
                    "mockSource": "offline",
                    "updatedAt": _now_iso(),
                }
            )
        )
    return [(0, out)]