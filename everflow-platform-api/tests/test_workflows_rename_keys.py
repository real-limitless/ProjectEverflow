"""Tests for the Rename Keys node executor (n8n-nodes-base.renameKeys)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import exec_rename_keys


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="r1",
        name="RenameKeys",
        type="n8n-nodes-base.renameKeys",
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
    return {"name": "rename-keys-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


# ── Direct rename tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simple_direct_rename() -> None:
    items = [ExecutionItem(json={"a": 1, "b": 2})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "b"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert len(out) == 1 and out[0][0] == 0
    renamed = out[0][1]
    assert len(renamed) == 1
    # Without overwrite, the new key already exists, so skip
    assert renamed[0].json == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_direct_rename_with_overwrite() -> None:
    items = [ExecutionItem(json={"a": 1, "b": 2})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "b"}], "overwrite": True})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    renamed = out[0][1]
    assert renamed[0].json == {"b": 1}


@pytest.mark.asyncio
async def test_direct_rename_to_new_key() -> None:
    items = [ExecutionItem(json={"a": 1, "x": 9})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "b"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    renamed = out[0][1]
    assert renamed[0].json == {"b": 1, "x": 9}


@pytest.mark.asyncio
async def test_multiple_direct_renames() -> None:
    items = [ExecutionItem(json={"firstName": "Ada", "lastName": "Lovelace", "age": 36})]
    node = _node({
        "keys": [
            {"oldKey": "firstName", "newKey": "given_name"},
            {"oldKey": "lastName", "newKey": "family_name"},
        ]
    })
    out = await exec_rename_keys(node, items, ctx=_ctx())
    renamed = out[0][1]
    assert renamed[0].json == {
        "given_name": "Ada",
        "family_name": "Lovelace",
        "age": 36,
    }


@pytest.mark.asyncio
async def test_direct_rename_preserves_string_value() -> None:
    items = [ExecutionItem(json={"a": "hello world"})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "greeting"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"greeting": "hello world"}


@pytest.mark.asyncio
async def test_direct_rename_preserves_number_value() -> None:
    items = [ExecutionItem(json={"a": 42, "b": 3.14, "c": 0})]
    node = _node({
        "keys": [
            {"oldKey": "a", "newKey": "x"},
            {"oldKey": "b", "newKey": "y"},
            {"oldKey": "c", "newKey": "z"},
        ]
    })
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"x": 42, "y": 3.14, "z": 0}


@pytest.mark.asyncio
async def test_direct_rename_preserves_list_value() -> None:
    items = [ExecutionItem(json={"a": [1, 2, 3]})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "xs"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"xs": [1, 2, 3]}


@pytest.mark.asyncio
async def test_direct_rename_preserves_dict_value() -> None:
    items = [ExecutionItem(json={"a": {"nested": True, "n": 7}})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "obj"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"obj": {"nested": True, "n": 7}}


@pytest.mark.asyncio
async def test_direct_rename_preserves_none_value() -> None:
    items = [ExecutionItem(json={"a": None, "b": "kept"})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "x"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"x": None, "b": "kept"}


# ── Regex rename tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regex_rename_strips_prefix() -> None:
    items = [ExecutionItem(json={"prefix_a": 1, "prefix_b": 2, "other": 3})]
    node = _node({"regexReplacements": [
        {"searchRegex": "^prefix_", "replaceRegex": "x_"}
    ]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"x_a": 1, "x_b": 2, "other": 3}


@pytest.mark.asyncio
async def test_regex_rename_uses_alternate_key_names() -> None:
    items = [ExecutionItem(json={"user.name": "Ada", "user.age": 36})]
    node = _node({"regexReplacements": [
        {"regex": "\\.", "replace": "_"}
    ]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"user_name": "Ada", "user_age": 36}


@pytest.mark.asyncio
async def test_regex_then_direct_rename() -> None:
    """Regex runs first; direct rename can target the produced key."""
    items = [ExecutionItem(json={"prefix_firstName": "Ada"})]
    node = _node({
        "regexReplacements": [{"searchRegex": "^prefix_", "replaceRegex": ""}],
        "keys": [{"oldKey": "firstName", "newKey": "given_name"}],
    })
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"given_name": "Ada"}


@pytest.mark.asyncio
async def test_invalid_regex_is_skipped() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"regexReplacements": [
        {"searchRegex": "[unclosed", "replaceRegex": "x"}
    ]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    # Invalid regex is silently dropped; item passes through unchanged.
    assert out[0][1][0].json == {"a": 1}


# ── Overwrite & edge cases ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_overwrite_false_keeps_existing_new_key() -> None:
    items = [ExecutionItem(json={"a": 1, "b": 999})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "b"}]})  # overwrite defaults to False
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"a": 1, "b": 999}


@pytest.mark.asyncio
async def test_overwrite_true_replaces_existing_new_key() -> None:
    items = [ExecutionItem(json={"a": 1, "b": 999})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "b"}], "overwrite": True})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"b": 1}


@pytest.mark.asyncio
async def test_missing_old_key_is_noop() -> None:
    items = [ExecutionItem(json={"present": 1})]
    node = _node({"keys": [{"oldKey": "absent", "newKey": "renamed"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"present": 1}


@pytest.mark.asyncio
async def test_same_old_and_new_key_is_skipped() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"keys": [{"oldKey": "a", "newKey": "a"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"a": 1}


@pytest.mark.asyncio
async def test_empty_parameters_is_passthrough() -> None:
    items = [ExecutionItem(json={"a": 1, "b": 2})]
    node = _node({})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_empty_items_returns_empty_output() -> None:
    node = _node({"keys": [{"oldKey": "a", "newKey": "b"}]})
    out = await exec_rename_keys(node, [], ctx=_ctx())
    assert out == [(0, [])]


@pytest.mark.asyncio
async def test_rename_applies_to_each_item_independently() -> None:
    items = [
        ExecutionItem(json={"a": 1, "b": 2}),
        ExecutionItem(json={"a": 10, "c": 30}),
    ]
    node = _node({"keys": [{"oldKey": "a", "newKey": "alpha"}]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    renamed = out[0][1]
    assert renamed[0].json == {"alpha": 1, "b": 2}
    assert renamed[1].json == {"alpha": 10, "c": 30}


@pytest.mark.asyncio
async def test_keys_wrapped_in_values() -> None:
    items = [ExecutionItem(json={"a": 1})]
    node = _node({"keys": {"values": [{"oldKey": "a", "newKey": "alpha"}]}})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"alpha": 1}


@pytest.mark.asyncio
async def test_malformed_entries_are_ignored() -> None:
    items = [ExecutionItem(json={"a": 1, "b": 2})]
    node = _node({"keys": [
        {"oldKey": "a", "newKey": "alpha"},
        {"oldKey": "b"},  # missing newKey → ignored
        "not-a-dict",  # ignored
        {"oldKey": "", "newKey": "ignored"},
    ]})
    out = await exec_rename_keys(node, items, ctx=_ctx())
    assert out[0][1][0].json == {"alpha": 1, "b": 2}


# ── Descriptor & end-to-end ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.renameKeys" in REGISTRY
    assert "n8n-nodes-base.renameKeys" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.renameKeys"] == "transform"
    desc = REGISTRY["n8n-nodes-base.renameKeys"]
    assert desc.executor.endswith(":exec_rename_keys")


@pytest.mark.asyncio
async def test_end_to_end_manual_trigger_set_renamekeys_set() -> None:
    """Manual → Set (creates ``old`` field) → renameKeys → Set reads ``renamed`` field."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("p1", "Produce", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "old", "value": "secret", "type": "string"},
                    {"name": "keep", "value": "yes", "type": "string"},
                ]}
            }),
            _n("r1", "RenameKeys", "n8n-nodes-base.renameKeys", {
                "keys": [{"oldKey": "old", "newKey": "renamed"}],
            }),
            _n("d1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "saw_renamed", "value": "={{ $json.renamed }}", "type": "string"},
                    {"name": "no_old", "value": "={{ $json.old }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Produce", "type": "main", "index": 0}]]},
            "Produce": {"main": [[{"node": "RenameKeys", "type": "main", "index": 0}]]},
            "RenameKeys": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    rename_step = next(s for s in result.steps if s.node_name == "RenameKeys")
    assert rename_step.output_count == 1

    downstream_step = next(s for s in result.steps if s.node_name == "Downstream")
    assert downstream_step.input_count == 1
    # The downstream Set sees the renamed field; the old key is gone.
    final_items = result.final_items
    assert final_items, "expected at least one final item"
    final = final_items[0].get("json") if isinstance(final_items[0], dict) else None
    assert final is not None
    assert final.get("saw_renamed") == "secret"
    assert final.get("no_old") is None
    assert final.get("keep") == "yes"
