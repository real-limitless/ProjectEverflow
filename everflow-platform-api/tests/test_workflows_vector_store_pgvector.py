"""Tests for the Postgres+pgvector Vector Store executor (vectorStorePGVector).

Covers:

- ``ctx.mocks['vector_store_output']`` returning a list of documents
- ``ctx.mocks['vector_store_output']`` as a callable receiving
  ``(mode, items, params, ctx)``
- ``ctx.mocks['embeddings_output']`` mock provides embeddings for insert
- Insert mode: stores documents in the mocked table and emits stored items
- Retrieve mode: top-k similarity returns best matches
- Retrieve with no query -> empty results
- ``topK`` is respected
- ``tableName`` and ``distanceStrategy`` echoed in output
- Same-run store isolation across ``tableName`` keys
- Metadata preserved through insert / retrieve
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger -> vectorStorePGVector (insert mock) ->
  vectorStorePGVector (retrieve mock) -> Set sees documents
- End-to-end: Manual Trigger -> embeddingsOpenAi -> vectorStorePGVector
  (insert) -> vectorStorePGVector (retrieve)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes import vector_store_pgvector as vsp_mod
from app.services.workflows.nodes.vector_store_pgvector import (
    exec_vector_store_pgvector,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "v1",
    name: str = "PGVector",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.vectorStorePGVector",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    mocks: dict[str, Any] | None = None,
    ai_inputs: list[ExecNode] | None = None,
    lm_configs: dict[str, Any] | None = None,
    run_id: str | None = "test-run",
) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: list(ai_inputs or [])
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    ctx = EngineContext(  # type: ignore[arg-type]
        graph=g,
        mocks=mocks or {},
        run_id=run_id,
    )
    if lm_configs:
        ctx.lm_configs.update(lm_configs)
    return ctx


def _items(rows: list[dict[str, Any]] | None = None):
    return items_from_json_list(rows or [])


@pytest.fixture(autouse=True)
def _reset_tables() -> None:
    """Make the mocked pgvector table map pristine before each test."""
    vsp_mod._PGVECTOR_TABLES.clear()


# ── 1. vector_store_output mock returns a list of documents ────────────


@pytest.mark.asyncio
async def test_vector_store_output_mock_list_of_docs_insert() -> None:
    node = _node({"mode": "insert"})
    ctx = _ctx(
        mocks={
            "vector_store_output": [
                {"pageContent": "alpha", "metadata": {"src": "mock"}},
                {"pageContent": "beta", "metadata": {"src": "mock"}},
            ]
        }
    )
    items = _items([{"text": "ignored"}])

    result = await exec_vector_store_pgvector(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert len(out_items) == 2
    pages = {it.json["document"]["pageContent"] for it in out_items}
    assert pages == {"alpha", "beta"}
    for it in out_items:
        assert it.json["stored"] is True
        assert it.json["mode"] == "insert"
        assert it.json["source"] == "vectorStorePGVector"
        assert it.json["tableName"] == "n8n_pgvector_embeddings"
        assert it.json["distanceStrategy"] == "cosine"

    # Stored in the mocked table under (run_id, node.id, tableName)
    key = f"{ctx.run_id}:{node.id}:n8n_pgvector_embeddings"
    bucket = vsp_mod._PGVECTOR_TABLES[key]
    assert len(bucket) == 2
    assert {d["content"] for d in bucket} == {"alpha", "beta"}
    # Auto ids (1-based, integer)
    assert [d["id"] for d in bucket] == [1, 2]


# ── 2. vector_store_output callable mock receives (mode, items, params, ctx) ─


@pytest.mark.asyncio
async def test_vector_store_output_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def fake(mode, items, params, ctx):
        captured["mode"] = mode
        captured["items"] = items
        captured["params"] = params
        captured["ctx"] = ctx
        return [
            {"pageContent": "from-callable", "metadata": {"tag": "x"}},
        ]

    node = _node(
        {
            "mode": "insert",
            "topK": 2,
            "tableName": "demo",
            "distanceStrategy": "euclidean",
        }
    )
    ctx = _ctx(mocks={"vector_store_output": fake})
    items = _items([{"text": "alpha"}])

    result = await exec_vector_store_pgvector(node, items, ctx=ctx)
    assert captured["mode"] == "insert"
    assert captured["params"] == {
        "mode": "insert",
        "topK": 2,
        "tableName": "demo",
        "distanceStrategy": "euclidean",
    }
    assert captured["items"] is items
    assert captured["ctx"] is ctx
    assert result[0][1][0].json["document"]["pageContent"] == "from-callable"
    assert result[0][1][0].json["tableName"] == "demo"
    assert result[0][1][0].json["distanceStrategy"] == "euclidean"


# ── 3. embeddings_output mock provides embeddings for insert ─────────


@pytest.mark.asyncio
async def test_embeddings_output_mock_provides_embeddings_for_insert() -> None:
    emb_node = ExecNode(
        id="e1",
        name="Embeddings",
        type="@n8n/n8n-nodes-langchain.embeddingsOpenAi",
        type_version=1,
        parameters={"model": "text-embedding-3-small"},
        credentials=None,
        position={"x": 0, "y": 0},
    )

    seen: list[tuple[str, Any, str]] = []

    def fake_embed(text, item, model):
        seen.append((text, item, model))
        return [float(len(text)), 0.0, 0.0]

    node = _node({"mode": "insert"})
    ctx = _ctx(
        mocks={"embeddings_output": fake_embed},
        ai_inputs=[emb_node],
        lm_configs={
            emb_node.id: {
                "name": emb_node.name,
                "parameters": {"model": "text-embedding-3-small"},
            }
        },
    )
    items = _items(
        [
            {"pageContent": "hi"},
            {"pageContent": "longer text"},
        ]
    )

    await exec_vector_store_pgvector(node, items, ctx=ctx)

    assert [t for t, _, _ in seen] == ["hi", "longer text"]
    key = f"{ctx.run_id}:{node.id}:n8n_pgvector_embeddings"
    bucket = vsp_mod._PGVECTOR_TABLES[key]
    assert bucket[0]["embedding"] == [2.0, 0.0, 0.0]
    assert bucket[1]["embedding"] == [11.0, 0.0, 0.0]


# ── 4. Insert mode: stores documents in mocked table ─────────────────


@pytest.mark.asyncio
async def test_insert_mode_offline_stores_documents_from_items() -> None:
    node = _node({"mode": "insert"})
    ctx = _ctx()
    items = _items(
        [
            {"pageContent": "doc-1", "metadata": {"tag": "a"}},
            {"pageContent": "doc-2", "metadata": {"tag": "b"}},
        ]
    )

    result = await exec_vector_store_pgvector(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 2
    key = f"{ctx.run_id}:{node.id}:n8n_pgvector_embeddings"
    bucket = vsp_mod._PGVECTOR_TABLES[key]
    assert len(bucket) == 2
    assert bucket[0]["content"] == "doc-1"
    assert bucket[0]["metadata"] == {"tag": "a"}
    assert bucket[1]["content"] == "doc-2"
    assert bucket[1]["metadata"] == {"tag": "b"}
    # No embedding mock, no model connected -> embedding is an empty list
    assert bucket[0]["embedding"] == []
    assert bucket[1]["embedding"] == []


# ── 5. Retrieve mode: top-k similarity returns best matches ───────────


@pytest.mark.asyncio
async def test_retrieve_keyword_match_returns_best_first() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node({"mode": "retrieve", "topK": 2}, id_="v1", name="V1")
    ctx = _ctx()

    await exec_vector_store_pgvector(
        insert,
        _items(
            [
                {"pageContent": "the quick brown fox"},
                {"pageContent": "completely unrelated text"},
                {"pageContent": "quick silver coins"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_pgvector(
        retrieve, _items([{"query": "quick fox"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 2
    assert out[0].json["document"]["pageContent"] == "the quick brown fox"
    assert out[0].json["score"] > out[1].json["score"]


@pytest.mark.asyncio
async def test_retrieve_cosine_similarity_with_embeddings() -> None:
    emb_node = ExecNode(
        id="e1",
        name="Embeddings",
        type="@n8n/n8n-nodes-langchain.embeddingsOpenAi",
        type_version=1,
        parameters={"model": "text-embedding-3-small"},
        credentials=None,
        position={"x": 0, "y": 0},
    )

    def embed_factory():
        counter = {"n": 0}

        def fake(text, item, model):
            counter["n"] += 1
            n = counter["n"]
            if n == 1:
                return [1.0, 0.0]
            if n == 2:
                return [0.0, 1.0]
            if n == 3:
                return [0.7, 0.7]
            return [1.0, 0.0]

        return fake

    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node({"mode": "retrieve", "topK": 3}, id_="v1", name="V1")
    ctx = _ctx(
        mocks={"embeddings_output": embed_factory()},
        ai_inputs=[emb_node],
        lm_configs={
            emb_node.id: {
                "name": emb_node.name,
                "parameters": {"model": "text-embedding-3-small"},
            }
        },
    )

    await exec_vector_store_pgvector(
        insert,
        _items(
            [
                {"pageContent": "doc-A"},
                {"pageContent": "doc-B"},
                {"pageContent": "doc-C"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_pgvector(
        retrieve, _items([{"query": "anything"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 3
    assert out[0].json["document"]["pageContent"] == "doc-A"
    assert out[0].json["score"] == pytest.approx(1.0, abs=1e-6)
    assert out[1].json["document"]["pageContent"] == "doc-C"
    assert out[1].json["score"] == pytest.approx(0.70710678, abs=1e-5)
    assert out[2].json["document"]["pageContent"] == "doc-B"
    assert out[2].json["score"] == 0.0


# ── 6. Retrieve with no query -> empty results ─────────────────────────


@pytest.mark.asyncio
async def test_retrieve_with_no_query_returns_empty() -> None:
    node = _node({"mode": "retrieve"})
    ctx = _ctx()
    vsp_mod._PGVECTOR_TABLES[
        f"{ctx.run_id}:{node.id}:n8n_pgvector_embeddings"
    ] = [
        {"id": 1, "content": "anything", "metadata": {}, "embedding": []},
    ]
    result = await exec_vector_store_pgvector(
        node, _items([{"unrelated": "no query fields here"}]), ctx=ctx
    )
    assert result[0][1] == []


@pytest.mark.asyncio
async def test_retrieve_with_empty_query_string_returns_empty() -> None:
    node = _node({"mode": "retrieve"})
    ctx = _ctx()
    vsp_mod._PGVECTOR_TABLES[
        f"{ctx.run_id}:{node.id}:n8n_pgvector_embeddings"
    ] = [{"id": 1, "content": "x", "metadata": {}, "embedding": []}]
    result = await exec_vector_store_pgvector(
        node, _items([{"query": ""}]), ctx=ctx
    )
    assert result[0][1] == []


# ── 7. topK respected ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_topk_respected() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node({"mode": "retrieve", "topK": 2}, id_="v1", name="V1")
    ctx = _ctx()

    await exec_vector_store_pgvector(
        insert,
        _items(
            [
                {"pageContent": "alpha alpha"},
                {"pageContent": "alpha beta"},
                {"pageContent": "alpha gamma"},
                {"pageContent": "alpha delta"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_pgvector(
        retrieve, _items([{"query": "alpha"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 2
    for it in out:
        assert "alpha" in it.json["document"]["pageContent"]


@pytest.mark.asyncio
async def test_topk_default_is_4() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node({"mode": "retrieve"}, id_="v1", name="V1")
    ctx = _ctx()

    await exec_vector_store_pgvector(
        insert,
        _items([{"pageContent": f"alpha doc {i}"} for i in range(6)]),
        ctx=ctx,
    )
    result = await exec_vector_store_pgvector(
        retrieve, _items([{"query": "alpha"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 4


# ── 8. tableName and distanceStrategy echoed in output ────────────────


@pytest.mark.asyncio
async def test_tablename_and_distance_strategy_echoed() -> None:
    node = _node(
        {
            "mode": "insert",
            "tableName": "my_pg_table",
            "distanceStrategy": "euclidean",
        }
    )
    ctx = _ctx()
    items = _items([{"pageContent": "hello"}])

    result = await exec_vector_store_pgvector(node, items, ctx=ctx)
    out = result[0][1]
    assert out[0].json["tableName"] == "my_pg_table"
    assert out[0].json["distanceStrategy"] == "euclidean"

    retrieve = _node(
        {
            "mode": "retrieve",
            "tableName": "my_pg_table",
            "distanceStrategy": "euclidean",
            "query": "hello",
        }
    )
    result2 = await exec_vector_store_pgvector(
        retrieve, _items([{"query": "hello"}]), ctx=ctx
    )
    out2 = result2[0][1]
    assert len(out2) >= 1
    assert out2[0].json["tableName"] == "my_pg_table"
    assert out2[0].json["distanceStrategy"] == "euclidean"


@pytest.mark.asyncio
async def test_tablename_default_and_distance_strategy_default() -> None:
    node = _node({"mode": "insert"})
    ctx = _ctx()
    items = _items([{"pageContent": "x"}])
    result = await exec_vector_store_pgvector(node, items, ctx=ctx)
    assert result[0][1][0].json["tableName"] == "n8n_pgvector_embeddings"
    assert result[0][1][0].json["distanceStrategy"] == "cosine"


# ── 9. Same-run store isolation across tableName keys ──────────────


@pytest.mark.asyncio
async def test_tablename_isolation_within_run() -> None:
    ctx = _ctx(run_id="run-1")
    n_a = _node(
        {"mode": "insert", "tableName": "tblA"},
        id_="shared",
        name="Shared",
    )
    n_b = _node(
        {"mode": "insert", "tableName": "tblB"},
        id_="shared",
        name="Shared",
    )
    await exec_vector_store_pgvector(
        n_a, _items([{"pageContent": "in-A"}]), ctx=ctx
    )
    await exec_vector_store_pgvector(
        n_b, _items([{"pageContent": "in-B"}]), ctx=ctx
    )

    assert (
        vsp_mod._PGVECTOR_TABLES["run-1:shared:tblA"][0]["content"] == "in-A"
    )
    assert (
        vsp_mod._PGVECTOR_TABLES["run-1:shared:tblB"][0]["content"] == "in-B"
    )


@pytest.mark.asyncio
async def test_two_different_runs_do_not_share_table() -> None:
    node = _node({"mode": "insert"}, id_="v1", name="V1")
    ctx1 = _ctx(run_id="run-A")
    ctx2 = _ctx(run_id="run-B")
    await exec_vector_store_pgvector(
        node, _items([{"pageContent": "only in A"}]), ctx=ctx1
    )
    retrieve = _node(
        {"mode": "retrieve", "query": "only"}, id_="v1", name="V1"
    )
    result = await exec_vector_store_pgvector(
        retrieve, _items([{"query": "only"}]), ctx=ctx2
    )
    assert result[0][1] == []


# ── 10. Metadata preserved through insert / retrieve ─────────────────


@pytest.mark.asyncio
async def test_metadata_preserved_through_insert_and_retrieve() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node(
        {"mode": "retrieve", "topK": 1}, id_="v1", name="V1"
    )
    ctx = _ctx(
        mocks={
            "vector_store_output": [
                {
                    "pageContent": "alpha",
                    "metadata": {"source": "wiki", "version": 3},
                }
            ]
        }
    )
    await exec_vector_store_pgvector(insert, _items([{}]), ctx=ctx)
    result = await exec_vector_store_pgvector(
        retrieve, _items([{"query": "alpha"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["document"]["pageContent"] == "alpha"
    assert out[0].json["document"]["metadata"] == {"source": "wiki", "version": 3}


# ── 11. Mode auto-detection: query present -> retrieve, else insert ──


@pytest.mark.asyncio
async def test_auto_mode_with_query_in_parameter_uses_retrieve() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    auto = _node({"query": "anything"}, id_="v1", name="V1")
    ctx = _ctx()
    await exec_vector_store_pgvector(
        insert, _items([{"pageContent": "doc"}]), ctx=ctx
    )
    result = await exec_vector_store_pgvector(
        auto, _items([{"unrelated": "placeholder"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    assert "score" in out[0].json


@pytest.mark.asyncio
async def test_auto_mode_without_query_defaults_to_insert() -> None:
    auto = _node({}, id_="v1", name="V1")
    ctx = _ctx()
    result = await exec_vector_store_pgvector(
        auto, _items([{"pageContent": "inserted"}]), ctx=ctx
    )
    out = result[0][1]
    assert out[0].json["mode"] == "insert"
    key = f"{ctx.run_id}:v1:n8n_pgvector_embeddings"
    assert vsp_mod._PGVECTOR_TABLES[key][0]["content"] == "inserted"


# ── 12. Descriptor registration (CI invariant) ──────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert (
        "@n8n/n8n-nodes-langchain.vectorStorePGVector" in REGISTRY
    )
    assert (
        "@n8n/n8n-nodes-langchain.vectorStorePGVector" in SUPPORTED_NODE_TYPES
    )
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.vectorStorePGVector"]
        == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.vectorStorePGVector"]
    assert desc.executor.endswith(":exec_vector_store_pgvector")
    assert desc.category == "ai"


# ── 13. End-to-end: Manual -> vectorStorePGVector (insert mock) -> vectorStorePGVector (retrieve mock) -> Set ─


def _doc(nodes, connections):
    return {
        "name": "vector-store-pgvector-e2e",
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
async def test_end_to_end_insert_then_retrieve_two_nodes() -> None:
    """Linear chain: Manual Trigger -> PGVector(insert) -> PGVector(retrieve)
    -> Set. The insert uses the static ``vector_store_output`` mock to
    store two docs; the retrieve uses the callable ``vs_mock`` which
    ignores the query and returns pre-scored docs so the Set node sees
    the expected ``alpha`` document, the configured ``tableName`` /
    ``distanceStrategy``, and ``source: 'vectorStorePGVector'``.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "v1",
                "PGInsert",
                "@n8n/n8n-nodes-langchain.vectorStorePGVector",
                {
                    "mode": "insert",
                    "tableName": "demo",
                    "distanceStrategy": "cosine",
                },
            ),
            _n(
                "v2",
                "PGRetrieve",
                "@n8n/n8n-nodes-langchain.vectorStorePGVector",
                {
                    "mode": "retrieve",
                    "topK": 1,
                    "query": "={{ 'anything' }}",
                    "tableName": "demo",
                    "distanceStrategy": "cosine",
                },
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "page",
                                "value": "={{ $json.document.pageContent }}",
                                "type": "string",
                            },
                            {
                                "name": "score",
                                "value": "={{ $json.score }}",
                                "type": "number",
                            },
                            {
                                "name": "src",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            },
                            {
                                "name": "tableName",
                                "value": "={{ $json.tableName }}",
                                "type": "string",
                            },
                            {
                                "name": "distanceStrategy",
                                "value": "={{ $json.distanceStrategy }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "PGInsert", "type": "main", "index": 0}]]
            },
            "PGInsert": {
                "main": [[{"node": "PGRetrieve", "type": "main", "index": 0}]]
            },
            "PGRetrieve": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )

    def vs_mock(mode, items, params, ctx):
        if mode == "retrieve":
            return [
                {"pageContent": "alpha content", "score": 0.9},
                {"pageContent": "beta content", "score": 0.1},
            ]
        return [
            {"pageContent": "alpha content", "metadata": {"tag": "a"}},
            {"pageContent": "beta content", "metadata": {"tag": "b"}},
        ]

    pin_data = {"Start": [{"text": "ignored"}]}
    engine = WorkflowEngine(doc, mocks={"vector_store_output": vs_mock})
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    insert_step = next(s for s in result.steps if s.node_name == "PGInsert")
    assert insert_step.status == "success", insert_step.error
    assert insert_step.output_count == 2

    retrieve_step = next(
        s for s in result.steps if s.node_name == "PGRetrieve"
    )
    assert retrieve_step.status == "success", retrieve_step.error
    assert retrieve_step.output_count == 2
    assert (
        retrieve_step.sample_output[0]["json"]["document"]["pageContent"]
        == "alpha content"
    )
    # Score is a number (executor recomputes via keyword/cosine; pre-supplied
    # mock score is used by the Qdrant sibling, not by this executor)
    assert isinstance(
        retrieve_step.sample_output[0]["json"]["score"], (int, float)
    )

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    sample = set_step.sample_output[0]["json"]
    assert sample["page"] == "alpha content"
    assert isinstance(sample["score"], (int, float))
    # The first retrieved doc is the top match (regardless of score value)
    assert sample["src"] == "vectorStorePGVector"
    assert sample["tableName"] == "demo"
    assert sample["distanceStrategy"] == "cosine"
    assert sample["src"] == "vectorStorePGVector"
    assert sample["tableName"] == "demo"
    assert sample["distanceStrategy"] == "cosine"


# ── 14. End-to-end: Manual -> embeddingsOpenAi -> vectorStorePGVector (insert) -> vectorStorePGVector (retrieve) ─


@pytest.mark.asyncio
async def test_end_to_end_with_connected_embeddings_openai() -> None:
    """Linear chain: Manual Trigger -> embeddingsOpenAi -> vectorStorePGVector
    (insert, id=v1) -> vectorStorePGVector (retrieve, id=v2) -> Set. The
    retrieve is fed by the mock's pre-scored docs (since the insert and
    retrieve have distinct node ids and therefore distinct mocked tables)
    and the embedding sub-node is connected to the insert so its mock is
    invoked per doc.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "e1",
                "Embeddings",
                "@n8n/n8n-nodes-langchain.embeddingsOpenAi",
                {"model": "text-embedding-3-small"},
            ),
            _n(
                "v1",
                "PGInsert",
                "@n8n/n8n-nodes-langchain.vectorStorePGVector",
                {"mode": "insert"},
            ),
            _n(
                "v2",
                "PGRetrieve",
                "@n8n/n8n-nodes-langchain.vectorStorePGVector",
                {"mode": "retrieve", "topK": 1, "query": "match"},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "page",
                                "value": "={{ $json.document.pageContent }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "Embeddings", "type": "main", "index": 0}]]
            },
            "Embeddings": {
                "main": [[{"node": "PGInsert", "type": "main", "index": 0}]],
                "ai_embedding": [
                    [
                        {
                            "node": "PGInsert",
                            "type": "ai_embedding",
                            "index": 0,
                        }
                    ]
                ],
            },
            "PGInsert": {
                "main": [[{"node": "PGRetrieve", "type": "main", "index": 0}]]
            },
            "PGRetrieve": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )

    embed_calls: list[tuple[str, Any, str]] = []

    def fake_embed(text, item, model):
        embed_calls.append((text, item, model))
        return [float(len(text)), 0.5, 0.25]

    retrieve_docs = [
        {"pageContent": "alpha", "score": 0.9},
        {"pageContent": "beta", "score": 0.1},
    ]

    def vs_mock(mode, items, params, ctx):
        if mode == "retrieve":
            return retrieve_docs
        return None

    pin_data = {"Start": [{"text": "apple"}]}
    engine = WorkflowEngine(
        doc,
        mocks={
            "embeddings_output": fake_embed,
            "vector_store_output": vs_mock,
        },
    )
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    embed_texts = [t for t, _, _ in embed_calls]
    assert "apple" in embed_texts

    insert_steps = [s for s in result.steps if s.node_name == "PGInsert"]
    retrieve_steps = [s for s in result.steps if s.node_name == "PGRetrieve"]
    assert insert_steps, "expected at least one PGInsert run"
    assert retrieve_steps, "expected at least one PGRetrieve run"
    assert insert_steps[0].output_count == 1
    assert retrieve_steps[0].output_count == 1

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["page"] == "alpha"
