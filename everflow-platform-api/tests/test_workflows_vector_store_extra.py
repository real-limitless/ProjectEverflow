"""Tests for the extra Vector Store executors (Milvus, Weaviate, Redis, MongoDB).

Covers for EACH store:

- Mock dict used verbatim
- Offline insert produces output with ``source``
- Offline load returns documents
- Offline retrieve returns top-K results
- Mode defaults to ``"insert"``
- Descriptor registration (all four in REGISTRY)
- End-to-end: Manual → vectorStoreMilvus (insert) → Set extracts ``source``
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes import vector_store_extra as vse_mod
from app.services.workflows.nodes.vector_store_extra import (
    exec_vector_store_milvus,
    exec_vector_store_mongodb,
    exec_vector_store_redis,
    exec_vector_store_weaviate,
)


def _node(
    params: dict[str, Any] | None,
    *,
    type_: str = "@n8n/n8n-nodes-langchain.vectorStoreMilvus",
    id_: str = "n1",
    name: str = "Milvus",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params or {},
        credentials=None,
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


def _items(rows: list[dict[str, Any]] | None = None):
    return items_from_json_list(rows or [])


def _out_items(result):
    out = []
    for _idx, items in result:
        out.extend(items)
    return out


@pytest.fixture(autouse=True)
def _reset_stores() -> None:
    vse_mod._MILVUS_COLLECTIONS.clear()
    vse_mod._WEAVIATE_COLLECTIONS.clear()
    vse_mod._REDIS_INDEXES.clear()
    vse_mod._MONGODB_COLLECTIONS.clear()


MILVUS = "@n8n/n8n-nodes-langchain.vectorStoreMilvus"
WEAVIATE = "@n8n/n8n-nodes-langchain.vectorStoreWeaviate"
REDIS = "@n8n/n8n-nodes-langchain.vectorStoreRedis"
MONGODB = "@n8n/n8n-nodes-langchain.vectorStoreMongoDb"


# ── Milvus ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_milvus_mock_dict_used_verbatim() -> None:
    node = _node({"mode": "insert"}, type_=MILVUS)
    ctx = _ctx(
        mocks={
            "vector_store_output": [
                {"pageContent": "alpha", "metadata": {"src": "mock"}},
                {"pageContent": "beta", "metadata": {"src": "mock"}},
            ]
        }
    )
    result = await exec_vector_store_milvus(
        node, _items([{"text": "ignored"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 2
    pages = {it.json["document"]["pageContent"] for it in out}
    assert pages == {"alpha", "beta"}
    for it in out:
        assert it.json["source"] == "vectorStoreMilvus"
        assert it.json["stored"] is True


@pytest.mark.asyncio
async def test_milvus_offline_insert_produces_source() -> None:
    node = _node({"mode": "insert"}, type_=MILVUS)
    ctx = _ctx()
    result = await exec_vector_store_milvus(
        node, _items([{"pageContent": "hello"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["source"] == "vectorStoreMilvus"
    assert out[0].json["document"]["pageContent"] == "hello"
    assert out[0].json["collectionName"] == "n8n_milvus"
    assert out[0].json["host"] == "localhost"
    assert out[0].json["port"] == 19530


@pytest.mark.asyncio
async def test_milvus_offline_load_returns_documents() -> None:
    insert = _node({"mode": "insert"}, type_=MILVUS, id_="n1", name="Milvus")
    load = _node({"mode": "load"}, type_=MILVUS, id_="n1", name="Milvus")
    ctx = _ctx()
    await exec_vector_store_milvus(
        insert,
        _items([{"pageContent": "doc-a"}, {"pageContent": "doc-b"}]),
        ctx=ctx,
    )
    result = await exec_vector_store_milvus(load, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 2
    pages = {it.json["document"]["pageContent"] for it in out}
    assert pages == {"doc-a", "doc-b"}
    for it in out:
        assert it.json["mode"] == "load"
        assert it.json["source"] == "vectorStoreMilvus"


@pytest.mark.asyncio
async def test_milvus_offline_retrieve_returns_top_k() -> None:
    insert = _node({"mode": "insert"}, type_=MILVUS, id_="n1", name="Milvus")
    retrieve = _node(
        {"mode": "retrieve", "topK": 2}, type_=MILVUS, id_="n1", name="Milvus"
    )
    ctx = _ctx()
    await exec_vector_store_milvus(
        insert,
        _items(
            [
                {"pageContent": "the quick brown fox"},
                {"pageContent": "completely unrelated"},
                {"pageContent": "quick silver coins"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_milvus(
        retrieve, _items([{"query": "quick fox"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 2
    for it in out:
        assert "score" in it.json
        assert it.json["source"] == "vectorStoreMilvus"


@pytest.mark.asyncio
async def test_milvus_mode_defaults_to_insert() -> None:
    node = _node({}, type_=MILVUS)
    ctx = _ctx()
    result = await exec_vector_store_milvus(
        node, _items([{"pageContent": "inserted"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["mode"] == "insert"


# ── Weaviate ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_weaviate_mock_dict_used_verbatim() -> None:
    node = _node({"mode": "insert"}, type_=WEAVIATE, name="Weaviate")
    ctx = _ctx(
        mocks={
            "vector_store_output": [
                {"pageContent": "alpha", "metadata": {"src": "mock"}},
                {"pageContent": "beta", "metadata": {"src": "mock"}},
            ]
        }
    )
    result = await exec_vector_store_weaviate(
        node, _items([{"text": "ignored"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 2
    pages = {it.json["document"]["pageContent"] for it in out}
    assert pages == {"alpha", "beta"}
    for it in out:
        assert it.json["source"] == "vectorStoreWeaviate"


@pytest.mark.asyncio
async def test_weaviate_offline_insert_produces_source() -> None:
    node = _node({"mode": "insert"}, type_=WEAVIATE, name="Weaviate")
    ctx = _ctx()
    result = await exec_vector_store_weaviate(
        node, _items([{"pageContent": "hello"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["source"] == "vectorStoreWeaviate"
    assert out[0].json["document"]["pageContent"] == "hello"
    assert out[0].json["className"] == "Document"
    assert out[0].json["url"] == "http://localhost:8080"


@pytest.mark.asyncio
async def test_weaviate_offline_load_returns_documents() -> None:
    insert = _node({"mode": "insert"}, type_=WEAVIATE, id_="n1", name="Weaviate")
    load = _node({"mode": "load"}, type_=WEAVIATE, id_="n1", name="Weaviate")
    ctx = _ctx()
    await exec_vector_store_weaviate(
        insert,
        _items([{"pageContent": "doc-a"}, {"pageContent": "doc-b"}]),
        ctx=ctx,
    )
    result = await exec_vector_store_weaviate(load, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 2
    pages = {it.json["document"]["pageContent"] for it in out}
    assert pages == {"doc-a", "doc-b"}
    for it in out:
        assert it.json["mode"] == "load"
        assert it.json["source"] == "vectorStoreWeaviate"


@pytest.mark.asyncio
async def test_weaviate_offline_retrieve_returns_top_k() -> None:
    insert = _node({"mode": "insert"}, type_=WEAVIATE, id_="n1", name="Weaviate")
    retrieve = _node(
        {"mode": "retrieve", "topK": 2}, type_=WEAVIATE, id_="n1", name="Weaviate"
    )
    ctx = _ctx()
    await exec_vector_store_weaviate(
        insert,
        _items(
            [
                {"pageContent": "the quick brown fox"},
                {"pageContent": "completely unrelated"},
                {"pageContent": "quick silver coins"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_weaviate(
        retrieve, _items([{"query": "quick fox"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 2
    for it in out:
        assert "score" in it.json
        assert it.json["source"] == "vectorStoreWeaviate"


@pytest.mark.asyncio
async def test_weaviate_mode_defaults_to_insert() -> None:
    node = _node({}, type_=WEAVIATE, name="Weaviate")
    ctx = _ctx()
    result = await exec_vector_store_weaviate(
        node, _items([{"pageContent": "inserted"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["mode"] == "insert"


# ── Redis ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redis_mock_dict_used_verbatim() -> None:
    node = _node({"mode": "insert"}, type_=REDIS, name="Redis")
    ctx = _ctx(
        mocks={
            "vector_store_output": [
                {"pageContent": "alpha", "metadata": {"src": "mock"}},
                {"pageContent": "beta", "metadata": {"src": "mock"}},
            ]
        }
    )
    result = await exec_vector_store_redis(
        node, _items([{"text": "ignored"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 2
    pages = {it.json["document"]["pageContent"] for it in out}
    assert pages == {"alpha", "beta"}
    for it in out:
        assert it.json["source"] == "vectorStoreRedis"


@pytest.mark.asyncio
async def test_redis_offline_insert_produces_source() -> None:
    node = _node({"mode": "insert"}, type_=REDIS, name="Redis")
    ctx = _ctx()
    result = await exec_vector_store_redis(
        node, _items([{"pageContent": "hello"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["source"] == "vectorStoreRedis"
    assert out[0].json["document"]["pageContent"] == "hello"
    assert out[0].json["indexName"] == "n8n_redis_index"
    assert out[0].json["redisUrl"] == "redis://localhost:6379"


@pytest.mark.asyncio
async def test_redis_offline_load_returns_documents() -> None:
    insert = _node({"mode": "insert"}, type_=REDIS, id_="n1", name="Redis")
    load = _node({"mode": "load"}, type_=REDIS, id_="n1", name="Redis")
    ctx = _ctx()
    await exec_vector_store_redis(
        insert,
        _items([{"pageContent": "doc-a"}, {"pageContent": "doc-b"}]),
        ctx=ctx,
    )
    result = await exec_vector_store_redis(load, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 2
    pages = {it.json["document"]["pageContent"] for it in out}
    assert pages == {"doc-a", "doc-b"}
    for it in out:
        assert it.json["mode"] == "load"
        assert it.json["source"] == "vectorStoreRedis"


@pytest.mark.asyncio
async def test_redis_offline_retrieve_returns_top_k() -> None:
    insert = _node({"mode": "insert"}, type_=REDIS, id_="n1", name="Redis")
    retrieve = _node(
        {"mode": "retrieve", "topK": 2}, type_=REDIS, id_="n1", name="Redis"
    )
    ctx = _ctx()
    await exec_vector_store_redis(
        insert,
        _items(
            [
                {"pageContent": "the quick brown fox"},
                {"pageContent": "completely unrelated"},
                {"pageContent": "quick silver coins"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_redis(
        retrieve, _items([{"query": "quick fox"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 2
    for it in out:
        assert "score" in it.json
        assert it.json["source"] == "vectorStoreRedis"


@pytest.mark.asyncio
async def test_redis_mode_defaults_to_insert() -> None:
    node = _node({}, type_=REDIS, name="Redis")
    ctx = _ctx()
    result = await exec_vector_store_redis(
        node, _items([{"pageContent": "inserted"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["mode"] == "insert"


# ── MongoDB ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mongodb_mock_dict_used_verbatim() -> None:
    node = _node({"mode": "insert"}, type_=MONGODB, name="MongoDB")
    ctx = _ctx(
        mocks={
            "vector_store_output": [
                {"pageContent": "alpha", "metadata": {"src": "mock"}},
                {"pageContent": "beta", "metadata": {"src": "mock"}},
            ]
        }
    )
    result = await exec_vector_store_mongodb(
        node, _items([{"text": "ignored"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 2
    pages = {it.json["document"]["pageContent"] for it in out}
    assert pages == {"alpha", "beta"}
    for it in out:
        assert it.json["source"] == "vectorStoreMongoDb"


@pytest.mark.asyncio
async def test_mongodb_offline_insert_produces_source() -> None:
    node = _node({"mode": "insert"}, type_=MONGODB, name="MongoDB")
    ctx = _ctx()
    result = await exec_vector_store_mongodb(
        node, _items([{"pageContent": "hello"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["source"] == "vectorStoreMongoDb"
    assert out[0].json["document"]["pageContent"] == "hello"
    assert out[0].json["collectionName"] == "documents"
    assert out[0].json["indexName"] == "vector_index"
    assert out[0].json["databaseName"] == "default"


@pytest.mark.asyncio
async def test_mongodb_offline_load_returns_documents() -> None:
    insert = _node({"mode": "insert"}, type_=MONGODB, id_="n1", name="MongoDB")
    load = _node({"mode": "load"}, type_=MONGODB, id_="n1", name="MongoDB")
    ctx = _ctx()
    await exec_vector_store_mongodb(
        insert,
        _items([{"pageContent": "doc-a"}, {"pageContent": "doc-b"}]),
        ctx=ctx,
    )
    result = await exec_vector_store_mongodb(load, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 2
    pages = {it.json["document"]["pageContent"] for it in out}
    assert pages == {"doc-a", "doc-b"}
    for it in out:
        assert it.json["mode"] == "load"
        assert it.json["source"] == "vectorStoreMongoDb"


@pytest.mark.asyncio
async def test_mongodb_offline_retrieve_returns_top_k() -> None:
    insert = _node({"mode": "insert"}, type_=MONGODB, id_="n1", name="MongoDB")
    retrieve = _node(
        {"mode": "retrieve", "topK": 2}, type_=MONGODB, id_="n1", name="MongoDB"
    )
    ctx = _ctx()
    await exec_vector_store_mongodb(
        insert,
        _items(
            [
                {"pageContent": "the quick brown fox"},
                {"pageContent": "completely unrelated"},
                {"pageContent": "quick silver coins"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_mongodb(
        retrieve, _items([{"query": "quick fox"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 2
    for it in out:
        assert "score" in it.json
        assert it.json["source"] == "vectorStoreMongoDb"


@pytest.mark.asyncio
async def test_mongodb_mode_defaults_to_insert() -> None:
    node = _node({}, type_=MONGODB, name="MongoDB")
    ctx = _ctx()
    result = await exec_vector_store_mongodb(
        node, _items([{"pageContent": "inserted"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["mode"] == "insert"


# ── Descriptor registration ──────────────────────────────────────────


def test_all_descriptors_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    for ntype, source in [
        (MILVUS, "vectorStoreMilvus"),
        (WEAVIATE, "vectorStoreWeaviate"),
        (REDIS, "vectorStoreRedis"),
        (MONGODB, "vectorStoreMongoDb"),
    ]:
        assert ntype in REGISTRY, f"{ntype} missing from REGISTRY"
        assert ntype in SUPPORTED_NODE_TYPES, f"{ntype} missing from SUPPORTED_NODE_TYPES"
        assert SUPPORTED_NODE_TYPES[ntype] == "ai"
        desc = REGISTRY[ntype]
        assert desc.category == "ai"


def test_descriptor_executors_resolve() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY

    expected = {
        MILVUS: "exec_vector_store_milvus",
        WEAVIATE: "exec_vector_store_weaviate",
        REDIS: "exec_vector_store_redis",
        MONGODB: "exec_vector_store_mongodb",
    }
    for ntype, fn_name in expected.items():
        desc = REGISTRY[ntype]
        assert desc.executor.endswith(f":{fn_name}"), (
            f"{ntype} executor {desc.executor!r} does not end with :{fn_name}"
        )


# ── End-to-end: Manual → vectorStoreMilvus (insert) → Set ────────────


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
async def test_e2e_milvus_insert_then_set_extracts_source() -> None:
    doc = {
        "name": "milvus-e2e",
        "nodes": [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "v1",
                "MilvusInsert",
                MILVUS,
                {"mode": "insert"},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "result",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        "connections": {
            "Start": {
                "main": [[{"node": "MilvusInsert", "type": "main", "index": 0}]]
            },
            "MilvusInsert": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    }
    engine = WorkflowEngine(
        doc,
        mocks={
            "vector_store_output": [
                {"pageContent": "hello world", "metadata": {}}
            ],
        },
    )
    result = await engine.run(trigger="manual", pin_data={"Start": [{"text": "hi"}]})
    assert result.status == "success", result.error_message

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["result"] == "vectorStoreMilvus"


@pytest.mark.asyncio
async def test_e2e_weaviate_insert_then_set_extracts_source() -> None:
    doc = {
        "name": "weaviate-e2e",
        "nodes": [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "v1",
                "WeaviateInsert",
                WEAVIATE,
                {"mode": "insert"},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "result",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        "connections": {
            "Start": {
                "main": [[{"node": "WeaviateInsert", "type": "main", "index": 0}]]
            },
            "WeaviateInsert": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    }
    engine = WorkflowEngine(
        doc,
        mocks={
            "vector_store_output": [
                {"pageContent": "hello world", "metadata": {}}
            ],
        },
    )
    result = await engine.run(trigger="manual", pin_data={"Start": [{"text": "hi"}]})
    assert result.status == "success", result.error_message

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["result"] == "vectorStoreWeaviate"


# ── Extra: topK default and load on empty store ──────────────────────


@pytest.mark.asyncio
async def test_milvus_topk_default_is_4() -> None:
    insert = _node({"mode": "insert"}, type_=MILVUS, id_="n1", name="Milvus")
    retrieve = _node({"mode": "retrieve"}, type_=MILVUS, id_="n1", name="Milvus")
    ctx = _ctx()
    await exec_vector_store_milvus(
        insert,
        _items([{"pageContent": f"doc {i}"} for i in range(6)]),
        ctx=ctx,
    )
    result = await exec_vector_store_milvus(
        retrieve, _items([{"query": "doc"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 4


@pytest.mark.asyncio
async def test_milvus_load_on_empty_store_returns_empty() -> None:
    node = _node({"mode": "load"}, type_=MILVUS)
    ctx = _ctx()
    result = await exec_vector_store_milvus(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out == []


@pytest.mark.asyncio
async def test_mongodb_retrieve_with_mock_prescores() -> None:
    node = _node({"mode": "retrieve", "topK": 1}, type_=MONGODB, name="MongoDB")
    ctx = _ctx(
        mocks={
            "vector_store_output": [
                {"pageContent": "alpha", "score": 0.95},
                {"pageContent": "beta", "score": 0.10},
            ]
        }
    )
    result = await exec_vector_store_mongodb(
        node, _items([{"query": "anything"}]), ctx=ctx
    )
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["document"]["pageContent"] == "alpha"
    assert out[0].json["score"] == 0.95
    assert out[0].json["source"] == "vectorStoreMongoDb"