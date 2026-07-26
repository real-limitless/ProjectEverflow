"""Tests for the Wait node: time-based + webhook resume hooks."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.services.workflows.engine import EngineContext
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.flow import exec_wait


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="w1",
        name="Wait",
        type="n8n-nodes-base.wait",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx() -> EngineContext:
    g = type("G", (), {})()
    g.trigger_nodes = lambda preferred=None: []  # type: ignore
    return EngineContext(graph=g)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_time_based_wait_uses_amount_and_unit() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"amount": 0.05, "unit": "seconds"})
    ctx = _ctx()

    t0 = time.monotonic()
    out = await exec_wait(node, items, ctx=ctx)
    elapsed = time.monotonic() - t0
    assert out[0][1] == items
    assert elapsed >= 0.04, f"wait did not block: elapsed={elapsed}"


@pytest.mark.asyncio
async def test_time_based_wait_zero_returns_immediately() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"amount": 0, "unit": "seconds"})
    ctx = _ctx()
    t0 = time.monotonic()
    out = await exec_wait(node, items, ctx=ctx)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.05
    assert out[0][1] == items


@pytest.mark.asyncio
async def test_wait_minutes_unit_multiplies() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"amount": 1, "unit": "minutes"})
    ctx = _ctx()
    # Patch asyncio.sleep so the test does not actually wait 60s.
    from app.services.workflows.nodes import flow as flow_mod

    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def _fake_sleep(amount: float) -> None:
        sleeps.append(amount)
        # yield to the loop once so we don't stall
        await real_sleep(0)

    flow_mod.asyncio.sleep = _fake_sleep  # type: ignore[attr-defined]
    try:
        out = await exec_wait(node, items, ctx=ctx)
    finally:
        flow_mod.asyncio.sleep = real_sleep  # type: ignore[attr-defined]
    assert out[0][1] == items
    assert sleeps == [60.0], f"expected 60s sleep, got {sleeps}"


@pytest.mark.asyncio
async def test_wait_resume_webhook_records_resume_url() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"resume": {"resume": "webhook"}})
    ctx = _ctx()
    ctx.run_id = "run-abc"
    out = await exec_wait(node, items, ctx=ctx)
    # Items still pass through (engine decides whether to park execution).
    assert len(out[0][1]) == 1
    assert "$execution" in out[0][1][0].json
    assert "resumeUrl" in out[0][1][0].json["$execution"]
    assert "run-abc" in out[0][1][0].json["$execution"]["resumeUrl"]
    assert out[0][1][0].json["$execution"]["resumeFired"] is False
    # Wait state recorded on the context
    assert "w1" in ctx.wait_states
    assert ctx.wait_states["w1"]["mode"] == "webhook"


@pytest.mark.asyncio
async def test_wait_resume_webhook_fires_via_mock() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"resume": {"resume": "webhook"}})
    ctx = _ctx()
    ctx.run_id = "run-xyz"
    ctx.mocks = {"wait_resume": {"w1": True}}
    out = await exec_wait(node, items, ctx=ctx)
    # Fired: state cleared, items flagged
    assert "w1" not in ctx.wait_states
    assert out[0][1][0].json["$execution"]["resumeFired"] is True
    assert "run-xyz" in out[0][1][0].json["$execution"]["resumeUrl"]


@pytest.mark.asyncio
async def test_wait_unknown_unit_falls_back_to_seconds() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"amount": 0, "unit": "fortnights"})
    ctx = _ctx()
    out = await exec_wait(node, items, ctx=ctx)
    assert out[0][1] == items


@pytest.mark.asyncio
async def test_wait_engine_does_not_park_on_resolved_wait() -> None:
    """If the wait is fired via mock, engine should continue normally."""
    from app.services.workflows.engine import WorkflowEngine

    doc = {
        "name": "wait-test",
        "nodes": [
            {"id": "t1", "name": "Start", "type": "n8n-nodes-base.manualTrigger",
             "typeVersion": 1, "position": [0, 0], "parameters": {}},
            {"id": "w1", "name": "Wait", "type": "n8n-nodes-base.wait",
             "typeVersion": 1, "position": [200, 0],
             "parameters": {"resume": {"resume": "webhook"}}},
            {"id": "s1", "name": "Set", "type": "n8n-nodes-base.set",
             "typeVersion": 3, "position": [400, 0],
             "parameters": {"assignments": {"assignments": [
                 {"name": "x", "value": "done", "type": "string"}
             ]}}},
        ],
        "connections": {
            "Start": {"main": [[{"node": "Wait", "type": "main", "index": 0}]]},
            "Wait": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    }
    mocks = {"wait_resume": {"w1": True}}
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    names = [s.node_name for s in result.steps]
    assert "Wait" in names
    assert "Set" in names
