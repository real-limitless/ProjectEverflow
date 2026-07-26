"""Jira executor (clean-room n8n ``n8n-nodes-base.jira``).

v1 covers the operations most commonly used in n8n templates:

- ``jira`` — create/get/update/search/delete issues in Jira via the Jira
  REST API. Emits one item per input (or one item per issue for ``search``
  in array mode) with operation-specific fields and ``source: 'jira'``.

When a ``jiraApi`` credential is attached and no mock is present, real
calls are made to the Jira REST API via
:func:`execute_http_request`. Otherwise the executor is mock-driven with
an offline synthetic fallback.

Parameters honored by ``jira``:

- ``operation``   (one of ``create`` / ``get`` / ``update`` / ``search`` /
  ``delete``; default ``get``)
- ``issueKey``    (string; ``$json.issueKey`` / ``$json.key`` /
  ``$json.id`` fallback; required for ``get`` / ``update`` / ``delete``)
- For ``create``:
  - ``projectKey``   (string; ``$json.projectKey`` fallback; required)
  - ``summary``      (string; ``$json.summary`` / ``$json.title`` fallback)
  - ``description``  (string; ``$json.description`` fallback)
  - ``issueType``    (string; default ``Task``)
  - ``assignee``     (string; optional)
  - ``labels``       (list; optional)
  - ``priority``     (string; optional)
- For ``update``:
  - ``summary``      (string; optional)
  - ``description``  (string; optional)
  - ``status``       (string; optional)
  - ``assignee``     (string; optional)
  - ``priority``     (string; optional)
- For ``search``:
  - ``jql``          (JQL query string; ``$json.jql`` fallback; default
    ``project = DEMO ORDER BY created DESC``)
  - ``maxResults``   (int; default 10)
  - ``fields``       (list of field names; default
    ``['summary', 'status', 'assignee']``)
  - ``dataMode``     (``array`` / ``object``; default ``array``; when
    ``object``, emit one item with an ``issues`` array)

Behavior precedence:

1. ``ctx.mocks['jira_response']`` — when present, the value drives the
   executor. A callable is invoked as
   ``mock(operation, issue_or_jql, params, item, ctx)`` and may return a
   dict (used as the response) or any other value (falls back to offline
   synthesis, tagged ``jira_response``). A non-callable dict is used
   directly as the response.
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response.
3. If a ``jiraApi`` credential resolves (``baseUrl``, ``email``, and
   ``apiToken`` present), a real call is made to the Jira REST API via
   :func:`execute_http_request` and the response is used.
4. Offline synthetic response with deterministic-looking numbers and
   timestamps.

Items with an empty resolved ``issueKey`` (for ``get`` / ``update`` /
``delete``) or an empty ``projectKey`` (for ``create``) are skipped (no
item emitted).
"""

from __future__ import annotations

import base64
import logging
import random
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


JIRA_OPERATIONS: tuple[str, ...] = ("create", "get", "update", "search", "delete")
JIRA_DEFAULT_OPERATION: str = "get"
JIRA_DEFAULT_ISSUE_TYPE: str = "Task"
JIRA_DEFAULT_JQL: str = "project = DEMO ORDER BY created DESC"
JIRA_DEFAULT_MAX_RESULTS: int = 10
JIRA_DEFAULT_FIELDS: tuple[str, ...] = ("summary", "status", "assignee")
JIRA_OFFLINE_MAX_ISSUES: int = 3
JIRA_DATA_MODES: tuple[str, ...] = ("array", "object")
JIRA_DEFAULT_DATA_MODE: str = "array"


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
        for key in ("value", "name", "id", "key", "summary", "title"):
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


def _coerce_int(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                return default
    return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_number() -> int:
    return random.randint(1000, 99999)


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
            if fk in item.json and item.json[fk] is not None:
                resolved = item.json[fk]
                break
    return _coerce_str_list(resolved)


# ── Offline synthesis ─────────────────────────────────────────────────


def _synthesize_create(
    project_key: str,
    summary: str,
    description: str,
    issue_type: str,
) -> dict[str, Any]:
    issue_id = _random_number()
    return {
        "id": str(issue_id),
        "key": f"{project_key}-{issue_id}",
        "self": f"https://mock-jira.atlassian.net/rest/api/3/issue/{issue_id}",
        "fields": {
            "summary": summary,
            "description": description,
            "status": {"name": "Open"},
            "issuetype": {"name": issue_type},
            "project": {"key": project_key},
            "created": _now_iso(),
        },
    }


def _synthesize_get(issue_key: str) -> dict[str, Any]:
    issue_id = _random_number()
    now = _now_iso()
    return {
        "id": str(issue_id),
        "key": issue_key,
        "self": f"https://mock-jira.atlassian.net/rest/api/3/issue/{issue_id}",
        "fields": {
            "summary": "Mock Issue",
            "description": "Mock issue description",
            "status": {"name": "Open"},
            "issuetype": {"name": "Task"},
            "project": {"key": "DEMO"},
            "created": now,
            "updated": now,
        },
    }


def _synthesize_update(
    issue_key: str,
    summary: str,
    status: str,
) -> dict[str, Any]:
    issue_id = _random_number()
    return {
        "id": str(issue_id),
        "key": issue_key,
        "self": f"https://mock-jira.atlassian.net/rest/api/3/issue/{issue_id}",
        "fields": {
            "summary": summary or "Updated",
            "status": {"name": status or "Open"},
            "updated": _now_iso(),
        },
    }


def _synthesize_search(max_results: int) -> dict[str, Any]:
    count = min(max_results, JIRA_OFFLINE_MAX_ISSUES)
    issues: list[dict[str, Any]] = []
    for i in range(1, count + 1):
        issues.append(
            {
                "id": f"{i}",
                "key": f"DEMO-{i}",
                "fields": {
                    "summary": f"Mock Issue {i}",
                    "status": {"name": "Open"},
                    "assignee": {"displayName": "Mock User"},
                },
            }
        )
    return {
        "startAt": 0,
        "maxResults": max_results,
        "total": count,
        "issues": issues,
    }


def _synthesize_delete(issue_key: str) -> dict[str, Any]:
    return {
        "success": True,
        "issueKey": issue_key,
        "deletedAt": _now_iso(),
    }


def _synthesize_offline(
    operation: str,
    *,
    issue_key: str,
    project_key: str,
    summary: str,
    description: str,
    issue_type: str,
    status: str,
    max_results: int,
) -> dict[str, Any]:
    if operation == "create":
        return _synthesize_create(project_key, summary, description, issue_type)
    if operation == "get":
        return _synthesize_get(issue_key)
    if operation == "update":
        return _synthesize_update(issue_key, summary, status)
    if operation == "search":
        return _synthesize_search(max_results)
    if operation == "delete":
        return _synthesize_delete(issue_key)
    return {}


# ── Real HTTP request building ────────────────────────────────────────


def _build_jira_request(
    cred: dict[str, Any],
    operation: str,
    issue_key: str,
    project_key: str,
    summary: str,
    description: str,
    issue_type: str,
    assignee: str,
    labels: list[str],
    priority: str,
    status: str,
    jql: str,
    max_results: int,
    fields: list[str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    """Build a real Jira REST API request config.

    Returns ``None`` when the credential lacks ``baseUrl``, ``email``,
    or ``apiToken``.
    """
    base_url = str(
        cred.get("baseUrl") or cred.get("base_url") or ""
    ).rstrip("/")
    email = str(cred.get("email") or "")
    api_token = str(
        cred.get("apiToken") or cred.get("api_token") or ""
    )
    if not base_url or not email or not api_token:
        return None

    raw = f"{email}:{api_token}".encode("utf-8")
    auth_header = "Basic " + base64.b64encode(raw).decode("ascii")
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    api_base = f"{base_url}/rest/api/3"

    if operation == "create":
        body: dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "issuetype": {"name": issue_type},
            }
        }
        if description:
            body["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }
        if assignee:
            body["fields"]["assignee"] = {"accountId": assignee}
        if labels:
            body["fields"]["labels"] = labels
        if priority:
            body["fields"]["priority"] = {"name": priority}
        return HttpRequestConfig(
            url=f"{api_base}/issue",
            method="POST",
            headers=headers,
            body=body,
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    if operation == "get":
        return HttpRequestConfig(
            url=f"{api_base}/issue/{issue_key}",
            method="GET",
            headers=headers,
            response_mode="json",
            timeout=30.0,
        )

    if operation == "update":
        body = {"fields": {}}
        if summary:
            body["fields"]["summary"] = summary
        if description:
            body["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }
        if assignee:
            body["fields"]["assignee"] = {"accountId": assignee}
        if priority:
            body["fields"]["priority"] = {"name": priority}
        return HttpRequestConfig(
            url=f"{api_base}/issue/{issue_key}",
            method="PUT",
            headers=headers,
            body=body,
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    if operation == "delete":
        return HttpRequestConfig(
            url=f"{api_base}/issue/{issue_key}",
            method="DELETE",
            headers=headers,
            response_mode="json",
            timeout=30.0,
        )

    if operation == "search":
        body = {
            "jql": jql,
            "maxResults": max_results,
            "fields": fields,
        }
        return HttpRequestConfig(
            url=f"{api_base}/search",
            method="POST",
            headers=headers,
            body=body,
            body_mode="json",
            response_mode="json",
            timeout=30.0,
        )

    return None


def _envelope_from_jira_api(
    data: dict[str, Any],
    operation: str,
    issue_key: str,
) -> dict[str, Any]:
    """Convert a real Jira REST API response to the internal envelope shape."""
    if operation == "delete":
        return {
            "success": True,
            "issueKey": issue_key,
            "deletedAt": _now_iso(),
        }
    if operation == "search":
        return {
            "startAt": data.get("startAt", 0),
            "maxResults": data.get("maxResults", 0),
            "total": data.get("total", 0),
            "issues": data.get("issues") or [],
        }
    return {
        "id": data.get("id"),
        "key": data.get("key") or issue_key,
        "self": data.get("self", ""),
        "fields": data.get("fields") if isinstance(data.get("fields"), dict) else {},
    }


# ── Mock resolution ───────────────────────────────────────────────────


async def _resolve_jira_response(
    *,
    operation: str,
    issue_or_jql: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
    synth: Any,
    issue_key: str,
    project_key: str,
    summary: str,
    description: str,
    issue_type: str,
    assignee: str,
    labels: list[str],
    priority: str,
    status: str,
    jql: str,
    max_results: int,
    fields: list[str],
) -> tuple[dict[str, Any], str]:
    """Return ``(response, source)`` for the current call.

    ``source`` is one of ``"jira_response"``, ``"http_response"``,
    ``"jira_api"``, ``"offline"``.
    """
    mocks = ctx.mocks or {}
    jmock = mocks.get("jira_response")
    if jmock is not None:
        if callable(jmock):
            raw = jmock(operation, issue_or_jql, params, item, ctx)
        else:
            raw = jmock
        if isinstance(raw, dict):
            return raw, "jira_response"
        return synth(), "jira_response"

    hmock = mocks.get("http_response")
    if hmock is not None and isinstance(hmock, dict):
        body = hmock.get("body")
        if isinstance(body, dict):
            return body, "http_response"

    cred = resolve_credential(node, ctx, "jiraApi")
    if cred:
        cfg = _build_jira_request(
            cred,
            operation=operation,
            issue_key=issue_key,
            project_key=project_key,
            summary=summary,
            description=description,
            issue_type=issue_type,
            assignee=assignee,
            labels=labels,
            priority=priority,
            status=status,
            jql=jql,
            max_results=max_results,
            fields=fields,
            params=params,
        )
        if cfg is not None:
            logger.info(
                "jira real HTTP call operation=%s issueKey=%s",
                operation,
                issue_key,
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_jira_api(resp.body, operation, issue_key),
                        "jira_api",
                    )
            except Exception as exc:
                logger.warning("jira HTTP call failed: %s", exc)

    return synth(), "offline"


# ── Action executor ───────────────────────────────────────────────────


async def exec_jira(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Jira node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(params.get("operation") or JIRA_DEFAULT_OPERATION).strip().lower()
    if operation not in JIRA_OPERATIONS:
        raise ValueError(
            f"jira: unsupported operation {operation!r}; "
            f"expected one of {JIRA_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        # Resolve issueKey (used by get/update/delete; echoed for create)
        issue_key = _resolve_str_param(
            params, "issueKey", item, ectx, ("issueKey", "key", "id")
        )

        # Operation-specific parameter resolution
        project_key: str = ""
        summary: str = ""
        description: str = ""
        issue_type: str = JIRA_DEFAULT_ISSUE_TYPE
        assignee: str = ""
        labels: list[str] = []
        priority: str = ""
        status: str = ""
        jql: str = JIRA_DEFAULT_JQL
        max_results: int = JIRA_DEFAULT_MAX_RESULTS
        fields: list[str] = list(JIRA_DEFAULT_FIELDS)
        data_mode: str = JIRA_DEFAULT_DATA_MODE

        if operation == "create":
            project_key = _resolve_str_param(
                params, "projectKey", item, ectx, ("projectKey",)
            )
            summary = _resolve_str_param(
                params, "summary", item, ectx, ("summary", "title")
            )
            description = _resolve_str_param(
                params, "description", item, ectx, ("description",)
            )
            issue_type = _resolve_str_param(
                params, "issueType", item, ectx, ("issueType",),
                default=JIRA_DEFAULT_ISSUE_TYPE,
            )
            assignee = _resolve_str_param(
                params, "assignee", item, ectx, ("assignee",)
            )
            labels = _resolve_list_param(
                params, "labels", item, ectx, ("labels",)
            )
            priority = _resolve_str_param(
                params, "priority", item, ectx, ("priority",)
            )

        elif operation == "update":
            summary = _resolve_str_param(
                params, "summary", item, ectx, ("summary", "title")
            )
            description = _resolve_str_param(
                params, "description", item, ectx, ("description",)
            )
            status = _resolve_str_param(
                params, "status", item, ectx, ("status",)
            )
            assignee = _resolve_str_param(
                params, "assignee", item, ectx, ("assignee",)
            )
            priority = _resolve_str_param(
                params, "priority", item, ectx, ("priority",)
            )

        elif operation == "search":
            jql = _resolve_str_param(
                params, "jql", item, ectx, ("jql",),
                default=JIRA_DEFAULT_JQL,
            )
            max_results_raw = _resolve_param(
                params, "maxResults", item, ectx, ("maxResults",)
            )
            max_results = _coerce_int(
                max_results_raw, JIRA_DEFAULT_MAX_RESULTS
            )
            fields = _resolve_list_param(
                params, "fields", item, ectx, ("fields",)
            ) or list(JIRA_DEFAULT_FIELDS)
            data_mode_raw = _resolve_param(
                params, "dataMode", item, ectx, ("dataMode",)
            )
            data_mode_str = _coerce_str(data_mode_raw).strip().lower()
            if data_mode_str in JIRA_DATA_MODES:
                data_mode = data_mode_str

        # Skip checks
        if operation == "create":
            if not project_key:
                logger.info(
                    "jira %s skipped: empty projectKey on node %r",
                    operation,
                    node.name,
                )
                continue
        elif operation in ("get", "update", "delete"):
            if not issue_key:
                logger.info(
                    "jira %s skipped: empty issueKey on node %r",
                    operation,
                    node.name,
                )
                continue

        # The "issue_or_jql" passed to the callable mock
        if operation == "search":
            issue_or_jql = jql
        else:
            issue_or_jql = issue_key

        def _synth() -> dict[str, Any]:
            return _synthesize_offline(
                operation,
                issue_key=issue_key,
                project_key=project_key,
                summary=summary,
                description=description,
                issue_type=issue_type,
                status=status,
                max_results=max_results,
            )

        response, source = await _resolve_jira_response(
            operation=operation,
            issue_or_jql=issue_or_jql,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
            synth=_synth,
            issue_key=issue_key,
            project_key=project_key,
            summary=summary,
            description=description,
            issue_type=issue_type,
            assignee=assignee,
            labels=labels,
            priority=priority,
            status=status,
            jql=jql,
            max_results=max_results,
            fields=fields,
        )

        # Build emitted items
        if operation == "search":
            out.extend(
                _build_search_items(
                    item=item,
                    response=response,
                    source=source,
                    jql=jql,
                    max_results=max_results,
                    fields=fields,
                    data_mode=data_mode,
                )
            )
        elif operation == "delete":
            payload: dict[str, Any] = {
                "issueKey": response.get("issueKey") or issue_key,
                "success": response.get("success", True),
                "deletedAt": response.get("deletedAt") or _now_iso(),
                "source": "jira",
            }
            if source not in ("jira_response", "jira_api"):
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)
        else:
            # create / get / update
            fields_obj = response.get("fields") or {}
            payload = {
                "issueId": response.get("id") or str(_random_number()),
                "issueKey": response.get("key") or issue_key,
                "summary": fields_obj.get("summary") or summary,
                "description": fields_obj.get("description", description),
                "status": (
                    fields_obj.get("status", {}).get("name")
                    if isinstance(fields_obj.get("status"), dict)
                    else fields_obj.get("status", "Open")
                ),
                "issueType": (
                    fields_obj.get("issuetype", {}).get("name", issue_type)
                    if isinstance(fields_obj.get("issuetype"), dict)
                    else issue_type
                ),
                "projectKey": (
                    fields_obj.get("project", {}).get("key", project_key)
                    if isinstance(fields_obj.get("project"), dict)
                    else project_key
                ),
                "self": response.get(
                    "self",
                    f"https://mock-jira.atlassian.net/rest/api/3/issue/{response.get('id', '')}",
                ),
                "source": "jira",
            }
            if source not in ("jira_response", "jira_api"):
                payload["mockSource"] = source
            # Echo optional resolved fields for create
            if operation == "create":
                if assignee:
                    payload["assignee"] = assignee
                if labels:
                    payload["labels"] = labels
                if priority:
                    payload["priority"] = priority
            # Echo optional resolved fields for update
            if operation == "update":
                if assignee:
                    payload["assignee"] = assignee
                if priority:
                    payload["priority"] = priority
                if status:
                    payload["status"] = status
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        logger.info(
            "jira %s issueKey=%s projectKey=%s source=%s",
            operation,
            issue_key,
            project_key,
            source,
        )

    return [(0, out)]


# ── Search payload builder ────────────────────────────────────────────


def _build_search_items(
    *,
    item: ExecutionItem,
    response: dict[str, Any],
    source: str,
    jql: str,
    max_results: int,
    fields: list[str],
    data_mode: str,
) -> list[ExecutionItem]:
    issues = response.get("issues") or []
    total = response.get("total", len(issues))
    results: list[ExecutionItem] = []

    if data_mode == "object":
        payload: dict[str, Any] = {
            "issues": list(issues),
            "total": total,
            "startAt": response.get("startAt", 0),
            "maxResults": response.get("maxResults", max_results),
            "jql": jql,
            "fields": fields,
            "source": "jira",
        }
        if source not in ("jira_response", "jira_api"):
            payload["mockSource"] = source
        ni = item.clone()
        ni.json = {**item.json, **payload}
        results.append(ni)
    else:
        for entry in issues:
            entry_fields = entry.get("fields") or {}
            assignee_obj = entry_fields.get("assignee")
            assignee_name = ""
            if isinstance(assignee_obj, dict):
                assignee_name = assignee_obj.get("displayName", "")
            elif isinstance(assignee_obj, str):
                assignee_name = assignee_obj
            status_obj = entry_fields.get("status")
            status_name = ""
            if isinstance(status_obj, dict):
                status_name = status_obj.get("name", "")
            elif isinstance(status_obj, str):
                status_name = status_obj
            payload = {
                "issueId": entry.get("id", ""),
                "issueKey": entry.get("key", ""),
                "summary": entry_fields.get("summary", ""),
                "status": status_name,
                "assignee": assignee_name,
                "source": "jira",
            }
            if source not in ("jira_response", "jira_api"):
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            results.append(ni)

    return results


__all__ = [
    "exec_jira",
    "JIRA_OPERATIONS",
    "JIRA_DEFAULT_OPERATION",
    "JIRA_DEFAULT_ISSUE_TYPE",
    "JIRA_DEFAULT_JQL",
    "JIRA_DEFAULT_MAX_RESULTS",
    "JIRA_DEFAULT_FIELDS",
    "JIRA_OFFLINE_MAX_ISSUES",
    "JIRA_DATA_MODES",
    "JIRA_DEFAULT_DATA_MODE",
]