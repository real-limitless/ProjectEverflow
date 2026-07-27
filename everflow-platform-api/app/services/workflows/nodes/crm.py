"""CRM executors (clean-room ``n8n-nodes-base.*``).

Implements Salesforce, Pipedrive, Zendesk, Zoho CRM, HighLevel, Odoo, HubSpot Trigger.

Each response executor follows a credential-aware precedence chain:

1. ``ctx.mocks['<service>_response']`` — dict or callable (test/dry-run)
2. ``ctx.mocks['http_response']`` — generic HTTP mock body fallback
3. **If a credential resolves** (e.g. ``salesforceApi``), a real HTTP call is
   made via :func:`execute_http_request` and the API response is converted to
   the internal envelope. On exception the executor falls through to offline.
4. Offline synthetic response tagged with ``source``.

When the result comes from the real API, ``source`` is set to
``"<service>_api"`` and no ``mockSource`` is added. For the
``http_response`` and offline fallbacks, a ``mockSource`` field records the
origin. Odoo is XML-RPC based and stays mock-only (no real HTTP step); all
other executors make real calls when their credential type is attached.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

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


def _resolve_param(key, params, item, ctx, *, default=""):
    raw = params.get(key)
    if raw is None:
        return default
    return _coerce_str(evaluate(raw, _ectx(item, ctx)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mock_response(mock_key, operation, params, item, ctx):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is None:
        return None
    if callable(mock):
        result = mock(operation, params, item, ctx)
        return result if isinstance(result, dict) else None
    return mock if isinstance(mock, dict) else None


def _http_response(ctx):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    hr = mocks.get("http_response")
    if isinstance(hr, dict):
        body = hr.get("body")
        if isinstance(body, dict):
            return body
    return None


def _trigger_payload(ctx, *keys):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    for key in keys:
        val = mocks.get(key)
        if isinstance(val, dict):
            return val
        if callable(val):
            result = val()
            if isinstance(result, dict):
                return result
    return None


def _gen_id(*parts: str) -> str:
    return str(abs(hash("".join(parts) + _now_iso())) % 100000)


def _json_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if extra:
        headers.update(extra)
    return headers


# ── Salesforce ───────────────────────────────────────────────────────


SALESFORCE_OPERATIONS = ("create", "get", "update", "delete", "list", "upsert")
SALESFORCE_DEFAULT_OPERATION = "create"


def _build_salesforce_request(cred, operation, params, item, ctx):
    """Build a Salesforce REST API request config.

    Returns ``None`` when the credential lacks ``baseUrl`` or ``accessToken``.
    """
    base_url = str(cred.get("baseUrl") or cred.get("instanceUrl") or "").rstrip("/")
    token = str(cred.get("accessToken") or cred.get("access_token") or "")
    if not base_url or not token:
        return None
    headers = _json_headers({"Authorization": f"Bearer {token}"})
    sobject = _resolve_param("object", params, item, ctx) or "Account"
    record_id = (
        _resolve_param("id", params, item, ctx)
        or _resolve_param("recordId", params, item, ctx)
    )
    name = _resolve_param("name", params, item, ctx)
    body: dict[str, Any] = {}
    if name:
        body["Name"] = name

    if operation == "create":
        return HttpRequestConfig(
            url=f"{base_url}/services/data/v58.0/sobjects/{sobject}",
            method="POST", headers=headers, body=body or None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "delete", "update"):
        if not record_id:
            return None
        url = f"{base_url}/services/data/v58.0/sobjects/{sobject}/{record_id}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="PATCH", headers=headers,
                body=body or None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="GET" if operation == "get" else "DELETE",
            headers=headers, response_mode="json", timeout=30.0,
        )
    if operation in ("list", "upsert"):
        if operation == "list":
            query = (
                _resolve_param("query", params, item, ctx)
                or f"SELECT Id, Name FROM {sobject} LIMIT 100"
            )
            return HttpRequestConfig(
                url=f"{base_url}/services/data/v58.0/query?q={quote(query)}",
                method="GET", headers=headers, response_mode="json", timeout=30.0,
            )
        ext_field = _resolve_param("externalIdField", params, item, ctx) or "Id"
        ext_id = _resolve_param("externalId", params, item, ctx) or record_id
        if not ext_id:
            return None
        return HttpRequestConfig(
            url=f"{base_url}/services/data/v58.0/sobjects/{sobject}/{ext_field}/{ext_id}",
            method="PATCH", headers=headers, body=body or None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_salesforce_api(data, operation):
    """Convert a Salesforce REST API response to the internal envelope."""
    records = data.get("records")
    if isinstance(records, list):
        return {
            "records": records,
            "operation": operation,
            "source": "salesforce_api",
            "updatedAt": _now_iso(),
            "raw": data,
        }
    record_id = data.get("id") or data.get("Id") or data.get("recordId") or ""
    name = data.get("Name") or data.get("name") or ""
    return {
        "recordId": record_id,
        "name": name,
        "operation": operation,
        "source": "salesforce_api",
        "updatedAt": _now_iso(),
        "raw": data,
    }


async def _resolve_salesforce_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("salesforce_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "salesforce_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "salesforceApi") or resolve_credential(
        node, ctx, "salesforceOAuth2Api"
    )
    if cred:
        cfg = _build_salesforce_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("salesforce real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_salesforce_api(resp.body, operation),
                        "salesforce_api",
                    )
            except Exception as exc:
                logger.warning("salesforce HTTP call failed: %s", exc)
    name = _resolve_param("name", params, item, ctx)
    return {
        "recordId": _gen_id("sf", name), "name": name,
        "operation": operation, "source": "salesforce",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_salesforce(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", SALESFORCE_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_salesforce_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("salesforce_response", "salesforce_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── Pipedrive ────────────────────────────────────────────────────────


PIPEDRIVE_OPERATIONS = ("create", "get", "update", "delete", "list", "search")
PIPEDRIVE_DEFAULT_OPERATION = "create"


def _build_pipedrive_request(cred, operation, params, item, ctx):
    """Build a Pipedrive API request config.

    Returns ``None`` when the credential lacks ``apiKey``.
    """
    api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
    base_url = str(cred.get("baseUrl") or "https://api.pipedrive.com").rstrip("/")
    if not api_key:
        return None
    resource = _resolve_param("resource", params, item, ctx) or "deals"
    token_q = f"api_token={quote(api_key, safe='')}"
    title = _resolve_param("title", params, item, ctx)
    body: dict[str, Any] = {}
    if title:
        body["title"] = title

    if operation == "create":
        return HttpRequestConfig(
            url=f"{base_url}/v1/{resource}?{token_q}",
            method="POST", headers=_json_headers(),
            body=body or None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("dealId", params, item, ctx)
        if not rid:
            return None
        url = f"{base_url}/v1/{resource}/{rid}?{token_q}"
        if operation == "get":
            return HttpRequestConfig(
                url=url, method="GET", response_mode="json", timeout=30.0,
            )
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="PUT", headers=_json_headers(),
                body=body or None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="DELETE", response_mode="json", timeout=30.0,
        )
    if operation in ("list", "search"):
        return HttpRequestConfig(
            url=f"{base_url}/v1/{resource}?{token_q}",
            method="GET", response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_pipedrive_api(data, operation):
    """Convert a Pipedrive API response to the internal envelope."""
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    deal_id = inner.get("id") or inner.get("dealId") or ""
    title = inner.get("title") or ""
    return {
        "dealId": deal_id, "title": title,
        "operation": operation, "source": "pipedrive_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_pipedrive_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("pipedrive_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "pipedrive_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "pipedriveApi")
    if cred:
        cfg = _build_pipedrive_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("pipedrive real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_pipedrive_api(resp.body, operation),
                        "pipedrive_api",
                    )
            except Exception as exc:
                logger.warning("pipedrive HTTP call failed: %s", exc)
    title = _resolve_param("title", params, item, ctx)
    return {
        "dealId": _gen_id("pd", title), "title": title,
        "operation": operation, "source": "pipedrive",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_pipedrive(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", PIPEDRIVE_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_pipedrive_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("pipedrive_response", "pipedrive_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── Zendesk ──────────────────────────────────────────────────────────


ZENDESK_OPERATIONS = ("create", "get", "update", "delete", "list", "search")
ZENDESK_DEFAULT_OPERATION = "create"


def _build_zendesk_request(cred, operation, params, item, ctx):
    """Build a Zendesk Sell API request config.

    Returns ``None`` when the credential lacks ``apiKey`` or ``baseUrl``.
    """
    api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
    base_url = str(cred.get("baseUrl") or "").rstrip("/")
    if not api_key or not base_url:
        return None
    headers = _json_headers({"Authorization": f"Bearer {api_key}"})
    resource = _resolve_param("resource", params, item, ctx) or "contacts"
    subject = _resolve_param("subject", params, item, ctx)
    body: dict[str, Any] = {}
    if subject:
        body["subject"] = subject

    if operation == "create":
        return HttpRequestConfig(
            url=f"{base_url}/v2/{resource}",
            method="POST", headers=headers, body=body or None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("ticketId", params, item, ctx)
        if not rid:
            return None
        url = f"{base_url}/v2/{resource}/{rid}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="PUT", headers=headers,
                body=body or None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="GET" if operation == "get" else "DELETE",
            headers=headers, response_mode="json", timeout=30.0,
        )
    if operation in ("list", "search"):
        return HttpRequestConfig(
            url=f"{base_url}/v2/{resource}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_zendesk_api(data, operation):
    """Convert a Zendesk API response to the internal envelope."""
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    ticket_id = inner.get("id") or inner.get("ticketId") or ""
    subject = inner.get("subject") or ""
    return {
        "ticketId": ticket_id, "subject": subject,
        "status": inner.get("status", "open"),
        "operation": operation, "source": "zendesk_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_zendesk_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("zendesk_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "zendesk_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "zendeskApi")
    if cred:
        cfg = _build_zendesk_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("zendesk real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_zendesk_api(resp.body, operation),
                        "zendesk_api",
                    )
            except Exception as exc:
                logger.warning("zendesk HTTP call failed: %s", exc)
    subject = _resolve_param("subject", params, item, ctx)
    return {
        "ticketId": _gen_id("zd", subject), "subject": subject,
        "status": "open", "operation": operation, "source": "zendesk",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_zendesk(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", ZENDESK_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_zendesk_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("zendesk_response", "zendesk_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── Zoho CRM ─────────────────────────────────────────────────────────


ZOHO_OPERATIONS = ("create", "get", "update", "delete", "list", "search")
ZOHO_DEFAULT_OPERATION = "create"


def _build_zoho_request(cred, operation, params, item, ctx):
    """Build a Zoho CRM API request config.

    Returns ``None`` when the credential lacks ``accessToken``.
    """
    token = str(cred.get("accessToken") or cred.get("access_token") or "")
    base_url = str(cred.get("baseUrl") or "https://www.zohoapis.com").rstrip("/")
    if not token:
        return None
    headers = _json_headers({"Authorization": f"Bearer {token}"})
    module = (
        _resolve_param("module", params, item, ctx)
        or _resolve_param("object", params, item, ctx)
        or "Leads"
    )
    name = _resolve_param("name", params, item, ctx)
    fields: dict[str, Any] = {}
    if name:
        fields["Name"] = name

    if operation == "create":
        return HttpRequestConfig(
            url=f"{base_url}/crm/v3/{module}",
            method="POST", headers=headers,
            body={"data": [fields]} if fields else None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("recordId", params, item, ctx)
        if not rid:
            return None
        url = f"{base_url}/crm/v3/{module}/{rid}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="PUT", headers=headers,
                body={"data": [fields]} if fields else None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="GET" if operation == "get" else "DELETE",
            headers=headers, response_mode="json", timeout=30.0,
        )
    if operation in ("list", "search"):
        return HttpRequestConfig(
            url=f"{base_url}/crm/v3/{module}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_zoho_api(data, operation):
    """Convert a Zoho CRM API response to the internal envelope."""
    inner = data.get("data")
    first: dict[str, Any] = {}
    if isinstance(inner, list) and inner and isinstance(inner[0], dict):
        first = inner[0]
    elif isinstance(inner, dict):
        first = inner
    record_id = first.get("id") or data.get("id") or ""
    name = first.get("Name") or first.get("name") or data.get("Name") or ""
    return {
        "recordId": record_id, "name": name,
        "operation": operation, "source": "zoho_crm_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_zoho_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("zoho_crm_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "zoho_crm_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "zohoApi")
    if cred:
        cfg = _build_zoho_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("zoho real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_zoho_api(resp.body, operation),
                        "zoho_crm_api",
                    )
            except Exception as exc:
                logger.warning("zoho HTTP call failed: %s", exc)
    name = _resolve_param("name", params, item, ctx)
    return {
        "recordId": _gen_id("zoho", name), "name": name,
        "operation": operation, "source": "zoho_crm",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_zoho_crm(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", ZOHO_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_zoho_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("zoho_crm_response", "zoho_crm_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── HighLevel ────────────────────────────────────────────────────────


HIGHLEVEL_OPERATIONS = ("create", "get", "update", "delete", "list")
HIGHLEVEL_DEFAULT_OPERATION = "create"


def _build_highlevel_request(cred, operation, params, item, ctx):
    """Build a GoHighLevel API request config.

    Returns ``None`` when the credential lacks ``apiKey``.
    """
    api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
    base_url = str(
        cred.get("baseUrl") or "https://services.leadconnectorhq.com"
    ).rstrip("/")
    if not api_key:
        return None
    headers = _json_headers({
        "Authorization": f"Bearer {api_key}",
        "Version": "2021-07-28",
    })
    resource = _resolve_param("resource", params, item, ctx) or "contacts"
    name = _resolve_param("name", params, item, ctx)
    body: dict[str, Any] = {}
    if name:
        body["name"] = name

    if operation == "create":
        return HttpRequestConfig(
            url=f"{base_url}/{resource}",
            method="POST", headers=headers, body=body or None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("contactId", params, item, ctx)
        if not rid:
            return None
        url = f"{base_url}/{resource}/{rid}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="PUT", headers=headers,
                body=body or None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="GET" if operation == "get" else "DELETE",
            headers=headers, response_mode="json", timeout=30.0,
        )
    if operation == "list":
        return HttpRequestConfig(
            url=f"{base_url}/{resource}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_highlevel_api(data, operation):
    """Convert a GoHighLevel API response to the internal envelope."""
    inner = data.get("contact") if isinstance(data.get("contact"), dict) else data
    contact_id = inner.get("id") or inner.get("contactId") or ""
    name = inner.get("name") or inner.get("firstName") or ""
    return {
        "contactId": contact_id, "name": name,
        "operation": operation, "source": "highlevel_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_highlevel_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("highlevel_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "highlevel_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "highlevelApi")
    if cred:
        cfg = _build_highlevel_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("highlevel real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_highlevel_api(resp.body, operation),
                        "highlevel_api",
                    )
            except Exception as exc:
                logger.warning("highlevel HTTP call failed: %s", exc)
    name = _resolve_param("name", params, item, ctx)
    return {
        "contactId": _gen_id("hl", name), "name": name,
        "operation": operation, "source": "highlevel",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_highlevel(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", HIGHLEVEL_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_highlevel_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("highlevel_response", "highlevel_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── Odoo ─────────────────────────────────────────────────────────────


ODOO_OPERATIONS = ("create", "get", "update", "delete", "list", "search")
ODOO_DEFAULT_OPERATION = "create"


async def _resolve_odoo_response(
    *, operation, params, item, node, ctx
):
    """Odoo is XML-RPC based and stays mock-only (no real HTTP step)."""
    mock = _mock_response("odoo_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "odoo_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    name = _resolve_param("name", params, item, ctx)
    return {
        "recordId": _gen_id("odoo", name), "name": name,
        "model": "res.partner", "operation": operation, "source": "odoo",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_odoo(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", ODOO_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_odoo_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("odoo_response", "odoo_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── HubSpot Trigger ──────────────────────────────────────────────────


async def exec_hubspot_trigger(node, items, *, ctx):
    payload = _trigger_payload(ctx, "hubspot_trigger_payload", "trigger_payload")
    if payload is not None:
        return [(0, [ExecutionItem(json=payload)])]
    return [(0, [ExecutionItem(json={
        "event": "contact.creation",
        "objectId": _gen_id("hs_trigger"),
        "source": "hubspot",
        "createdAt": _now_iso(),
    })])]