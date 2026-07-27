"""E-commerce / finance executors (clean-room ``n8n-nodes-base.*``).

Implements WooCommerce, Shopify, Stripe, Stripe Trigger, QuickBooks, Xero, PayPal, PagerDuty.

Each response executor follows a credential-aware precedence chain:

1. ``ctx.mocks['<service>_response']`` — dict or callable (test/dry-run)
2. ``ctx.mocks['http_response']`` — generic HTTP mock body fallback
3. **If a credential resolves** (e.g. ``stripeApi``), a real HTTP call is
   made via :func:`execute_http_request` and the API response is converted to
   the internal envelope. On exception the executor falls through to offline.
4. Offline synthetic response tagged with ``source``.

When the result comes from the real API, ``source`` is set to
``"<service>_api"`` and no ``mockSource`` is added. For the
``http_response`` and offline fallbacks, a ``mockSource`` field records the
origin.
"""

from __future__ import annotations

import base64
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


def _basic_auth_header(user: str, pw: str) -> str:
    raw = f"{user}:{pw}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


# ── WooCommerce ──────────────────────────────────────────────────────


WOOCOMMERCE_OPERATIONS = ("create", "get", "update", "delete", "list")
WOOCOMMERCE_DEFAULT_OPERATION = "create"


def _build_woocommerce_request(cred, operation, params, item, ctx):
    """Build a WooCommerce REST API request config.

    Returns ``None`` when the credential lacks ``baseUrl``,
    ``consumerKey``, or ``consumerSecret``.
    """
    base_url = str(cred.get("baseUrl") or "").rstrip("/")
    consumer_key = str(cred.get("consumerKey") or cred.get("consumer_key") or "")
    consumer_secret = str(cred.get("consumerSecret") or cred.get("consumer_secret") or "")
    if not base_url or not consumer_key or not consumer_secret:
        return None
    headers = _json_headers({
        "Authorization": _basic_auth_header(consumer_key, consumer_secret),
    })
    resource = _resolve_param("resource", params, item, ctx) or "products"
    name = _resolve_param("name", params, item, ctx)
    body: dict[str, Any] = {}
    if name:
        body["name"] = name

    if operation == "create":
        return HttpRequestConfig(
            url=f"{base_url}/wp-json/wc/v3/{resource}",
            method="POST", headers=headers, body=body or None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("productId", params, item, ctx)
        if not rid:
            return None
        url = f"{base_url}/wp-json/wc/v3/{resource}/{rid}"
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
            url=f"{base_url}/wp-json/wc/v3/{resource}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_woocommerce_api(data, operation):
    """Convert a WooCommerce REST API response to the internal envelope."""
    product_id = data.get("id") or data.get("productId") or ""
    name = data.get("name") or ""
    return {
        "productId": product_id, "name": name,
        "operation": operation, "source": "woocommerce_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_woocommerce_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("woocommerce_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "woocommerce_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "woocommerceApi")
    if cred:
        cfg = _build_woocommerce_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("woocommerce real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_woocommerce_api(resp.body, operation),
                        "woocommerce_api",
                    )
            except Exception as exc:
                logger.warning("woocommerce HTTP call failed: %s", exc)
    name = _resolve_param("name", params, item, ctx)
    return {
        "productId": _gen_id("wc", name), "name": name,
        "operation": operation, "source": "woocommerce",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_woocommerce(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", WOOCOMMERCE_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_woocommerce_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("woocommerce_response", "woocommerce_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── Shopify ──────────────────────────────────────────────────────────


SHOPIFY_OPERATIONS = ("create", "get", "update", "delete", "list")
SHOPIFY_DEFAULT_OPERATION = "create"


def _build_shopify_request(cred, operation, params, item, ctx):
    """Build a Shopify Admin API request config.

    Returns ``None`` when the credential lacks ``shopName`` or ``apiKey``.
    """
    shop_name = str(cred.get("shopName") or cred.get("shop") or "")
    api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
    password = str(cred.get("password") or "")
    if not shop_name or not api_key:
        return None
    headers = _json_headers({"Authorization": _basic_auth_header(api_key, password)})
    resource = _resolve_param("resource", params, item, ctx) or "products"
    title = _resolve_param("title", params, item, ctx)
    body: dict[str, Any] = {}
    if title:
        body["title"] = title

    if operation == "create":
        return HttpRequestConfig(
            url=f"https://{shop_name}.myshopify.com/admin/api/2024-01/{resource}.json",
            method="POST", headers=headers,
            body={resource[:-1] if resource.endswith("s") else resource: body} if body else None,
            body_mode="json", response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("productId", params, item, ctx)
        if not rid:
            return None
        url = f"https://{shop_name}.myshopify.com/admin/api/2024-01/{resource}/{rid}.json"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="PUT", headers=headers,
                body={resource[:-1] if resource.endswith("s") else resource: body} if body else None,
                body_mode="json", response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="GET" if operation == "get" else "DELETE",
            headers=headers, response_mode="json", timeout=30.0,
        )
    if operation == "list":
        return HttpRequestConfig(
            url=f"https://{shop_name}.myshopify.com/admin/api/2024-01/{resource}.json",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_shopify_api(data, operation):
    """Convert a Shopify Admin API response to the internal envelope."""
    inner = data
    for key in data:
        if isinstance(data.get(key), dict):
            inner = data[key]
            break
    product_id = inner.get("id") or inner.get("productId") or ""
    title = inner.get("title") or ""
    return {
        "productId": product_id, "title": title,
        "operation": operation, "source": "shopify_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_shopify_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("shopify_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "shopify_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "shopifyApi")
    if cred:
        cfg = _build_shopify_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("shopify real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_shopify_api(resp.body, operation),
                        "shopify_api",
                    )
            except Exception as exc:
                logger.warning("shopify HTTP call failed: %s", exc)
    title = _resolve_param("title", params, item, ctx)
    return {
        "productId": _gen_id("shop", title), "title": title,
        "operation": operation, "source": "shopify",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_shopify(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", SHOPIFY_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_shopify_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("shopify_response", "shopify_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── Stripe ───────────────────────────────────────────────────────────


STRIPE_OPERATIONS = ("create", "get", "update", "delete", "list", "createCharge", "createPaymentIntent")
STRIPE_DEFAULT_OPERATION = "create"


def _build_stripe_request(cred, operation, params, item, ctx):
    """Build a Stripe API request config.

    Returns ``None`` when the credential lacks ``secretKey``.
    """
    secret = str(cred.get("secretKey") or cred.get("secret_key") or "")
    if not secret:
        return None
    headers = {"Authorization": f"Bearer {secret}"}
    resource_map = {
        "createCharge": "charges",
        "createPaymentIntent": "payment_intents",
    }
    resource = (
        resource_map.get(operation)
        or _resolve_param("resource", params, item, ctx)
        or "customers"
    )
    name = _resolve_param("name", params, item, ctx)
    body: dict[str, Any] = {}
    if name:
        body["name"] = name

    if operation in ("create", "createCharge", "createPaymentIntent"):
        return HttpRequestConfig(
            url=f"https://api.stripe.com/v1/{resource}",
            method="POST", headers=headers,
            body=body or None, body_mode="form",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("objectId", params, item, ctx)
        if not rid:
            return None
        url = f"https://api.stripe.com/v1/{resource}/{rid}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="POST", headers=headers,
                body=body or None, body_mode="form",
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="GET" if operation == "get" else "DELETE",
            headers=headers, response_mode="json", timeout=30.0,
        )
    if operation == "list":
        return HttpRequestConfig(
            url=f"https://api.stripe.com/v1/{resource}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_stripe_api(data, operation):
    """Convert a Stripe API response to the internal envelope."""
    obj_id = data.get("id") or data.get("objectId") or ""
    status = data.get("status") or "succeeded"
    return {
        "objectId": obj_id,
        "operation": operation, "source": "stripe_api",
        "status": status,
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_stripe_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("stripe_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "stripe_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "stripeApi")
    if cred:
        cfg = _build_stripe_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("stripe real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_stripe_api(resp.body, operation),
                        "stripe_api",
                    )
            except Exception as exc:
                logger.warning("stripe HTTP call failed: %s", exc)
    return {
        "objectId": _gen_id("stripe", operation),
        "operation": operation, "source": "stripe",
        "status": "succeeded",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_stripe(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", STRIPE_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_stripe_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("stripe_response", "stripe_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
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


def _build_quickbooks_request(cred, operation, params, item, ctx):
    """Build a QuickBooks API request config.

    Returns ``None`` when the credential lacks ``accessToken`` or ``realmId``.
    """
    token = str(cred.get("accessToken") or cred.get("access_token") or "")
    realm_id = str(cred.get("realmId") or cred.get("realm_id") or "")
    base_url = str(
        cred.get("baseUrl") or "https://quickbooks.api.intuit.com"
    ).rstrip("/")
    if not token or not realm_id:
        return None
    headers = _json_headers({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    resource = _resolve_param("resource", params, item, ctx) or "customer"
    name = _resolve_param("name", params, item, ctx)
    body: dict[str, Any] = {}
    if name:
        body["Name"] = name
    base = f"{base_url}/v3/company/{realm_id}/{resource}"

    if operation == "create":
        return HttpRequestConfig(
            url=base, method="POST", headers=headers,
            body=body or None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("recordId", params, item, ctx)
        if not rid:
            return None
        url = f"{base}/{rid}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="POST", headers=headers,
                body=body or None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        if operation == "get":
            return HttpRequestConfig(
                url=url, method="GET", headers=headers,
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="POST", headers=headers,
            body={"operation": "delete"}, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("list", "query"):
        query = _resolve_param("query", params, item, ctx) or f"SELECT * FROM {resource.capitalize()} MAXRESULTS 100"
        return HttpRequestConfig(
            url=f"{base}?query={quote(query)}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_quickbooks_api(data, operation):
    """Convert a QuickBooks API response to the internal envelope."""
    inner = data.get("Customer") if isinstance(data.get("Customer"), dict) else data
    record_id = inner.get("Id") or inner.get("id") or data.get("id") or ""
    name = inner.get("Name") or inner.get("name") or ""
    return {
        "recordId": record_id, "name": name,
        "operation": operation, "source": "quickbooks_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_quickbooks_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("quickbooks_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "quickbooks_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "quickbooksApi")
    if cred:
        cfg = _build_quickbooks_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("quickbooks real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_quickbooks_api(resp.body, operation),
                        "quickbooks_api",
                    )
            except Exception as exc:
                logger.warning("quickbooks HTTP call failed: %s", exc)
    name = _resolve_param("name", params, item, ctx)
    return {
        "recordId": _gen_id("qb", name), "name": name,
        "operation": operation, "source": "quickbooks",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_quickbooks(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", QUICKBOOKS_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_quickbooks_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("quickbooks_response", "quickbooks_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── Xero ─────────────────────────────────────────────────────────────


XERO_OPERATIONS = ("create", "get", "update", "delete", "list")
XERO_DEFAULT_OPERATION = "create"


def _build_xero_request(cred, operation, params, item, ctx):
    """Build a Xero API request config.

    Returns ``None`` when the credential lacks ``accessToken``.
    """
    token = str(cred.get("accessToken") or cred.get("access_token") or "")
    if not token:
        return None
    headers = _json_headers({
        "Authorization": f"Bearer {token}",
        "Xero-tenant-id": str(cred.get("tenantId") or cred.get("tenant_id") or ""),
    })
    resource = _resolve_param("resource", params, item, ctx) or "Contacts"
    name = _resolve_param("name", params, item, ctx)
    body: dict[str, Any] = {}
    if name:
        body["Name"] = name

    if operation == "create":
        return HttpRequestConfig(
            url=f"https://api.xero.com/api.xro/2.0/{resource}",
            method="PUT", headers=headers,
            body={resource: [body]} if body else None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("recordId", params, item, ctx)
        if not rid:
            return None
        url = f"https://api.xero.com/api.xro/2.0/{resource}/{rid}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="POST", headers=headers,
                body={resource: [body]} if body else None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        if operation == "get":
            return HttpRequestConfig(
                url=url, method="GET", headers=headers,
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="DELETE", headers=headers,
            response_mode="json", timeout=30.0,
        )
    if operation == "list":
        return HttpRequestConfig(
            url=f"https://api.xero.com/api.xro/2.0/{resource}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_xero_api(data, operation):
    """Convert a Xero API response to the internal envelope."""
    inner = data
    for key in data:
        if isinstance(data.get(key), list) and data[key] and isinstance(data[key][0], dict):
            inner = data[key][0]
            break
    record_id = inner.get("ContactID") or inner.get("id") or data.get("id") or ""
    name = inner.get("Name") or inner.get("name") or ""
    return {
        "recordId": record_id, "name": name,
        "operation": operation, "source": "xero_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_xero_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("xero_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "xero_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "xeroApi")
    if cred:
        cfg = _build_xero_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("xero real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_xero_api(resp.body, operation),
                        "xero_api",
                    )
            except Exception as exc:
                logger.warning("xero HTTP call failed: %s", exc)
    name = _resolve_param("name", params, item, ctx)
    return {
        "recordId": _gen_id("xero", name), "name": name,
        "operation": operation, "source": "xero",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_xero(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", XERO_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_xero_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("xero_response", "xero_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── PayPal ───────────────────────────────────────────────────────────


PAYPAL_OPERATIONS = ("create", "get", "update", "list", "createOrder", "capturePayment")
PAYPAL_DEFAULT_OPERATION = "create"


def _build_paypal_request(cred, operation, params, item, ctx):
    """Build a PayPal API request config.

    Returns ``None`` when the credential lacks ``clientId`` or ``clientSecret``.
    """
    client_id = str(cred.get("clientId") or cred.get("client_id") or "")
    client_secret = str(cred.get("clientSecret") or cred.get("client_secret") or "")
    base_url = str(
        cred.get("baseUrl") or "https://api-m.paypal.com"
    ).rstrip("/")
    if not client_id or not client_secret:
        return None
    headers = _json_headers({
        "Authorization": _basic_auth_header(client_id, client_secret),
    })
    resource_map = {
        "createOrder": "checkout/orders",
        "capturePayment": "payments/captures",
    }
    resource = (
        resource_map.get(operation)
        or _resolve_param("resource", params, item, ctx)
        or "orders"
    )
    amount = _resolve_param("amount", params, item, ctx)
    currency = _resolve_param("currency", params, item, ctx, default="USD")
    body: dict[str, Any] = {}
    if operation in ("create", "createOrder"):
        body["intent"] = "CAPTURE"
        if amount:
            body["purchase_units"] = [{
                "amount": {"currency_code": currency, "value": amount},
            }]

    if operation in ("create", "createOrder"):
        return HttpRequestConfig(
            url=f"{base_url}/v2/{resource}",
            method="POST", headers=headers, body=body or None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation == "capturePayment":
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("orderId", params, item, ctx)
        if not rid:
            return None
        return HttpRequestConfig(
            url=f"{base_url}/v2/{resource}/{rid}/capture",
            method="POST", headers=headers, body=None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("orderId", params, item, ctx)
        if not rid:
            return None
        url = f"{base_url}/v2/{resource}/{rid}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="PATCH", headers=headers,
                body=body or None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="GET", headers=headers,
            response_mode="json", timeout=30.0,
        )
    if operation == "list":
        return HttpRequestConfig(
            url=f"{base_url}/v2/{resource}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_paypal_api(data, operation):
    """Convert a PayPal API response to the internal envelope."""
    order_id = data.get("id") or data.get("orderId") or ""
    status = data.get("status") or "COMPLETED"
    return {
        "orderId": order_id,
        "operation": operation, "source": "paypal_api",
        "status": status,
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_paypal_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("paypal_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "paypal_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "paypalApi")
    if cred:
        cfg = _build_paypal_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("paypal real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_paypal_api(resp.body, operation),
                        "paypal_api",
                    )
            except Exception as exc:
                logger.warning("paypal HTTP call failed: %s", exc)
    return {
        "orderId": _gen_id("paypal", operation),
        "operation": operation, "source": "paypal",
        "status": "COMPLETED",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_paypal(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", PAYPAL_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_paypal_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("paypal_response", "paypal_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]


# ── PagerDuty ────────────────────────────────────────────────────────


PAGERDUTY_OPERATIONS = ("create", "get", "update", "delete", "list", "createIncident")
PAGERDUTY_DEFAULT_OPERATION = "create"


def _build_pagerduty_request(cred, operation, params, item, ctx):
    """Build a PagerDuty API request config.

    Returns ``None`` when the credential lacks ``apiKey``.
    """
    api_key = str(cred.get("apiKey") or cred.get("api_key") or "")
    if not api_key:
        return None
    headers = _json_headers({
        "Authorization": f"Token token={api_key}",
        "Accept": "application/json",
    })
    resource_map = {
        "createIncident": "incidents",
    }
    resource = (
        resource_map.get(operation)
        or _resolve_param("resource", params, item, ctx)
        or "incidents"
    )
    title = _resolve_param("title", params, item, ctx)
    body: dict[str, Any] = {}
    if title:
        body["title"] = title

    if operation in ("create", "createIncident"):
        return HttpRequestConfig(
            url=f"https://api.pagerduty.com/{resource}",
            method="POST", headers=headers,
            body={"incident": body} if body else None, body_mode="json",
            response_mode="json", timeout=30.0,
        )
    if operation in ("get", "update", "delete"):
        rid = _resolve_param("id", params, item, ctx) or _resolve_param("incidentId", params, item, ctx)
        if not rid:
            return None
        url = f"https://api.pagerduty.com/{resource}/{rid}"
        if operation == "update":
            return HttpRequestConfig(
                url=url, method="PUT", headers=headers,
                body={"incident": body} if body else None, body_mode="json",
                response_mode="json", timeout=30.0,
            )
        return HttpRequestConfig(
            url=url, method="GET" if operation == "get" else "DELETE",
            headers=headers, response_mode="json", timeout=30.0,
        )
    if operation == "list":
        return HttpRequestConfig(
            url=f"https://api.pagerduty.com/{resource}",
            method="GET", headers=headers, response_mode="json", timeout=30.0,
        )
    return None


def _envelope_from_pagerduty_api(data, operation):
    """Convert a PagerDuty API response to the internal envelope."""
    inner = data.get("incident") if isinstance(data.get("incident"), dict) else data
    incident_id = inner.get("id") or inner.get("incidentId") or ""
    title = inner.get("title") or ""
    return {
        "incidentId": incident_id, "title": title,
        "status": inner.get("status", "triggered"),
        "operation": operation, "source": "pagerduty_api",
        "updatedAt": _now_iso(), "raw": data,
    }


async def _resolve_pagerduty_response(
    *, operation, params, item, node, ctx
):
    mock = _mock_response("pagerduty_response", operation, params, item, ctx)
    if mock:
        return dict(mock), "pagerduty_response"
    http = _http_response(ctx)
    if http:
        return dict(http), "http_response"
    cred = resolve_credential(node, ctx, "pagerDutyApi")
    if cred:
        cfg = _build_pagerduty_request(cred, operation, params, item, ctx)
        if cfg is not None:
            logger.info("pagerduty real HTTP call operation=%s", operation)
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        _envelope_from_pagerduty_api(resp.body, operation),
                        "pagerduty_api",
                    )
            except Exception as exc:
                logger.warning("pagerduty HTTP call failed: %s", exc)
    title = _resolve_param("title", params, item, ctx)
    return {
        "incidentId": _gen_id("pd", title), "title": title,
        "status": "triggered", "operation": operation, "source": "pagerduty",
        "updatedAt": _now_iso(),
    }, "offline"


async def exec_pagerduty(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", PAGERDUTY_DEFAULT_OPERATION)
    out = []
    for item in items:
        envelope, source = await _resolve_pagerduty_response(
            operation=operation, params=params, item=item, node=node, ctx=ctx,
        )
        if source not in ("pagerduty_response", "pagerduty_api"):
            envelope["mockSource"] = source
        out.append(ExecutionItem(json=envelope))
    return [(0, out)]