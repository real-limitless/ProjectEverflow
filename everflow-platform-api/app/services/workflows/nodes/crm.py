"""CRM executors (clean-room ``n8n-nodes-base.*``).

Implements Salesforce, Pipedrive, Zendesk, Zoho CRM, HighLevel, Odoo, HubSpot Trigger.
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


# ── Salesforce ───────────────────────────────────────────────────────


SALESFORCE_OPERATIONS = ("create", "get", "update", "delete", "list", "upsert")
SALESFORCE_DEFAULT_OPERATION = "create"


async def exec_salesforce(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", SALESFORCE_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("salesforce_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={
            "recordId": _gen_id("sf", name), "name": name,
            "operation": operation, "source": "salesforce",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── Pipedrive ────────────────────────────────────────────────────────


PIPEDRIVE_OPERATIONS = ("create", "get", "update", "delete", "list", "search")
PIPEDRIVE_DEFAULT_OPERATION = "create"


async def exec_pipedrive(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", PIPEDRIVE_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("pipedrive_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        title = _resolve_param("title", params, item, ctx)
        out.append(ExecutionItem(json={
            "dealId": _gen_id("pd", title), "title": title,
            "operation": operation, "source": "pipedrive",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── Zendesk ──────────────────────────────────────────────────────────


ZENDESK_OPERATIONS = ("create", "get", "update", "delete", "list", "search")
ZENDESK_DEFAULT_OPERATION = "create"


async def exec_zendesk(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", ZENDESK_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("zendesk_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        subject = _resolve_param("subject", params, item, ctx)
        out.append(ExecutionItem(json={
            "ticketId": _gen_id("zd", subject), "subject": subject,
            "status": "open", "operation": operation, "source": "zendesk",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── Zoho CRM ─────────────────────────────────────────────────────────


ZOHO_OPERATIONS = ("create", "get", "update", "delete", "list", "search")
ZOHO_DEFAULT_OPERATION = "create"


async def exec_zoho_crm(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", ZOHO_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("zoho_crm_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={
            "recordId": _gen_id("zoho", name), "name": name,
            "operation": operation, "source": "zoho_crm",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── HighLevel ────────────────────────────────────────────────────────


HIGHLEVEL_OPERATIONS = ("create", "get", "update", "delete", "list")
HIGHLEVEL_DEFAULT_OPERATION = "create"


async def exec_highlevel(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", HIGHLEVEL_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("highlevel_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={
            "contactId": _gen_id("hl", name), "name": name,
            "operation": operation, "source": "highlevel",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── Odoo ─────────────────────────────────────────────────────────────


ODOO_OPERATIONS = ("create", "get", "update", "delete", "list", "search")
ODOO_DEFAULT_OPERATION = "create"


async def exec_odoo(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", ODOO_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("odoo_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={
            "recordId": _gen_id("odoo", name), "name": name,
            "model": "res.partner", "operation": operation, "source": "odoo",
            "updatedAt": _now_iso(),
        }))
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