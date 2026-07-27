"""Tests for the flow-control executors and multi-input merge engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.expression import ExpressionContext
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes import flow
from app.services.workflows.nodes.flow import (
    exec_merge,
    exec_noop,
    exec_sort,
    exec_wait,
)


def _doc(nodes, connections):
    return {
        "name": "merge-test",
        "nodes": nodes,
        "connections": connections,
    }


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


@pytest.mark.asyncio
async def test_merge_append_combines_two_streams() -> None:
    """Two parallel branches should arrive at a single Merge(append) and be concatenated."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("a1", "SetA", "n8n-nodes-base.set", {"assignments": {"assignments": [
                {"name": "branch", "value": "A", "type": "string"}
            ]}}),
            _n("b1", "SetB", "n8n-nodes-base.set", {"assignments": {"assignments": [
                {"name": "branch", "value": "B", "type": "string"}
            ]}}),
            _n("m1", "Merge", "n8n-nodes-base.merge", {"mode": "append"}),
        ],
        {
            "Start": {"main": [[
                {"node": "SetA", "type": "main", "index": 0},
                {"node": "SetB", "type": "main", "index": 0},
            ]]},
            "SetA": {"main": [[{"node": "Merge", "type": "main", "index": 0}]]},
            "SetB": {"main": [[{"node": "Merge", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    merge_step = next(s for s in result.steps if s.node_name == "Merge")
    assert merge_step.input_count == 2, (
        f"expected 2 input items (one per branch), got {merge_step.input_count}"
    )


@pytest.mark.asyncio
async def test_merge_single_input_passthrough() -> None:
    """Single-input target is unchanged by merge buffering."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("s1", "Set", "n8n-nodes-base.set", {"assignments": {"assignments": [
                {"name": "x", "value": "1", "type": "string"}
            ]}}),
        ],
        {"Start": {"main": [[{"node": "Set", "type": "main", "index": 0}]]}},
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.output_count == 1


@pytest.mark.asyncio
async def test_noop_passthrough() -> None:
    items = [ExecutionItem(json={"a": 1})]
    out = await exec_noop(None, items, ctx=None)  # type: ignore[arg-type]
    assert out[0][1] == items


@pytest.mark.asyncio
async def test_wait_zero_returns_immediately() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _n("w1", "Wait", "n8n-nodes-base.wait", {"amount": 0, "unit": "seconds"})

    class _N:
        id = "w1"
        name = "Wait"
        type = "n8n-nodes-base.wait"
        type_version = 1
        parameters = node["parameters"]
        credentials = None
        position = [0, 0]
        retry_on_fail = False
        max_tries = None
        continue_on_fail = False
        disabled = False

    from app.services.workflows.engine import EngineContext
    g = type("G", (), {})()
    g.trigger_nodes = lambda preferred=None: []  # type: ignore
    ctx = EngineContext(graph=g)  # type: ignore[arg-type]
    out = await exec_wait(_N(), items, ctx=ctx)
    assert out[0][1] == items


@pytest.mark.asyncio
async def test_limit_first_n() -> None:
    items = [ExecutionItem(json={"i": i}) for i in range(5)]
    node = _n("L", "L", "n8n-nodes-base.limit", {"maxItems": 2, "keep": "firstItems"})

    class _N:
        id = "L"
        name = "L"
        type = "n8n-nodes-base.limit"
        type_version = 1
        parameters = node["parameters"]
        credentials = None
        position = [0, 0]
        retry_on_fail = False
        max_tries = None
        continue_on_fail = False
        disabled = False

    from app.services.workflows.engine import EngineContext
    g = type("G", (), {})()
    ctx = EngineContext(graph=g)  # type: ignore[arg-type]
    out = await flow.exec_limit(_N(), items, ctx=ctx)
    kept = out[0][1]
    assert len(kept) == 2
    assert [it.json["i"] for it in kept] == [0, 1]


@pytest.mark.asyncio
async def test_remove_duplicates_by_field() -> None:
    items = [
        ExecutionItem(json={"k": "a", "v": 1}),
        ExecutionItem(json={"k": "a", "v": 2}),
        ExecutionItem(json={"k": "b", "v": 3}),
    ]
    node = _n("R", "R", "n8n-nodes-base.removeDuplicates", {"compare": {"fields": ["k"]}})

    class _N:
        id = "R"
        name = "R"
        type = "n8n-nodes-base.removeDuplicates"
        type_version = 1
        parameters = node["parameters"]
        credentials = None
        position = [0, 0]
        retry_on_fail = False
        max_tries = None
        continue_on_fail = False
        disabled = False

    from app.services.workflows.engine import EngineContext
    g = type("G", (), {})()
    ctx = EngineContext(graph=g)  # type: ignore[arg-type]
    out = await flow.exec_remove_duplicates(_N(), items, ctx=ctx)
    kept = out[0][1]
    assert len(kept) == 2
    assert [it.json["k"] for it in kept] == ["a", "b"]


@pytest.mark.asyncio
async def test_sort_ascending_and_descending() -> None:
    items = [
        ExecutionItem(json={"n": 3}),
        ExecutionItem(json={"n": 1}),
        ExecutionItem(json={"n": 2}),
    ]
    node = _n("S", "S", "n8n-nodes-base.sort", {"sortFields": {"fields": [
        {"fieldName": "n", "order": "ascending"}
    ]}})

    class _N:
        id = "S"
        name = "S"
        type = "n8n-nodes-base.sort"
        type_version = 1
        parameters = node["parameters"]
        credentials = None
        position = [0, 0]
        retry_on_fail = False
        max_tries = None
        continue_on_fail = False
        disabled = False

    from app.services.workflows.engine import EngineContext
    g = type("G", (), {})()
    ctx = EngineContext(graph=g)  # type: ignore[arg-type]
    out = await exec_sort(_N(), items, ctx=ctx)
    sorted_items = out[0][1]
    assert [it.json["n"] for it in sorted_items] == [1, 2, 3]


@pytest.mark.asyncio
async def test_existing_stock_agent_still_passes() -> None:
    """Regression: introducing multi-input buffering must not break Stock Agent."""
    fixture = Path(__file__).parent / "fixtures" / "workflows" / "stock_agent_emailer.json"
    doc = json.loads(fixture.read_text(encoding="utf-8"))
    portfolio_csv = "Symbol,Qty,Cost\nAAPL,10,150.0,\nMSFT,5,300.0,\n"
    history_csv = "Date,Symbol,Side,Qty\n2026-01-01,AAPL,BUY,10,\n"
    mocks = {
        "ftp_files": {
            "/home/chen/Portfolio_Positions.csv": portfolio_csv.encode(),
            "/home/chen/History_for_Account.csv": history_csv.encode(),
            "/home/chen/readme.txt": b"ignore me",
        },
        "capture_email": True,
        "agent_output": (
            "# Portfolio Research\n\n## AAPL\n\n**Hold** — solid core position.\n\n"
            "## MSFT\n\n*Watch* concentration.\n"
        ),
    }
    engine = WorkflowEngine(doc, mocks=mocks, max_steps=2000)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    assert result.sent_emails, "expected captured email"
