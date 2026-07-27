"""Tests for the Execution Data node executor (n8n-nodes-base.executionData)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest

from app.services.workflows.engine import EngineContext, StepLog, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import exec_execution_data


# ── Helpers ───────────────────────────────────────────────────────────


_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+\d{2}:\d{2}|Z)?$"
)


def _node(name: str = "Exec", params: dict | None = None) -> ExecNode:
    return ExecNode(
        id="e1",
        name=name,
        type="n8n-nodes-base.executionData",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    run_id: str | None = "rid-123",
    now: datetime | None = None,
    step_count: int = 0,
    steps: list[StepLog] | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    return EngineContext(
        graph=g,
        now=now or datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc),
        run_id=run_id,
        step_count=step_count,
        steps=list(steps or []),
    )


def _doc(nodes, connections):
    return {"name": "execution-data-test", "nodes": nodes, "connections": connections}


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
async def test_returns_one_item_with_expected_fields() -> None:
    steps = [
        StepLog(
            node_id="t1",
            node_name="Start",
            n8n_type="n8n-nodes-base.manualTrigger",
            status="success",
        )
    ]
    ctx = _ctx(run_id="rid-abc", step_count=4, steps=steps)
    node = _node(name="ExecInfo")

    out = await exec_execution_data(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["runId"] == "rid-abc"
    assert payload["workflowId"] is None  # ExecGraph has no workflow_id yet
    assert payload["triggerType"] == "manual"
    assert payload["now"] == "2026-07-25T12:00:00+00:00"
    assert payload["stepCount"] == 4
    assert payload["nodeName"] == "ExecInfo"


@pytest.mark.asyncio
async def test_now_is_iso_8601() -> None:
    ctx = _ctx(now=datetime(2026, 1, 2, 3, 4, 5, 678_901, tzinfo=timezone.utc))
    out = await exec_execution_data(_node(), items=[], ctx=ctx)
    payload = out[0][1][0].json
    assert isinstance(payload["now"], str)
    assert _ISO_RE.match(payload["now"]), f"now is not ISO 8601: {payload['now']!r}"
    # Round-trip cleanly
    parsed = datetime.fromisoformat(payload["now"])
    assert parsed == ctx.now


@pytest.mark.asyncio
async def test_trigger_type_inferred_from_steps_log() -> None:
    ctx = _ctx(
        steps=[
            StepLog(node_id="a", node_name="A", n8n_type="n8n-nodes-base.aggregate", status="success"),
            StepLog(node_id="s", node_name="Start", n8n_type="n8n-nodes-base.scheduleTrigger", status="success"),
        ]
    )
    out = await exec_execution_data(_node(), items=[], ctx=ctx)
    assert out[0][1][0].json["triggerType"] == "schedule"


@pytest.mark.asyncio
async def test_trigger_type_defaults_to_unknown_without_trigger_step() -> None:
    ctx = _ctx(steps=[])
    out = await exec_execution_data(_node(), items=[], ctx=ctx)
    assert out[0][1][0].json["triggerType"] == "unknown"


@pytest.mark.asyncio
async def test_input_items_are_passed_through() -> None:
    ctx = _ctx()
    in_items = [
        ExecutionItem(json={"a": 1}),
        ExecutionItem(json={"a": 2}),
    ]
    out = await exec_execution_data(_node(), items=in_items, ctx=ctx)
    items = out[0][1]
    # 1 metadata + 2 passthrough
    assert len(items) == 3
    # First is the metadata item
    assert "runId" in items[0].json
    # The passthrough items are clones — same JSON, distinct objects
    assert items[1].json == {"a": 1}
    assert items[2].json == {"a": 2}
    assert items[1] is not in_items[0]
    assert items[2] is not in_items[1]


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.executionData" in REGISTRY
    assert "n8n-nodes-base.executionData" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.executionData"] == "transform"
    desc = REGISTRY["n8n-nodes-base.executionData"]
    assert desc.executor.endswith(":exec_execution_data")


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_manual_trigger_executiondata_set() -> None:
    """Manual → executionData → Set sees runId and stepCount from the metadata item."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("e1", "ExecInfo", "n8n-nodes-base.executionData", {}),
            _n("d1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "seen_run_id", "value": "={{ $json.runId }}", "type": "string"},
                    {"name": "seen_step_count", "value": "={{ $json.stepCount }}", "type": "number"},
                    {"name": "seen_trigger", "value": "={{ $json.triggerType }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "ExecInfo", "type": "main", "index": 0}]]},
            "ExecInfo": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    assert engine.run_id is not None
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    exec_step = next(s for s in result.steps if s.node_name == "ExecInfo")
    # 1 metadata item + 1 passthrough item from the manualTrigger seed
    assert exec_step.output_count == 2

    downstream_step = next(s for s in result.steps if s.node_name == "Downstream")
    assert downstream_step.input_count == 2
    assert downstream_step.output_count == 2

    # Find the downstream item that saw the metadata payload. Set runs
    # per input item, so the runId/stepCount are visible on the item
    # whose input json carried them.
    final_items = result.final_items
    metadata_item = next(
        (it for it in final_items if isinstance(it, dict) and it.get("json", {}).get("runId")),
        None,
    )
    assert metadata_item is not None, "downstream must see the metadata item"
    final = metadata_item["json"]
    assert final["seen_run_id"] == engine.run_id
    # stepCount at the time executionData runs = 2 (Start + ExecInfo)
    assert final["seen_step_count"] == 2
    assert final["seen_trigger"] == "manual"
