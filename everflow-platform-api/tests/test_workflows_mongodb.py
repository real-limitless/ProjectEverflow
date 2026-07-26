"""Tests for the MongoDb node executor (``n8n-nodes-base.mongoDb``).

Covers:

- ``mongodb_response`` dict mock → envelope used per operation
- ``mongodb_response`` callable mock receives
  ``(operation, collection, params, item, ctx)``
- ``db_response`` fallback
- ``http_response`` fallback unwraps a JSON body
- Offline find: returns up to 3 documents
- Offline insert: insertedCount present
- Offline update: matchedCount=1, modifiedCount=1
- Offline delete: deletedCount=1
- Offline aggregate: result present
- ``operation='find'`` reflected on output
- ``collection`` default from ``$json``
- ``limit`` honored
- Empty collection → no item
- End-to-end: Manual Trigger → mongoDb (find mock) → Set sees documents
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.mongodb import (
    MONGODB_DEFAULT_OPERATION,
    MONGODB_OPERATIONS,
    exec_mongodb,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.mongoDb",
    id_: str = "md1",
    name: str = "MongoDb",
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


# ── 1. mongodb_response dict mock (find) ───────────────────────────


@pytest.mark.asyncio
async def test_mongodb_response_dict_mock_find_used_verbatim() -> None:
    node = _node(
        {
            "operation": "find",
            "collection": "users",
            "query": {"status": "active"},
        }
    )
    ctx = _ctx(
        {
            "mongodb_response": {
                "documents": [
                    {"_id": "a1", "name": "Alice"},
                    {"_id": "b2", "name": "Bob"},
                ],
                "count": 2,
            }
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 2
    assert out[0].json["document"]["name"] == "Alice"
    assert out[0].json["count"] == 2
    assert out[0].json["source"] == "mongoDb"
    assert out[0].json["operation"] == "find"
    assert "mockSource" not in out[0].json
    assert out[1].json["document"]["name"] == "Bob"


# ── 2. mongodb_response callable mock signature ───────────────────


@pytest.mark.asyncio
async def test_mongodb_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, collection, params, item, ctx):
        captured["operation"] = operation
        captured["collection"] = collection
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "documents": [{"_id": "x1", "name": "Only"}],
            "count": 1,
        }

    node = _node(
        {
            "operation": "find",
            "collection": "users",
            "extra": "keep",
        }
    )
    ctx = _ctx({"mongodb_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_mongodb(node, [item], ctx=ctx))

    assert captured["operation"] == "find"
    assert captured["collection"] == "users"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["document"]["name"] == "Only"


# ── 3. db_response fallback ───────────────────────────────────────


@pytest.mark.asyncio
async def test_db_response_fallback_used() -> None:
    node = _node(
        {
            "operation": "find",
            "collection": "users",
        }
    )
    ctx = _ctx(
        {
            "db_response": {
                "documents": [{"_id": "d9", "name": "From DB"}],
                "count": 1,
            }
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["document"]["name"] == "From DB"
    assert out[0].json["mockSource"] == "db_response"
    assert out[0].json["source"] == "mongoDb"


# ── 4. http_response fallback ─────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "find",
            "collection": "users",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "documents": [{"_id": "h7", "name": "From HTTP"}],
                    "count": 1,
                },
            }
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["document"]["name"] == "From HTTP"
    assert out[0].json["mockSource"] == "http_response"
    assert out[0].json["source"] == "mongoDb"


# ── 5. Offline find: returns up to 3 documents ────────────────────


@pytest.mark.asyncio
async def test_offline_find_returns_up_to_three_documents() -> None:
    node = _node(
        {
            "operation": "find",
            "collection": "users",
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3
    assert out[0].json["document"]["_id"] == "obj_1"
    assert out[0].json["document"]["name"] == "Mock Doc 1"
    assert out[0].json["document"]["value"] == 10
    assert out[0].json["count"] == 3
    assert out[0].json["source"] == "mongoDb"
    assert out[0].json["operation"] == "find"
    assert out[0].json["mockSource"] == "offline"
    assert out[1].json["document"]["_id"] == "obj_2"
    assert out[1].json["document"]["name"] == "Mock Doc 2"
    assert out[1].json["document"]["value"] == 20
    assert out[2].json["document"]["_id"] == "obj_3"
    assert out[2].json["document"]["name"] == "Mock Doc 3"
    assert out[2].json["document"]["value"] == 30


# ── 6. Offline insert: insertedCount present ──────────────────────


@pytest.mark.asyncio
async def test_offline_insert_inserted_count_present() -> None:
    node = _node(
        {
            "operation": "insert",
            "collection": "users",
            "documents": [{"name": "A"}, {"name": "B"}],
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["insertedCount"] == 2
    assert isinstance(p["insertedIds"], list)
    assert p["acknowledged"] is True
    assert p["source"] == "mongoDb"
    assert p["operation"] == "insert"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_insert_no_documents_inserted_one() -> None:
    node = _node(
        {
            "operation": "insert",
            "collection": "users",
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    assert out[0].json["insertedCount"] == 1


# ── 7. Offline update: matchedCount=1, modifiedCount=1 ────────────


@pytest.mark.asyncio
async def test_offline_update_matched_and_modified_one() -> None:
    node = _node(
        {
            "operation": "update",
            "collection": "users",
            "query": {"status": "old"},
            "update": {"$set": {"status": "new"}},
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["matchedCount"] == 1
    assert p["modifiedCount"] == 1
    assert p["upsertedId"] is None
    assert p["acknowledged"] is True
    assert p["source"] == "mongoDb"
    assert p["operation"] == "update"
    assert p["mockSource"] == "offline"


# ── 8. Offline delete: deletedCount=1 ─────────────────────────────


@pytest.mark.asyncio
async def test_offline_delete_deleted_count_one() -> None:
    node = _node(
        {
            "operation": "delete",
            "collection": "users",
            "query": {"status": "archived"},
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["deletedCount"] == 1
    assert p["acknowledged"] is True
    assert p["source"] == "mongoDb"
    assert p["operation"] == "delete"
    assert p["mockSource"] == "offline"


# ── 9. Offline aggregate: result present ──────────────────────────


@pytest.mark.asyncio
async def test_offline_aggregate_result_present() -> None:
    node = _node(
        {
            "operation": "aggregate",
            "collection": "orders",
            "pipeline": [{"$group": {"_id": "$status", "count": {"$sum": 1}}}],
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["result"]["_id"] == "group1"
    assert p["result"]["count"] == 5
    assert p["result"]["total"] == 150
    assert p["source"] == "mongoDb"
    assert p["operation"] == "aggregate"
    assert p["mockSource"] == "offline"


# ── 10. operation='find' reflected ────────────────────────────────


@pytest.mark.asyncio
async def test_operation_find_reflected() -> None:
    node = _node(
        {
            "operation": "find",
            "collection": "users",
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) > 0
    assert out[0].json["operation"] == "find"
    assert out[0].json["source"] == "mongoDb"


# ── 11. collection default from $json ─────────────────────────────


@pytest.mark.asyncio
async def test_collection_default_from_json() -> None:
    node = _node({"operation": "find"})
    item = ExecutionItem(json={"collection": "json_collection"})
    out = _out_items(await exec_mongodb(node, [item], ctx=_ctx()))
    assert len(out) == 3
    assert out[0].json["source"] == "mongoDb"


@pytest.mark.asyncio
async def test_collection_name_default_from_json() -> None:
    node = _node({"operation": "find"})
    item = ExecutionItem(json={"collectionName": "json_coll_name"})
    out = _out_items(await exec_mongodb(node, [item], ctx=_ctx()))
    assert len(out) == 3


# ── 12. limit honored ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_limit_honored() -> None:
    node = _node(
        {
            "operation": "find",
            "collection": "users",
            "limit": 2,
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 2
    assert out[0].json["document"]["_id"] == "obj_1"
    assert out[1].json["document"]["_id"] == "obj_2"
    assert out[0].json["count"] == 2


@pytest.mark.asyncio
async def test_limit_one_returns_single_document() -> None:
    node = _node(
        {
            "operation": "find",
            "collection": "users",
            "limit": 1,
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    assert out[0].json["count"] == 1


# ── 13. Empty collection → no item ────────────────────────────────


@pytest.mark.asyncio
async def test_empty_collection_skips_find() -> None:
    node = _node({"operation": "find", "collection": ""})
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_collection_skips_insert() -> None:
    node = _node({"operation": "insert", "collection": ""})
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_collection_skips_update() -> None:
    node = _node({"operation": "update", "collection": ""})
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_collection_skips_delete() -> None:
    node = _node({"operation": "delete", "collection": ""})
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_collection_skips_aggregate() -> None:
    node = _node({"operation": "aggregate", "collection": ""})
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


# ── 14. Unsupported operation raises ──────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "distinct", "collection": "t"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 15. dataMode honored ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_mode_object_find_is_accepted() -> None:
    node = _node(
        {
            "operation": "find",
            "collection": "users",
            "dataMode": "object",
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["documents"], list)
    assert len(p["documents"]) == 3
    assert p["count"] == 3
    assert p["source"] == "mongoDb"


@pytest.mark.asyncio
async def test_data_mode_object_aggregate_is_accepted() -> None:
    node = _node(
        {
            "operation": "aggregate",
            "collection": "orders",
            "dataMode": "object",
        }
    )
    out = _out_items(
        await exec_mongodb(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["results"], list)
    assert len(p["results"]) == 1
    assert p["ok"] == 1
    assert p["source"] == "mongoDb"


# ── 16. Default operation is 'find' ───────────────────────────────


def test_default_operation_is_find() -> None:
    assert MONGODB_DEFAULT_OPERATION == "find"
    assert set(MONGODB_OPERATIONS) == {
        "find",
        "insert",
        "update",
        "delete",
        "aggregate",
    }


# ── 17. Multiple input items ──────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input_for_insert() -> None:
    node = _node({"operation": "insert", "collection": "t"})
    items = [
        ExecutionItem(json={"name": "a"}),
        ExecutionItem(json={"name": "b"}),
        ExecutionItem(json={"name": "c"}),
    ]
    out = _out_items(await exec_mongodb(node, items, ctx=_ctx()))
    assert len(out) == 3
    for o in out:
        assert o.json["source"] == "mongoDb"
        assert o.json["operation"] == "insert"


# ── 18. Descriptor registration ───────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.mongoDb" in REGISTRY
    assert "n8n-nodes-base.mongoDb" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.mongoDb"] == "output"
    desc = REGISTRY["n8n-nodes-base.mongoDb"]
    assert desc.executor.endswith(":exec_mongodb")
    assert desc.category == "output"


# ── 19. End-to-end: Manual Trigger → mongoDb (find mock) → Set ────


def _doc(nodes, connections):
    return {"name": "mongodb-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_mongodb_find_set_sees_documents() -> None:
    """Manual Trigger → mongoDb (find, mongodb_response mock) → Set pulls document fields."""
    mocks = {
        "mongodb_response": {
            "documents": [
                {"_id": "101", "name": "First", "value": 10},
                {"_id": "102", "name": "Second", "value": 20},
            ],
            "count": 2,
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "m1",
                "MongoDb",
                "n8n-nodes-base.mongoDb",
                {
                    "operation": "find",
                    "collection": "users",
                    "query": {"status": "active"},
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "result_name",
                                "value": "={{ $json.document.name }}",
                                "type": "string",
                            },
                            {
                                "name": "result_value",
                                "value": "={{ $json.document.value }}",
                                "type": "number",
                            },
                            {
                                "name": "result_source",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "MongoDb", "type": "main", "index": 0}]]
            },
            "MongoDb": {
                "main": [[{"node": "Downstream", "type": "main", "index": 0}]]
            },
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    md_step = next(s for s in result.steps if s.node_name == "MongoDb")
    assert md_step.status == "success", md_step.error
    assert md_step.output_count == 2

    final = result.final_items
    assert final, "expected at least one final item"
    names = [f.get("json", {}).get("result_name") for f in final]
    values = [f.get("json", {}).get("result_value") for f in final]
    sources = [f.get("json", {}).get("result_source") for f in final]
    assert names == ["First", "Second"]
    assert values == [10, 20]
    assert sources == ["mongoDb", "mongoDb"]