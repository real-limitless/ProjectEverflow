"""Tests for the Webhook + Respond to Webhook nodes (v1 in-engine)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.flow import exec_respond_to_webhook, exec_webhook


def _node(params: dict, *, type_: str, id_: str) -> ExecNode:
    return ExecNode(
        id=id_,
        name=type_.rsplit(".", 1)[-1],
        type=type_,
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx() -> EngineContext:
    g = type("G", (), {})()
    g.trigger_nodes = lambda preferred=None: []
    return EngineContext(graph=g)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_webhook_executor_seeds_item_from_mock_request() -> None:
    node = _node({}, type_="n8n-nodes-base.webhook", id_="wh1")
    ctx = _ctx()
    ctx.mocks = {
        "webhook_request": {
            "method": "POST",
            "path": "/hook",
            "headers": {"x-test": "1"},
            "query": {"q": "v"},
            "body": {"name": "alice"},
        }
    }
    out = await exec_webhook(node, [], ctx=ctx)
    items = out[0][1]
    assert len(items) == 1
    it = items[0]
    assert it.json["method"] == "POST"
    assert it.json["path"] == "/hook"
    assert it.json["body"] == {"name": "alice"}
    assert it.json["headers"]["x-test"] == "1"
    assert it.json["query"]["q"] == "v"
    # Path recorded on context for respondToWebhook
    assert "wh1" in ctx.webhook_meta
    assert ctx.webhook_meta["wh1"]["path"] == "/hook"


@pytest.mark.asyncio
async def test_webhook_executor_without_mock_uses_empty_payload() -> None:
    node = _node({}, type_="n8n-nodes-base.webhook", id_="wh1")
    ctx = _ctx()
    out = await exec_webhook(node, [], ctx=ctx)
    items = out[0][1]
    assert len(items) == 1
    it = items[0]
    assert it.json["method"] == "POST"
    assert it.json["body"] is None


@pytest.mark.asyncio
async def test_respond_to_webhook_default_captures_last_item() -> None:
    node = _node(
        {"options": {"responseMode": "lastNode"}},
        type_="n8n-nodes-base.respondToWebhook",
        id_="rw1",
    )
    ctx = _ctx()
    items = [
        ExecutionItem(json={"a": 1}),
        ExecutionItem(json={"result": "ok", "n": 42}),
    ]
    out = await exec_respond_to_webhook(node, items, ctx=ctx)
    assert out[0][1] == items
    assert ctx.webhook_response is not None
    assert ctx.webhook_response["status"] == 200
    assert ctx.webhook_response["body"] == {"result": "ok", "n": 42}


@pytest.mark.asyncio
async def test_respond_to_webhook_all_entries_captures_all_items() -> None:
    node = _node(
        {"options": {"responseMode": "allEntries"}},
        type_="n8n-nodes-base.respondToWebhook",
        id_="rw1",
    )
    ctx = _ctx()
    items = [ExecutionItem(json={"i": i}) for i in range(3)]
    out = await exec_respond_to_webhook(node, items, ctx=ctx)
    assert ctx.webhook_response is not None
    body = ctx.webhook_response["body"]
    assert isinstance(body, list) and len(body) == 3


@pytest.mark.asyncio
async def test_respond_to_webhook_response_body_override() -> None:
    node = _node(
        {"responseBody": {"forced": True}},
        type_="n8n-nodes-base.respondToWebhook",
        id_="rw1",
    )
    ctx = _ctx()
    items = [ExecutionItem(json={"a": 1})]
    await exec_respond_to_webhook(node, items, ctx=ctx)
    assert ctx.webhook_response["body"] == {"forced": True}


@pytest.mark.asyncio
async def test_respond_to_webhook_custom_status() -> None:
    node = _node(
        {"options": {"responseCode": 201, "responseMode": "lastNode"}},
        type_="n8n-nodes-base.respondToWebhook",
        id_="rw1",
    )
    ctx = _ctx()
    items = [ExecutionItem(json={"ok": True})]
    await exec_respond_to_webhook(node, items, ctx=ctx)
    assert ctx.webhook_response["status"] == 201


@pytest.mark.asyncio
async def test_webhook_full_workflow_engine_responds() -> None:
    """End-to-end: webhook → set → respondToWebhook. Engine should record
    the response so the platform API can return it."""
    doc = {
        "name": "webhook-test",
        "nodes": [
            {
                "id": "wh1",
                "name": "Hook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1,
                "position": [0, 0],
                "parameters": {},
            },
            {
                "id": "s1",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3,
                "position": [200, 0],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            {"name": "greeting", "value": "hi", "type": "string"},
                        ]
                    },
                    "includeOtherFields": True,
                },
            },
            {
                "id": "rw1",
                "name": "Respond",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1,
                "position": [400, 0],
                "parameters": {"options": {"responseMode": "lastNode"}},
            },
        ],
        "connections": {
            "Hook": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
            "Set": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
        },
    }
    mocks = {
        "webhook_request": {
            "method": "POST",
            "path": "/hook",
            "headers": {},
            "query": {},
            "body": {"name": "alice"},
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="webhook")
    assert result.status == "success", result.error_message
    assert engine.last_webhook_response is not None
    body = engine.last_webhook_response["body"]
    assert body.get("greeting") == "hi"
    assert body.get("webhook") is True
