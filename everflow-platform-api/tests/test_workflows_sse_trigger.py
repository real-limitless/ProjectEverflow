"""Tests for the SSE Trigger node executor (n8n-nodes-base.sseTrigger)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.core import exec_sse_trigger


# ── Helpers ───────────────────────────────────────────────────────────


def _node(name: str = "SSE", params: dict | None = None) -> ExecNode:
    return ExecNode(
        id="s1",
        name=name,
        type="n8n-nodes-base.sseTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    sse_event: object | None = None,
    mocks: dict | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    if mocks is None and sse_event is not None:
        mocks = {"sse_event": sse_event}
    return EngineContext(graph=g, mocks=mocks or {})


def _doc(nodes, connections):
    return {"name": "sse-trigger-test", "nodes": nodes, "connections": connections}


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
async def test_single_event_from_mock_emits_one_item() -> None:
    ctx = _ctx(
        sse_event={"event": "message", "data": "hello", "id": "1"},
    )
    node = _node()

    out = await exec_sse_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["event"] == "message"
    assert payload["data"] == "hello"
    assert payload["id"] == "1"


@pytest.mark.asyncio
async def test_list_of_three_events_emits_three_items() -> None:
    events = [
        {"event": "msg", "data": "one", "id": "1"},
        {"event": "msg", "data": "two", "id": "2"},
        {"event": "ping", "data": "pong", "id": "3"},
    ]
    ctx = _ctx(sse_event=events)
    node = _node()

    out = await exec_sse_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 3
    assert [it.json["data"] for it in items] == ["one", "two", "pong"]
    assert [it.json["id"] for it in items] == ["1", "2", "3"]
    assert items[2].json["event"] == "ping"


@pytest.mark.asyncio
async def test_empty_or_missing_mock_emits_single_empty_item() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_sse_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"event": "", "data": "", "id": ""}


@pytest.mark.asyncio
async def test_non_dict_mock_falls_back_to_empty_item() -> None:
    ctx = EngineContext(graph=ExecGraph(nodes_by_id={}, nodes_by_name={}))
    ctx.mocks["sse_event"] = "not a dict"  # type: ignore[index]
    node = _node()

    out = await exec_sse_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"event": "", "data": "", "id": ""}


@pytest.mark.asyncio
async def test_empty_list_mock_falls_back_to_empty_item() -> None:
    ctx = _ctx(sse_event=[])
    node = _node()

    out = await exec_sse_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"event": "", "data": "", "id": ""}


@pytest.mark.asyncio
async def test_event_with_extra_fields_preserves_them() -> None:
    """Extra fields on the event dict are passed through verbatim."""
    ctx = _ctx(
        sse_event={
            "event": "msg",
            "data": "hi",
            "id": "42",
            "retry": 3000,
            "custom": "keep",
        },
    )
    node = _node()

    out = await exec_sse_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["event"] == "msg"
    assert payload["data"] == "hi"
    assert payload["id"] == "42"
    assert payload["retry"] == 3000
    assert payload["custom"] == "keep"


@pytest.mark.asyncio
async def test_event_missing_fields_get_empty_defaults() -> None:
    ctx = _ctx(sse_event={"data": "only data"})
    node = _node()

    out = await exec_sse_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload == {"event": "", "data": "only data", "id": ""}


@pytest.mark.asyncio
async def test_input_items_are_dropped() -> None:
    """SSE Trigger is a clean slate; upstream items are not propagated."""
    ctx = _ctx(sse_event={"event": "msg", "data": "x", "id": "1"})
    node = _node()

    in_items = [ExecutionItem(json={"foo": 1}), ExecutionItem(json={"bar": 2})]
    out = await exec_sse_trigger(node, items=in_items, ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert "foo" not in items[0].json
    assert "bar" not in items[0].json


@pytest.mark.asyncio
async def test_list_mixed_with_non_dicts_filters_them_out() -> None:
    ctx = _ctx(
        sse_event=[
            {"event": "a", "data": "1", "id": "1"},
            "not a dict",
            {"event": "b", "data": "2", "id": "2"},
        ],
    )
    node = _node()

    out = await exec_sse_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 2
    assert items[0].json["data"] == "1"
    assert items[1].json["data"] == "2"


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.sseTrigger" in REGISTRY
    assert "n8n-nodes-base.sseTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.sseTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.sseTrigger"]
    assert desc.executor.endswith(":exec_sse_trigger")
    assert desc.category == "trigger"


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_sse_trigger_seeds_downstream_set() -> None:
    """SSE → Set. The SSE trigger reads the pinned event via mocks and the
    downstream Set should see ``$json.event`` in scope."""
    doc = _doc(
        [
            _n("s1", "SSE", "n8n-nodes-base.sseTrigger"),
            _n(
                "st1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {
                            "name": "echo_event",
                            "value": "={{ 'event=' + $json.event }}",
                            "type": "string",
                        },
                    ]}
                },
            ),
        ],
        {
            "SSE": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    mocks = {
        "sse_event": {"event": "message", "data": "hello", "id": "7"},
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="sse")

    assert result.status == "success", result.error_message
    assert result.final_items, "expected final items from Stamp"
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("echo_event") == "event=message"
    # data and id from the SSE event are preserved on the item
    assert final_json.get("data") == "hello"
    assert final_json.get("id") == "7"


@pytest.mark.asyncio
async def test_end_to_end_sse_trigger_list_emits_one_item_per_event() -> None:
    """SSE → Set with a list of events: each event flows through to Set."""
    doc = _doc(
        [
            _n("s1", "SSE", "n8n-nodes-base.sseTrigger"),
            _n(
                "st1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {
                            "name": "tag",
                            "value": "={{ $json.data }}",
                            "type": "string",
                        },
                    ]}
                },
            ),
        ],
        {
            "SSE": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    mocks = {
        "sse_event": [
            {"event": "a", "data": "alpha", "id": "1"},
            {"event": "b", "data": "beta", "id": "2"},
        ],
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="sse")

    assert result.status == "success", result.error_message
    assert len(result.final_items) == 2
    tags = [it.get("json", {}).get("tag") for it in result.final_items]
    assert tags == ["alpha", "beta"]
