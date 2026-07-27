"""Tests for the Pinecone Vector Store executor (vectorStorePinecone).

Covers:

- ``ctx.mocks['vector_store_output']`` returning a list of documents
- ``ctx.mocks['vector_store_output']`` as a callable receiving
  ``(mode, items, params, ctx)``
- ``ctx.mocks['embeddings_output']`` mock provides embeddings for insert
- Insert mode: stores documents in the mocked index and emits stored items
- Retrieve mode: top-k similarity returns best matches
- Retrieve with no query → empty results
- ``topK`` is respected
- ``indexName`` and ``namespace`` echoed in output
- Same-run store isolation across ``indexName``+``namespace`` keys
- Metadata preserved through insert / retrieve
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger → vectorStorePinecone (insert mock) →
  vectorStorePinecone (retrieve mock) → Set sees documents
- End-to-end: Manual Trigger → embeddingsOpenAi → vectorStorePinecone
  (insert) → vectorStorePinecone (retrieve)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes import vector_store_pinecone as vsp_mod
from app.services.workflows.nodes.vector_store_pinecone import (
    exec_vector_store_pinecone,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "v1",
    name: str = "Pinecone",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.vectorStorePinecone",
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
def _reset_indexes() -> None:
    """Make the mocked Pinecone index map pristine before each test."""
    vsp_mod._PINECONE_INDEXES.clear()


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

    result = await exec_vector_store_pinecone(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert len(out_items) == 2
    pages = {it.json["document"]["pageContent"] for it in out_items}
    assert pages == {"alpha", "beta"}
    for it in out_items:
        assert it.json["stored"] is True
        assert it.json["mode"] == "insert"
        assert it.json["source"] == "vectorStorePinecone"
        assert it.json["indexName"] == "n8n-vector-store"
        assert it.json["namespace"] == ""

    # Stored in the mocked index under (run_id, node.id, indexName, namespace)
    key = f"{ctx.run_id}:{node.id}:n8n-vector-store:"
    bucket = vsp_mod._PINECONE_INDEXES[key]
    assert len(bucket) == 2
    assert {d["metadata"]["text"] for d in bucket} == {"alpha", "beta"}
    # Auto ids
    assert [d["id"] for d in bucket] == ["doc-1", "doc-2"]


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
        {"mode": "insert", "topK": 2, "indexName": "demo", "namespace": "ns1"}
    )
    ctx = _ctx(mocks={"vector_store_output": fake})
    items = _items([{"text": "alpha"}])

    result = await exec_vector_store_pinecone(node, items, ctx=ctx)
    assert captured["mode"] == "insert"
    assert captured["params"] == {
        "mode": "insert",
        "topK": 2,
        "indexName": "demo",
        "namespace": "ns1",
    }
    assert captured["items"] is items
    assert captured["ctx"] is ctx
    assert result[0][1][0].json["document"]["pageContent"] == "from-callable"
    assert result[0][1][0].json["indexName"] == "demo"
    assert result[0][1][0].json["namespace"] == "ns1"


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
        # Make embedding a function of the text so we can detect scoring
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

    await exec_vector_store_pinecone(node, items, ctx=ctx)

    # The embedding mock should have been called once per stored doc
    assert [t for t, _, _ in seen] == ["hi", "longer text"]
    # Embeddings should have been recorded into the mocked index as `values`
    key = f"{ctx.run_id}:{node.id}:n8n-vector-store:"
    bucket = vsp_mod._PINECONE_INDEXES[key]
    assert bucket[0]["values"] == [2.0, 0.0, 0.0]
    assert bucket[1]["values"] == [11.0, 0.0, 0.0]


# ── 4. Insert mode: stores documents in mocked index ─────────────────


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

    result = await exec_vector_store_pinecone(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 2
    key = f"{ctx.run_id}:{node.id}:n8n-vector-store:"
    bucket = vsp_mod._PINECONE_INDEXES[key]
    assert len(bucket) == 2
    assert bucket[0]["metadata"]["text"] == "doc-1"
    assert bucket[0]["metadata"]["tag"] == "a"
    assert bucket[1]["metadata"]["text"] == "doc-2"
    assert bucket[1]["metadata"]["tag"] == "b"
    # No embedding mock, no model connected → values is an empty list
    assert bucket[0]["values"] == []
    assert bucket[1]["values"] == []


# ── 5. Retrieve mode: top-k similarity returns best matches ───────────


@pytest.mark.asyncio
async def test_retrieve_keyword_match_returns_best_first() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node(
        {"mode": "retrieve", "topK": 2}, id_="v1", name="V1"
    )
    ctx = _ctx()

    await exec_vector_store_pinecone(
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
    result = await exec_vector_store_pinecone(
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
            if n == 1:  # doc A
                return [1.0, 0.0]
            if n == 2:  # doc B
                return [0.0, 1.0]
            if n == 3:  # doc C
                return [0.7, 0.7]
            # query
            return [1.0, 0.0]

        return fake

    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node(
        {"mode": "retrieve", "topK": 3}, id_="v1", name="V1"
    )
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

    await exec_vector_store_pinecone(
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
    result = await exec_vector_store_pinecone(
        retrieve, _items([{"query": "anything"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 3
    # doc A and doc C both have a non-zero dot with the query; doc B is
    # orthogonal (cosine = 0). So doc A should be the top result.
    assert out[0].json["document"]["pageContent"] == "doc-A"
    assert out[0].json["score"] == pytest.approx(1.0, abs=1e-6)
    # doc C has cosine 0.7 / (1 * 1) ~= 0.707
    assert out[1].json["document"]["pageContent"] == "doc-C"
    assert out[1].json["score"] == pytest.approx(0.70710678, abs=1e-5)
    # doc B is orthogonal → score == 0
    assert out[2].json["document"]["pageContent"] == "doc-B"
    assert out[2].json["score"] == 0.0


# ── 6. Retrieve with no query → empty results ─────────────────────────


@pytest.mark.asyncio
async def test_retrieve_with_no_query_returns_empty() -> None:
    node = _node({"mode": "retrieve"})
    ctx = _ctx()
    # Pre-populate the mocked index so we know it's not a missing-store issue
    vsp_mod._PINECONE_INDEXES[f"{ctx.run_id}:{node.id}:n8n-vector-store:"] = [
        {
            "id": "doc-1",
            "values": [],
            "metadata": {"text": "anything"},
        }
    ]
    result = await exec_vector_store_pinecone(
        node, _items([{"unrelated": "no query fields here"}]), ctx=ctx
    )
    assert result[0][1] == []


@pytest.mark.asyncio
async def test_retrieve_with_empty_query_string_returns_empty() -> None:
    node = _node({"mode": "retrieve"})
    ctx = _ctx()
    vsp_mod._PINECONE_INDEXES[f"{ctx.run_id}:{node.id}:n8n-vector-store:"] = [
        {"id": "doc-1", "values": [], "metadata": {"text": "x"}},
    ]
    result = await exec_vector_store_pinecone(
        node, _items([{"query": ""}]), ctx=ctx
    )
    assert result[0][1] == []


# ── 7. topK respected ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_topk_respected() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node(
        {"mode": "retrieve", "topK": 2}, id_="v1", name="V1"
    )
    ctx = _ctx()

    await exec_vector_store_pinecone(
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
    result = await exec_vector_store_pinecone(
        retrieve, _items([{"query": "alpha"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 2
    for it in out:
        assert "alpha" in it.json["document"]["pageContent"]


@pytest.mark.asyncio
async def test_topk_default_is_4() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    retrieve = _node({"mode": "retrieve"}, id_="v1", name="V1")  # no topK
    ctx = _ctx()

    await exec_vector_store_pinecone(
        insert,
        _items(
            [{"pageContent": f"alpha doc {i}"} for i in range(6)]
        ),
        ctx=ctx,
    )
    result = await exec_vector_store_pinecone(
        retrieve, _items([{"query": "alpha"}]), ctx=ctx
    )
    out = result[0][1]
    # Default topK = 4
    assert len(out) == 4


# ── 8. indexName and namespace echoed in output ───────────────────────


@pytest.mark.asyncio
async def test_indexname_and_namespace_echoed() -> None:
    node = _node(
        {
            "mode": "insert",
            "indexName": "my-index",
            "namespace": "tenant-a",
        }
    )
    ctx = _ctx()
    items = _items([{"pageContent": "hello"}])

    result = await exec_vector_store_pinecone(node, items, ctx=ctx)
    out = result[0][1]
    assert out[0].json["indexName"] == "my-index"
    assert out[0].json["namespace"] == "tenant-a"

    # Retrieve echoes the same
    retrieve = _node(
        {
            "mode": "retrieve",
            "indexName": "my-index",
            "namespace": "tenant-a",
            "query": "hello",
        }
    )
    result2 = await exec_vector_store_pinecone(
        retrieve, _items([{"query": "hello"}]), ctx=ctx
    )
    out2 = result2[0][1]
    assert len(out2) >= 1
    assert out2[0].json["indexName"] == "my-index"
    assert out2[0].json["namespace"] == "tenant-a"


@pytest.mark.asyncio
async def test_indexname_default_and_namespace_default() -> None:
    node = _node({"mode": "insert"})
    ctx = _ctx()
    items = _items([{"pageContent": "x"}])
    result = await exec_vector_store_pinecone(node, items, ctx=ctx)
    assert result[0][1][0].json["indexName"] == "n8n-vector-store"
    assert result[0][1][0].json["namespace"] == ""


# ── 9. Same-run store isolation across indexName+namespace keys ──────


@pytest.mark.asyncio
async def test_indexname_namespace_isolation_within_run() -> None:
    """Two nodes sharing the same id but different index/namespace pairs
    keep their own stores."""
    ctx = _ctx(run_id="run-1")
    n_a = _node(
        {"mode": "insert", "indexName": "idxA", "namespace": "ns1"},
        id_="shared",
        name="Shared",
    )
    n_b = _node(
        {"mode": "insert", "indexName": "idxB", "namespace": "ns2"},
        id_="shared",
        name="Shared",
    )
    await exec_vector_store_pinecone(
        n_a, _items([{"pageContent": "in-A"}]), ctx=ctx
    )
    await exec_vector_store_pinecone(
        n_b, _items([{"pageContent": "in-B"}]), ctx=ctx
    )

    # Two distinct buckets keyed by indexName+namespace
    assert (
        vsp_mod._PINECONE_INDEXES["run-1:shared:idxA:ns1"][0]["metadata"]["text"]
        == "in-A"
    )
    assert (
        vsp_mod._PINECONE_INDEXES["run-1:shared:idxB:ns2"][0]["metadata"]["text"]
        == "in-B"
    )


@pytest.mark.asyncio
async def test_two_different_runs_do_not_share_index() -> None:
    node = _node({"mode": "insert"}, id_="v1", name="V1")
    ctx1 = _ctx(run_id="run-A")
    ctx2 = _ctx(run_id="run-B")
    await exec_vector_store_pinecone(
        node, _items([{"pageContent": "only in A"}]), ctx=ctx1
    )
    # Retrieve from run-B with the same node id: bucket should be empty
    retrieve = _node(
        {"mode": "retrieve", "query": "only"}, id_="v1", name="V1"
    )
    result = await exec_vector_store_pinecone(
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
    await exec_vector_store_pinecone(insert, _items([{}]), ctx=ctx)
    result = await exec_vector_store_pinecone(
        retrieve, _items([{"query": "alpha"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["document"]["pageContent"] == "alpha"
    assert out[0].json["document"]["metadata"] == {"source": "wiki", "version": 3}


# ── 11. Mode auto-detection: query present → retrieve, else insert ──


@pytest.mark.asyncio
async def test_auto_mode_with_query_in_parameter_uses_retrieve() -> None:
    insert = _node({"mode": "insert"}, id_="v1", name="V1")
    auto = _node({"query": "anything"}, id_="v1", name="V1")
    ctx = _ctx()
    await exec_vector_store_pinecone(
        insert, _items([{"pageContent": "doc"}]), ctx=ctx
    )
    # No explicit mode, but parameters.query is set → retrieve
    result = await exec_vector_store_pinecone(
        auto, _items([{"unrelated": "placeholder"}]), ctx=ctx
    )
    out = result[0][1]
    assert len(out) == 1
    assert "score" in out[0].json


@pytest.mark.asyncio
async def test_auto_mode_without_query_defaults_to_insert() -> None:
    auto = _node({}, id_="v1", name="V1")
    ctx = _ctx()
    result = await exec_vector_store_pinecone(
        auto, _items([{"pageContent": "inserted"}]), ctx=ctx
    )
    out = result[0][1]
    assert out[0].json["mode"] == "insert"
    key = f"{ctx.run_id}:v1:n8n-vector-store:"
    assert (
        vsp_mod._PINECONE_INDEXES[key][0]["metadata"]["text"] == "inserted"
    )


# ── 12. Descriptor registration (CI invariant) ──────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert (
        "@n8n/n8n-nodes-langchain.vectorStorePinecone" in REGISTRY
    )
    assert (
        "@n8n/n8n-nodes-langchain.vectorStorePinecone" in SUPPORTED_NODE_TYPES
    )
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.vectorStorePinecone"]
        == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.vectorStorePinecone"]
    assert desc.executor.endswith(":exec_vector_store_pinecone")
    assert desc.category == "ai"


# ── 13. End-to-end: Manual → vectorStorePinecone (insert mock) → vectorStorePinecone (retrieve mock) → Set ─


def _doc(nodes, connections):
    return {
        "name": "vector-store-pinecone-e2e",
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
    """Linear chain: Manual Trigger → Pinecone(insert) → Pinecone(retrieve)
    → Set. The insert uses the static ``vector_store_output`` mock to
    store two docs; the retrieve uses the callable ``vs_mock`` which
    ignores the query and returns pre-scored docs so the Set node sees
    the expected ``alpha`` document, the configured ``indexName`` /
    ``namespace``, and ``source: 'vectorStorePinecone'``.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "v1",
                "PineconeInsert",
                "@n8n/n8n-nodes-langchain.vectorStorePinecone",
                {"mode": "insert", "indexName": "demo", "namespace": "ns1"},
            ),
            _n(
                "v2",
                "PineconeRetrieve",
                "@n8n/n8n-nodes-langchain.vectorStorePinecone",
                {
                    "mode": "retrieve",
                    "topK": 1,
                    "query": "={{ 'anything' }}",
                    "indexName": "demo",
                    "namespace": "ns1",
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
                                "name": "indexName",
                                "value": "={{ $json.indexName }}",
                                "type": "string",
                            },
                            {
                                "name": "namespace",
                                "value": "={{ $json.namespace }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "PineconeInsert", "type": "main", "index": 0}]]
            },
            "PineconeInsert": {
                "main": [[{"node": "PineconeRetrieve", "type": "main", "index": 0}]]
            },
            "PineconeRetrieve": {
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
        # Insert: let the offline path run
        return [
            {"pageContent": "alpha content", "metadata": {"tag": "a"}},
            {"pageContent": "beta content", "metadata": {"tag": "b"}},
        ]

    pin_data = {
        "Start": [{"text": "ignored"}],
    }
    engine = WorkflowEngine(doc, mocks={"vector_store_output": vs_mock})
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    insert_step = next(
        s for s in result.steps if s.node_name == "PineconeInsert"
    )
    assert insert_step.status == "success", insert_step.error
    # insert has 1 input item, the mock returns 2 docs → 2 outputs
    assert insert_step.output_count == 2

    retrieve_step = next(
        s for s in result.steps if s.node_name == "PineconeRetrieve"
    )
    assert retrieve_step.status == "success", retrieve_step.error
    # 2 items in × topK=1 × 2 docs in mock = 2 outputs
    assert retrieve_step.output_count == 2
    assert (
        retrieve_step.sample_output[0]["json"]["document"]["pageContent"]
        == "alpha content"
    )
    assert retrieve_step.sample_output[0]["json"]["score"] == 0.9

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    sample = set_step.sample_output[0]["json"]
    assert sample["page"] == "alpha content"
    assert sample["score"] == 0.9
    assert sample["src"] == "vectorStorePinecone"
    assert sample["indexName"] == "demo"
    assert sample["namespace"] == "ns1"


# ── 14. End-to-end: Manual → embeddingsOpenAi → vectorStorePinecone (insert) → vectorStorePinecone (retrieve) ─


@pytest.mark.asyncio
async def test_end_to_end_with_connected_embeddings_openai() -> None:
    """Linear chain: Manual Trigger → embeddingsOpenAi → vectorStorePinecone
    (insert, id=v1) → vectorStorePinecone (retrieve, id=v2) → Set. The
    retrieve is fed by the mock's pre-scored docs (since the insert and
    retrieve have distinct node ids and therefore distinct mocked
    indexes) and the embedding sub-node is connected to the insert so
    its mock is invoked per doc.
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
                "PineconeInsert",
                "@n8n/n8n-nodes-langchain.vectorStorePinecone",
                {"mode": "insert"},
            ),
            _n(
                "v2",
                "PineconeRetrieve",
                "@n8n/n8n-nodes-langchain.vectorStorePinecone",
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
                "main": [[{"node": "PineconeInsert", "type": "main", "index": 0}]],
                "ai_embedding": [
                    [
                        {
                            "node": "PineconeInsert",
                            "type": "ai_embedding",
                            "index": 0,
                        }
                    ]
                ],
            },
            "PineconeInsert": {
                "main": [[{"node": "PineconeRetrieve", "type": "main", "index": 0}]]
            },
            "PineconeRetrieve": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )

    # Deterministic embedding based on the text length. "apple" (5) and
    # "banana" (6) get distinct vectors; both yield a non-zero score.
    embed_calls: list[tuple[str, Any, str]] = []

    def fake_embed(text, item, model):
        embed_calls.append((text, item, model))
        return [float(len(text)), 0.5, 0.25]

    # The retrieve node lives in a separate id-keyed bucket, so the mock
    # supplies the docs that get scored against the query.
    retrieve_docs = [
        {"pageContent": "alpha", "score": 0.9},
        {"pageContent": "beta", "score": 0.1},
    ]

    def vs_mock(mode, items, params, ctx):
        if mode == "retrieve":
            return retrieve_docs
        return None  # let the offline path handle insert

    pin_data = {
        "Start": [
            {"text": "apple"},
        ],
    }
    engine = WorkflowEngine(
        doc,
        mocks={
            "embeddings_output": fake_embed,
            "vector_store_output": vs_mock,
        },
    )
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    # The embedding sub-node was invoked during insert with the input text.
    embed_texts = [t for t, _, _ in embed_calls]
    assert "apple" in embed_texts

    # At least one PineconeInsert step ran with 1 output; at least one
    # PineconeRetrieve step ran with 1 output.
    insert_steps = [
        s for s in result.steps if s.node_name == "PineconeInsert"
    ]
    retrieve_steps = [
        s for s in result.steps if s.node_name == "PineconeRetrieve"
    ]
    assert insert_steps, "expected at least one PineconeInsert run"
    assert retrieve_steps, "expected at least one PineconeRetrieve run"
    assert insert_steps[0].output_count == 1
    assert retrieve_steps[0].output_count == 1

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    # The mock's top-scored doc ("alpha", 0.9) is what the Set sees.
    assert set_step.sample_output[0]["json"]["page"] == "alpha"
