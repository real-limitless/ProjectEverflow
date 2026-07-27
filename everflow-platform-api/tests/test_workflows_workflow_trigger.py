"""Tests for the Workflow Trigger node executor (n8n-nodes-base.workflowTrigger)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.core import exec_workflow_trigger


# ── Helpers ───────────────────────────────────────────────────────────


def _node(name: str = "WTrigger", params: dict | None = None) -> ExecNode:
    return ExecNode(
        id="w1",
        name=name,
        type="n8n-nodes-base.workflowTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    workflow_call: dict | None = None,
    mocks: dict | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    if mocks is None and workflow_call is not None:
        mocks = {"workflow_call": workflow_call}
    return EngineContext(graph=g, mocks=mocks or {})


def _doc(nodes, connections):
    return {"name": "workflow-trigger-test", "nodes": nodes, "connections": connections}


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
async def test_emits_item_from_mock_workflow_call() -> None:
    call = {
        "workflowId": "wf-parent",
        "executionId": "exec-123",
        "data": {"foo": "bar", "n": 42},
    }
    ctx = _ctx(workflow_call=call)
    node = _node()

    out = await exec_workflow_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["workflowId"] == "wf-parent"
    assert payload["executionId"] == "exec-123"
    assert payload["foo"] == "bar"
    assert payload["n"] == 42


@pytest.mark.asyncio
async def test_falls_back_when_no_mock_workflow_call() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_workflow_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"workflowId": "", "executionId": ""}


@pytest.mark.asyncio
async def test_data_keys_are_promoted_to_top_level() -> None:
    call = {
        "workflowId": "wf-parent",
        "executionId": "exec-123",
        "data": {"alpha": 1, "beta": "two", "nested": {"x": 3}},
    }
    ctx = _ctx(workflow_call=call)
    node = _node()

    out = await exec_workflow_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    # workflowId and executionId remain
    assert payload["workflowId"] == "wf-parent"
    assert payload["executionId"] == "exec-123"
    # Data keys are at the top level
    assert payload["alpha"] == 1
    assert payload["beta"] == "two"
    assert payload["nested"] == {"x": 3}
    # The "data" envelope is not smuggled in
    assert "data" not in payload


@pytest.mark.asyncio
async def test_data_key_overrides_take_precedence_over_envelope() -> None:
    """If data contains a key named workflowId/executionId, data wins."""
    call = {
        "workflowId": "envelope-id",
        "executionId": "envelope-exec",
        "data": {"workflowId": "data-id", "executionId": "data-exec"},
    }
    ctx = _ctx(workflow_call=call)
    node = _node()

    out = await exec_workflow_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    # promotion order: envelope first, then data.update → data wins
    assert payload["workflowId"] == "data-id"
    assert payload["executionId"] == "data-exec"


@pytest.mark.asyncio
async def test_non_dict_workflow_call_mock_falls_back() -> None:
    """If the mock is not a dict, treat it as no mock."""
    ctx = _ctx()
    ctx.mocks["workflow_call"] = "not a dict"  # type: ignore[index]
    node = _node()

    out = await exec_workflow_trigger(node, items=[], ctx=ctx)

    assert out[0][1][0].json == {"workflowId": "", "executionId": ""}


@pytest.mark.asyncio
async def test_workflow_call_with_no_data_key_still_emits_ids() -> None:
    call = {"workflowId": "wf-x", "executionId": "exec-y"}
    ctx = _ctx(workflow_call=call)
    node = _node()

    out = await exec_workflow_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["workflowId"] == "wf-x"
    assert payload["executionId"] == "exec-y"
    assert "data" not in payload


@pytest.mark.asyncio
async def test_non_dict_data_falls_back_to_envelope_only() -> None:
    call = {"workflowId": "wf-x", "executionId": "exec-y", "data": "oops"}
    ctx = _ctx(workflow_call=call)
    node = _node()

    out = await exec_workflow_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload == {"workflowId": "wf-x", "executionId": "exec-y"}


@pytest.mark.asyncio
async def test_input_items_are_dropped() -> None:
    """Workflow Trigger is a clean slate; upstream items are not propagated."""
    call = {"workflowId": "wf-x", "executionId": "exec-y", "data": {"k": "v"}}
    ctx = _ctx(workflow_call=call)
    node = _node()

    in_items = [ExecutionItem(json={"foo": 1}), ExecutionItem(json={"bar": 2})]
    out = await exec_workflow_trigger(node, items=in_items, ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert "k" in items[0].json
    assert "foo" not in items[0].json
    assert "bar" not in items[0].json


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.workflowTrigger" in REGISTRY
    assert "n8n-nodes-base.workflowTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.workflowTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.workflowTrigger"]
    assert desc.executor.endswith(":exec_workflow_trigger")
    assert desc.category == "trigger"


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_workflow_trigger_seeds_downstream_set() -> None:
    """workflowTrigger → Set. The trigger reads the pinned workflow_call via
    mocks and the downstream Set should see ``$json.workflowId`` in scope."""
    doc = _doc(
        [
            _n("w1", "WorkflowTrig", "n8n-nodes-base.workflowTrigger"),
            _n(
                "s1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {"name": "fromParent", "value": "={{ $json.workflowId }}", "type": "string"},
                    ]}
                },
            ),
        ],
        {
            "WorkflowTrig": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    mocks = {
        "workflow_call": {
            "workflowId": "wf-parent",
            "executionId": "exec-1",
            "data": {"input": "hello"},
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message
    assert result.final_items, "expected final items from Stamp"
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("fromParent") == "wf-parent"
    # executionId + data promotion survives to final item
    assert final_json.get("executionId") == "exec-1"
    assert final_json.get("input") == "hello"


@pytest.mark.asyncio
async def test_end_to_end_workflow_trigger_without_mock_emits_empty_ids() -> None:
    """End-to-end with no workflow_call mock: downstream still receives
    one item with empty workflowId/executionId."""
    doc = _doc(
        [
            _n("w1", "WorkflowTrig", "n8n-nodes-base.workflowTrigger"),
            _n(
                "s1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {"name": "parentId", "value": "='none' if $json.workflowId == '' else $json.workflowId", "type": "string"},
                    ]}
                },
            ),
        ],
        {
            "WorkflowTrig": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message
    assert result.final_items
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("parentId") == "none"
    assert final_json.get("executionId") == ""
