"""Tests for the Local File Trigger node executor (n8n-nodes-base.localFileTrigger)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.core import exec_local_file_trigger


# ── Helpers ───────────────────────────────────────────────────────────


def _node(name: str = "LocalFile", params: dict | None = None) -> ExecNode:
    return ExecNode(
        id="lf1",
        name=name,
        type="n8n-nodes-base.localFileTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    file_change: object | None = None,
    mocks: dict | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    if mocks is None and file_change is not None:
        mocks = {"file_change": file_change}
    return EngineContext(graph=g, mocks=mocks or {})


def _doc(nodes, connections):
    return {"name": "local-file-trigger-test", "nodes": nodes, "connections": connections}


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
async def test_single_change_from_mock_emits_one_item() -> None:
    ctx = _ctx(
        file_change={"path": "/tmp/a.txt", "event": "modified", "size": 128},
    )
    node = _node()

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["path"] == "/tmp/a.txt"
    assert payload["event"] == "modified"
    assert payload["size"] == 128


@pytest.mark.asyncio
async def test_list_of_three_changes_emits_three_items() -> None:
    changes = [
        {"path": "/tmp/a.txt", "event": "created", "size": 10},
        {"path": "/tmp/b.txt", "event": "modified", "size": 20},
        {"path": "/tmp/c.txt", "event": "deleted", "size": 0},
    ]
    ctx = _ctx(file_change=changes)
    node = _node()

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 3
    assert [it.json["path"] for it in items] == ["/tmp/a.txt", "/tmp/b.txt", "/tmp/c.txt"]
    assert [it.json["event"] for it in items] == ["created", "modified", "deleted"]
    assert [it.json["size"] for it in items] == [10, 20, 0]


@pytest.mark.asyncio
async def test_empty_or_missing_mock_emits_single_empty_item() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"path": "", "event": "", "size": 0}


@pytest.mark.asyncio
async def test_parameters_path_used_as_default_when_no_mock() -> None:
    ctx = _ctx()
    node = _node(params={"path": "/var/data"})

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"path": "/var/data", "event": "", "size": 0}


@pytest.mark.asyncio
async def test_parameters_path_used_as_default_when_change_missing_path() -> None:
    ctx = _ctx(file_change={"event": "modified", "size": 5})
    node = _node(params={"path": "/var/data"})

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"path": "/var/data", "event": "modified", "size": 5}


@pytest.mark.asyncio
async def test_change_explicit_path_overrides_parameter_default() -> None:
    ctx = _ctx(file_change={"path": "/explicit.txt", "event": "modified", "size": 7})
    node = _node(params={"path": "/var/data"})

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert items[0].json["path"] == "/explicit.txt"


@pytest.mark.asyncio
async def test_change_with_extra_fields_preserves_them() -> None:
    ctx = _ctx(
        file_change={
            "path": "/tmp/a.txt",
            "event": "modified",
            "size": 12,
            "mtime": "2026-07-25T12:00:00Z",
            "custom": "keep",
        },
    )
    node = _node()

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["path"] == "/tmp/a.txt"
    assert payload["event"] == "modified"
    assert payload["size"] == 12
    assert payload["mtime"] == "2026-07-25T12:00:00Z"
    assert payload["custom"] == "keep"


@pytest.mark.asyncio
async def test_change_missing_event_and_size_get_defaults() -> None:
    ctx = _ctx(file_change={"path": "/tmp/a.txt"})
    node = _node()

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload == {"path": "/tmp/a.txt", "event": "", "size": 0}


@pytest.mark.asyncio
async def test_non_dict_mock_falls_back_to_empty_item() -> None:
    ctx = EngineContext(graph=ExecGraph(nodes_by_id={}, nodes_by_name={}))
    ctx.mocks["file_change"] = "not a dict"  # type: ignore[index]
    node = _node()

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"path": "", "event": "", "size": 0}


@pytest.mark.asyncio
async def test_empty_list_mock_falls_back_to_empty_item() -> None:
    ctx = _ctx(file_change=[])
    node = _node()

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"path": "", "event": "", "size": 0}


@pytest.mark.asyncio
async def test_list_mixed_with_non_dicts_filters_them_out() -> None:
    ctx = _ctx(
        file_change=[
            {"path": "/a", "event": "modified", "size": 1},
            "not a dict",
            {"path": "/b", "event": "created", "size": 2},
        ],
    )
    node = _node()

    out = await exec_local_file_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 2
    assert items[0].json["path"] == "/a"
    assert items[1].json["path"] == "/b"


@pytest.mark.asyncio
async def test_input_items_are_dropped() -> None:
    """Local File Trigger is a clean slate; upstream items are not propagated."""
    ctx = _ctx(file_change={"path": "/a", "event": "modified", "size": 1})
    node = _node()

    in_items = [ExecutionItem(json={"foo": 1}), ExecutionItem(json={"bar": 2})]
    out = await exec_local_file_trigger(node, items=in_items, ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert "foo" not in items[0].json
    assert "bar" not in items[0].json


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.localFileTrigger" in REGISTRY
    assert "n8n-nodes-base.localFileTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.localFileTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.localFileTrigger"]
    assert desc.executor.endswith(":exec_local_file_trigger")
    assert desc.category == "trigger"


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_local_file_trigger_seeds_downstream_set() -> None:
    """LocalFile → Set. The Local File trigger reads the pinned change via
    mocks and the downstream Set should see ``$json.path`` in scope."""
    doc = _doc(
        [
            _n("lf1", "LocalFile", "n8n-nodes-base.localFileTrigger"),
            _n(
                "st1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {
                            "name": "tag",
                            "value": "={{ 'path=' + $json.path }}",
                            "type": "string",
                        },
                    ]}
                },
            ),
        ],
        {
            "LocalFile": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    mocks = {
        "file_change": {"path": "/tmp/a.txt", "event": "modified", "size": 42},
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="localfile")

    assert result.status == "success", result.error_message
    assert result.final_items, "expected final items from Stamp"
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("tag") == "path=/tmp/a.txt"
    # path / event / size from the change are preserved on the item
    assert final_json.get("path") == "/tmp/a.txt"
    assert final_json.get("event") == "modified"
    assert final_json.get("size") == 42


@pytest.mark.asyncio
async def test_end_to_end_local_file_trigger_list_emits_one_item_per_change() -> None:
    """LocalFile → Set with a list of changes: each change flows through to Set."""
    doc = _doc(
        [
            _n("lf1", "LocalFile", "n8n-nodes-base.localFileTrigger"),
            _n(
                "st1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {
                            "name": "tag",
                            "value": "={{ $json.path }}",
                            "type": "string",
                        },
                    ]}
                },
            ),
        ],
        {
            "LocalFile": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    mocks = {
        "file_change": [
            {"path": "/a", "event": "created", "size": 1},
            {"path": "/b", "event": "modified", "size": 2},
        ],
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="localfile")

    assert result.status == "success", result.error_message
    assert len(result.final_items) == 2
    tags = [it.get("json", {}).get("tag") for it in result.final_items]
    assert tags == ["/a", "/b"]
