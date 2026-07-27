"""Tests for the Execute Sub-workflow node."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.flow import exec_execute_workflow


def _node(params: dict, *, type_: str, id_: str) -> ExecNode:
    return ExecNode(
        id=id_,
        name="Sub",
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


from app.services.workflows.engine import EngineContext  # noqa: E402  (after _ctx)


@pytest.mark.asyncio
async def test_execute_subworkflow_returns_final_items() -> None:
    """Sub-workflow's final items flow into the parent executor's outputs."""
    sub_doc = {
        "name": "child",
        "nodes": [
            {
                "id": "t1",
                "name": "Start",
                "type": "n8n-nodes-base.manualTrigger",
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
                    "assignments": {"assignments": [
                        {"name": "child_value", "value": "hello-from-child", "type": "string"},
                    ]},
                    "includeOtherFields": True,
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    }
    parent_doc = {
        "name": "parent",
        "nodes": [
            {
                "id": "t1",
                "name": "Start",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
                "parameters": {},
            },
            {
                "id": "sub1",
                "name": "Sub",
                "type": "n8n-nodes-base.executeWorkflow",
                "typeVersion": 1,
                "position": [200, 0],
                "parameters": {"workflowId": "child-1"},
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Sub", "type": "main", "index": 0}]]},
        },
    }
    mocks = {"subworkflows": {"child-1": sub_doc}}
    engine = WorkflowEngine(parent_doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    step_names = [s.node_name for s in result.steps]
    assert "Sub" in step_names
    sub_step = next(s for s in result.steps if s.node_name == "Sub")
    assert sub_step.output_count >= 1
    sample = sub_step.sample_output
    assert any(
        row.get("json", {}).get("child_value") == "hello-from-child"
        for row in sample
    )


@pytest.mark.asyncio
async def test_execute_subworkflow_raises_when_missing() -> None:
    node = _node({"workflowId": "missing"}, type_="n8n-nodes-base.executeWorkflow", id_="sub1")
    ctx = _ctx()
    ctx.mocks = {"subworkflows": {}}
    with pytest.raises(RuntimeError, match="not found"):
        await exec_execute_workflow(node, [ExecutionItem(json={})], ctx=ctx)


@pytest.mark.asyncio
async def test_execute_subworkflow_no_items_uses_sub_engine_alone() -> None:
    sub_doc = {
        "name": "child",
        "nodes": [
            {"id": "t1", "name": "Start", "type": "n8n-nodes-base.manualTrigger",
             "typeVersion": 1, "position": [0, 0], "parameters": {}},
            {"id": "s1", "name": "Set", "type": "n8n-nodes-base.set",
             "typeVersion": 3, "position": [200, 0],
             "parameters": {"assignments": {"assignments": [
                 {"name": "k", "value": "v", "type": "string"},
             ]}, "includeOtherFields": True}},
        ],
        "connections": {
            "Start": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    }
    node = _node({"workflowId": "child-1"}, type_="n8n-nodes-base.executeWorkflow", id_="sub1")
    ctx = _ctx()
    ctx.mocks = {"subworkflows": {"child-1": sub_doc}}
    out = await exec_execute_workflow(node, [], ctx=ctx)
    items = out[0][1]
    assert items and items[0].json.get("k") == "v"
