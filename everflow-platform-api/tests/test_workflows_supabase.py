"""Tests for the Supabase node executor (``n8n-nodes-base.supabase``).

Covers:

- ``supabase_response`` dict mock → envelope used per operation
- ``supabase_response`` callable mock receives
  ``(operation, table, params, item, ctx)``
- ``db_response`` fallback
- ``http_response`` fallback
- Offline select: returns up to 3 rows
- Offline insert: data present, status=201
- Offline update: count=1, status=200
- Offline upsert: upserted=True
- ``operation='select'`` reflected on output
- ``table`` default from ``$json``
- ``limit`` honored
- Empty table → no item
- End-to-end: Manual Trigger → supabase (select mock) → Set sees data
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.supabase import (
    SUPABASE_DEFAULT_OPERATION,
    SUPABASE_OPERATIONS,
    exec_supabase,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.supabase",
    id_: str = "sb1",
    name: str = "Supabase",
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


# ── 1. supabase_response dict mock (select) ────────────────────────


@pytest.mark.asyncio
async def test_supabase_response_dict_mock_select_used_verbatim() -> None:
    node = _node(
        {
            "operation": "select",
            "table": "users",
        }
    )
    ctx = _ctx(
        {
            "supabase_response": {
                "data": [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                ],
                "count": 2,
                "status": 200,
            }
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 2
    assert out[0].json["row"]["name"] == "Alice"
    assert out[0].json["count"] == 2
    assert out[0].json["source"] == "supabase"
    assert "mockSource" not in out[0].json
    assert out[1].json["row"]["name"] == "Bob"


# ── 2. supabase_response callable mock signature ───────────────────


@pytest.mark.asyncio
async def test_supabase_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, table, params, item, ctx):
        captured["operation"] = operation
        captured["table"] = table
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "data": [{"id": 1, "name": "Only"}],
            "count": 1,
            "status": 200,
        }

    node = _node(
        {
            "operation": "select",
            "table": "users",
            "extra": "keep",
        }
    )
    ctx = _ctx({"supabase_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_supabase(node, [item], ctx=ctx))

    assert captured["operation"] == "select"
    assert captured["table"] == "users"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["row"]["name"] == "Only"


# ── 3. db_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_db_response_fallback_used() -> None:
    node = _node(
        {
            "operation": "select",
            "table": "users",
        }
    )
    ctx = _ctx(
        {
            "db_response": {
                "data": [{"id": 9, "name": "From DB"}],
                "count": 1,
                "status": 200,
            }
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["row"]["name"] == "From DB"
    assert out[0].json["mockSource"] == "db_response"
    assert out[0].json["source"] == "supabase"


# ── 4. http_response fallback ───────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "select",
            "table": "users",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "data": [{"id": 7, "name": "From HTTP"}],
                    "count": 1,
                    "status": 200,
                },
            }
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["row"]["name"] == "From HTTP"
    assert out[0].json["mockSource"] == "http_response"
    assert out[0].json["source"] == "supabase"


# ── 5. Offline select: returns up to 3 rows ────────────────────────


@pytest.mark.asyncio
async def test_offline_select_returns_three_rows() -> None:
    node = _node(
        {
            "operation": "select",
            "table": "users",
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3
    assert out[0].json["row"]["id"] == 1
    assert out[0].json["row"]["name"] == "Mock Row 1"
    assert out[0].json["row"]["value"] == 10
    assert out[0].json["count"] == 3
    assert out[0].json["source"] == "supabase"
    assert out[0].json["mockSource"] == "offline"
    assert out[1].json["row"]["id"] == 2
    assert out[1].json["row"]["name"] == "Mock Row 2"
    assert out[1].json["row"]["value"] == 20
    assert out[2].json["row"]["id"] == 3
    assert out[2].json["row"]["name"] == "Mock Row 3"
    assert out[2].json["row"]["value"] == 30


# ── 6. Offline insert: data present, status=201 ────────────────────


@pytest.mark.asyncio
async def test_offline_insert_data_present_status_201() -> None:
    node = _node(
        {
            "operation": "insert",
            "table": "users",
            "records": [{"name": "Alice", "email": "alice@example.com"}],
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["data"], list)
    assert len(p["data"]) == 1
    assert p["data"][0]["name"] == "Alice"
    assert p["data"][0]["email"] == "alice@example.com"
    assert isinstance(p["data"][0]["id"], int)
    assert p["count"] == 1
    assert p["status"] == 201
    assert p["source"] == "supabase"
    assert p["mockSource"] == "offline"
    assert "upserted" not in p


@pytest.mark.asyncio
async def test_offline_insert_wraps_json_as_single_record() -> None:
    node = _node({"operation": "insert", "table": "users"})
    item = ExecutionItem(json={"name": "FromJson", "age": 30})
    out = _out_items(await exec_supabase(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["data"][0]["name"] == "FromJson"
    assert p["data"][0]["age"] == 30
    assert p["status"] == 201


# ── 7. Offline update: count=1, status=200 ─────────────────────────


@pytest.mark.asyncio
async def test_offline_update_count_one_status_200() -> None:
    node = _node(
        {
            "operation": "update",
            "table": "users",
            "records": [{"name": "Updated"}],
            "match": {"id": 42},
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["count"] == 1
    assert p["status"] == 200
    assert p["data"][0]["id"] == 42
    assert p["data"][0]["name"] == "Updated"
    assert p["source"] == "supabase"
    assert p["mockSource"] == "offline"
    assert "upserted" not in p


# ── 8. Offline upsert: upserted=True ───────────────────────────────


@pytest.mark.asyncio
async def test_offline_upsert_upserted_true() -> None:
    node = _node(
        {
            "operation": "upsert",
            "table": "users",
            "records": [{"name": "Upserted"}],
            "match": {"id": 42},
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["count"] == 1
    assert p["status"] == 201
    assert p["upserted"] is True
    assert p["data"][0]["id"] == 42
    assert p["data"][0]["name"] == "Upserted"
    assert p["source"] == "supabase"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_upsert_no_match_generates_new_id() -> None:
    node = _node(
        {
            "operation": "upsert",
            "table": "users",
            "records": [{"name": "New"}],
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["upserted"] is True
    assert isinstance(p["data"][0]["id"], int)


# ── 9. operation='select' reflected ─────────────────────────────────


@pytest.mark.asyncio
async def test_operation_select_reflected_in_output() -> None:
    node = _node({"operation": "select", "table": "users"})
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) > 0
    assert "row" in out[0].json
    assert out[0].json["source"] == "supabase"


# ── 10. table default from $json ────────────────────────────────────


@pytest.mark.asyncio
async def test_table_default_from_json() -> None:
    node = _node({"operation": "select"})
    item = ExecutionItem(json={"table": "json_table"})
    out = _out_items(await exec_supabase(node, [item], ctx=_ctx()))
    assert len(out) > 0
    assert out[0].json["source"] == "supabase"


@pytest.mark.asyncio
async def test_table_name_default_from_json() -> None:
    node = _node({"operation": "select"})
    item = ExecutionItem(json={"tableName": "json_table_name"})
    out = _out_items(await exec_supabase(node, [item], ctx=_ctx()))
    assert len(out) > 0
    assert out[0].json["source"] == "supabase"


# ── 11. limit honored ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_honored() -> None:
    node = _node(
        {
            "operation": "select",
            "table": "users",
            "limit": 2,
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 2
    assert out[0].json["row"]["id"] == 1
    assert out[1].json["row"]["id"] == 2
    assert out[0].json["count"] == 2


@pytest.mark.asyncio
async def test_limit_one_returns_single_row() -> None:
    node = _node(
        {
            "operation": "select",
            "table": "users",
            "limit": 1,
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    assert out[0].json["row"]["id"] == 1
    assert out[0].json["count"] == 1


@pytest.mark.asyncio
async def test_limit_zero_returns_no_rows() -> None:
    node = _node(
        {
            "operation": "select",
            "table": "users",
            "limit": 0,
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


# ── 12. Empty table → no item ───────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_table_skips_select() -> None:
    node = _node({"operation": "select", "table": ""})
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_table_skips_insert() -> None:
    node = _node({"operation": "insert", "table": ""})
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_table_skips_update() -> None:
    node = _node({"operation": "update", "table": ""})
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


# ── 13. Unsupported operation raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "delete", "table": "t"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 14. dataMode honored ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_mode_object_is_accepted() -> None:
    node = _node(
        {
            "operation": "select",
            "table": "users",
            "dataMode": "object",
        }
    )
    out = _out_items(
        await exec_supabase(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["data"], list)
    assert len(p["data"]) == 3
    assert p["count"] == 3
    assert p["source"] == "supabase"


# ── 15. Default operation is 'select' ───────────────────────────────


def test_default_operation_is_select() -> None:
    assert SUPABASE_DEFAULT_OPERATION == "select"
    assert set(SUPABASE_OPERATIONS) == {"select", "insert", "update", "upsert"}


# ── 16. Multiple input items ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input_for_insert() -> None:
    node = _node({"operation": "insert", "table": "t"})
    items = [
        ExecutionItem(json={"name": "A"}),
        ExecutionItem(json={"name": "B"}),
        ExecutionItem(json={"name": "C"}),
    ]
    out = _out_items(await exec_supabase(node, items, ctx=_ctx()))
    assert len(out) == 3
    for o in out:
        assert o.json["source"] == "supabase"
        assert o.json["status"] == 201


# ── 17. Descriptor registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.supabase" in REGISTRY
    assert "n8n-nodes-base.supabase" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.supabase"] == "output"
    desc = REGISTRY["n8n-nodes-base.supabase"]
    assert desc.executor.endswith(":exec_supabase")
    assert desc.category == "output"


# ── 18. End-to-end: Manual Trigger → supabase (select mock) → Set ─


def _doc(nodes, connections):
    return {"name": "supabase-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_supabase_select_set_sees_data() -> None:
    """Manual Trigger → supabase (select, supabase_response mock) → Set pulls row fields."""
    mocks = {
        "supabase_response": {
            "data": [
                {"id": 101, "name": "First", "value": 10},
                {"id": 102, "name": "Second", "value": 20},
            ],
            "count": 2,
            "status": 200,
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "s1",
                "Supabase",
                "n8n-nodes-base.supabase",
                {
                    "operation": "select",
                    "table": "users",
                },
            ),
            _n(
                "d1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_id", "value": "={{ $json.row.id }}", "type": "number"},
                            {"name": "result_name", "value": "={{ $json.row.name }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Supabase", "type": "main", "index": 0}]]},
            "Supabase": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    sb_step = next(s for s in result.steps if s.node_name == "Supabase")
    assert sb_step.status == "success", sb_step.error
    assert sb_step.output_count == 2

    final = result.final_items
    assert final, "expected at least one final item"
    names = [f.get("json", {}).get("result_name") for f in final]
    ids = [f.get("json", {}).get("result_id") for f in final]
    sources = [f.get("json", {}).get("result_source") for f in final]
    assert names == ["First", "Second"]
    assert ids == [101, 102]
    assert sources == ["supabase", "supabase"]