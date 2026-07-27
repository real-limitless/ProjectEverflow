"""Tests for the Chat Trigger node executor (@n8n/n8n-nodes-langchain.chatTrigger)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.core import exec_chat_trigger


# ── Helpers ───────────────────────────────────────────────────────────


def _node(name: str = "Chat", params: dict | None = None) -> ExecNode:
    return ExecNode(
        id="c1",
        name=name,
        type="@n8n/n8n-nodes-langchain.chatTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    chat_input: dict | None = None,
    mocks: dict | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    if mocks is None and chat_input is not None:
        mocks = {"chat_input": chat_input}
    return EngineContext(graph=g, mocks=mocks or {})


def _doc(nodes, connections):
    return {"name": "chat-trigger-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


# ── Unit tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emits_item_with_chat_input_from_mock() -> None:
    ctx = _ctx(chat_input={"text": "hello", "sessionId": "abc"})
    node = _node()

    out = await exec_chat_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["chatInput"] == "hello"
    assert payload["sessionId"] == "abc"


@pytest.mark.asyncio
async def test_falls_back_when_no_mock_chat_input() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_chat_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"chatInput": "", "sessionId": "default"}


@pytest.mark.asyncio
async def test_session_id_parameter_override() -> None:
    """When the mock omits a sessionId, the parameter is used as override."""
    ctx = _ctx(chat_input={"text": "hi"})
    node = _node(params={"sessionId": "param-session"})

    out = await exec_chat_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["chatInput"] == "hi"
    assert payload["sessionId"] == "param-session"


@pytest.mark.asyncio
async def test_session_id_from_mock_wins_over_parameter() -> None:
    ctx = _ctx(chat_input={"text": "hi", "sessionId": "from-mock"})
    node = _node(params={"sessionId": "from-param"})

    out = await exec_chat_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["sessionId"] == "from-mock"


@pytest.mark.asyncio
async def test_default_session_id_from_parameter() -> None:
    ctx = _ctx()
    node = _node(params={"sessionId": "my-session"})

    out = await exec_chat_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload == {"chatInput": "", "sessionId": "my-session"}


@pytest.mark.asyncio
async def test_chat_input_key_alias() -> None:
    """If a mock uses ``chatInput`` instead of ``text``, it is still read."""
    ctx = _ctx(chat_input={"chatInput": "via-alias", "sessionId": "s1"})
    node = _node()

    out = await exec_chat_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["chatInput"] == "via-alias"
    assert payload["sessionId"] == "s1"


@pytest.mark.asyncio
async def test_empty_session_id_in_mock_falls_back_to_parameter() -> None:
    ctx = _ctx(chat_input={"text": "x", "sessionId": ""})
    node = _node(params={"sessionId": "param-default"})

    out = await exec_chat_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["chatInput"] == "x"
    assert payload["sessionId"] == "param-default"


@pytest.mark.asyncio
async def test_input_items_are_dropped() -> None:
    """Chat Trigger is a clean slate; upstream items are not propagated."""
    ctx = _ctx(chat_input={"text": "hi", "sessionId": "s"})
    node = _node()

    in_items = [ExecutionItem(json={"foo": 1}), ExecutionItem(json={"bar": 2})]
    out = await exec_chat_trigger(node, items=in_items, ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert "chatInput" in items[0].json
    assert "foo" not in items[0].json
    assert "bar" not in items[0].json


@pytest.mark.asyncio
async def test_non_dict_chat_input_mock_falls_back() -> None:
    """If the mock is not a dict, treat it as no mock."""
    ctx = _ctx()
    ctx.mocks["chat_input"] = "not a dict"  # type: ignore[index]
    node = _node(params={"sessionId": "fallback"})

    out = await exec_chat_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload == {"chatInput": "", "sessionId": "fallback"}


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.chatTrigger" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.chatTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.chatTrigger"] == "trigger"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.chatTrigger"]
    assert desc.executor.endswith(":exec_chat_trigger")
    assert desc.category == "trigger"


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_chat_trigger_seeds_downstream_set() -> None:
    """Manual → chatTrigger → Set. The chat trigger reads the pinned
    chat_input via mocks and the downstream Set should see ``$json.chatInput``
    in scope."""
    doc = _doc(
        [
            _n("m1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "c1",
                "Chat",
                "@n8n/n8n-nodes-langchain.chatTrigger",
                {"sessionId": "s-1"},
            ),
            _n(
                "s1",
                "Echo",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {"name": "echo", "value": "={{ $json.chatInput }}", "type": "string"},
                    ]}
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Chat", "type": "main", "index": 0}]]},
            "Chat": {"main": [[{"node": "Echo", "type": "main", "index": 0}]]},
        },
    )
    mocks = {"chat_input": {"text": "hello there", "sessionId": "s-1"}}
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message
    assert result.final_items, "expected final items from Echo"
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("echo") == "hello there"
    # sessionId is preserved on the item
    assert final_json.get("sessionId") == "s-1"


@pytest.mark.asyncio
async def test_end_to_end_chat_trigger_without_mock_emits_default_session() -> None:
    """End-to-end with no chat_input mock: downstream still receives one
    item with the default sessionId from the node parameter."""
    doc = _doc(
        [
            _n("m1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "c1",
                "Chat",
                "@n8n/n8n-nodes-langchain.chatTrigger",
                {"sessionId": "default-session"},
            ),
        ],
        {
            "Start": {"main": [[{"node": "Chat", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message
    assert result.final_items
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("chatInput") == ""
    assert final_json.get("sessionId") == "default-session"
