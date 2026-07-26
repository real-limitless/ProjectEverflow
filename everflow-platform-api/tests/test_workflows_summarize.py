"""Tests for the Summarize node executor (n8n-nodes-base.summarize)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import exec_summarize


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="s1",
        name="Summarize",
        type="n8n-nodes-base.summarize",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx() -> EngineContext:
    g = type("G", (), {})()
    g.trigger_nodes = lambda preferred=None: []  # type: ignore
    return EngineContext(graph=g)  # type: ignore[arg-type]


def _doc(nodes, connections):
    return {"name": "summarize-test", "nodes": nodes, "connections": connections}


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
async def test_count_on_five_items_returns_five() -> None:
    items = [ExecutionItem(json={"i": i}) for i in range(5)]
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "count", "fieldName": "i", "aggregation": "count"}
        ]
    })
    out = await exec_summarize(node, items, ctx=_ctx())
    assert len(out) == 1 and out[0][0] == 0
    summary = out[0][1]
    assert len(summary) == 1
    assert summary[0].json == {"count": 5}


@pytest.mark.asyncio
async def test_sum_numeric_field() -> None:
    items = [
        ExecutionItem(json={"amount": 10}),
        ExecutionItem(json={"amount": 20}),
        ExecutionItem(json={"amount": 5}),
    ]
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "total", "fieldName": "amount", "aggregation": "sum"}
        ]
    })
    out = await exec_summarize(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"total": 35}


@pytest.mark.asyncio
async def test_avg_numeric_field() -> None:
    items = [
        ExecutionItem(json={"n": 2}),
        ExecutionItem(json={"n": 4}),
        ExecutionItem(json={"n": 6}),
    ]
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "mean", "fieldName": "n", "aggregation": "avg"}
        ]
    })
    out = await exec_summarize(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"mean": 4.0}


@pytest.mark.asyncio
async def test_min_and_max_numeric_field() -> None:
    items = [
        ExecutionItem(json={"v": 7}),
        ExecutionItem(json={"v": 1}),
        ExecutionItem(json={"v": 9}),
        ExecutionItem(json={"v": 3}),
    ]
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "lo", "fieldName": "v", "aggregation": "min"},
            {"fieldDisplayName": "hi", "fieldName": "v", "aggregation": "max"},
        ]
    })
    out = await exec_summarize(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"lo": 1, "hi": 9}


@pytest.mark.asyncio
async def test_count_distinct_string_field() -> None:
    items = [
        ExecutionItem(json={"tag": "a"}),
        ExecutionItem(json={"tag": "b"}),
        ExecutionItem(json={"tag": "a"}),
        ExecutionItem(json={"tag": "c"}),
        ExecutionItem(json={"tag": "b"}),
    ]
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "unique", "fieldName": "tag", "aggregation": "count_distinct"}
        ]
    })
    out = await exec_summarize(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"unique": 3}


@pytest.mark.asyncio
async def test_first_and_last_pick_by_field() -> None:
    items = [
        ExecutionItem(json={"label": "alpha"}),
        ExecutionItem(json={"label": "beta"}),
        ExecutionItem(json={"label": "gamma"}),
    ]
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "first", "fieldName": "label", "aggregation": "first"},
            {"fieldDisplayName": "last", "fieldName": "label", "aggregation": "last"},
        ]
    })
    out = await exec_summarize(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"first": "alpha", "last": "gamma"}


@pytest.mark.asyncio
async def test_last_skips_trailing_nulls() -> None:
    items = [
        ExecutionItem(json={"x": 1}),
        ExecutionItem(json={"x": 2}),
        ExecutionItem(json={"x": None}),
    ]
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "tail", "fieldName": "x", "aggregation": "last"},
        ]
    })
    out = await exec_summarize(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"tail": 2}


@pytest.mark.asyncio
async def test_empty_input_returns_empty_output() -> None:
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "total", "fieldName": "amount", "aggregation": "sum"}
        ]
    })
    out = await exec_summarize(node, [], ctx=_ctx())
    assert out == [(0, [])]


@pytest.mark.asyncio
async def test_no_fields_aggregated_yields_count_only() -> None:
    items = [ExecutionItem(json={"a": i}) for i in range(3)]
    node = _node({})
    out = await exec_summarize(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"count": 3}


@pytest.mark.asyncio
async def test_sum_with_no_numeric_values_returns_zero() -> None:
    items = [
        ExecutionItem(json={"x": "abc"}),
        ExecutionItem(json={"x": None}),
    ]
    node = _node({
        "fieldsToAggregate": [
            {"fieldDisplayName": "total", "fieldName": "x", "aggregation": "sum"},
        ]
    })
    out = await exec_summarize(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"total": 0}


@pytest.mark.asyncio
async def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.summarize" in REGISTRY
    assert "n8n-nodes-base.summarize" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.summarize"] == "transform"


@pytest.mark.asyncio
async def test_end_to_end_manual_trigger_set_summarize_set() -> None:
    """Manual → Set (3 items) → Summarize → Set reaches downstream with the summary."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("p1", "Produce", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "amount", "value": "={{ 0 }}", "type": "number"}
                ]}
            }),
            # Static three items via aggregate of a single trigger isn't enough,
            # so we use a Code node to emit 3 items by adding a list field, then
            # SplitOut to fan out.
            _n("c1", "Code", "n8n-nodes-base.code", {
                "mode": "runOnceForAllItems",
                "jsCode": "return [{json: {amount: 10}}, {json: {amount: 20}}, {json: {amount: 5}}];",
            }),
            _n("s1", "Summarize", "n8n-nodes-base.summarize", {
                "fieldsToAggregate": [
                    {"fieldDisplayName": "total", "fieldName": "amount", "aggregation": "sum"},
                    {"fieldDisplayName": "count", "fieldName": "amount", "aggregation": "count"},
                    {"fieldDisplayName": "avg_amount", "fieldName": "amount", "aggregation": "avg"},
                ]
            }),
            _n("d1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "seen_total", "value": "={{ $json.total }}", "type": "number"}
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Produce", "type": "main", "index": 0}]]},
            "Produce": {"main": [[{"node": "Code", "type": "main", "index": 0}]]},
            "Code": {"main": [[{"node": "Summarize", "type": "main", "index": 0}]]},
            "Summarize": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    summary_step = next(s for s in result.steps if s.node_name == "Summarize")
    assert summary_step.output_count == 1, "Summarize must collapse items to a single item"
    downstream_step = next(s for s in result.steps if s.node_name == "Downstream")
    assert downstream_step.input_count == 1
    assert downstream_step.output_count == 1
