"""Tests for e-commerce / finance nodes (``n8n-nodes-base.*``).

Covers WooCommerce, Shopify, Stripe, Stripe Trigger, QuickBooks, Xero, PayPal, PagerDuty.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.ecommerce import (
    exec_pagerduty,
    exec_paypal,
    exec_quickbooks,
    exec_shopify,
    exec_stripe,
    exec_stripe_trigger,
    exec_woocommerce,
    exec_xero,
)
from app.services.workflows.registry import REGISTRY


def _node(params, *, type_="n8n-nodes-base.wooCommerce", id_="n1", name="WooCommerce"):
    return ExecNode(id=id_, name=name, type=type_, type_version=1, parameters=params, credentials=None, position={"x": 0, "y": 0})

def _ctx(mocks=None):
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {})

def _out_items(result):
    out = []
    for _idx, items in result:
        out.extend(items)
    return out

def _input_item(**kw):
    return ExecutionItem(json=kw)


# ── WooCommerce ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_woocommerce_dict_mock() -> None:
    node = _node({"operation": "create"})
    ctx = _ctx({"woocommerce_response": {"productId": "p1", "custom": True}})
    items = _out_items(await exec_woocommerce(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_woocommerce_offline() -> None:
    node = _node({"operation": "create", "name": "Widget"})
    items = _out_items(await exec_woocommerce(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "woocommerce"
    assert items[0].json["name"] == "Widget"


# ── Shopify ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shopify_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.shopify", name="Shopify")
    ctx = _ctx({"shopify_response": {"productId": "p1", "custom": True}})
    items = _out_items(await exec_shopify(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_shopify_offline() -> None:
    node = _node({"operation": "create", "title": "Gadget"}, type_="n8n-nodes-base.shopify")
    items = _out_items(await exec_shopify(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "shopify"
    assert items[0].json["title"] == "Gadget"


# ── Stripe ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stripe_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.stripe", name="Stripe")
    ctx = _ctx({"stripe_response": {"objectId": "pi_1", "custom": True}})
    items = _out_items(await exec_stripe(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_stripe_offline() -> None:
    node = _node({"operation": "createCharge"}, type_="n8n-nodes-base.stripe")
    items = _out_items(await exec_stripe(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "stripe"
    assert items[0].json["status"] == "succeeded"


# ── Stripe Trigger ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stripe_trigger_dict_mock() -> None:
    node = _node({}, type_="n8n-nodes-base.stripeTrigger", name="Stripe Trigger")
    ctx = _ctx({"stripe_trigger_payload": {"event": "invoice.paid", "objectId": "in_1"}})
    items = _out_items(await exec_stripe_trigger(node, [], ctx=ctx))
    assert items[0].json["objectId"] == "in_1"


@pytest.mark.asyncio
async def test_stripe_trigger_offline() -> None:
    node = _node({}, type_="n8n-nodes-base.stripeTrigger")
    items = _out_items(await exec_stripe_trigger(node, [], ctx=_ctx()))
    assert items[0].json["source"] == "stripe"
    assert "event" in items[0].json


# ── QuickBooks ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quickbooks_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.quickbooks", name="QuickBooks")
    ctx = _ctx({"quickbooks_response": {"recordId": "q1", "custom": True}})
    items = _out_items(await exec_quickbooks(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_quickbooks_offline() -> None:
    node = _node({"operation": "create", "name": "Invoice"}, type_="n8n-nodes-base.quickbooks")
    items = _out_items(await exec_quickbooks(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "quickbooks"


# ── Xero ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_xero_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.xero", name="Xero")
    ctx = _ctx({"xero_response": {"recordId": "x1", "custom": True}})
    items = _out_items(await exec_xero(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_xero_offline() -> None:
    node = _node({"operation": "create", "name": "Bill"}, type_="n8n-nodes-base.xero")
    items = _out_items(await exec_xero(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "xero"


# ── PayPal ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_paypal_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.payPal", name="PayPal")
    ctx = _ctx({"paypal_response": {"orderId": "o1", "custom": True}})
    items = _out_items(await exec_paypal(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_paypal_offline() -> None:
    node = _node({"operation": "createOrder"}, type_="n8n-nodes-base.payPal")
    items = _out_items(await exec_paypal(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "paypal"
    assert items[0].json["status"] == "COMPLETED"


# ── PagerDuty ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pagerduty_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.pagerDuty", name="PagerDuty")
    ctx = _ctx({"pagerduty_response": {"incidentId": "i1", "custom": True}})
    items = _out_items(await exec_pagerduty(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_pagerduty_offline() -> None:
    node = _node({"operation": "createIncident", "title": "Down"}, type_="n8n-nodes-base.pagerDuty")
    items = _out_items(await exec_pagerduty(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "pagerduty"
    assert items[0].json["title"] == "Down"


# ── E2E ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_stripe_to_set() -> None:
    doc = {
        "nodes": [
            {"id": "t", "name": "Manual", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "parameters": {}, "position": [0, 0]},
            {"id": "s", "name": "Stripe", "type": "n8n-nodes-base.stripe", "typeVersion": 1, "parameters": {"operation": "createCharge"}, "position": [200, 0]},
            {"id": "set", "name": "Set", "type": "n8n-nodes-base.set", "typeVersion": 1, "parameters": {"assignments": {"assignments": [{"name": "result", "value": "={{ $json.source }}", "type": "string"}]}}, "position": [400, 0]},
        ],
        "connections": {
            "t": {"main": [[{"node": "s", "index": 0}]]},
            "s": {"main": [[{"node": "set", "index": 0}]]},
        },
    }
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run()
    assert result.status == "success"
    assert result.final_items[0]["json"]["result"] == "stripe"


# ── Descriptor registration ─────────────────────────────────────────


def test_descriptors_registered() -> None:
    types = [
        "n8n-nodes-base.wooCommerce",
        "n8n-nodes-base.shopify",
        "n8n-nodes-base.stripe",
        "n8n-nodes-base.stripeTrigger",
        "n8n-nodes-base.quickbooks",
        "n8n-nodes-base.xero",
        "n8n-nodes-base.payPal",
        "n8n-nodes-base.pagerDuty",
    ]
    for t in types:
        assert t in REGISTRY, f"{t} not registered"