"""Tests for CRM nodes (``n8n-nodes-base.*``).

Covers Salesforce, Pipedrive, Zendesk, Zoho CRM, HighLevel, Odoo, HubSpot Trigger.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.crm import (
    exec_highlevel,
    exec_hubspot_trigger,
    exec_odoo,
    exec_pipedrive,
    exec_salesforce,
    exec_zendesk,
    exec_zoho_crm,
)
from app.services.workflows.registry import REGISTRY


def _node(params, *, type_="n8n-nodes-base.salesforce", id_="n1", name="Salesforce"):
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


# ── Salesforce ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_salesforce_dict_mock() -> None:
    node = _node({"operation": "create"})
    ctx = _ctx({"salesforce_response": {"recordId": "r1", "custom": True}})
    items = _out_items(await exec_salesforce(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_salesforce_callable_mock() -> None:
    calls = []
    def mock(op, params, item, c):
        calls.append(op)
        return {"recordId": "r2", "ok": True}
    node = _node({"operation": "create"})
    items = _out_items(await exec_salesforce(node, [_input_item()], ctx=_ctx({"salesforce_response": mock})))
    assert items[0].json["ok"] is True
    assert calls == ["create"]


@pytest.mark.asyncio
async def test_salesforce_http_fallback() -> None:
    node = _node({"operation": "create"})
    ctx = _ctx({"http_response": {"status_code": 200, "body": {"recordId": "hr1"}}})
    items = _out_items(await exec_salesforce(node, [_input_item()], ctx=ctx))
    assert items[0].json["recordId"] == "hr1"


@pytest.mark.asyncio
async def test_salesforce_offline() -> None:
    node = _node({"operation": "create", "name": "Acme"})
    items = _out_items(await exec_salesforce(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "salesforce"
    assert items[0].json["name"] == "Acme"


# ── Pipedrive ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipedrive_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.pipedrive", name="Pipedrive")
    ctx = _ctx({"pipedrive_response": {"dealId": "d1", "custom": True}})
    items = _out_items(await exec_pipedrive(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_pipedrive_offline() -> None:
    node = _node({"operation": "create", "title": "Big Deal"}, type_="n8n-nodes-base.pipedrive")
    items = _out_items(await exec_pipedrive(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "pipedrive"
    assert items[0].json["title"] == "Big Deal"


# ── Zendesk ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zendesk_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.zendesk", name="Zendesk")
    ctx = _ctx({"zendesk_response": {"ticketId": "t1", "custom": True}})
    items = _out_items(await exec_zendesk(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_zendesk_offline() -> None:
    node = _node({"operation": "create", "subject": "Help"}, type_="n8n-nodes-base.zendesk")
    items = _out_items(await exec_zendesk(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "zendesk"
    assert items[0].json["subject"] == "Help"


# ── Zoho CRM ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zoho_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.zohoCrm", name="Zoho")
    ctx = _ctx({"zoho_crm_response": {"recordId": "z1", "custom": True}})
    items = _out_items(await exec_zoho_crm(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_zoho_offline() -> None:
    node = _node({"operation": "create", "name": "Lead"}, type_="n8n-nodes-base.zohoCrm")
    items = _out_items(await exec_zoho_crm(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "zoho_crm"


# ── HighLevel ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_highlevel_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.highLevel", name="HighLevel")
    ctx = _ctx({"highlevel_response": {"contactId": "h1", "custom": True}})
    items = _out_items(await exec_highlevel(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_highlevel_offline() -> None:
    node = _node({"operation": "create", "name": "Bob"}, type_="n8n-nodes-base.highLevel")
    items = _out_items(await exec_highlevel(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "highlevel"


# ── Odoo ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_odoo_dict_mock() -> None:
    node = _node({"operation": "create"}, type_="n8n-nodes-base.odoo", name="Odoo")
    ctx = _ctx({"odoo_response": {"recordId": "o1", "custom": True}})
    items = _out_items(await exec_odoo(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_odoo_offline() -> None:
    node = _node({"operation": "create", "name": "Partner"}, type_="n8n-nodes-base.odoo")
    items = _out_items(await exec_odoo(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "odoo"
    assert items[0].json["model"] == "res.partner"


# ── HubSpot Trigger ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hubspot_trigger_dict_mock() -> None:
    node = _node({}, type_="n8n-nodes-base.hubspotTrigger", name="HubSpot Trigger")
    ctx = _ctx({"hubspot_trigger_payload": {"event": "contact.update", "objectId": "x1"}})
    items = _out_items(await exec_hubspot_trigger(node, [], ctx=ctx))
    assert items[0].json["objectId"] == "x1"


@pytest.mark.asyncio
async def test_hubspot_trigger_trigger_payload_alias() -> None:
    node = _node({}, type_="n8n-nodes-base.hubspotTrigger")
    ctx = _ctx({"trigger_payload": {"event": "deal.creation"}})
    items = _out_items(await exec_hubspot_trigger(node, [], ctx=ctx))
    assert items[0].json["event"] == "deal.creation"


@pytest.mark.asyncio
async def test_hubspot_trigger_offline() -> None:
    node = _node({}, type_="n8n-nodes-base.hubspotTrigger")
    items = _out_items(await exec_hubspot_trigger(node, [], ctx=_ctx()))
    assert items[0].json["source"] == "hubspot"
    assert "event" in items[0].json


# ── E2E ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_salesforce_to_set() -> None:
    doc = {
        "nodes": [
            {"id": "t", "name": "Manual", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "parameters": {}, "position": [0, 0]},
            {"id": "s", "name": "Salesforce", "type": "n8n-nodes-base.salesforce", "typeVersion": 1, "parameters": {"operation": "create", "name": "Test"}, "position": [200, 0]},
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
    assert result.final_items[0]["json"]["result"] == "salesforce"


# ── Descriptor registration ─────────────────────────────────────────


def test_descriptors_registered() -> None:
    types = [
        "n8n-nodes-base.salesforce",
        "n8n-nodes-base.pipedrive",
        "n8n-nodes-base.zendesk",
        "n8n-nodes-base.zohoCrm",
        "n8n-nodes-base.highLevel",
        "n8n-nodes-base.odoo",
        "n8n-nodes-base.hubspotTrigger",
    ]
    for t in types:
        assert t in REGISTRY, f"{t} not registered"