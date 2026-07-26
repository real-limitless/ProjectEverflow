"""Google extra executors (clean-room n8n-nodes-base.*).

v1 covers:

- ``googleAnalytics``      — GA reporting.
- ``googleSlides``         — Google Slides operations.
- ``googleTasks``          — Google Tasks operations.
- ``googleContacts``       — Google Contacts operations.
- ``googleTranslate``      — translate text.
- ``googleAds``            — Google Ads operations.
- ``googleBigQuery``       — BigQuery operations.
- ``googleCloudStorage``   — GCS operations.
- ``googleBusinessProfile``— GBP operations.
- ``googleChat``           — Google Chat operations.
- ``gSuiteAdmin``          — Admin directory operations.

All API calls are mock-driven — no real network I/O is performed.

Behavior precedence (all nodes):

1. ``ctx.mocks['<node>_response']`` — callable invoked as
   ``mock(operation, params, item, ctx)`` or dict used directly.
2. ``ctx.mocks['http_response']`` — generic fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used.
3. Offline synthetic response.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)

GA_OPERATIONS: tuple[str, ...] = ("getReport", "getProperties", "getMetrics")
SLIDES_OPERATIONS: tuple[str, ...] = ("get", "create", "update", "getPage", "addPage")
TASKS_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "list",
    "update",
    "delete",
    "createList",
    "listLists",
)
CONTACTS_OPERATIONS: tuple[str, ...] = ("create", "get", "list", "update", "delete")
TRANSLATE_OPERATIONS: tuple[str, ...] = ("translate", "detect")
ADS_OPERATIONS: tuple[str, ...] = ("query", "getReport", "getCampaigns")
BIGQUERY_OPERATIONS: tuple[str, ...] = (
    "executeQuery",
    "insertRows",
    "listTables",
    "createTable",
)
GCS_OPERATIONS: tuple[str, ...] = ("download", "upload", "list", "delete")
GBP_OPERATIONS: tuple[str, ...] = ("get", "list", "update")
CHAT_OPERATIONS: tuple[str, ...] = (
    "sendMessage",
    "createSpace",
    "listSpaces",
    "getMember",
)
GSUITE_ADMIN_OPERATIONS: tuple[str, ...] = (
    "listUsers",
    "getUser",
    "createUser",
    "listGroups",
    "getGroup",
)


# ── Shared helpers ────────────────────────────────────────────────────


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
        for key in ("value", "name", "id", "text", "title"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


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
    return _coerce_str(_resolve_param(params, key, item, ectx, json_fallbacks))


def _iso(ctx: "EngineContext") -> str:
    now = ctx.now if ctx.now else datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _mock_item(items: list[ExecutionItem]) -> ExecutionItem:
    return items[0] if items else ExecutionItem(json={})


def _resolve_mock_response(
    ctx: "EngineContext",
    mock_key: str,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
) -> tuple[Any, str]:
    """Return ``(value, source)`` from ``ctx.mocks[mock_key]`` or http_response.

    A callable mock is invoked as ``mock(operation, params, item, ctx)``; a
    non-callable is used as-is.  If the callable returns ``None`` the call is
    treated as a miss and the http_response fallback is tried.
    """
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is not None:
        if callable(mock):
            val = mock(operation, params, item, ctx)
            if val is not None:
                return val, mock_key
        else:
            return mock, mock_key
    http = mocks.get("http_response")
    if http is not None:
        if isinstance(http, dict):
            body = http.get("body", http)
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except (ValueError, TypeError):
                    return http, "http_response"
            return body, "http_response"
        return http, "http_response"
    return None, ""


def _add_mock_source(payload: dict[str, Any], src: str, mock_key: str) -> None:
    if src and src != mock_key:
        payload["mockSource"] = src


def _resolve_operation(
    params: dict[str, Any],
    default: str,
    allowed: tuple[str, ...],
    node_name: str,
) -> str:
    raw = params.get("operation")
    if raw is None:
        return default
    op = _coerce_str(raw).strip() or default
    if op not in allowed:
        raise ValueError(
            f"{node_name}: unsupported operation {op!r}; "
            f"expected one of {allowed}"
        )
    return op


def _new_id() -> str:
    return uuid.uuid4().hex


# ── 1. Google Analytics ──────────────────────────────────────────────


def _synthesize_google_analytics(
    operation: str, property_id: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "reports": [
            {
                "propertyId": property_id,
                "dateRange": "last_7_days",
                "metrics": ["sessions", "users"],
                "dimensions": ["date"],
                "rows": [["2024-01-01", "100", "50"]],
            }
        ],
        "propertyId": property_id,
        "operation": operation,
        "source": "google_analytics",
        "generatedAt": _iso(ctx),
    }


async def exec_google_analytics(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Analytics — get GA reports.

    Operations: ``getReport`` (default), ``getProperties``, ``getMetrics``.
    Emits one item with ``{reports, propertyId, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "getReport", GA_OPERATIONS, "googleAnalytics"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    property_id = _resolve_str_param(
        params, "propertyId", item, ectx, ("propertyId", "property_id")
    )

    mock_val, src = _resolve_mock_response(
        ctx, "google_analytics_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_analytics(operation, property_id, ctx)
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = {
            "reports": mock_val.get("reports", []),
            "propertyId": mock_val.get("propertyId", property_id),
            "operation": mock_val.get("operation", operation),
            "source": "google_analytics",
        }
    else:
        payload = _synthesize_google_analytics(operation, property_id, ctx)
        src = "offline"

    _add_mock_source(payload, src, "google_analytics_response")

    logger.info("googleAnalytics %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 2. Google Slides ─────────────────────────────────────────────────


def _synthesize_google_slides(
    operation: str, presentation_id: str, title: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "presentationId": presentation_id or "pres_" + _new_id()[:12],
        "title": title or "Untitled Presentation",
        "operation": operation,
        "source": "google_slides",
        "createdAt": _iso(ctx),
    }


async def exec_google_slides(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Slides — Google Slides operations.

    Operations: ``get`` (default), ``create``, ``update``, ``getPage``,
    ``addPage``.  Emits one item with
    ``{presentationId, title, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "get", SLIDES_OPERATIONS, "googleSlides"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    presentation_id = _resolve_str_param(
        params, "presentationId", item, ectx, ("presentationId", "presentation_id")
    )
    title = _resolve_str_param(params, "title", item, ectx, ("title", "name"))

    mock_val, src = _resolve_mock_response(
        ctx, "google_slides_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_slides(
            operation, presentation_id, title, ctx
        )
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = {
            "presentationId": mock_val.get(
                "presentationId", presentation_id or "pres_" + _new_id()[:12]
            ),
            "title": mock_val.get("title", title or "Untitled Presentation"),
            "operation": mock_val.get("operation", operation),
            "source": "google_slides",
        }
    else:
        payload = _synthesize_google_slides(
            operation, presentation_id, title, ctx
        )
        src = "offline"

    _add_mock_source(payload, src, "google_slides_response")

    logger.info("googleSlides %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 3. Google Tasks ──────────────────────────────────────────────────


def _synthesize_google_tasks(
    operation: str,
    task_title: str,
    task_list_id: str,
    task_id: str,
    ctx: "EngineContext",
) -> dict[str, Any]:
    return {
        "taskId": task_id or "task_" + _new_id()[:12],
        "taskTitle": task_title or "Untitled Task",
        "taskListId": task_list_id or "default",
        "operation": operation,
        "source": "google_tasks",
        "updatedAt": _iso(ctx),
    }


async def exec_google_tasks(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Tasks — Google Tasks operations.

    Operations: ``create`` (default), ``get``, ``list``, ``update``,
    ``delete``, ``createList``, ``listLists``.  Emits one item with
    ``{taskId, taskTitle, taskListId, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "create", TASKS_OPERATIONS, "googleTasks"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    task_title = _resolve_str_param(
        params, "taskTitle", item, ectx, ("taskTitle", "title", "summary")
    )
    task_list_id = _resolve_str_param(
        params, "taskListId", item, ectx, ("taskListId", "task_list_id")
    )
    task_id = _resolve_str_param(
        params, "taskId", item, ectx, ("taskId", "task_id", "id")
    )

    mock_val, src = _resolve_mock_response(
        ctx, "google_tasks_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_tasks(
            operation, task_title, task_list_id, task_id, ctx
        )
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = {
            "taskId": mock_val.get("taskId", task_id or "task_" + _new_id()[:12]),
            "taskTitle": mock_val.get("taskTitle", task_title or "Untitled Task"),
            "taskListId": mock_val.get("taskListId", task_list_id or "default"),
            "operation": mock_val.get("operation", operation),
            "source": "google_tasks",
        }
    else:
        payload = _synthesize_google_tasks(
            operation, task_title, task_list_id, task_id, ctx
        )
        src = "offline"

    _add_mock_source(payload, src, "google_tasks_response")

    logger.info("googleTasks %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 4. Google Contacts ───────────────────────────────────────────────


def _synthesize_google_contacts(
    operation: str,
    contact_id: str,
    name: str,
    email: str,
    ctx: "EngineContext",
) -> dict[str, Any]:
    return {
        "contactId": contact_id or "contact_" + _new_id()[:12],
        "name": name or "Mock Contact",
        "email": email or "mock@example.com",
        "operation": operation,
        "source": "google_contacts",
        "updatedAt": _iso(ctx),
    }


async def exec_google_contacts(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Contacts — Google Contacts operations.

    Operations: ``create`` (default), ``get``, ``list``, ``update``,
    ``delete``.  Emits one item with
    ``{contactId, name, email, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "create", CONTACTS_OPERATIONS, "googleContacts"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    contact_id = _resolve_str_param(
        params, "contactId", item, ectx, ("contactId", "contact_id", "id")
    )
    name = _resolve_str_param(params, "name", item, ectx, ("name",))
    email = _resolve_str_param(params, "email", item, ectx, ("email",))

    mock_val, src = _resolve_mock_response(
        ctx, "google_contacts_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_contacts(
            operation, contact_id, name, email, ctx
        )
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = {
            "contactId": mock_val.get(
                "contactId", contact_id or "contact_" + _new_id()[:12]
            ),
            "name": mock_val.get("name", name or "Mock Contact"),
            "email": mock_val.get("email", email or "mock@example.com"),
            "operation": mock_val.get("operation", operation),
            "source": "google_contacts",
        }
    else:
        payload = _synthesize_google_contacts(
            operation, contact_id, name, email, ctx
        )
        src = "offline"

    _add_mock_source(payload, src, "google_contacts_response")

    logger.info("googleContacts %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 5. Google Translate ──────────────────────────────────────────────


def _synthesize_google_translate(
    operation: str,
    text: str,
    source_lang: str,
    target_lang: str,
) -> dict[str, Any]:
    if operation == "detect":
        return {
            "detectedSourceLanguage": source_lang or "auto",
            "text": text,
            "operation": operation,
            "source": "google_translate",
        }
    return {
        "translatedText": text if not source_lang else f"[{target_lang}] {text}",
        "detectedSourceLanguage": source_lang or "auto",
        "text": text,
        "target": target_lang,
        "operation": operation,
        "source": "google_translate",
    }


async def exec_google_translate(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Translate — translate text.

    Operations: ``translate`` (default), ``detect``.  Emits one item with
    ``{translatedText, detectedSourceLanguage, text, target, operation,
    source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "translate", TRANSLATE_OPERATIONS, "googleTranslate"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    text = _resolve_str_param(params, "text", item, ectx, ("text", "message", "content"))
    source_lang = _resolve_str_param(params, "source", item, ectx, ("source", "sourceLang"))
    target_lang = _resolve_str_param(
        params, "target", item, ectx, ("target", "targetLang")
    ) or "en"

    mock_val, src = _resolve_mock_response(
        ctx, "google_translate_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_translate(
            operation, text, source_lang, target_lang
        )
        src = "offline"

    if isinstance(mock_val, dict):
        if operation == "detect":
            payload: dict[str, Any] = {
                "detectedSourceLanguage": mock_val.get(
                    "detectedSourceLanguage", source_lang or "auto"
                ),
                "text": mock_val.get("text", text),
                "operation": mock_val.get("operation", operation),
                "source": "google_translate",
            }
        else:
            payload = {
                "translatedText": mock_val.get(
                    "translatedText",
                    text if not source_lang else f"[{target_lang}] {text}",
                ),
                "detectedSourceLanguage": mock_val.get(
                    "detectedSourceLanguage", source_lang or "auto"
                ),
                "text": mock_val.get("text", text),
                "target": mock_val.get("target", target_lang),
                "operation": mock_val.get("operation", operation),
                "source": "google_translate",
            }
    else:
        payload = _synthesize_google_translate(
            operation, text, source_lang, target_lang
        )
        src = "offline"

    _add_mock_source(payload, src, "google_translate_response")

    logger.info("googleTranslate %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 6. Google Ads ────────────────────────────────────────────────────


def _synthesize_google_ads(
    operation: str, customer_id: str, query: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "results": [
            {
                "campaignId": "camp_" + str(i + 1),
                "name": f"Mock Campaign {i + 1}",
                "status": "ENABLED",
                "budget": 100.0 * (i + 1),
            }
            for i in range(2)
        ],
        "customerId": customer_id,
        "query": query,
        "operation": operation,
        "source": "google_ads",
        "generatedAt": _iso(ctx),
    }


async def exec_google_ads(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Ads — Google Ads operations.

    Operations: ``query`` (default), ``getReport``, ``getCampaigns``.
    Emits one item with ``{results, customerId, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "query", ADS_OPERATIONS, "googleAds"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    customer_id = _resolve_str_param(
        params, "customerId", item, ectx, ("customerId", "customer_id")
    )
    query = _resolve_str_param(params, "query", item, ectx, ("query", "gaql"))

    mock_val, src = _resolve_mock_response(
        ctx, "google_ads_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_ads(operation, customer_id, query, ctx)
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = {
            "results": mock_val.get("results", []),
            "customerId": mock_val.get("customerId", customer_id),
            "operation": mock_val.get("operation", operation),
            "source": "google_ads",
        }
    else:
        payload = _synthesize_google_ads(operation, customer_id, query, ctx)
        src = "offline"

    _add_mock_source(payload, src, "google_ads_response")

    logger.info("googleAds %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 7. Google BigQuery ───────────────────────────────────────────────


def _synthesize_google_bigquery(
    operation: str,
    project_id: str,
    dataset_id: str,
    table_id: str,
    query: str,
    ctx: "EngineContext",
) -> dict[str, Any]:
    rows = [
        {"id": i + 1, "name": f"row_{i + 1}", "value": (i + 1) * 10}
        for i in range(2)
    ]
    return {
        "rows": rows,
        "totalRows": len(rows),
        "projectId": project_id,
        "datasetId": dataset_id,
        "tableId": table_id,
        "query": query,
        "operation": operation,
        "source": "google_bigquery",
        "generatedAt": _iso(ctx),
    }


async def exec_google_bigquery(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google BigQuery — BigQuery operations.

    Operations: ``executeQuery`` (default), ``insertRows``, ``listTables``,
    ``createTable``.  Emits one item with
    ``{rows, totalRows, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "executeQuery", BIGQUERY_OPERATIONS, "googleBigQuery"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    project_id = _resolve_str_param(
        params, "projectId", item, ectx, ("projectId", "project_id")
    )
    dataset_id = _resolve_str_param(
        params, "datasetId", item, ectx, ("datasetId", "dataset_id")
    )
    table_id = _resolve_str_param(
        params, "tableId", item, ectx, ("tableId", "table_id")
    )
    query = _resolve_str_param(params, "query", item, ectx, ("query", "sql"))

    mock_val, src = _resolve_mock_response(
        ctx, "google_bigquery_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_bigquery(
            operation, project_id, dataset_id, table_id, query, ctx
        )
        src = "offline"

    if isinstance(mock_val, dict):
        rows = mock_val.get("rows", [])
        if not isinstance(rows, list):
            rows = []
        payload: dict[str, Any] = {
            "rows": rows,
            "totalRows": mock_val.get("totalRows", len(rows)),
            "operation": mock_val.get("operation", operation),
            "source": "google_bigquery",
        }
    else:
        payload = _synthesize_google_bigquery(
            operation, project_id, dataset_id, table_id, query, ctx
        )
        src = "offline"

    _add_mock_source(payload, src, "google_bigquery_response")

    logger.info("googleBigQuery %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 8. Google Cloud Storage ──────────────────────────────────────────


def _synthesize_google_cloud_storage(
    operation: str, bucket_name: str, file_name: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "bucketName": bucket_name or "mock-bucket",
        "fileName": file_name or "mock_file.txt",
        "fileSize": 1024,
        "operation": operation,
        "source": "google_cloud_storage",
        "updatedAt": _iso(ctx),
    }


async def exec_google_cloud_storage(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Cloud Storage — GCS operations.

    Operations: ``download`` (default), ``upload``, ``list``, ``delete``.
    Emits one item with
    ``{bucketName, fileName, fileSize, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "download", GCS_OPERATIONS, "googleCloudStorage"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    bucket_name = _resolve_str_param(
        params, "bucketName", item, ectx, ("bucketName", "bucket", "bucket_name")
    )
    file_name = _resolve_str_param(
        params, "fileName", item, ectx, ("fileName", "file_name", "key", "name")
    )

    mock_val, src = _resolve_mock_response(
        ctx, "google_cloud_storage_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_cloud_storage(
            operation, bucket_name, file_name, ctx
        )
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = {
            "bucketName": mock_val.get("bucketName", bucket_name or "mock-bucket"),
            "fileName": mock_val.get(
                "fileName", file_name or "mock_file.txt"
            ),
            "fileSize": mock_val.get("fileSize", 1024),
            "operation": mock_val.get("operation", operation),
            "source": "google_cloud_storage",
        }
    else:
        payload = _synthesize_google_cloud_storage(
            operation, bucket_name, file_name, ctx
        )
        src = "offline"

    _add_mock_source(payload, src, "google_cloud_storage_response")

    logger.info("googleCloudStorage %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 9. Google Business Profile ───────────────────────────────────────


def _synthesize_google_business_profile(
    operation: str, location_id: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "locationId": location_id or "loc_" + _new_id()[:12],
        "name": "Mock Business",
        "operation": operation,
        "source": "google_business_profile",
        "updatedAt": _iso(ctx),
    }


async def exec_google_business_profile(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Business Profile — GBP operations.

    Operations: ``get`` (default), ``list``, ``update``.  Emits one item
    with ``{locationId, name, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "get", GBP_OPERATIONS, "googleBusinessProfile"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    location_id = _resolve_str_param(
        params, "locationId", item, ectx, ("locationId", "location_id", "id")
    )

    mock_val, src = _resolve_mock_response(
        ctx, "google_business_profile_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_business_profile(
            operation, location_id, ctx
        )
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = {
            "locationId": mock_val.get(
                "locationId", location_id or "loc_" + _new_id()[:12]
            ),
            "name": mock_val.get("name", "Mock Business"),
            "operation": mock_val.get("operation", operation),
            "source": "google_business_profile",
        }
    else:
        payload = _synthesize_google_business_profile(
            operation, location_id, ctx
        )
        src = "offline"

    _add_mock_source(payload, src, "google_business_profile_response")

    logger.info("googleBusinessProfile %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 10. Google Chat ──────────────────────────────────────────────────


def _synthesize_google_chat(
    operation: str, space_id: str, text: str, ctx: "EngineContext"
) -> dict[str, Any]:
    return {
        "messageId": "msg_" + _new_id()[:12],
        "spaceId": space_id or "spaces/mock",
        "text": text,
        "operation": operation,
        "source": "google_chat",
        "createdAt": _iso(ctx),
    }


async def exec_google_chat(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Chat — Google Chat operations.

    Operations: ``sendMessage`` (default), ``createSpace``,
    ``listSpaces``, ``getMember``.  Emits one item with
    ``{messageId, spaceId, text, operation, source}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "sendMessage", CHAT_OPERATIONS, "googleChat"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    space_id = _resolve_str_param(
        params, "spaceId", item, ectx, ("spaceId", "space_id", "space")
    )
    text = _resolve_str_param(params, "text", item, ectx, ("text", "message"))

    mock_val, src = _resolve_mock_response(
        ctx, "google_chat_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_google_chat(operation, space_id, text, ctx)
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = {
            "messageId": mock_val.get("messageId", "msg_" + _new_id()[:12]),
            "spaceId": mock_val.get("spaceId", space_id or "spaces/mock"),
            "text": mock_val.get("text", text),
            "operation": mock_val.get("operation", operation),
            "source": "google_chat",
        }
    else:
        payload = _synthesize_google_chat(operation, space_id, text, ctx)
        src = "offline"

    _add_mock_source(payload, src, "google_chat_response")

    logger.info("googleChat %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 11. G Suite Admin ────────────────────────────────────────────────


def _synthesize_g_suite_admin(
    operation: str, user_key: str, group_key: str, ctx: "EngineContext"
) -> dict[str, Any]:
    if operation == "listUsers":
        return {
            "users": [
                {
                    "id": "user_" + str(i + 1),
                    "primaryEmail": f"user{i + 1}@example.com",
                    "name": {"fullName": f"Mock User {i + 1}"},
                    "suspended": False,
                }
                for i in range(3)
            ],
            "operation": operation,
            "source": "g_suite_admin",
            "generatedAt": _iso(ctx),
        }
    if operation == "getUser":
        return {
            "id": "user_1",
            "primaryEmail": user_key or "user1@example.com",
            "name": {"fullName": "Mock User"},
            "suspended": False,
            "operation": operation,
            "source": "g_suite_admin",
        }
    if operation == "createUser":
        return {
            "id": "user_" + _new_id()[:12],
            "primaryEmail": user_key or "newuser@example.com",
            "name": {"fullName": "New User"},
            "suspended": False,
            "operation": operation,
            "source": "g_suite_admin",
            "createdAt": _iso(ctx),
        }
    if operation == "listGroups":
        return {
            "groups": [
                {
                    "id": "group_" + str(i + 1),
                    "email": f"group{i + 1}@example.com",
                    "name": f"Mock Group {i + 1}",
                }
                for i in range(3)
            ],
            "operation": operation,
            "source": "g_suite_admin",
            "generatedAt": _iso(ctx),
        }
    if operation == "getGroup":
        return {
            "id": "group_1",
            "email": group_key or "group1@example.com",
            "name": "Mock Group",
            "operation": operation,
            "source": "g_suite_admin",
        }
    return {
        "operation": operation,
        "source": "g_suite_admin",
        "generatedAt": _iso(ctx),
    }


async def exec_g_suite_admin(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """G Suite Admin — Admin directory operations.

    Operations: ``listUsers`` (default), ``getUser``, ``createUser``,
    ``listGroups``, ``getGroup``.  Emits one item with synthetic directory
    data and ``{operation, source: 'g_suite_admin'}``.
    """
    params = node.parameters or {}
    operation = _resolve_operation(
        params, "listUsers", GSUITE_ADMIN_OPERATIONS, "gSuiteAdmin"
    )

    item = _mock_item(items)
    ectx = _ectx(item, ctx)
    user_key = _resolve_str_param(
        params, "userKey", item, ectx, ("userKey", "user_key", "email")
    )
    group_key = _resolve_str_param(
        params, "groupKey", item, ectx, ("groupKey", "group_key", "groupEmail")
    )

    mock_val, src = _resolve_mock_response(
        ctx, "g_suite_admin_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_g_suite_admin(
            operation, user_key, group_key, ctx
        )
        src = "offline"

    if isinstance(mock_val, dict):
        payload: dict[str, Any] = dict(mock_val)
        payload.setdefault("operation", operation)
        payload["source"] = "g_suite_admin"
    else:
        payload = _synthesize_g_suite_admin(
            operation, user_key, group_key, ctx
        )
        src = "offline"

    _add_mock_source(payload, src, "g_suite_admin_response")

    logger.info("gSuiteAdmin %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


__all__ = [
    "exec_google_analytics",
    "exec_google_slides",
    "exec_google_tasks",
    "exec_google_contacts",
    "exec_google_translate",
    "exec_google_ads",
    "exec_google_bigquery",
    "exec_google_cloud_storage",
    "exec_google_business_profile",
    "exec_google_chat",
    "exec_g_suite_admin",
    "GA_OPERATIONS",
    "SLIDES_OPERATIONS",
    "TASKS_OPERATIONS",
    "CONTACTS_OPERATIONS",
    "TRANSLATE_OPERATIONS",
    "ADS_OPERATIONS",
    "BIGQUERY_OPERATIONS",
    "GCS_OPERATIONS",
    "GBP_OPERATIONS",
    "CHAT_OPERATIONS",
    "GSUITE_ADMIN_OPERATIONS",
]