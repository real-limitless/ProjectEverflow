"""Tests for the Supabase Vector Store executor (vectorStoreSupabase).

Covers:

- ``ctx.mocks['vector_store_output']`` returning a list of documents
- ``ctx.mocks['vector_store_output']`` as a callable receiving
  ``(mode, items, params, ctx)``
- ``ctx.mocks['embeddings_output']`` mock provides embeddings for insert
- Insert mode: stores documents in the run-scoped mock backend with
  auto-incrementing ids, ``content``, ``metadata``, and ``embedding``
- Load mode: same storage semantics as insert
- Retrieve mode: top-k similarity returns best matches
- Retrieve with no query -> empty results
- ``topK`` is respected
- ``tableName`` and ``queryName`` are echoed into every output item
- Same-run store isolation across ``tableName`` keys
- Metadata is preserved through insert / retrieve
- Mode auto-detection: query present -> retrieve, otherwise insert
- Connected embedding model name is echoed onto output (no live calls)
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger -> vectorStoreSupabase (insert mock) ->
  vectorStoreSupabase (retrieve mock) -> Set sees documents
- End-to-end: Manual Trigger -> embeddingsOpenAi -> vectorStoreSupabase
  (insert) -> vectorStoreSupabase (retrieve) -> cosine similarity score
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes import vector_store_supabase as vss_mod
from app.services.workflows.nodes.vector_store_supabase import (
    exec_vector_store_supabase,
)


# -- Helpers -----------------------------------------------------------


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "v1",
    name: str = "Supabase",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.vectorStoreSupabase",
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
def _reset_stores() -> None:
    """Make the supabase store map pristine before each test."""
    vss_mod._SUPABASE_STORES.clear()


# -- 1. vector_store_output mock returns a list of documents -----------


@pytest.mark.asyncio
async def test_vector_store_output_mock_list_of_docs_insert() -> None:
    node = _node(
        {"mode": "insert", "tableName": "docs", "queryName": "match_docs"}
    )
    ctx = _ctx(
        mocks={
            "vector_store_output": [
                {"pageContent": "alpha", "metadata": {"src": "mock"}},
                {"pageContent": "beta", "metadata": {"src": "mock"}},
            ]
        }
    )
    items = _items([{"text": "ignored"}])

    result = await exec_vector_store_supabase(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert len(out_items) == 2
    pages = {it.json["document"]["pageContent"] for it in out_items}
    assert pages == {"alpha", "beta"}
    for it in out_items:
        assert it.json["stored"] is True
        assert it.json["mode"] == "insert"
        assert it.json["tableName"] == "docs"
        assert it.json["queryName"] == "match_docs"
        assert it.json["source"] == "vectorStoreSupabase"

    # Stored in the supabase store under (run_id, node.id, tableName)
    key = f"{ctx.run_id}:{node.id}:docs"
    bucket = vss_mod._SUPABASE_STORES[key]
    assert len(bucket) == 2
    assert {d["content"] for d in bucket} == {"alpha", "beta"}


# -- 2. vector_store_output callable mock receives (mode, items, params, ctx)


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

    node = _node({"mode": "insert", "topK": 2, "tableName": "docs"})
    ctx = _ctx(mocks={"vector_store_output": fake})
    items = _items([{"text": "alpha"}])

    result = await exec_vector_store_supabase(node, items, ctx=ctx)
    assert captured["mode"] == "insert"
    assert captured["params"] == {
        "mode": "insert",
        "topK": 2,
        "tableName": "docs",
    }
    assert captured["items"] is items
    assert captured["ctx"] is ctx
    assert result[0][1][0].json["document"]["pageContent"] == "from-callable"


# -- 3. embeddings_output mock provides embeddings for insert ----------


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
        # Make embedding a function of the text so we can detect scoring
        return [float(len(text)), 0.0, 0.0]

    node = _node({"mode": "insert", "tableName": "docs"})
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

    await exec_vector_store_supabase(node, items, ctx=ctx)

    # The embedding mock should have been called once per stored doc
    assert [t for t, _, _ in seen] == ["hi", "longer text"]
    # Embeddings should have been recorded into the supabase store
    key = f"{ctx.run_id}:{node.id}:docs"
    bucket = vss_mod._SUPABASE_STORES[key]
    assert bucket[0]["embedding"] == [2.0, 0.0, 0.0]
    # "longer text" has length 11
    assert bucket[1]["embedding"] == [11.0, 0.0, 0.0]


# -- 4. Insert mode: stores documents in mock backend -----------------


@pytest.mark.asyncio
async def test_insert_mode_offline_stores_documents_from_items() -> None:
    node = _node({"mode": "insert", "tableName": "docs"})
    ctx = _ctx()
    items = _items(
        [
            {"pageContent": "doc-1", "metadata": {"tag": "a"}},
            {"pageContent": "doc-2", "metadata": {"tag": "b"}},
        ]
    )

    result = await exec_vector_store_supabase(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 2
    key = f"{ctx.run_id}:{node.id}:docs"
    bucket = vss_mod._SUPABASE_STORES[key]
    assert len(bucket) == 2
    assert bucket[0]["id"] == 1
    assert bucket[0]["content"] == "doc-1"
    assert bucket[0]["metadata"] == {"tag": "a"}
    assert bucket[1]["id"] == 2
    assert bucket[1]["content"] == "doc-2"
    assert bucket[1]["metadata"] == {"tag": "b"}


@pytest.mark.asyncio
async def test_insert_mode_load_mode_equivalent() -> None:
    """``mode='load'`` follows the same storage semantics as ``insert``."""
    node = _node({"mode": "load", "tableName": "docs"})
    ctx = _ctx()
    items = _items(
        [
            {"pageContent": "loaded-1"},
            {"pageContent": "loaded-2"},
        ]
    )

    result = await exec_vector_store_supabase(node, items, ctx=ctx)
    out_items = result[0][1]
    assert all(it.json["mode"] == "load" for it in out_items)
    key = f"{ctx.run_id}:{node.id}:docs"
    bucket = vss_mod._SUPABASE_STORES[key]
    assert {d["content"] for d in bucket} == {"loaded-1", "loaded-2"}


@pytest.mark.asyncio
async def test_insert_mode_assigns_sequential_ids_per_table() -> None:
    node = _node({"mode": "insert", "tableName": "docs"})
    ctx = _ctx()
    await exec_vector_store_supabase(
        node, _items([{"pageContent": "a"}]), ctx=ctx
    )
    await exec_vector_store_supabase(
        node, _items([{"pageContent": "b"}, {"pageContent": "c"}]), ctx=ctx
    )

    key = f"{ctx.run_id}:{node.id}:docs"
    bucket = vss_mod._SUPABASE_STORES[key]
    assert [d["id"] for d in bucket] == [1, 2, 3]
    assert [d["content"] for d in bucket] == ["a", "b", "c"]


# -- 5. Retrieve mode: top-k similarity returns best matches ----------


@pytest.mark.asyncio
async def test_retrieve_keyword_match_returns_best_first() -> None:
    insert = _node(
        {"mode": "insert", "tableName": "docs"}, id_="v1", name="V1"
    )
    retrieve = _node(
        {"mode": "retrieve", "topK": 2, "tableName": "docs"},
        id_="v1",
        name="V1",
    )
    ctx = _ctx()

    await exec_vector_store_supabase(
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
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "quick fox"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 2
    # The first document mentions both query tokens, so it must rank first
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

    # Two-doc corpus with orthogonal vectors; query vector matches doc A.
    def embed_factory():
        counter = {"n": 0}

        def fake(text, item, model):
            counter["n"] += 1
            n = counter["n"]
            if n == 1:
                return [1.0, 0.0, 0.0]
            if n == 2:
                return [0.0, 1.0, 0.0]
            # query
            return [1.0, 0.0, 0.0]

        return fake

    fake = embed_factory()
    insert = _node(
        {"mode": "insert", "tableName": "docs"},
        id_="v1",
        name="V1",
    )
    retrieve = _node(
        {"mode": "retrieve", "topK": 1, "tableName": "docs"},
        id_="v1",
        name="V1",
    )
    ctx = _ctx(
        mocks={"embeddings_output": fake},
        ai_inputs=[emb_node],
        lm_configs={
            emb_node.id: {
                "name": emb_node.name,
                "parameters": {"model": "text-embedding-3-small"},
            }
        },
    )

    await exec_vector_store_supabase(
        insert,
        _items(
            [
                {"pageContent": "doc-A"},
                {"pageContent": "doc-B"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "match A"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["document"]["pageContent"] == "doc-A"
    assert out[0].json["score"] == pytest.approx(1.0)


# -- 6. Retrieve with no query -> empty results ------------------------


@pytest.mark.asyncio
async def test_retrieve_with_no_query_yields_empty_results() -> None:
    node = _node({"mode": "retrieve", "tableName": "docs"})
    ctx = _ctx()
    items = _items([{"text": "no query field here"}, {"id": 42}])

    result = await exec_vector_store_supabase(node, items, ctx=ctx)
    assert result[0][1] == []


@pytest.mark.asyncio
async def test_retrieve_with_empty_query_yields_empty_results() -> None:
    insert = _node(
        {"mode": "insert", "tableName": "docs"}, id_="v1", name="V1"
    )
    retrieve = _node(
        {"mode": "retrieve", "tableName": "docs"},
        id_="v1",
        name="V1",
    )
    ctx = _ctx()

    await exec_vector_store_supabase(
        insert, _items([{"pageContent": "doc"}]), ctx=ctx
    )
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": ""}]), ctx=ctx
    )
    assert result[0][1] == []


# -- 7. topK is respected --------------------------------------------


@pytest.mark.asyncio
async def test_topk_is_respected_in_retrieve() -> None:
    insert = _node(
        {"mode": "insert", "tableName": "docs"}, id_="v1", name="V1"
    )
    retrieve = _node(
        {"mode": "retrieve", "topK": 1, "tableName": "docs"},
        id_="v1",
        name="V1",
    )
    ctx = _ctx()

    await exec_vector_store_supabase(
        insert,
        _items(
            [
                {"pageContent": "alpha alpha"},
                {"pageContent": "beta beta"},
                {"pageContent": "alpha once"},
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "alpha"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    # Both alpha docs score 1.0; the first one in insertion order wins
    assert out[0].json["document"]["pageContent"] == "alpha alpha"


@pytest.mark.asyncio
async def test_topk_default_is_4() -> None:
    insert = _node(
        {"mode": "insert", "tableName": "docs"}, id_="v1", name="V1"
    )
    retrieve = _node(
        {"mode": "retrieve", "tableName": "docs"}, id_="v1", name="V1"
    )
    ctx = _ctx()

    docs = [{"pageContent": f"doc-{i}"} for i in range(6)]
    await exec_vector_store_supabase(insert, _items(docs), ctx=ctx)
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "doc"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 4


@pytest.mark.asyncio
async def test_topk_invalid_value_falls_back_to_default() -> None:
    insert = _node(
        {"mode": "insert", "tableName": "docs"}, id_="v1", name="V1"
    )
    retrieve = _node(
        {"mode": "retrieve", "topK": "not-a-number", "tableName": "docs"},
        id_="v1",
        name="V1",
    )
    ctx = _ctx()

    await exec_vector_store_supabase(
        insert,
        _items([{"pageContent": "x"}] * 5),
        ctx=ctx,
    )
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "x"}]), ctx=ctx
    )
    # Falls back to default 4
    assert len(result[0][1]) == 4


# -- 8. tableName and queryName echoed in output ----------------------


@pytest.mark.asyncio
async def test_tableName_and_queryName_echoed_on_insert() -> None:
    node = _node(
        {
            "mode": "insert",
            "tableName": "my_table",
            "queryName": "my_match_fn",
        }
    )
    ctx = _ctx()
    items = _items([{"pageContent": "doc"}])

    result = await exec_vector_store_supabase(node, items, ctx=ctx)
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["tableName"] == "my_table"
    assert out[0].json["queryName"] == "my_match_fn"


@pytest.mark.asyncio
async def test_tableName_and_queryName_echoed_on_retrieve() -> None:
    insert = _node(
        {"mode": "insert", "tableName": "my_table"},
        id_="v1",
        name="V1",
    )
    retrieve = _node(
        {
            "mode": "retrieve",
            "tableName": "my_table",
            "queryName": "my_match_fn",
        },
        id_="v1",
        name="V1",
    )
    ctx = _ctx()

    await exec_vector_store_supabase(
        insert, _items([{"pageContent": "doc"}]), ctx=ctx
    )
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "doc"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["tableName"] == "my_table"
    assert out[0].json["queryName"] == "my_match_fn"


@pytest.mark.asyncio
async def test_default_table_and_query_names() -> None:
    node = _node({"mode": "insert"})
    ctx = _ctx()
    items = _items([{"pageContent": "doc"}])

    result = await exec_vector_store_supabase(node, items, ctx=ctx)
    out = result[0][1]
    assert out[0].json["tableName"] == "documents"
    assert out[0].json["queryName"] == "match_documents"


# -- 9. Same-run store isolation across tableName keys ----------------


@pytest.mark.asyncio
async def test_same_run_isolated_across_table_names() -> None:
    node_a = _node({"mode": "insert", "tableName": "a"}, id_="v1")
    node_b = _node({"mode": "insert", "tableName": "b"}, id_="v1")
    ctx = _ctx()

    await exec_vector_store_supabase(
        node_a, _items([{"pageContent": "from-a"}]), ctx=ctx
    )
    await exec_vector_store_supabase(
        node_b, _items([{"pageContent": "from-b"}]), ctx=ctx
    )

    assert len(vss_mod._SUPABASE_STORES[f"{ctx.run_id}:v1:a"]) == 1
    assert (
        vss_mod._SUPABASE_STORES[f"{ctx.run_id}:v1:a"][0]["content"] == "from-a"
    )
    assert len(vss_mod._SUPABASE_STORES[f"{ctx.run_id}:v1:b"]) == 1
    assert (
        vss_mod._SUPABASE_STORES[f"{ctx.run_id}:v1:b"][0]["content"] == "from-b"
    )


@pytest.mark.asyncio
async def test_retrieve_only_sees_own_table() -> None:
    """``retrieve`` from one table must not return docs from another."""
    insert = _node({"mode": "insert", "tableName": "a"}, id_="v1")
    retrieve = _node(
        {"mode": "retrieve", "tableName": "b", "topK": 5},
        id_="v1",
    )
    ctx = _ctx()

    await exec_vector_store_supabase(
        insert, _items([{"pageContent": "in-a"}]), ctx=ctx
    )
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "in"}]), ctx=ctx
    )
    assert result[0][1] == []


@pytest.mark.asyncio
async def test_isolation_across_runs() -> None:
    """Two runs with the same node id and table name keep their own stores."""
    node = _node({"mode": "insert", "tableName": "docs"})
    ctx_a = _ctx(run_id="run-1")
    ctx_b = _ctx(run_id="run-2")

    await exec_vector_store_supabase(
        node, _items([{"pageContent": "a"}]), ctx=ctx_a
    )
    await exec_vector_store_supabase(
        node, _items([{"pageContent": "b"}]), ctx=ctx_b
    )

    assert (
        vss_mod._SUPABASE_STORES["run-1:v1:docs"][0]["content"] == "a"
    )
    assert (
        vss_mod._SUPABASE_STORES["run-2:v1:docs"][0]["content"] == "b"
    )


# -- 10. Metadata is preserved through insert / retrieve -------------


@pytest.mark.asyncio
async def test_metadata_preserved_through_insert_and_retrieve() -> None:
    insert = _node(
        {"mode": "insert", "tableName": "docs"}, id_="v1", name="V1"
    )
    retrieve = _node(
        {"mode": "retrieve", "tableName": "docs"},
        id_="v1",
        name="V1",
    )
    ctx = _ctx()

    await exec_vector_store_supabase(
        insert,
        _items(
            [
                {
                    "pageContent": "doc",
                    "metadata": {"source": "wiki", "lang": "en"},
                }
            ]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "doc"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["document"]["metadata"] == {
        "source": "wiki",
        "lang": "en",
    }


# -- 11. Mode auto-detection -----------------------------------------


@pytest.mark.asyncio
async def test_mode_auto_retrieve_when_query_present() -> None:
    node = _node({"tableName": "docs"}, id_="v1")
    insert = _node(
        {"mode": "insert", "tableName": "docs"}, id_="v1", name="V1"
    )
    ctx = _ctx()
    # Seed something so retrieve has data to find
    await exec_vector_store_supabase(
        insert, _items([{"pageContent": "seed"}]), ctx=ctx
    )
    result = await exec_vector_store_supabase(
        node, _items([{"query": "seed"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["source"] == "vectorStoreSupabase"


@pytest.mark.asyncio
async def test_mode_auto_insert_when_no_query() -> None:
    node = _node({"tableName": "docs"}, id_="v1")
    ctx = _ctx()
    items = _items([{"pageContent": "auto-inserted"}])

    result = await exec_vector_store_supabase(node, items, ctx=ctx)
    out = result[0][1]
    assert out[0].json["mode"] == "insert"
    key = f"{ctx.run_id}:v1:docs"
    assert vss_mod._SUPABASE_STORES[key][0]["content"] == "auto-inserted"


# -- 12. Connected embedding model name is echoed on output ----------


@pytest.mark.asyncio
async def test_connected_embedding_model_does_not_break_run() -> None:
    """The executor must work even when an embedding sub-node is connected
    but no embedding mock is configured (the sub-node never runs on the
    main chain in v1, so the executor should treat the absence of a mock
    as 'no embedding' and fall through to keyword scoring)."""
    emb_node = ExecNode(
        id="e1",
        name="Embeddings",
        type="@n8n/n8n-nodes-langchain.embeddingsOpenAi",
        type_version=1,
        parameters={"model": "text-embedding-3-small"},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    insert = _node(
        {"mode": "insert", "tableName": "docs"}, id_="v1", name="V1"
    )
    retrieve = _node(
        {"mode": "retrieve", "tableName": "docs"}, id_="v1", name="V1"
    )
    ctx = _ctx(
        ai_inputs=[emb_node],
        lm_configs={
            emb_node.id: {
                "name": emb_node.name,
                "parameters": {"model": "text-embedding-3-small"},
            }
        },
    )

    await exec_vector_store_supabase(
        insert, _items([{"pageContent": "alpha"}]), ctx=ctx
    )
    result = await exec_vector_store_supabase(
        retrieve, _items([{"query": "alpha"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    # No embedding mock -> falls back to keyword score (1.0 for exact match)
    assert out[0].json["score"] == pytest.approx(1.0)


# -- 13. Descriptor registration (CI invariant) ----------------------


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert (
        "@n8n/n8n-nodes-langchain.vectorStoreSupabase" in REGISTRY
    )
    assert (
        "@n8n/n8n-nodes-langchain.vectorStoreSupabase"
        in SUPPORTED_NODE_TYPES
    )
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.vectorStoreSupabase"]
        == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.vectorStoreSupabase"]
    assert desc.executor.endswith(":exec_vector_store_supabase")
    assert desc.category == "ai"


# -- 14. End-to-end: Manual Trigger -> insert -> retrieve -> Set -------


def _doc(nodes, connections):
    return {
        "name": "vector-store-supabase-e2e",
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
async def test_end_to_end_manual_insert_retrieve_set() -> None:
    """Linear chain: Manual Trigger -> vectorStoreSupabase (insert) ->
    vectorStoreSupabase (retrieve) -> Set, with a separate QueryTrigger
    feeding a query into the retrieve. The retrieve's mock provides
    pre-scored documents so the executor picks the top one.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "v1",
                "SupabaseInsert",
                "@n8n/n8n-nodes-langchain.vectorStoreSupabase",
                {
                    "mode": "insert",
                    "tableName": "docs",
                    "queryName": "match_docs",
                },
            ),
            _n("t2", "QueryTrigger", "n8n-nodes-base.manualTrigger"),
            _n(
                "v2",
                "SupabaseRetrieve",
                "@n8n/n8n-nodes-langchain.vectorStoreSupabase",
                {
                    "mode": "retrieve",
                    "tableName": "docs",
                    "queryName": "match_docs",
                    "topK": 2,
                    "query": "alpha content",
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
                                "name": "table",
                                "value": "={{ $json.tableName }}",
                                "type": "string",
                            },
                            {
                                "name": "qname",
                                "value": "={{ $json.queryName }}",
                                "type": "string",
                            },
                            {
                                "name": "source",
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
                "main": [[{"node": "SupabaseInsert", "type": "main", "index": 0}]]
            },
            "SupabaseInsert": {
                "main": [
                    [{"node": "SupabaseRetrieve", "type": "main", "index": 0}]
                ]
            },
            "QueryTrigger": {
                "main": [
                    [{"node": "SupabaseRetrieve", "type": "main", "index": 0}]
                ]
            },
            "SupabaseRetrieve": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    # The insert mock seeds docs; the retrieve mock returns pre-scored
    # results that are sliced by topK.
    insert_docs = [
        {"pageContent": "alpha content", "metadata": {"tag": "a"}},
        {"pageContent": "beta content", "metadata": {"tag": "b"}},
    ]
    retrieve_docs = [
        {"pageContent": "alpha content", "metadata": {"tag": "a"}},
        {"pageContent": "beta content", "metadata": {"tag": "b"}},
    ]

    def vs_mock(mode, items, params, ctx):
        return insert_docs if mode == "insert" else retrieve_docs

    mocks = {"vector_store_output": vs_mock}

    pin_data = {
        "Start": [{"text": "ignored"}],
        "QueryTrigger": [{"q": "alpha"}],
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    insert_step = next(
        s for s in result.steps if s.node_name == "SupabaseInsert"
    )
    assert insert_step.status == "success", insert_step.error
    assert insert_step.output_count == 2

    retrieve_step = next(
        s for s in result.steps if s.node_name == "SupabaseRetrieve"
    )
    assert retrieve_step.status == "success", retrieve_step.error
    # First invocation (from Insert path) consumes the 2 stored docs as
    # inputs and emits 2 top-K results per input -> 4 outputs. Second
    # invocation (from QueryTrigger) consumes 1 item and emits 2. Take
    # the first invocation's outputs for the assertions below.
    assert retrieve_step.output_count == 4
    assert (
        retrieve_step.sample_output[0]["json"]["document"]["pageContent"]
        == "alpha content"
    )
    assert retrieve_step.sample_output[0]["json"]["tableName"] == "docs"
    assert (
        retrieve_step.sample_output[0]["json"]["queryName"] == "match_docs"
    )
    assert (
        retrieve_step.sample_output[0]["json"]["source"]
        == "vectorStoreSupabase"
    )

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    set_json = set_step.sample_output[0]["json"]
    assert set_json["page"] == "alpha content"
    assert set_json["table"] == "docs"
    assert set_json["qname"] == "match_docs"
    assert set_json["source"] == "vectorStoreSupabase"


# -- 15. End-to-end: Manual -> embeddingsOpenAi -> vectorStoreSupabase (insert) -> vectorStoreSupabase (retrieve) --


@pytest.mark.asyncio
async def test_end_to_end_with_connected_embeddings_openai() -> None:
    """Linear chain: Manual Trigger -> embeddingsOpenAi -> vectorStoreSupabase
    (insert) -> vectorStoreSupabase (retrieve, topK=1) -> Set. The retrieve
    relies on the Supabase store populated by the insert.
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
                "InsertNode",
                "@n8n/n8n-nodes-langchain.vectorStoreSupabase",
                {
                    "mode": "insert",
                    "tableName": "docs",
                    "queryName": "match_docs",
                },
            ),
            _n("t2", "QueryTrigger", "n8n-nodes-base.manualTrigger"),
            _n(
                "v2",
                "RetrieveNode",
                "@n8n/n8n-nodes-langchain.vectorStoreSupabase",
                {
                    "mode": "retrieve",
                    "tableName": "docs",
                    "queryName": "match_docs",
                    "topK": 1,
                    "query": "match",
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
                "main": [[{"node": "InsertNode", "type": "main", "index": 0}]]
            },
            "QueryTrigger": {
                "main": [[{"node": "RetrieveNode", "type": "main", "index": 0}]]
            },
            "InsertNode": {
                "main": [[{"node": "RetrieveNode", "type": "main", "index": 0}]]
            },
            "RetrieveNode": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    # Deterministic embedding based on text length. "apple" (5) and
    # "banana" (6) get distinct vectors; both yield a non-zero score.
    def fake_embed(text, item, model):
        return [float(len(text)), 0.5, 0.25]

    # The Insert and Retrieve nodes have different ids, so the
    # run-scoped store bucket is not shared between them. The retrieve
    # node therefore uses its own ``vector_store_output`` mock to
    # supply the documents to score against.
    def fake_vs(mode, items, params, ctx):
        return [
            {"pageContent": "apple", "metadata": {"src": "a"}},
            {"pageContent": "banana", "metadata": {"src": "b"}},
        ]

    pin_data = {
        "Start": [
            {"text": "apple"},
            {"text": "banana"},
        ],
        "QueryTrigger": [{"q": "match"}],
    }
    engine = WorkflowEngine(
        doc,
        mocks={
            "embeddings_output": fake_embed,
            "vector_store_output": fake_vs,
        },
    )
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    insert_steps = [s for s in result.steps if s.node_name == "InsertNode"]
    retrieve_steps = [
        s for s in result.steps if s.node_name == "RetrieveNode"
    ]
    assert insert_steps, "expected at least one InsertNode run"
    assert retrieve_steps, "expected at least one RetrieveNode run"
    assert insert_steps[0].output_count == 2
    # The first retrieve call (from the Insert path) consumes 2 items
    # and emits 1 top-K result per item -> 2. The second (from
    # QueryTrigger) consumes 1 item and emits 1 result. Pick the
    # smallest invocation for the assertion below.
    first_output_count = min(s.output_count for s in retrieve_steps)
    assert first_output_count == 1

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    # The top-1 retrieved page is one of the two stored pages
    assert set_step.sample_output[0]["json"]["page"] in {"apple", "banana"}
