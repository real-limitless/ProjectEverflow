"""Tests for messaging extra executors (List B)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes.messaging_extra import (
    exec_gotify,
    exec_matrix,
    exec_mattermost,
    exec_message_bird,
    exec_pushbullet,
    exec_pushover,
    exec_rocket_chat,
    exec_sms77,
)


def _node(
    type_: str,
    params: dict[str, Any] | None = None,
    id_: str = "n1",
    name: str = "Node",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(mocks: dict[str, Any] | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {}, run_id="test")  # type: ignore[arg-type]


def _items(rows: list[dict] | None = None):
    return items_from_json_list(rows or [])


def _out_items(result):
    out = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── Mattermost ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mattermost_mock_dict() -> None:
    node = _node("n8n-nodes-base.mattermost", {"channelId": "ch1", "message": "hi"})
    ctx = _ctx({"mattermost_response": {"messageId": "m9", "channelId": "ch1"}})
    result = await exec_mattermost(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "m9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_mattermost_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append((operation, params, item, ctx))
        return {"messageId": "m1"}

    node = _node("n8n-nodes-base.mattermost", {"operation": "sendMessage", "channelId": "c", "message": "x"})
    ctx = _ctx({"mattermost_response": mock})
    await exec_mattermost(node, _items([{"a": 1}]), ctx=ctx)
    assert seen[0][0] == "sendMessage"
    assert seen[0][2].json == {"a": 1}
    assert seen[0][3] is ctx


@pytest.mark.asyncio
async def test_mattermost_offline() -> None:
    node = _node("n8n-nodes-base.mattermost", {"channelId": "abc", "message": "hello"})
    ctx = _ctx()
    result = await exec_mattermost(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["channelId"] == "abc"
    assert out[0].json["message"] == "hello"
    assert out[0].json["source"] == "mattermost"
    assert "messageId" in out[0].json
    assert "createdAt" in out[0].json


@pytest.mark.asyncio
async def test_mattermost_http_fallback() -> None:
    node = _node("n8n-nodes-base.mattermost", {"channelId": "c", "message": "m"})
    ctx = _ctx({"http_response": {"body": {"messageId": "fb1"}}})
    result = await exec_mattermost(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Matrix ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_matrix_mock_dict() -> None:
    node = _node("n8n-nodes-base.matrix", {"roomId": "r1", "message": "hi"})
    ctx = _ctx({"matrix_response": {"eventId": "e9", "roomId": "r1"}})
    result = await exec_matrix(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["eventId"] == "e9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_matrix_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append((operation, params))
        return {"eventId": "e1"}

    node = _node("n8n-nodes-base.matrix", {"operation": "sendMessage", "roomId": "r", "message": "x"})
    ctx = _ctx({"matrix_response": mock})
    await exec_matrix(node, _items([{}]), ctx=ctx)
    assert seen[0] == ("sendMessage", {"operation": "sendMessage", "roomId": "r", "message": "x"})


@pytest.mark.asyncio
async def test_matrix_offline() -> None:
    node = _node("n8n-nodes-base.matrix", {"roomId": "!room:server", "message": "hello"})
    ctx = _ctx()
    result = await exec_matrix(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["roomId"] == "!room:server"
    assert out[0].json["message"] == "hello"
    assert out[0].json["source"] == "matrix"
    assert "eventId" in out[0].json


@pytest.mark.asyncio
async def test_matrix_http_fallback() -> None:
    node = _node("n8n-nodes-base.matrix", {"roomId": "r", "message": "m"})
    ctx = _ctx({"http_response": {"body": {"eventId": "fb1"}}})
    result = await exec_matrix(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["eventId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Rocket.Chat ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rocketchat_mock_dict() -> None:
    node = _node("n8n-nodes-base.rocketchat", {"channel": "general", "message": "hi"})
    ctx = _ctx({"rocketchat_response": {"messageId": "m9", "channel": "general"}})
    result = await exec_rocket_chat(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "m9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_rocketchat_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append(operation)
        return {"messageId": "m1"}

    node = _node("n8n-nodes-base.rocketchat", {"operation": "sendMessage", "channel": "c", "message": "x"})
    ctx = _ctx({"rocketchat_response": mock})
    await exec_rocket_chat(node, _items([{}]), ctx=ctx)
    assert seen[0] == "sendMessage"


@pytest.mark.asyncio
async def test_rocketchat_offline() -> None:
    node = _node("n8n-nodes-base.rocketchat", {"channel": "dev", "message": "hello", "alias": "bot"})
    ctx = _ctx()
    result = await exec_rocket_chat(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["channel"] == "dev"
    assert out[0].json["message"] == "hello"
    assert out[0].json["source"] == "rocketchat"
    assert "messageId" in out[0].json


@pytest.mark.asyncio
async def test_rocketchat_http_fallback() -> None:
    node = _node("n8n-nodes-base.rocketchat", {"channel": "c", "message": "m"})
    ctx = _ctx({"http_response": {"body": {"messageId": "fb1"}}})
    result = await exec_rocket_chat(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Gotify ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gotify_mock_dict() -> None:
    node = _node("n8n-nodes-base.gotify", {"title": "T", "message": "M"})
    ctx = _ctx({"gotify_response": {"messageId": 9, "title": "T"}})
    result = await exec_gotify(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == 9
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_gotify_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append(operation)
        return {"messageId": 1}

    node = _node("n8n-nodes-base.gotify", {"operation": "createMessage", "title": "t", "message": "m"})
    ctx = _ctx({"gotify_response": mock})
    await exec_gotify(node, _items([{}]), ctx=ctx)
    assert seen[0] == "createMessage"


@pytest.mark.asyncio
async def test_gotify_offline() -> None:
    node = _node("n8n-nodes-base.gotify", {"title": "Alert", "message": "Body", "priority": 8})
    ctx = _ctx()
    result = await exec_gotify(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["title"] == "Alert"
    assert out[0].json["message"] == "Body"
    assert out[0].json["priority"] == 8
    assert out[0].json["source"] == "gotify"
    assert "messageId" in out[0].json


@pytest.mark.asyncio
async def test_gotify_default_priority() -> None:
    node = _node("n8n-nodes-base.gotify", {"title": "T", "message": "M"})
    ctx = _ctx()
    result = await exec_gotify(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["priority"] == 5


@pytest.mark.asyncio
async def test_gotify_http_fallback() -> None:
    node = _node("n8n-nodes-base.gotify", {"title": "t", "message": "m"})
    ctx = _ctx({"http_response": {"body": {"messageId": 7}}})
    result = await exec_gotify(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == 7
    assert out[0].json["mockSource"] == "http_response"


# ── Pushover ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pushover_mock_dict() -> None:
    node = _node("n8n-nodes-base.pushover", {"title": "T", "message": "M"})
    ctx = _ctx({"pushover_response": {"requestId": "r9", "status": 1}})
    result = await exec_pushover(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["requestId"] == "r9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_pushover_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append(operation)
        return {"requestId": "r1", "status": 1}

    node = _node("n8n-nodes-base.pushover", {"title": "t", "message": "m"})
    ctx = _ctx({"pushover_response": mock})
    await exec_pushover(node, _items([{}]), ctx=ctx)
    assert seen[0] == "push"


@pytest.mark.asyncio
async def test_pushover_offline() -> None:
    node = _node(
        "n8n-nodes-base.pushover",
        {"title": "Alert", "message": "Body", "priority": 1, "sound": "cosmic", "device": "phone"},
    )
    ctx = _ctx()
    result = await exec_pushover(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["title"] == "Alert"
    assert out[0].json["message"] == "Body"
    assert out[0].json["priority"] == 1
    assert out[0].json["status"] == 1
    assert out[0].json["source"] == "pushover"
    assert "requestId" in out[0].json


@pytest.mark.asyncio
async def test_pushover_default_priority() -> None:
    node = _node("n8n-nodes-base.pushover", {"title": "T", "message": "M"})
    ctx = _ctx()
    result = await exec_pushover(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["priority"] == 0


@pytest.mark.asyncio
async def test_pushover_http_fallback() -> None:
    node = _node("n8n-nodes-base.pushover", {"title": "t", "message": "m"})
    ctx = _ctx({"http_response": {"body": {"requestId": "fb1", "status": 1}}})
    result = await exec_pushover(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["requestId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Pushbullet ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pushbullet_mock_dict() -> None:
    node = _node("n8n-nodes-base.pushbullet", {"title": "T", "body": "B"})
    ctx = _ctx({"pushbullet_response": {"iden": "i9", "active": True}})
    result = await exec_pushbullet(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["iden"] == "i9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_pushbullet_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append(operation)
        return {"iden": "i1", "active": True}

    node = _node("n8n-nodes-base.pushbullet", {"operation": "push", "title": "t", "body": "b"})
    ctx = _ctx({"pushbullet_response": mock})
    await exec_pushbullet(node, _items([{}]), ctx=ctx)
    assert seen[0] == "push"


@pytest.mark.asyncio
async def test_pushbullet_offline() -> None:
    node = _node("n8n-nodes-base.pushbullet", {"title": "T", "body": "B", "type": "note"})
    ctx = _ctx()
    result = await exec_pushbullet(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["title"] == "T"
    assert out[0].json["body"] == "B"
    assert out[0].json["type"] == "note"
    assert out[0].json["active"] is True
    assert out[0].json["source"] == "pushbullet"
    assert "iden" in out[0].json


@pytest.mark.asyncio
async def test_pushbullet_default_type() -> None:
    node = _node("n8n-nodes-base.pushbullet", {"title": "T", "body": "B"})
    ctx = _ctx()
    result = await exec_pushbullet(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["type"] == "note"


@pytest.mark.asyncio
async def test_pushbullet_http_fallback() -> None:
    node = _node("n8n-nodes-base.pushbullet", {"title": "t", "body": "b"})
    ctx = _ctx({"http_response": {"body": {"iden": "fb1", "active": True}}})
    result = await exec_pushbullet(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["iden"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── MessageBird ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_messagebird_mock_dict() -> None:
    node = _node("n8n-nodes-base.messageBird", {"to": "+123", "from": "+456", "body": "hi"})
    ctx = _ctx({"messagebird_response": {"messageId": "m9", "status": "sent"}})
    result = await exec_message_bird(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "m9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_messagebird_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append(operation)
        return {"messageId": "m1", "status": "sent"}

    node = _node("n8n-nodes-base.messageBird", {"operation": "sendSms", "to": "t", "from": "f", "body": "b"})
    ctx = _ctx({"messagebird_response": mock})
    await exec_message_bird(node, _items([{}]), ctx=ctx)
    assert seen[0] == "sendSms"


@pytest.mark.asyncio
async def test_messagebird_offline() -> None:
    node = _node("n8n-nodes-base.messageBird", {"to": "+123", "from": "+456", "body": "hello"})
    ctx = _ctx()
    result = await exec_message_bird(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["to"] == "+123"
    assert out[0].json["from"] == "+456"
    assert out[0].json["body"] == "hello"
    assert out[0].json["status"] == "sent"
    assert out[0].json["source"] == "messagebird"
    assert "messageId" in out[0].json


@pytest.mark.asyncio
async def test_messagebird_http_fallback() -> None:
    node = _node("n8n-nodes-base.messageBird", {"to": "t", "from": "f", "body": "b"})
    ctx = _ctx({"http_response": {"body": {"messageId": "fb1", "status": "sent"}}})
    result = await exec_message_bird(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── SMS77 ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sms77_mock_dict() -> None:
    node = _node("n8n-nodes-base.sms77", {"to": "+123", "from": "+456", "text": "hi"})
    ctx = _ctx({"sms77_response": {"messageId": "m9", "status": "sent"}})
    result = await exec_sms77(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "m9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_sms77_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append(operation)
        return {"messageId": "m1", "status": "sent"}

    node = _node("n8n-nodes-base.sms77", {"operation": "sendSms", "to": "t", "from": "f", "text": "x"})
    ctx = _ctx({"sms77_response": mock})
    await exec_sms77(node, _items([{}]), ctx=ctx)
    assert seen[0] == "sendSms"


@pytest.mark.asyncio
async def test_sms77_offline() -> None:
    node = _node("n8n-nodes-base.sms77", {"to": "+123", "from": "+456", "text": "hello"})
    ctx = _ctx()
    result = await exec_sms77(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["to"] == "+123"
    assert out[0].json["from"] == "+456"
    assert out[0].json["text"] == "hello"
    assert out[0].json["status"] == "sent"
    assert out[0].json["source"] == "sms77"
    assert "messageId" in out[0].json


@pytest.mark.asyncio
async def test_sms77_http_fallback() -> None:
    node = _node("n8n-nodes-base.sms77", {"to": "t", "from": "f", "text": "x"})
    ctx = _ctx({"http_response": {"body": {"messageId": "fb1", "status": "sent"}}})
    result = await exec_sms77(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Operation selection ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mattermost_default_operation() -> None:
    node = _node("n8n-nodes-base.mattermost", {"channelId": "c", "message": "m"})
    ctx = _ctx()
    result = await exec_mattermost(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "mattermost"


@pytest.mark.asyncio
async def test_matrix_default_operation() -> None:
    node = _node("n8n-nodes-base.matrix", {"roomId": "r", "message": "m"})
    ctx = _ctx()
    result = await exec_matrix(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "matrix"


@pytest.mark.asyncio
async def test_gotify_default_operation() -> None:
    node = _node("n8n-nodes-base.gotify", {"title": "t", "message": "m"})
    ctx = _ctx()
    result = await exec_gotify(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "gotify"


@pytest.mark.asyncio
async def test_pushover_default_operation() -> None:
    node = _node("n8n-nodes-base.pushover", {"title": "t", "message": "m"})
    ctx = _ctx()
    result = await exec_pushover(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "pushover"


@pytest.mark.asyncio
async def test_pushbullet_default_operation() -> None:
    node = _node("n8n-nodes-base.pushbullet", {"title": "t", "body": "b"})
    ctx = _ctx()
    result = await exec_pushbullet(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "pushbullet"


@pytest.mark.asyncio
async def test_messagebird_default_operation() -> None:
    node = _node("n8n-nodes-base.messageBird", {"to": "t", "from": "f", "body": "b"})
    ctx = _ctx()
    result = await exec_message_bird(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "messagebird"


@pytest.mark.asyncio
async def test_sms77_default_operation() -> None:
    node = _node("n8n-nodes-base.sms77", {"to": "t", "from": "f", "text": "x"})
    ctx = _ctx()
    result = await exec_sms77(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "sms77"


@pytest.mark.asyncio
async def test_rocketchat_default_operation() -> None:
    node = _node("n8n-nodes-base.rocketchat", {"channel": "c", "message": "m"})
    ctx = _ctx()
    result = await exec_rocket_chat(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "rocketchat"


# ── Descriptor registration (CI invariant) ────────────────────────────


def test_descriptors_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    expected = {
        "n8n-nodes-base.mattermost": "action",
        "n8n-nodes-base.matrix": "action",
        "n8n-nodes-base.rocketchat": "action",
        "n8n-nodes-base.gotify": "action",
        "n8n-nodes-base.pushover": "action",
        "n8n-nodes-base.pushbullet": "action",
        "n8n-nodes-base.messageBird": "action",
        "n8n-nodes-base.sms77": "action",
    }
    for ntype, category in expected.items():
        assert ntype in REGISTRY, f"{ntype} not in REGISTRY"
        assert ntype in SUPPORTED_NODE_TYPES, f"{ntype} not in SUPPORTED_NODE_TYPES"
        assert REGISTRY[ntype].category == category, (
            f"{ntype} category mismatch: expected {category}, got {REGISTRY[ntype].category}"
        )


# ── End-to-end ────────────────────────────────────────────────────────


def _doc(nodes, connections):
    return {"name": "msg-e2e", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": [0, 0],
        "parameters": params or {},
    }


@pytest.mark.asyncio
async def test_e2e_mattermost_to_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("m1", "MM", "n8n-nodes-base.mattermost", {"channelId": "ch1", "message": "hi"}),
            _n("s1", "Set", "n8n-nodes-base.set", {"assignments": {"assignments": [{"name": "seen", "value": "={{ $json.source }}", "type": "string"}]}}),
        ],
        {
            "Start": {"main": [[{"node": "MM", "type": "main", "index": 0}]]},
            "MM": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["seen"] == "mattermost"


@pytest.mark.asyncio
async def test_e2e_pushover_to_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("p1", "Push", "n8n-nodes-base.pushover", {"title": "T", "message": "M"}),
            _n("s1", "Set", "n8n-nodes-base.set", {"assignments": {"assignments": [{"name": "ok", "value": "={{ $json.status }}", "type": "number"}]}}),
        ],
        {
            "Start": {"main": [[{"node": "Push", "type": "main", "index": 0}]]},
            "Push": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["ok"] == 1