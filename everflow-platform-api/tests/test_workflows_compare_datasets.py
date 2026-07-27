"""Tests for the Compare Datasets node executor (n8n-nodes-base.compareDatasets).

Covers:
- field matching on a single key
- bucket counts for 2 streams of 3 items each (1 common, 1 different, 1 unique each)
- skipOnEqual drops items from ``different_items`` when the listed field matches
- descriptor is registered in the registry
- end-to-end pipeline: Manual Trigger → 2 Set nodes → compareDatasets → downstream Set
"""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode, ExecGraph
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.flow import (
    _match_key,
    _split_inputs_by_target_index,
    exec_compare_datasets,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="cd1",
        name="CompareDatasets",
        type="n8n-nodes-base.compareDatasets",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(node: ExecNode) -> EngineContext:
    """EngineContext wired to a graph with the two upstream Set nodes feeding this node."""
    g = ExecGraph(
        nodes_by_id={
            node.id: node,
            "src1": ExecNode(
                id="src1",
                name="SetA",
                type="n8n-nodes-base.set",
                type_version=1,
                parameters={},
                credentials=None,
                position={"x": 0, "y": 0},
            ),
            "src2": ExecNode(
                id="src2",
                name="SetB",
                type="n8n-nodes-base.set",
                type_version=1,
                parameters={},
                credentials=None,
                position={"x": 0, "y": 0},
            ),
        },
        nodes_by_name={
            "SetA": ExecNode(
                id="src1",
                name="SetA",
                type="n8n-nodes-base.set",
                type_version=1,
                parameters={},
                credentials=None,
                position={"x": 0, "y": 0},
            ),
            "SetB": ExecNode(
                id="src2",
                name="SetB",
                type="n8n-nodes-base.set",
                type_version=1,
                parameters={},
                credentials=None,
                position={"x": 0, "y": 0},
            ),
        },
        in_main={
            node.id: [
                __import__(
                    "app.services.workflows.graph", fromlist=["ExecEdge"]
                ).ExecEdge(
                    source_id="src1",
                    target_id=node.id,
                    source_name="SetA",
                    target_name=node.name,
                    connection_type="main",
                    source_index=0,
                    target_index=0,
                ),
                __import__(
                    "app.services.workflows.graph", fromlist=["ExecEdge"]
                ).ExecEdge(
                    source_id="src2",
                    target_id=node.id,
                    source_name="SetB",
                    target_name=node.name,
                    connection_type="main",
                    source_index=0,
                    target_index=1,
                ),
            ]
        },
    )
    ctx = EngineContext(graph=g)
    ctx.node_outputs["SetA"] = []
    ctx.node_outputs["SetB"] = []
    return ctx


def _doc(nodes, connections):
    return {"name": "compare-datasets-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


# ── Direct executor tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_two_streams_yields_expected_bucket_counts() -> None:
    """Two streams of 3 items each, 1 common, 1 different, 1 unique each."""
    input_1 = [
        ExecutionItem(json={"id": 1, "name": "a", "extra": "x"}),
        ExecutionItem(json={"id": 2, "name": "b", "extra": "x"}),
        ExecutionItem(json={"id": 3, "name": "c", "extra": "x"}),
    ]
    input_2 = [
        ExecutionItem(json={"id": 1, "name": "a", "extra": "y"}),  # same id, different extra
        ExecutionItem(json={"id": 2, "name": "B", "extra": "y"}),  # same id, name differs
        ExecutionItem(json={"id": 4, "name": "d", "extra": "y"}),  # unique to input_2
    ]
    node = _node({"fieldsToMatch": ["id"]})
    ctx = _ctx(node)
    ctx.node_outputs["SetA"] = input_1
    ctx.node_outputs["SetB"] = input_2

    out = await exec_compare_datasets(node, input_1 + input_2, ctx=ctx)
    # single output combines all buckets, tagged with compareBucket
    assert len(out) == 1
    idx, items = out[0]
    assert idx == 0
    buckets: dict[str, int] = {}
    for it in items:
        b = it.json.get("compareBucket")
        buckets[b] = buckets.get(b, 0) + 1
    # id=1 matches by id; different_items (extra differs, no skipOnEqual)
    # id=2 matches by id; different_items (name differs, no skipOnEqual)
    # id=3 -> unique_to_input_1
    # id=4 -> unique_to_input_2
    assert buckets.get("different_items") == 2, buckets
    assert buckets.get("unique_to_input_1") == 1, buckets
    assert buckets.get("unique_to_input_2") == 1, buckets
    assert buckets.get("equal_items", 0) == 0, buckets


@pytest.mark.asyncio
async def test_match_by_id_field_buckets_correctly() -> None:
    """Field matching by `id` field: 2-item overlap, others split."""
    input_1 = [
        ExecutionItem(json={"id": "a"}),
        ExecutionItem(json={"id": "b"}),
    ]
    input_2 = [
        ExecutionItem(json={"id": "a"}),
        ExecutionItem(json={"id": "c"}),
    ]
    node = _node({"fieldsToMatch": ["id"]})
    ctx = _ctx(node)
    ctx.node_outputs["SetA"] = input_1
    ctx.node_outputs["SetB"] = input_2

    out = await exec_compare_datasets(node, input_1 + input_2, ctx=ctx)
    _, items = out[0]
    buckets: dict[str, list[dict]] = {}
    for it in items:
        b = it.json["compareBucket"]
        buckets.setdefault(b, []).append(it.json)
    # No skipOnEqual → matched pair goes to different_items by default
    assert [d["id"] for d in buckets.get("different_items", [])] == ["a"]
    assert [d["id"] for d in buckets.get("unique_to_input_1", [])] == ["b"]
    assert [d["id"] for d in buckets.get("unique_to_input_2", [])] == ["c"]


@pytest.mark.asyncio
async def test_skip_on_equal_moves_item_to_equal_bucket() -> None:
    """skipOnEqual=['name']: pair with same name goes to equal, not different."""
    input_1 = [ExecutionItem(json={"id": 1, "name": "alice"})]
    input_2 = [ExecutionItem(json={"id": 1, "name": "alice", "extra": "new"})]
    node = _node({"fieldsToMatch": ["id"], "skipOnEqual": ["name"]})
    ctx = _ctx(node)
    ctx.node_outputs["SetA"] = input_1
    ctx.node_outputs["SetB"] = input_2

    out = await exec_compare_datasets(node, input_1 + input_2, ctx=ctx)
    _, items = out[0]
    buckets: dict[str, list[dict]] = {}
    for it in items:
        buckets.setdefault(it.json["compareBucket"], []).append(it.json)
    # name matches → drop from different_items, route to equal_items
    assert len(buckets.get("equal_items", [])) == 1
    assert "different_items" not in buckets


@pytest.mark.asyncio
async def test_skip_on_equal_keeps_item_in_different_when_field_differs() -> None:
    """skipOnEqual=['name']: when name differs, item stays in different_items."""
    input_1 = [ExecutionItem(json={"id": 1, "name": "alice"})]
    input_2 = [ExecutionItem(json={"id": 1, "name": "bob"})]
    node = _node({"fieldsToMatch": ["id"], "skipOnEqual": ["name"]})
    ctx = _ctx(node)
    ctx.node_outputs["SetA"] = input_1
    ctx.node_outputs["SetB"] = input_2

    out = await exec_compare_datasets(node, input_1 + input_2, ctx=ctx)
    _, items = out[0]
    buckets: dict[str, int] = {}
    for it in items:
        b = it.json["compareBucket"]
        buckets[b] = buckets.get(b, 0) + 1
    assert buckets.get("different_items") == 1
    assert "equal_items" not in buckets


@pytest.mark.asyncio
async def test_separate_output_format_emits_four_buckets() -> None:
    """outputFormat='separate' → four outputs with empty buckets as summary items."""
    input_1 = [ExecutionItem(json={"id": 1, "name": "a"})]
    input_2 = [ExecutionItem(json={"id": 1, "name": "a"})]  # equal
    node = _node({"fieldsToMatch": ["id"], "skipOnEqual": ["name"], "outputFormat": "separate"})
    ctx = _ctx(node)
    ctx.node_outputs["SetA"] = input_1
    ctx.node_outputs["SetB"] = input_2

    out = await exec_compare_datasets(node, input_1 + input_2, ctx=ctx)
    by_idx = {idx: items for idx, items in out}
    assert set(by_idx.keys()) == {0, 1, 2, 3}
    # 0=equal, 1=different, 2=unique_to_input_1, 3=unique_to_input_2
    assert by_idx[0] and by_idx[0][0].json["compareBucket"] == "equal_items"
    # empty buckets emit a summary item so the engine still walks them
    assert by_idx[1] and by_idx[1][0].json.get("compareSummary") is True
    assert by_idx[2] and by_idx[2][0].json.get("compareSummary") is True
    assert by_idx[3] and by_idx[3][0].json.get("compareSummary") is True


@pytest.mark.asyncio
async def test_prefer_by_field_consumes_first_match() -> None:
    """resolveBy=preferByField (default): input-1 item pairs with first match in input-2."""
    input_1 = [ExecutionItem(json={"id": 1, "tag": "a"})]
    input_2 = [
        ExecutionItem(json={"id": 1, "tag": "a"}),
        ExecutionItem(json={"id": 1, "tag": "b"}),  # would also match by id
    ]
    node = _node({"fieldsToMatch": ["id"]})
    ctx = _ctx(node)
    ctx.node_outputs["SetA"] = input_1
    ctx.node_outputs["SetB"] = input_2

    out = await exec_compare_datasets(node, input_1 + input_2, ctx=ctx)
    _, items = out[0]
    buckets: dict[str, list] = {}
    for it in items:
        buckets.setdefault(it.json["compareBucket"], []).append(it.json)
    # The first match (tag='a') is consumed; second input-2 item goes to unique_to_input_2.
    assert len(buckets.get("different_items", [])) == 1
    assert len(buckets.get("unique_to_input_2", [])) == 1
    assert buckets["unique_to_input_2"][0]["tag"] == "b"


# ── Internals ────────────────────────────────────────────────────────


def test_match_key_tuples_by_field_list() -> None:
    a = ExecutionItem(json={"id": 1, "name": "x"})
    b = ExecutionItem(json={"id": 1, "name": "x"})
    c = ExecutionItem(json={"id": 1, "name": "y"})
    assert _match_key(a, ["id", "name"]) == _match_key(b, ["id", "name"])
    assert _match_key(a, ["id", "name"]) != _match_key(c, ["id", "name"])
    assert _match_key(a, []) == ()


def test_split_inputs_by_target_index_uses_graph_and_node_outputs() -> None:
    node = _node({})
    ctx = _ctx(node)
    a_items = [ExecutionItem(json={"id": 1})]
    b_items = [ExecutionItem(json={"id": 2}), ExecutionItem(json={"id": 3})]
    ctx.node_outputs["SetA"] = a_items
    ctx.node_outputs["SetB"] = b_items
    split = _split_inputs_by_target_index(node, a_items + b_items, ctx=ctx)
    assert split.get(0) == a_items
    assert split.get(1) == b_items


# ── Descriptor / registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.compareDatasets" in REGISTRY
    assert "n8n-nodes-base.compareDatasets" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.compareDatasets"] == "transform"
    desc = REGISTRY["n8n-nodes-base.compareDatasets"]
    assert desc.executor == "app.services.workflows.nodes.flow:exec_compare_datasets"
    assert desc.outputs == (
        "equal_items",
        "different_items",
        "unique_to_input_1",
        "unique_to_input_2",
    )


# ── End-to-end ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_manual_two_sets_compare_downstream_sees_summary() -> None:
    """Manual → SetA (1 item) → compareDatasets ← SetB (1 item) → Downstream Set.

    Both items share id=1 and name='alice' so the match falls into ``equal_items``
    and the downstream Set node sees that bucket tag as a downstream field.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("a1", "SetA", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "id", "value": "1", "type": "number"},
                    {"name": "name", "value": "alice", "type": "string"},
                ]}
            }),
            _n("b1", "SetB", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "id", "value": "1", "type": "number"},
                    {"name": "name", "value": "alice", "type": "string"},
                    {"name": "note", "value": "extra", "type": "string"},
                ]}
            }),
            _n("cd1", "Compare", "n8n-nodes-base.compareDatasets", {
                "fieldsToMatch": ["id"],
                "skipOnEqual": ["name"],
                "outputFormat": "single",
            }),
            _n("d1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "saw_bucket", "value": "={{ $json.compareBucket }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[
                {"node": "SetA", "type": "main", "index": 0},
                {"node": "SetB", "type": "main", "index": 0},
            ]]},
            "SetA": {"main": [[{"node": "Compare", "type": "main", "index": 0}]]},
            "SetB": {"main": [[{"node": "Compare", "type": "main", "index": 1}]]},
            "Compare": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    compare_step = next(s for s in result.steps if s.node_name == "Compare")
    # One equal_items (id=1 match, name matches skipOnEqual)
    assert compare_step.output_count == 1
    sample = compare_step.sample_output[0]["json"]
    assert sample["compareBucket"] == "equal_items"
    assert sample["compareOpposite"]["id"] == "1"
    assert sample["compareOpposite"]["name"] == "alice"
    assert sample["compareOpposite"]["note"] == "extra"

    downstream_step = next(s for s in result.steps if s.node_name == "Downstream")
    assert downstream_step.input_count == 1
    assert downstream_step.output_count == 1
    # Downstream saw the summary tag we wrote in the Set node
    assert downstream_step.sample_output[0]["json"]["saw_bucket"] == "equal_items"
