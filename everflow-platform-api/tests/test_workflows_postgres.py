"""Tests for the Postgres node executor (``n8n-nodes-base.postgres``).

Covers:

- ``postgres_response`` dict mock → envelope used per operation
- ``postgres_response`` callable mock receives
  ``(operation, query_or_table, params, item, ctx)``
- ``db_response`` fallback
- ``http_response`` fallback
- Offline execute: returns 2 rows
- Offline insert: affectedRows present
- Offline update: affectedRows=1
- Offline upsert: upserted=True
- ``operation='execute'`` reflected on output
- ``query`` default from ``$json``
- ``table`` default from ``$json``
- Empty query → no item
- End-to-end: Manual Trigger → postgres (execute mock) → Set sees rows
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.postgres import (
    POSTGRES_DEFAULT_OPERATION,
    POSTGRES_OPERATIONS,
    exec_postgres,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.postgres",
    id_: str = "pg1",
    name: str = "Postgres",
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


# ── 1. postgres_response dict mock (execute) ────────────────────────


@pytest.mark.asyncio
async def test_postgres_response_dict_mock_execute_used_verbatim() -> None:
    node = _node(
        {
            "operation": "execute",
            "query": "SELECT * FROM users",
        }
    )
    ctx = _ctx(
        {
            "postgres_response": {
                "rows": [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                ],
                "rowCount": 2,
                "command": "SELECT",
            }
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 2
    assert out[0].json["row"]["name"] == "Alice"
    assert out[0].json["rowCount"] == 2
    assert out[0].json["command"] == "SELECT"
    assert out[0].json["source"] == "postgres"
    assert "mockSource" not in out[0].json
    assert out[1].json["row"]["name"] == "Bob"


# ── 2. postgres_response callable mock signature ───────────────────


@pytest.mark.asyncio
async def test_postgres_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, query_or_table, params, item, ctx):
        captured["operation"] = operation
        captured["query_or_table"] = query_or_table
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "rows": [{"id": 1, "name": "Only"}],
            "rowCount": 1,
            "command": "SELECT",
        }

    node = _node(
        {
            "operation": "execute",
            "query": "SELECT 1",
            "extra": "keep",
        }
    )
    ctx = _ctx({"postgres_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_postgres(node, [item], ctx=ctx))

    assert captured["operation"] == "execute"
    assert captured["query_or_table"] == "SELECT 1"
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
            "operation": "execute",
            "query": "SELECT * FROM t",
        }
    )
    ctx = _ctx(
        {
            "db_response": {
                "rows": [{"id": 9, "name": "From DB"}],
                "rowCount": 1,
                "command": "SELECT",
            }
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["row"]["name"] == "From DB"
    assert out[0].json["mockSource"] == "db_response"
    assert out[0].json["source"] == "postgres"


# ── 4. http_response fallback ───────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "execute",
            "query": "SELECT * FROM t",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "rows": [{"id": 7, "name": "From HTTP"}],
                    "rowCount": 1,
                    "command": "SELECT",
                },
            }
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["row"]["name"] == "From HTTP"
    assert out[0].json["mockSource"] == "http_response"
    assert out[0].json["source"] == "postgres"


# ── 5. Offline execute: returns 2 rows ──────────────────────────────


@pytest.mark.asyncio
async def test_offline_execute_returns_two_rows() -> None:
    node = _node(
        {
            "operation": "execute",
            "query": "SELECT * FROM users",
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 2
    assert out[0].json["row"]["id"] == 1
    assert out[0].json["row"]["name"] == "Mock Row 1"
    assert out[0].json["row"]["value"] == 100
    assert out[0].json["rowCount"] == 2
    assert out[0].json["command"] == "SELECT"
    assert out[0].json["source"] == "postgres"
    assert out[0].json["mockSource"] == "offline"
    assert out[1].json["row"]["id"] == 2
    assert out[1].json["row"]["name"] == "Mock Row 2"
    assert out[1].json["row"]["value"] == 200


# ── 6. Offline insert: affectedRows present ─────────────────────────


@pytest.mark.asyncio
async def test_offline_insert_affected_rows_present() -> None:
    node = _node(
        {
            "operation": "insert",
            "table": "users",
            "values": [["a", 1], ["b", 2]],
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["affectedRows"] == 2
    assert p["command"] == "INSERT"
    assert isinstance(p["lastInsertId"], int)
    assert p["source"] == "postgres"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_insert_no_values_affected_one() -> None:
    node = _node(
        {
            "operation": "insert",
            "table": "users",
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    assert out[0].json["affectedRows"] == 1


# ── 7. Offline update: affectedRows=1 ───────────────────────────────


@pytest.mark.asyncio
async def test_offline_update_affected_rows_one() -> None:
    node = _node(
        {
            "operation": "update",
            "table": "users",
            "where": "id = 1",
            "values": [["Alice"]],
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["affectedRows"] == 1
    assert p["command"] == "UPDATE"
    assert "lastInsertId" not in p
    assert p["source"] == "postgres"
    assert p["mockSource"] == "offline"


# ── 8. Offline upsert: upserted=True ────────────────────────────────


@pytest.mark.asyncio
async def test_offline_upsert_upserted_true() -> None:
    node = _node(
        {
            "operation": "upsert",
            "table": "users",
            "where": "id = 1",
            "values": [["Alice"]],
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["affectedRows"] == 1
    assert p["command"] == "INSERT"
    assert isinstance(p["lastInsertId"], int)
    assert p["upserted"] is True
    assert p["source"] == "postgres"
    assert p["mockSource"] == "offline"


# ── 9. operation='execute' reflected ─────────────────────────────────


@pytest.mark.asyncio
async def test_operation_execute_reflected_in_command() -> None:
    node = _node(
        {
            "operation": "execute",
            "query": "SELECT 1",
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) > 0
    assert out[0].json["command"] == "SELECT"
    assert out[0].json["source"] == "postgres"


# ── 10. query default from $json ────────────────────────────────────


@pytest.mark.asyncio
async def test_query_default_from_json() -> None:
    node = _node({"operation": "execute"})
    item = ExecutionItem(json={"query": "SELECT * FROM json_table"})
    out = _out_items(await exec_postgres(node, [item], ctx=_ctx()))
    assert len(out) == 2
    assert out[0].json["source"] == "postgres"


@pytest.mark.asyncio
async def test_query_sql_default_from_json() -> None:
    node = _node({"operation": "execute"})
    item = ExecutionItem(json={"sql": "SELECT 1"})
    out = _out_items(await exec_postgres(node, [item], ctx=_ctx()))
    assert len(out) == 2


# ── 11. table default from $json ────────────────────────────────────


@pytest.mark.asyncio
async def test_table_default_from_json() -> None:
    node = _node({"operation": "insert"})
    item = ExecutionItem(json={"table": "json_table"})
    out = _out_items(await exec_postgres(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["source"] == "postgres"


@pytest.mark.asyncio
async def test_table_name_default_from_json() -> None:
    node = _node({"operation": "insert"})
    item = ExecutionItem(json={"tableName": "json_table_name"})
    out = _out_items(await exec_postgres(node, [item], ctx=_ctx()))
    assert len(out) == 1


# ── 12. Empty query → no item ───────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_query_skips_item() -> None:
    node = _node({"operation": "execute", "query": ""})
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_table_skips_insert() -> None:
    node = _node({"operation": "insert", "table": ""})
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_table_skips_update() -> None:
    node = _node({"operation": "update", "table": ""})
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


# ── 13. Unsupported operation raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "delete", "table": "t"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 14. dataMode honored ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_mode_object_is_accepted() -> None:
    node = _node(
        {
            "operation": "execute",
            "query": "SELECT * FROM t",
            "dataMode": "object",
        }
    )
    out = _out_items(
        await exec_postgres(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["rows"], list)
    assert len(p["rows"]) == 2
    assert p["rowCount"] == 2
    assert p["source"] == "postgres"


# ── 15. Default operation is 'execute' ───────────────────────────────


def test_default_operation_is_execute() -> None:
    assert POSTGRES_DEFAULT_OPERATION == "execute"
    assert set(POSTGRES_OPERATIONS) == {"execute", "insert", "update", "upsert"}


# ── 16. Multiple input items ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input_for_insert() -> None:
    node = _node({"operation": "insert", "table": "t"})
    items = [
        ExecutionItem(json={"values": [[1]]}),
        ExecutionItem(json={"values": [[2]]}),
        ExecutionItem(json={"values": [[3]]}),
    ]
    out = _out_items(await exec_postgres(node, items, ctx=_ctx()))
    assert len(out) == 3
    for o in out:
        assert o.json["source"] == "postgres"
        assert o.json["command"] == "INSERT"


# ── 17. Descriptor registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.postgres" in REGISTRY
    assert "n8n-nodes-base.postgres" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.postgres"] == "output"
    desc = REGISTRY["n8n-nodes-base.postgres"]
    assert desc.executor.endswith(":exec_postgres")
    assert desc.category == "output"


# ── 18. End-to-end: Manual Trigger → postgres (execute mock) → Set ─


def _doc(nodes, connections):
    return {"name": "postgres-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_postgres_execute_set_sees_rows() -> None:
    """Manual Trigger → postgres (execute, postgres_response mock) → Set pulls row fields."""
    mocks = {
        "postgres_response": {
            "rows": [
                {"id": 101, "name": "First", "value": 10},
                {"id": 102, "name": "Second", "value": 20},
            ],
            "rowCount": 2,
            "command": "SELECT",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "p1",
                "Postgres",
                "n8n-nodes-base.postgres",
                {
                    "operation": "execute",
                    "query": "SELECT * FROM users",
                },
            ),
            _n(
                "s1",
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
            "Start": {"main": [[{"node": "Postgres", "type": "main", "index": 0}]]},
            "Postgres": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    pg_step = next(s for s in result.steps if s.node_name == "Postgres")
    assert pg_step.status == "success", pg_step.error
    assert pg_step.output_count == 2

    final = result.final_items
    assert final, "expected at least one final item"
    names = [f.get("json", {}).get("result_name") for f in final]
    ids = [f.get("json", {}).get("result_id") for f in final]
    sources = [f.get("json", {}).get("result_source") for f in final]
    assert names == ["First", "Second"]
    assert ids == [101, 102]
    assert sources == ["postgres", "postgres"]