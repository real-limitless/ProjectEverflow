"""Tests for the Airtable node executor (``n8n-nodes-base.airtable``).

Covers:

- ``airtable_response`` dict mock → envelope used per operation
- ``airtable_response`` callable mock receives
  ``(operation, base, table, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline list: returns up to 3 records
- Offline create: recordId present, fields echoed
- Offline read: recordId echoed, fields present
- Offline update: fields echoed
- Offline upsert: updatedRecords=1
- ``operation='list'`` reflected on output
- ``base``/``table`` defaults from ``$json``
- ``maxRecords`` honored
- Empty base → no item
- End-to-end: Manual Trigger → airtable (list mock) → Set sees recordId/fields
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.airtable import (
    AIRTABLE_DEFAULT_OPERATION,
    AIRTABLE_OPERATIONS,
    exec_airtable,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.airtable",
    id_: str = "at1",
    name: str = "Airtable",
    credentials: dict[str, Any] | None = None,
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params,
        credentials=credentials,
        position={"x": 0, "y": 0},
    )


def _ctx(mocks: dict[str, Any] | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {})  # type: ignore[arg-type]


def _out_items(result) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── 1. airtable_response dict mock (list) ─────────────────────────────


@pytest.mark.asyncio
async def test_airtable_response_dict_mock_list_used_verbatim() -> None:
    node = _node(
        {
            "operation": "list",
            "base": "appXXX",
            "table": "Tasks",
        }
    )
    ctx = _ctx(
        {
            "airtable_response": {
                "records": [
                    {
                        "id": "recA",
                        "fields": {"Name": "Task A", "Status": "Done"},
                        "createdTime": "2024-01-01T00:00:00.000Z",
                    },
                    {
                        "id": "recB",
                        "fields": {"Name": "Task B", "Status": "Todo"},
                        "createdTime": "2024-01-02T00:00:00.000Z",
                    },
                ]
            }
        }
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 2
    assert out[0].json["recordId"] == "recA"
    assert out[0].json["fields"]["Name"] == "Task A"
    assert out[0].json["fields"]["Status"] == "Done"
    assert out[0].json["createdTime"] == "2024-01-01T00:00:00.000Z"
    assert out[0].json["source"] == "airtable"
    assert out[0].json["operation"] == "list"
    assert "mockSource" not in out[0].json
    assert out[1].json["recordId"] == "recB"


# ── 2. airtable_response callable mock signature ─────────────────────


@pytest.mark.asyncio
async def test_airtable_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, base, table, params, item, ctx):
        captured["operation"] = operation
        captured["base"] = base
        captured["table"] = table
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "records": [
                {
                    "id": "rec1",
                    "fields": {"Name": "Only"},
                    "createdTime": "2024-01-01T00:00:00.000Z",
                }
            ]
        }

    node = _node(
        {
            "operation": "list",
            "base": "appYYY",
            "table": "MyTable",
            "extra": "keep",
        }
    )
    ctx = _ctx({"airtable_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_airtable(node, [item], ctx=ctx))

    assert captured["operation"] == "list"
    assert captured["base"] == "appYYY"
    assert captured["table"] == "MyTable"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["recordId"] == "rec1"
    assert out[0].json["fields"]["Name"] == "Only"


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "list",
            "base": "appZ",
            "table": "T",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "records": [
                        {
                            "id": "recX",
                            "fields": {"Name": "X"},
                            "createdTime": "2024-01-01T00:00:00.000Z",
                        },
                    ]
                },
            }
        }
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["recordId"] == "recX"
    assert out[0].json["fields"]["Name"] == "X"
    assert out[0].json["mockSource"] == "http_response"
    assert out[0].json["source"] == "airtable"


# ── 4. Offline list returns up to 3 records ───────────────────────────


@pytest.mark.asyncio
async def test_offline_list_returns_three_records() -> None:
    node = _node({"operation": "list", "base": "appA", "table": "T"})
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3
    for i, o in enumerate(out):
        assert o.json["recordId"] == f"rec{i + 1}"
        assert o.json["fields"]["Name"] == f"Mock Record {i + 1}"
        assert o.json["fields"]["Status"] == "Active"
        assert o.json["fields"]["Value"] == (i + 1) * 10
        assert o.json["source"] == "airtable"
        assert o.json["mockSource"] == "offline"
        assert o.json["operation"] == "list"
        assert o.json["createdTime"].endswith("Z")


# ── 5. Offline create: recordId present, fields echoed ────────────────


@pytest.mark.asyncio
async def test_offline_create_record_id_present_fields_echoed() -> None:
    node = _node(
        {
            "operation": "create",
            "base": "appB",
            "table": "T",
            "records": [{"fields": {"Name": "New Task", "Status": "Todo"}}],
        }
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["recordId"].startswith("rec")
    assert p["fields"]["Name"] == "New Task"
    assert p["fields"]["Status"] == "Todo"
    assert p["source"] == "airtable"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "create"
    assert p["createdTime"].endswith("Z")


@pytest.mark.asyncio
async def test_offline_create_use_item_fields() -> None:
    node = _node(
        {
            "operation": "create",
            "base": "appU",
            "table": "T",
            "useItemFields": True,
        }
    )
    item = ExecutionItem(json={"Name": "From Item", "Status": "New"})
    out = _out_items(await exec_airtable(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["recordId"].startswith("rec")
    assert p["fields"]["Name"] == "From Item"
    assert p["fields"]["Status"] == "New"
    assert p["source"] == "airtable"


# ── 6. Offline read: recordId echoed, fields present ──────────────────


@pytest.mark.asyncio
async def test_offline_read_record_id_echoed_fields_present() -> None:
    node = _node(
        {
            "operation": "read",
            "base": "appC",
            "table": "T",
            "recordId": "recRead1",
        }
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["recordId"] == "recRead1"
    assert "fields" in p
    assert isinstance(p["fields"], dict)
    assert p["fields"]["Name"] == "Mock Record"
    assert p["fields"]["Status"] == "Active"
    assert p["source"] == "airtable"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "read"
    assert p["createdTime"].endswith("Z")


# ── 7. Offline update: fields echoed ──────────────────────────────────


@pytest.mark.asyncio
async def test_offline_update_fields_echoed() -> None:
    node = _node(
        {
            "operation": "update",
            "base": "appD",
            "table": "T",
            "recordId": "recUpd1",
            "fields": {"Name": "Updated", "Status": "Done"},
        }
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["recordId"] == "recUpd1"
    assert p["fields"]["Name"] == "Updated"
    assert p["fields"]["Status"] == "Done"
    assert p["source"] == "airtable"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "update"
    assert p["createdTime"].endswith("Z")


# ── 8. Offline upsert: updatedRecords=1 ───────────────────────────────


@pytest.mark.asyncio
async def test_offline_upsert_updated_records_one() -> None:
    node = _node(
        {
            "operation": "upsert",
            "base": "appE",
            "table": "T",
            "recordId": "recUps1",
            "fields": {"Name": "Upserted"},
        }
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["recordId"] == "recUps1"
    assert p["fields"]["Name"] == "Upserted"
    assert p["updatedRecords"] == 1
    assert p["createdRecords"] == 0
    assert p["source"] == "airtable"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "upsert"
    assert p["createdTime"].endswith("Z")


# ── 9. operation='list' reflected ─────────────────────────────────────


@pytest.mark.asyncio
async def test_operation_list_reflected() -> None:
    node = _node({"operation": "list", "base": "appF", "table": "T"})
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) > 0
    assert out[0].json["operation"] == "list"
    assert out[0].json["source"] == "airtable"


# ── 10. base/table defaults from $json ────────────────────────────────


@pytest.mark.asyncio
async def test_base_table_defaults_from_json() -> None:
    node = _node({"operation": "list"})
    item = ExecutionItem(json={"base": "appJson", "table": "JsonTable"})
    out = _out_items(await exec_airtable(node, [item], ctx=_ctx()))
    assert len(out) == 3
    assert out[0].json["source"] == "airtable"


@pytest.mark.asyncio
async def test_base_id_table_name_defaults_from_json() -> None:
    node = _node({"operation": "list"})
    item = ExecutionItem(json={"baseId": "appJsonId", "tableName": "JsonTableName"})
    out = _out_items(await exec_airtable(node, [item], ctx=_ctx()))
    assert len(out) == 3


@pytest.mark.asyncio
async def test_record_id_default_from_json() -> None:
    node = _node({"operation": "read", "base": "appR", "table": "T"})
    item = ExecutionItem(json={"recordId": "from-json-rec"})
    out = _out_items(await exec_airtable(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["recordId"] == "from-json-rec"


@pytest.mark.asyncio
async def test_record_id_default_from_json_id() -> None:
    node = _node({"operation": "update", "base": "appR2", "table": "T"})
    item = ExecutionItem(json={"id": "from-json-id", "fields": {"X": 1}})
    out = _out_items(await exec_airtable(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["recordId"] == "from-json-id"


# ── 11. maxRecords honored ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_records_honored() -> None:
    node = _node(
        {"operation": "list", "base": "appG", "table": "T", "maxRecords": 2}
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 2
    assert out[0].json["recordId"] == "rec1"
    assert out[1].json["recordId"] == "rec2"


@pytest.mark.asyncio
async def test_max_records_one_returns_one_record() -> None:
    node = _node(
        {"operation": "list", "base": "appG2", "table": "T", "maxRecords": 1}
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    assert out[0].json["recordId"] == "rec1"


# ── 12. Empty base/table/recordId → no item ───────────────────────────


@pytest.mark.asyncio
async def test_empty_base_skips_item() -> None:
    node = _node({"operation": "list", "base": "", "table": "T"})
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_table_skips_item() -> None:
    node = _node({"operation": "list", "base": "appH", "table": ""})
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_record_id_skips_read() -> None:
    node = _node(
        {"operation": "read", "base": "appI", "table": "T", "recordId": ""}
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_record_id_skips_update() -> None:
    node = _node(
        {"operation": "update", "base": "appI2", "table": "T", "recordId": ""}
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_record_id_upsert_still_emits() -> None:
    """Upsert with empty recordId should still emit (create semantics)."""
    node = _node(
        {
            "operation": "upsert",
            "base": "appI3",
            "table": "T",
            "fields": {"Name": "Created"},
        }
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    assert out[0].json["operation"] == "upsert"


# ── 13. Unsupported operation raises ──────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "delete", "base": "appJ", "table": "T"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 14. dataMode honored ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_mode_object_is_accepted() -> None:
    node = _node(
        {
            "operation": "list",
            "base": "appO",
            "table": "T",
            "dataMode": "object",
        }
    )
    out = _out_items(
        await exec_airtable(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["records"], list)
    assert len(p["records"]) == 3
    assert p["source"] == "airtable"
    assert p["operation"] == "list"


# ── 15. Default operation is 'list' ───────────────────────────────────


def test_default_operation_is_list() -> None:
    assert AIRTABLE_DEFAULT_OPERATION == "list"
    assert set(AIRTABLE_OPERATIONS) == {"list", "create", "read", "update", "upsert"}


# ── 16. Multiple input items ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input_for_read() -> None:
    node = _node({"operation": "read", "base": "appM", "table": "T"})
    items = [
        ExecutionItem(json={"recordId": "a"}),
        ExecutionItem(json={"recordId": "b"}),
        ExecutionItem(json={"recordId": "c"}),
    ]
    out = _out_items(await exec_airtable(node, items, ctx=_ctx()))
    assert len(out) == 3
    assert [o.json["recordId"] for o in out] == ["a", "b", "c"]


# ── 17. Descriptor registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.airtable" in REGISTRY
    assert "n8n-nodes-base.airtable" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.airtable"] == "output"
    desc = REGISTRY["n8n-nodes-base.airtable"]
    assert desc.executor.endswith(":exec_airtable")
    assert desc.category == "output"


# ── 18. End-to-end: Manual Trigger → airtable (list mock) → Set ──────


def _doc(nodes, connections):
    return {"name": "airtable-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_airtable_list_set_sees_record_id_and_fields() -> None:
    """Manual Trigger → airtable (list, airtable_response mock) → Set pulls recordId/fields."""
    mocks = {
        "airtable_response": {
            "records": [
                {
                    "id": "recE1",
                    "fields": {"Name": "First", "Status": "Done"},
                    "createdTime": "2024-01-01T00:00:00.000Z",
                },
                {
                    "id": "recE2",
                    "fields": {"Name": "Second", "Status": "Todo"},
                    "createdTime": "2024-01-02T00:00:00.000Z",
                },
            ]
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "a1",
                "Airtable",
                "n8n-nodes-base.airtable",
                {
                    "operation": "list",
                    "base": "appE2E",
                    "table": "Tasks",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_id", "value": "={{ $json.recordId }}", "type": "string"},
                            {"name": "result_name", "value": "={{ $json.fields.Name }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Airtable", "type": "main", "index": 0}]]},
            "Airtable": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    airtable_step = next(s for s in result.steps if s.node_name == "Airtable")
    assert airtable_step.status == "success", airtable_step.error
    assert airtable_step.output_count == 2

    final = result.final_items
    assert final, "expected at least one final item"
    names = [f.get("json", {}).get("result_name") for f in final]
    ids = [f.get("json", {}).get("result_id") for f in final]
    sources = [f.get("json", {}).get("result_source") for f in final]
    assert names == ["First", "Second"]
    assert ids == ["recE1", "recE2"]
    assert sources == ["airtable", "airtable"]