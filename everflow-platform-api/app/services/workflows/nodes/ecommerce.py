"""E-commerce / finance executors (clean-room ``n8n-nodes-base.*``).

Implements WooCommerce, Shopify, Stripe, Stripe Trigger, QuickBooks, Xero, PayPal, PagerDuty.
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


# ── WooCommerce ──────────────────────────────────────────────────────


WOOCOMMERCE_OPERATIONS = ("create", "get", "update", "delete", "list")
WOOCOMMERCE_DEFAULT_OPERATION = "create"


async def exec_woocommerce(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", WOOCOMMERCE_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("woocommerce_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={
            "productId": _gen_id("wc", name), "name": name,
            "operation": operation, "source": "woocommerce",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── Shopify ──────────────────────────────────────────────────────────


SHOPIFY_OPERATIONS = ("create", "get", "update", "delete", "list")
SHOPIFY_DEFAULT_OPERATION = "create"


async def exec_shopify(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", SHOPIFY_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("shopify_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        title = _resolve_param("title", params, item, ctx)
        out.append(ExecutionItem(json={
            "productId": _gen_id("shop", title), "title": title,
            "operation": operation, "source": "shopify",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── Stripe ───────────────────────────────────────────────────────────


STRIPE_OPERATIONS = ("create", "get", "update", "delete", "list", "createCharge", "createPaymentIntent")
STRIPE_DEFAULT_OPERATION = "create"


async def exec_stripe(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", STRIPE_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("stripe_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        out.append(ExecutionItem(json={
            "objectId": _gen_id("stripe", operation),
            "operation": operation, "source": "stripe",
            "status": "succeeded",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── Stripe Trigger ───────────────────────────────────────────────────


async def exec_stripe_trigger(node, items, *, ctx):
    payload = _trigger_payload(ctx, "stripe_trigger_payload", "trigger_payload")
    if payload is not None:
        return [(0, [ExecutionItem(json=payload)])]
    return [(0, [ExecutionItem(json={
        "event": "payment_intent.succeeded",
        "objectId": _gen_id("stripe_trig"),
        "source": "stripe",
        "createdAt": _now_iso(),
    })])]


# ── QuickBooks ───────────────────────────────────────────────────────


QUICKBOOKS_OPERATIONS = ("create", "get", "update", "delete", "list", "query")
QUICKBOOKS_DEFAULT_OPERATION = "create"


async def exec_quickbooks(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", QUICKBOOKS_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("quickbooks_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={
            "recordId": _gen_id("qb", name), "name": name,
            "operation": operation, "source": "quickbooks",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── Xero ─────────────────────────────────────────────────────────────


XERO_OPERATIONS = ("create", "get", "update", "delete", "list")
XERO_DEFAULT_OPERATION = "create"


async def exec_xero(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", XERO_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("xero_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        name = _resolve_param("name", params, item, ctx)
        out.append(ExecutionItem(json={
            "recordId": _gen_id("xero", name), "name": name,
            "operation": operation, "source": "xero",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── PayPal ───────────────────────────────────────────────────────────


PAYPAL_OPERATIONS = ("create", "get", "update", "list", "createOrder", "capturePayment")
PAYPAL_DEFAULT_OPERATION = "create"


async def exec_paypal(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", PAYPAL_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("paypal_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        out.append(ExecutionItem(json={
            "orderId": _gen_id("paypal", operation),
            "operation": operation, "source": "paypal",
            "status": "COMPLETED",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]


# ── PagerDuty ────────────────────────────────────────────────────────


PAGERDUTY_OPERATIONS = ("create", "get", "update", "delete", "list", "createIncident")
PAGERDUTY_DEFAULT_OPERATION = "create"


async def exec_pagerduty(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", PAGERDUTY_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("pagerduty_response", operation, params, item, ctx)
        if mock:
            out.append(ExecutionItem(json=mock))
            continue
        http = _http_response(ctx)
        if http:
            out.append(ExecutionItem(json=http))
            continue
        title = _resolve_param("title", params, item, ctx)
        out.append(ExecutionItem(json={
            "incidentId": _gen_id("pd", title), "title": title,
            "status": "triggered", "operation": operation, "source": "pagerduty",
            "updatedAt": _now_iso(),
        }))
    return [(0, out)]