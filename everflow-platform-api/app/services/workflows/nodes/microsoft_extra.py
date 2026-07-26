"""Microsoft extra executors (clean-room ``n8n-nodes-base.*``).

Implements:

- ``microsoftExcel``        — read/append/update/delete Excel rows
- ``microsoftOneDrive``     — OneDrive file operations
- ``microsoftSharePoint``   — SharePoint file/list operations
- ``microsoftSql``          — MS SQL query execute
- ``microsoftEntra``        — Azure AD user/group operations
- ``microsoftToDo``         — To Do task operations

All executors are mock-driven — no real network I/O is performed.

Behavior precedence:

1. ``ctx.mocks['<node>_response']`` — callable or dict. A callable is
   invoked as ``mock(operation, params, item, ctx)``.
2. ``ctx.mocks['http_response']`` — generic fallback.
3. Offline synthetic response.
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


# ── Microsoft Excel ──────────────────────────────────────────────────


MSEXCEL_OPERATIONS: tuple[str, ...] = ("read", "append", "update", "delete")
MSEXCEL_DEFAULT_OPERATION: str = "read"


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
        if operation == "read":
            rows = [{"row": i, "col1": f"val-{i}", "col2": i * 10} for i in range(3)]
            out.append(
                ExecutionItem(
                    json={
                        "rows": rows,
                        "operation": operation,
                        "fileId": file_id,
                        "source": "microsoft_excel",
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
        out.append(
            ExecutionItem(
                json={
                    "fileName": file_name,
                    "fileSize": 1024,
                    "operation": operation,
                    "source": "microsoft_onedrive",
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
        out.append(
            ExecutionItem(
                json={
                    "siteId": site_id,
                    "listId": list_id,
                    "operation": operation,
                    "source": "microsoft_sharepoint",
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
    """Microsoft SQL — execute SQL queries."""
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
                        "queriedAt": _now_iso(),
                    }
                )
            )
        else:
            user_id = _resolve_param("userId", params, item, ctx)
            out.append(
                ExecutionItem(
                    json={
                        "id": user_id or "user-0",
                        "displayName": "Synthetic User",
                        "email": "user@example.com",
                        "operation": operation,
                        "source": "microsoft_entra",
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
        out.append(
            ExecutionItem(
                json={
                    "taskId": f"task-{abs(hash(task_title + _now_iso())) % 100000}",
                    "taskTitle": task_title,
                    "listId": list_id,
                    "operation": operation,
                    "source": "microsoft_todo",
                    "updatedAt": _now_iso(),
                }
            )
        )
    return [(0, out)]