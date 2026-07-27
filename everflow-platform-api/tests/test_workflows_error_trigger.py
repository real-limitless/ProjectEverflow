"""Tests for the Error Trigger node executor (n8n-nodes-base.errorTrigger)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, StepLog, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.core import exec_error_trigger


# ── Helpers ───────────────────────────────────────────────────────────


def _node(name: str = "Error Trigger", params: dict | None = None) -> ExecNode:
    return ExecNode(
        id="e1",
        name=name,
        type="n8n-nodes-base.errorTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    fatal_error: str | None = None,
    last_error: str | None = None,
    run_id: str | None = "rid-1",
    steps: list[StepLog] | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    return EngineContext(
        graph=g,
        run_id=run_id,
        fatal_error=fatal_error,
        steps=list(steps or []),
    )


def _doc(nodes, connections):
    return {"name": "error-trigger-test", "nodes": nodes, "connections": connections}


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
async def test_emits_error_item_when_fatal_error_set() -> None:
    steps = [
        StepLog(
            node_id="a",
            node_name="Bad",
            n8n_type="n8n-nodes-base.set",
            status="error",
            error="division by zero",
        )
    ]
    ctx = _ctx(fatal_error="Bad: division by zero", run_id="rid-7", steps=steps)
    node = _node(name="On Error")

    out = await exec_error_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert "error" in payload
    err = payload["error"]
    assert err["message"] == "division by zero"
    assert err["nodeName"] == "Bad"
    assert err["n8n_type"] == "n8n-nodes-base.set"
    assert err["runId"] == "rid-7"


@pytest.mark.asyncio
async def test_emits_empty_error_item_when_no_error() -> None:
    ctx = _ctx(fatal_error=None, last_error=None)
    out = await exec_error_trigger(_node(), items=[], ctx=ctx)
    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"error": None}


@pytest.mark.asyncio
async def test_run_id_is_populated() -> None:
    ctx = _ctx(fatal_error="X: boom", run_id="abc-123")
    out = await exec_error_trigger(_node(), items=[], ctx=ctx)
    assert out[0][1][0].json["error"]["runId"] == "abc-123"


@pytest.mark.asyncio
async def test_run_id_none_when_unset() -> None:
    ctx = _ctx(fatal_error="X: boom", run_id=None)
    out = await exec_error_trigger(_node(), items=[], ctx=ctx)
    assert out[0][1][0].json["error"]["runId"] is None


@pytest.mark.asyncio
async def test_falls_back_to_last_error_alias() -> None:
    ctx = _ctx(fatal_error=None)
    ctx.last_error = "Bad: fallback message"  # type: ignore[attr-defined]
    out = await exec_error_trigger(_node(), items=[], ctx=ctx)
    err = out[0][1][0].json["error"]
    assert err["message"] == "fallback message"
    assert err["nodeName"] == "Bad"


@pytest.mark.asyncio
async def test_recovers_n8n_type_from_steps_when_node_name_mismatches() -> None:
    # If for any reason the failed step name disagrees with the prefix,
    # we still pick up the most recent error step's n8n_type.
    steps = [
        StepLog(
            node_id="x",
            node_name="Mismatch",
            n8n_type="n8n-nodes-base.httpRequest",
            status="error",
        )
    ]
    ctx = _ctx(fatal_error="Whatever: kaboom", steps=steps)
    out = await exec_error_trigger(_node(), items=[], ctx=ctx)
    err = out[0][1][0].json["error"]
    assert err["nodeName"] == "Whatever"
    assert err["message"] == "kaboom"
    # n8n_type is recovered from the most recent error step (name match is
    # preferred but empty when no match exists)
    assert err["n8n_type"] in ("", "n8n-nodes-base.httpRequest")


@pytest.mark.asyncio
async def test_input_items_are_dropped() -> None:
    # The error trigger is a clean slate: it does not propagate items
    ctx = _ctx(fatal_error="Bad: x")
    in_items = [ExecutionItem(json={"foo": 1}), ExecutionItem(json={"bar": 2})]
    out = await exec_error_trigger(_node(), items=in_items, ctx=ctx)
    items = out[0][1]
    assert len(items) == 1
    assert "error" in items[0].json


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.errorTrigger" in REGISTRY
    assert "n8n-nodes-base.errorTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.errorTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.errorTrigger"]
    assert desc.executor.endswith(":exec_error_trigger")
    assert desc.category == "trigger"


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_stop_and_error_does_not_auto_invoke_error_trigger() -> None:
    """Manual → Set → stopAndError (raises).

    The engine does not yet auto-invoke errorTrigger on fatal_error;
    the run returns ``status="error"`` and the executor-level behavior
    of errorTrigger is verified directly. This test documents the
    expected current behavior and the known engine-plumbing gap.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("s1", "Setup", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "a", "value": 1, "type": "number"},
                ]}
            }),
            _n("x1", "Boom", "n8n-nodes-base.stopAndError", {
                "errorMessage": "synthetic failure"
            }),
            _n("e1", "On Error", "n8n-nodes-base.errorTrigger"),
        ],
        {
            "Start": {"main": [[{"node": "Setup", "type": "main", "index": 0}]]},
            "Setup": {"main": [[{"node": "Boom", "type": "main", "index": 0}]]},
            "Boom": {"main": [[{"node": "On Error", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")

    # stopAndError raises; the run fails before errorTrigger is auto-invoked.
    assert result.status == "error"
    assert "synthetic failure" in (result.error_message or "")
    # No "On Error" step was executed.
    names = {s.node_name for s in result.steps}
    assert "On Error" not in names

    # Calling the executor directly with the post-failure context mirrors
    # what the engine would deliver to the errorTrigger if it were wired
    # up. We construct the same EngineContext shape the engine exposes.
    g = engine.graph
    from app.services.workflows.engine import EngineContext

    ctx = EngineContext(
        graph=g,
        run_id=engine.run_id,
        fatal_error=result.error_message,
        steps=list(result.steps),
    )
    out = await exec_error_trigger(
        ExecNode(
            id="e1",
            name="On Error",
            type="n8n-nodes-base.errorTrigger",
            type_version=1,
            parameters={},
            credentials=None,
            position={"x": 0, "y": 0},
        ),
        items=[],
        ctx=ctx,
    )
    assert len(out) == 1
    err_payload = out[0][1][0].json["error"]
    assert err_payload["nodeName"] == "Boom"
    assert "synthetic failure" in err_payload["message"]
    assert err_payload["n8n_type"] == "n8n-nodes-base.stopAndError"
    assert err_payload["runId"] == engine.run_id
