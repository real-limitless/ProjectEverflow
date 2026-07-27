"""Project tracker executors (clean-room n8n-nodes-base.*).

Covers six project-tracker nodes:

- ``n8n-nodes-base.clickUp`` — ClickUp task operations
- ``n8n-nodes-base.trello`` — Trello card operations
- ``n8n-nodes-base.asana`` — Asana task operations
- ``n8n-nodes-base.mondayCom`` — Monday.com item operations
- ``n8n-nodes-base.todoist`` — Todoist task operations
- ``n8n-nodes-base.linear`` — Linear issue operations

Each executor honors ``parameters.operation`` (default ``create``) and
emits one item per input carrying the operation-specific fields and
``source: '<service>'``.

When a service credential is attached and no mock is present, real calls
are made to the service REST/GraphQL API via
:func:`execute_http_request`. Otherwise the executor is mock-driven with
an offline synthetic fallback.

Resolution precedence (per node):

1. ``ctx.mocks['<node>_response']`` — callable invoked as
   ``mock(operation, params, item, ctx)`` or dict used directly.
2. ``ctx.mocks['http_response']`` — generic fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response.
3. If a service credential resolves, a real API call is made via
   :func:`execute_http_request`; the response is converted to the
   internal envelope and ``source`` is set to ``'<service>_api'``.
4. Offline synthetic response with deterministic-looking ids.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


CLICKUP_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createList",
)
CLICKUP_DEFAULT_OPERATION: str = "create"

TRELLO_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createBoard",
    "createList",
)
TRELLO_DEFAULT_OPERATION: str = "create"

ASANA_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createProject",
)
ASANA_DEFAULT_OPERATION: str = "create"

MONDAY_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createBoard",
)
MONDAY_DEFAULT_OPERATION: str = "create"

TODOIST_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createProject",
)
TODOIST_DEFAULT_OPERATION: str = "create"

LINEAR_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createProject",
)
LINEAR_DEFAULT_OPERATION: str = "create"


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
        for key in ("value", "name", "id", "title", "content"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_id(source: str) -> str:
    return f"mock_{source}_{random.randint(10000, 99999)}"


def _resolve_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> Any:
    raw = params.get(key)
    if raw is not None:
        return evaluate(raw, ectx)
    for fk in json_fallbacks:
        if fk in item.json and item.json[fk] is not None:
            return item.json[fk]
    return None


def _resolve_str_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
    *,
    default: str = "",
) -> str:
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    s = _coerce_str(value).strip()
    return s or default


# ── HTTP request helpers ─────────────────────────────────────────────


def _req(
    url: str,
    method: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any = None,
    auth: str = "none",
    auth_credential: dict[str, Any] | None = None,
) -> HttpRequestConfig:
    return HttpRequestConfig(
        url=url,
        method=method,
        headers=headers or {},
        body=body,
        body_mode="json" if body is not None else "none",
        auth=auth,  # type: ignore[arg-type]
        auth_credential=auth_credential or {},
        response_mode="json",
        timeout=30.0,
    )


def _build_clickup_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    token = str(cred.get("accessToken") or "")
    if not token:
        return None
    base = "https://api.clickup.com/api/v2/"
    headers = {"Authorization": token}
    task_id = resolved.get("taskId", "")
    list_id = _coerce_str(params.get("listId")) or resolved.get("listId", "")
    name = resolved.get("name", "")
    status = resolved.get("status", "")
    if operation == "create":
        body: dict[str, Any] = {"name": name}
        if status:
            body["status"] = status
        return _req(f"{base}list/{list_id}/task", "POST", headers=headers, body=body)
    if operation == "get":
        return _req(f"{base}task/{task_id}", "GET", headers=headers)
    if operation == "update":
        body = {"name": name}
        if status:
            body["status"] = status
        return _req(f"{base}task/{task_id}", "PUT", headers=headers, body=body)
    if operation == "delete":
        return _req(f"{base}task/{task_id}", "DELETE", headers=headers)
    if operation == "list":
        return _req(f"{base}list/{list_id}/task", "GET", headers=headers)
    if operation == "createList":
        folder_id = _coerce_str(params.get("folderId"))
        return _req(
            f"{base}folder/{folder_id}/list", "POST", headers=headers, body={"name": name}
        )
    return None


def _envelope_from_clickup_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    if operation == "list" and isinstance(data.get("tasks"), list):
        tasks = data["tasks"]
        if not tasks:
            return {"taskId": "", "name": "", "status": "", "items": []}
        first = tasks[0] if isinstance(tasks[0], dict) else {}
        return {
            "taskId": str(first.get("id") or ""),
            "name": first.get("name") or "",
            "status": first.get("status") or "",
            "items": tasks,
        }
    return {
        "taskId": str(data.get("id") or resolved.get("taskId", "")),
        "name": data.get("name") or resolved.get("name", ""),
        "status": data.get("status") or resolved.get("status", ""),
    }


def _build_trello_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    api_key = str(cred.get("apiKey") or "")
    api_token = str(cred.get("apiToken") or "")
    if not api_key or not api_token:
        return None
    base = "https://api.trello.com/1/"
    auth_qs = f"?key={api_key}&token={api_token}"
    card_id = resolved.get("cardId", "")
    list_id = _coerce_str(params.get("listId")) or resolved.get("listId", "")
    board_id = _coerce_str(params.get("boardId"))
    name = resolved.get("name", "")
    if operation == "create":
        body: dict[str, Any] = {"name": name}
        if list_id:
            body["idList"] = list_id
        return _req(f"{base}cards{auth_qs}", "POST", body=body)
    if operation == "get":
        return _req(f"{base}cards/{card_id}{auth_qs}", "GET")
    if operation == "update":
        return _req(f"{base}cards/{card_id}{auth_qs}", "PUT", body={"name": name})
    if operation == "delete":
        return _req(f"{base}cards/{card_id}{auth_qs}", "DELETE")
    if operation == "list":
        return _req(f"{base}lists/{list_id}/cards{auth_qs}", "GET")
    if operation == "createBoard":
        return _req(f"{base}boards{auth_qs}", "POST", body={"name": name})
    if operation == "createList":
        body = {"name": name}
        if board_id:
            body["idBoard"] = board_id
        return _req(f"{base}lists{auth_qs}", "POST", body=body)
    return None


def _envelope_from_trello_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    if operation == "list" and isinstance(data, list):
        if not data:
            return {"cardId": "", "name": "", "listId": "", "items": []}
        first = data[0] if isinstance(data[0], dict) else {}
        return {
            "cardId": str(first.get("id") or ""),
            "name": first.get("name") or "",
            "listId": str(first.get("idList") or ""),
            "items": data,
        }
    return {
        "cardId": str(data.get("id") or resolved.get("cardId", "")),
        "name": data.get("name") or resolved.get("name", ""),
        "listId": str(data.get("idList") or resolved.get("listId", "")),
    }


def _build_asana_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    token = str(cred.get("accessToken") or "")
    if not token:
        return None
    base = "https://app.asana.com/api/1.0/"
    headers = {"Authorization": f"Bearer {token}"}
    task_id = resolved.get("taskId", "")
    project_id = _coerce_str(params.get("projectId")) or resolved.get("projectId", "")
    name = resolved.get("name", "")
    if operation == "create":
        data: dict[str, Any] = {"name": name}
        if project_id:
            data["projects"] = [project_id]
        return _req(f"{base}tasks", "POST", headers=headers, body={"data": data})
    if operation == "get":
        return _req(f"{base}tasks/{task_id}", "GET", headers=headers)
    if operation == "update":
        return _req(
            f"{base}tasks/{task_id}", "PUT", headers=headers, body={"data": {"name": name}}
        )
    if operation == "delete":
        return _req(f"{base}tasks/{task_id}", "DELETE", headers=headers)
    if operation == "list":
        return _req(f"{base}projects/{project_id}/tasks", "GET", headers=headers)
    if operation == "createProject":
        return _req(
            f"{base}projects", "POST", headers=headers, body={"data": {"name": name}}
        )
    return None


def _envelope_from_asana_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    if operation == "list" and isinstance(data.get("data"), list):
        items = data["data"]
        if not items:
            return {"taskId": "", "name": "", "projectId": "", "items": []}
        first = items[0] if isinstance(items[0], dict) else {}
        return {
            "taskId": str(first.get("gid") or ""),
            "name": first.get("name") or "",
            "projectId": resolved.get("projectId", ""),
            "items": items,
        }
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    return {
        "taskId": str(inner.get("gid") or inner.get("id") or resolved.get("taskId", "")),
        "name": inner.get("name") or resolved.get("name", ""),
        "projectId": resolved.get("projectId", ""),
    }


def _build_monday_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    token = str(cred.get("apiToken") or "")
    if not token:
        return None
    url = "https://api.monday.com/v2"
    headers = {"Authorization": token, "Content-Type": "application/json"}
    item_id = resolved.get("itemId", "")
    board_id = _coerce_str(params.get("boardId")) or resolved.get("boardId", "")
    item_name = resolved.get("itemName", "")
    if operation == "create":
        query = f'mutation {{ create_item (board_id: {board_id}, item_name: "{item_name}") {{ id }} }}'
    elif operation == "get":
        query = f"query {{ items (ids: [{item_id}]) {{ id name }} }}"
    elif operation == "update":
        query = f'mutation {{ update_item (board_id: {board_id}, item_id: {item_id}, column_values: "{{\\"name\\": \\"{item_name}\\"}}") {{ id }} }}'
    elif operation == "delete":
        query = f"mutation {{ delete_item (item_id: {item_id}) {{ id }} }}"
    elif operation == "list":
        query = f"query {{ boards (ids: [{board_id}]) {{ items {{ id name }} }} }}"
    elif operation == "createBoard":
        query = f'mutation {{ create_board (board_name: "{item_name}") {{ id }} }}'
    else:
        return None
    return _req(url, "POST", headers=headers, body={"query": query})


def _envelope_from_monday_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    for key in ("create_item", "delete_item", "update_item", "create_board"):
        node = inner.get(key)
        if isinstance(node, dict):
            return {
                "itemId": str(node.get("id") or resolved.get("itemId", "")),
                "itemName": resolved.get("itemName", ""),
                "boardId": resolved.get("boardId", ""),
            }
    items = inner.get("items")
    if isinstance(items, list) and items:
        first = items[0] if isinstance(items[0], dict) else {}
        return {
            "itemId": str(first.get("id") or ""),
            "itemName": first.get("name") or "",
            "boardId": resolved.get("boardId", ""),
            "items": items,
        }
    boards = inner.get("boards")
    if isinstance(boards, list) and boards:
        board = boards[0] if isinstance(boards[0], dict) else {}
        bitems = board.get("items") if isinstance(board, dict) else None
        if isinstance(bitems, list) and bitems:
            first = bitems[0] if isinstance(bitems[0], dict) else {}
            return {
                "itemId": str(first.get("id") or ""),
                "itemName": first.get("name") or "",
                "boardId": str(board.get("id") or resolved.get("boardId", "")),
                "items": bitems,
            }
    return {
        "itemId": resolved.get("itemId", ""),
        "itemName": resolved.get("itemName", ""),
        "boardId": resolved.get("boardId", ""),
    }


def _build_todoist_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    token = str(cred.get("apiToken") or "")
    if not token:
        return None
    base = "https://api.todoist.com/rest/v2/"
    headers = {"Authorization": f"Bearer {token}"}
    task_id = resolved.get("taskId", "")
    project_id = _coerce_str(params.get("projectId")) or resolved.get("projectId", "")
    content = resolved.get("content", "")
    if operation == "create":
        body: dict[str, Any] = {"content": content}
        if project_id:
            body["project_id"] = project_id
        return _req(f"{base}tasks", "POST", headers=headers, body=body)
    if operation == "get":
        return _req(f"{base}tasks/{task_id}", "GET", headers=headers)
    if operation == "update":
        return _req(f"{base}tasks/{task_id}", "POST", headers=headers, body={"content": content})
    if operation == "delete":
        return _req(f"{base}tasks/{task_id}", "DELETE", headers=headers)
    if operation == "list":
        url = f"{base}tasks"
        if project_id:
            url += f"?project_id={project_id}"
        return _req(url, "GET", headers=headers)
    if operation == "createProject":
        return _req(f"{base}projects", "POST", headers=headers, body={"name": content})
    return None


def _envelope_from_todoist_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    if operation == "list" and isinstance(data, list):
        if not data:
            return {"taskId": "", "content": "", "projectId": "", "items": []}
        first = data[0] if isinstance(data[0], dict) else {}
        return {
            "taskId": str(first.get("id") or ""),
            "content": first.get("content") or "",
            "projectId": str(first.get("project_id") or resolved.get("projectId", "")),
            "items": data,
        }
    return {
        "taskId": str(data.get("id") or resolved.get("taskId", "")),
        "content": data.get("content") or resolved.get("content", ""),
        "projectId": str(data.get("project_id") or resolved.get("projectId", "")),
    }


def _build_linear_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    key = str(cred.get("apiKey") or "")
    if not key:
        return None
    url = "https://api.linear.app/graphql"
    headers = {"Authorization": key, "Content-Type": "application/json"}
    issue_id = resolved.get("issueId", "")
    team_id = _coerce_str(params.get("teamId"))
    title = resolved.get("title", "")
    if operation == "create":
        query = f'team {{ issueCreate(input: {{ teamId: "{team_id}", title: "{title}" }}) {{ success issue {{ id title }} }} }}'
    elif operation == "get":
        query = f'issue(id: "{issue_id}") {{ id title state {{ name }} }}'
    elif operation == "update":
        query = f'issueUpdate(id: "{issue_id}", input: {{ title: "{title}" }}) {{ success issue {{ id title }} }}'
    elif operation == "delete":
        query = f'issueDelete(id: "{issue_id}") {{ success deletedIssueId }}'
    elif operation == "list":
        query = "issues { nodes { id title state { name } } }"
    elif operation == "createProject":
        query = f'projectCreate(input: {{ name: "{title}" }}) {{ success project {{ id name }} }}'
    else:
        return None
    return _req(url, "POST", headers=headers, body={"query": query})


def _envelope_from_linear_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    for key in ("issueCreate", "issueUpdate", "projectCreate"):
        node = inner.get(key)
        if isinstance(node, dict):
            issue = node.get("issue") or node.get("project") or {}
            if isinstance(issue, dict):
                return {
                    "issueId": str(issue.get("id") or resolved.get("issueId", "")),
                    "title": issue.get("title") or issue.get("name") or resolved.get("title", ""),
                    "status": resolved.get("status", ""),
                }
    if isinstance(inner.get("issueDelete"), dict):
        return {
            "issueId": str(inner["issueDelete"].get("deletedIssueId") or resolved.get("issueId", "")),
            "title": resolved.get("title", ""),
            "status": resolved.get("status", ""),
        }
    if isinstance(inner.get("issue"), dict):
        issue = inner["issue"]
        state = issue.get("state")
        return {
            "issueId": str(issue.get("id") or resolved.get("issueId", "")),
            "title": issue.get("title") or resolved.get("title", ""),
            "status": state.get("name") if isinstance(state, dict) else resolved.get("status", ""),
        }
    issues_node = inner.get("issues")
    if isinstance(issues_node, dict):
        nodes = issues_node.get("nodes")
        if isinstance(nodes, list):
            if not nodes:
                return {"issueId": "", "title": "", "status": "", "items": []}
            first = nodes[0] if isinstance(nodes[0], dict) else {}
            state = first.get("state")
            return {
                "issueId": str(first.get("id") or ""),
                "title": first.get("title") or "",
                "status": state.get("name") if isinstance(state, dict) else "",
                "items": nodes,
            }
    return {
        "issueId": resolved.get("issueId", ""),
        "title": resolved.get("title", ""),
        "status": resolved.get("status", ""),
    }


@dataclass(frozen=True)
class _Field:
    field: str
    param: str
    fallbacks: tuple[str, ...]
    default: str = ""
    role: str = "data"


@dataclass(frozen=True)
class _TrackerConfig:
    source: str
    mock_key: str
    operations: tuple[str, ...]
    default_operation: str
    default_name: str
    default_status: str
    fields: tuple[_Field, ...]
    cred_type: str
    build_request: Callable[..., HttpRequestConfig | None]
    convert_response: Callable[..., dict[str, Any]]


_CONFIGS: dict[str, _TrackerConfig] = {
    "clickup": _TrackerConfig(
        source="clickup",
        mock_key="clickup_response",
        operations=CLICKUP_OPERATIONS,
        default_operation=CLICKUP_DEFAULT_OPERATION,
        default_name="Mock Task",
        default_status="Open",
        fields=(
            _Field("taskId", "taskId", ("taskId", "id"), role="id"),
            _Field("name", "name", ("name", "title"), role="name"),
            _Field("status", "status", ("status",), role="status"),
        ),
        cred_type="clickUpApi",
        build_request=_build_clickup_request,
        convert_response=_envelope_from_clickup_api,
    ),
    "trello": _TrackerConfig(
        source="trello",
        mock_key="trello_response",
        operations=TRELLO_OPERATIONS,
        default_operation=TRELLO_DEFAULT_OPERATION,
        default_name="Mock Card",
        default_status="Open",
        fields=(
            _Field("cardId", "cardId", ("cardId", "id"), role="id"),
            _Field("name", "name", ("name", "title"), role="name"),
            _Field("listId", "listId", ("listId",), role="container"),
        ),
        cred_type="trelloApi",
        build_request=_build_trello_request,
        convert_response=_envelope_from_trello_api,
    ),
    "asana": _TrackerConfig(
        source="asana",
        mock_key="asana_response",
        operations=ASANA_OPERATIONS,
        default_operation=ASANA_DEFAULT_OPERATION,
        default_name="Mock Task",
        default_status="Open",
        fields=(
            _Field("taskId", "taskId", ("taskId", "id"), role="id"),
            _Field("name", "name", ("name", "title"), role="name"),
            _Field("projectId", "projectId", ("projectId",), role="container"),
        ),
        cred_type="asanaApi",
        build_request=_build_asana_request,
        convert_response=_envelope_from_asana_api,
    ),
    "monday": _TrackerConfig(
        source="monday",
        mock_key="monday_response",
        operations=MONDAY_OPERATIONS,
        default_operation=MONDAY_DEFAULT_OPERATION,
        default_name="Mock Item",
        default_status="Open",
        fields=(
            _Field("itemId", "itemId", ("itemId", "id"), role="id"),
            _Field("itemName", "itemName", ("itemName", "name"), role="name"),
            _Field("boardId", "boardId", ("boardId",), role="container"),
        ),
        cred_type="mondayApi",
        build_request=_build_monday_request,
        convert_response=_envelope_from_monday_api,
    ),
    "todoist": _TrackerConfig(
        source="todoist",
        mock_key="todoist_response",
        operations=TODOIST_OPERATIONS,
        default_operation=TODOIST_DEFAULT_OPERATION,
        default_name="Mock Task",
        default_status="Open",
        fields=(
            _Field("taskId", "taskId", ("taskId", "id"), role="id"),
            _Field("content", "content", ("content", "name", "title"), role="name"),
            _Field("projectId", "projectId", ("projectId",), role="container"),
        ),
        cred_type="todoistApi",
        build_request=_build_todoist_request,
        convert_response=_envelope_from_todoist_api,
    ),
    "linear": _TrackerConfig(
        source="linear",
        mock_key="linear_response",
        operations=LINEAR_OPERATIONS,
        default_operation=LINEAR_DEFAULT_OPERATION,
        default_name="Mock Issue",
        default_status="Open",
        fields=(
            _Field("issueId", "issueId", ("issueId", "id"), role="id"),
            _Field("title", "title", ("title", "name"), role="name"),
            _Field("status", "status", ("status",), role="status"),
        ),
        cred_type="linearApi",
        build_request=_build_linear_request,
        convert_response=_envelope_from_linear_api,
    ),
}


def _synthesize(
    config: _TrackerConfig,
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in config.fields:
        val = resolved.get(f.field, "")
        if f.role == "id":
            if operation in ("get", "update", "delete"):
                out[f.field] = val or _random_id(config.source)
            else:
                out[f.field] = _random_id(config.source)
        elif f.role == "name":
            out[f.field] = val or config.default_name
        elif f.role == "status":
            out[f.field] = val or config.default_status
        elif f.role == "container":
            out[f.field] = val or _random_id(config.source)
        else:
            out[f.field] = val or f.default
    return out


async def _resolve_response(
    *,
    config: _TrackerConfig,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
    resolved: dict[str, str],
    synth: Any,
) -> tuple[dict[str, Any], str]:
    mocks = ctx.mocks or {}
    nmock = mocks.get(config.mock_key)
    if nmock is not None:
        if callable(nmock):
            raw = nmock(operation, params, item, ctx)
        else:
            raw = nmock
        if isinstance(raw, dict):
            return raw, config.mock_key
        return synth(), config.mock_key

    hmock = mocks.get("http_response")
    if hmock is not None and isinstance(hmock, dict):
        body = hmock.get("body")
        if isinstance(body, dict):
            return body, "http_response"

    cred = resolve_credential(node, ctx, config.cred_type)
    if cred:
        cfg = config.build_request(cred, operation, resolved, params)
        if cfg is not None:
            logger.info(
                "%s real HTTP call operation=%s",
                config.source,
                operation,
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        config.convert_response(resp.body, operation, resolved),
                        f"{config.source}_api",
                    )
            except Exception as exc:
                logger.warning("%s HTTP call failed: %s", config.source, exc)

    return synth(), "offline"


def _build_payload(
    config: _TrackerConfig,
    operation: str,
    response: dict[str, Any],
    resolved: dict[str, str],
    source: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for f in config.fields:
        val = response.get(f.field)
        if val in (None, ""):
            val = resolved.get(f.field, "")
        payload[f.field] = val
    for k, v in response.items():
        if k not in payload and k not in ("operation", "source", "mockSource"):
            payload[k] = v
    payload["operation"] = operation
    payload["source"] = config.source
    if source not in (config.mock_key, f"{config.source}_api"):
        payload["mockSource"] = source
    return payload


async def _exec_tracker(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
    config: _TrackerConfig,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    op_raw = str(params.get("operation") or config.default_operation).strip()
    canonical = {o.lower(): o for o in config.operations}
    operation = canonical.get(op_raw.lower(), op_raw)
    if operation not in config.operations:
        raise ValueError(
            f"{config.source}: unsupported operation {op_raw!r}; "
            f"expected one of {config.operations}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        resolved: dict[str, str] = {}
        for f in config.fields:
            resolved[f.field] = _resolve_str_param(
                params, f.param, item, ectx, f.fallbacks, default=f.default
            )

        def _synth() -> dict[str, Any]:
            return _synthesize(config, operation, resolved)

        response, source = await _resolve_response(
            config=config,
            operation=operation,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
            resolved=resolved,
            synth=_synth,
        )

        payload = _build_payload(config, operation, response, resolved, source)
        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)

        logger.info(
            "%s %s source=%s",
            config.source,
            operation,
            source,
        )

    return [(0, out)]


async def exec_clickup(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """ClickUp node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["clickup"])


async def exec_trello(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Trello node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["trello"])


async def exec_asana(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Asana node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["asana"])


async def exec_monday(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Monday.com node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["monday"])


async def exec_todoist(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Todoist node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["todoist"])


async def exec_linear(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Linear node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["linear"])


__all__ = [
    "exec_clickup",
    "exec_trello",
    "exec_asana",
    "exec_monday",
    "exec_todoist",
    "exec_linear",
    "CLICKUP_OPERATIONS",
    "CLICKUP_DEFAULT_OPERATION",
    "TRELLO_OPERATIONS",
    "TRELLO_DEFAULT_OPERATION",
    "ASANA_OPERATIONS",
    "ASANA_DEFAULT_OPERATION",
    "MONDAY_OPERATIONS",
    "MONDAY_DEFAULT_OPERATION",
    "TODOIST_OPERATIONS",
    "TODOIST_DEFAULT_OPERATION",
    "LINEAR_OPERATIONS",
    "LINEAR_DEFAULT_OPERATION",
]