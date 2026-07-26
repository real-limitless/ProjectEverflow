"""Tests for the OpenAI Embeddings executor (embeddingsOpenAi).

Covers:

- ``ctx.mocks['embeddings_output']`` returning a ``list[float]``
- ``ctx.mocks['embeddings_output']`` as a callable receiving
  ``(text, item, model)``
- ``parameters.stripNewLines=True`` strips ``\\n`` from the resolved text
- ``parameters.stripNewLines=False`` preserves ``\\n``
- ``parameters.text`` is evaluated as an n8n expression when leading ``=``
- Offline: ``text-embedding-3-small`` produces a 1536-dim vector
- Offline: ``text-embedding-3-large`` produces a 3072-dim vector
- Offline: ``text-embedding-ada-002`` produces a 1536-dim vector
- Offline: same text + model yields identical embeddings (determinism)
- Offline: different text yields different embeddings
- Default text source falls back to ``$json.text`` then ``$json.pageContent``
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger → embeddingsOpenAi → Set sees ``embedding``,
  ``model``, ``dimensions``
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes.llm_agent import exec_embeddings_openai


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "e1",
    name: str = "Embeddings",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.embeddingsOpenAi",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    mocks: dict[str, Any] | None = None,
    ai_inputs: list[ExecNode] | None = None,
) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: list(ai_inputs or [])
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(  # type: ignore[arg-type]
        graph=g,
        mocks=mocks or {},
    )


def _items(rows: list[dict[str, Any]] | None = None):
    return items_from_json_list(rows or [])


# ── 1. embeddings_output mock returns list[float] ─────────────────────


@pytest.mark.asyncio
async def test_embeddings_output_mock_returns_list_of_floats() -> None:
    node = _node({})
    ctx = _ctx(
        mocks={"embeddings_output": [0.1, 0.2, 0.3, 0.4, 0.5]}
    )
    items = _items([{"text": "alpha"}, {"text": "beta"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert len(out_items) == 2
    # The mock is static; both items get the same vector, which is the
    # mock value right-padded with 0.0 to the model dimension (1536).
    assert out_items[0].json["embedding"] == out_items[1].json["embedding"]
    assert out_items[0].json["embedding"][:5] == [0.1, 0.2, 0.3, 0.4, 0.5]
    assert out_items[0].json["embedding"][5] == 0.0
    assert len(out_items[0].json["embedding"]) == 1536
    # Model + dimensions still come from the node
    assert out_items[0].json["model"] == "text-embedding-3-small"
    assert out_items[0].json["dimensions"] == 1536


@pytest.mark.asyncio
async def test_embeddings_output_mock_pads_and_truncates_to_dimensions() -> None:
    """A short mock value is right-padded with 0.0; an over-long one is truncated."""
    node = _node({"model": "text-embedding-3-small"})  # 1536 dims
    ctx = _ctx(mocks={"embeddings_output": [0.1, 0.2]})
    items = _items([{"text": "x"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out = result[0][1][0]
    assert len(out.json["embedding"]) == 1536
    assert out.json["embedding"][:2] == [0.1, 0.2]
    assert out.json["embedding"][2] == 0.0
    assert out.json["embedding"][-1] == 0.0


# ── 2. embeddings_output callable mock receives (text, item, model) ───


@pytest.mark.asyncio
async def test_embeddings_output_callable_mock_receives_text_item_model() -> None:
    captured: list[tuple[Any, Any, Any]] = []

    def fake(text, item, model):
        captured.append((text, item, model))
        # Encode a different pattern per call so we can prove each item
        # got its own embedding (right-padded with 0.0 to 1536 dims).
        idx = len(captured)
        return [float(idx), float(idx) + 0.5, float(idx) + 0.25]

    node = _node({"model": "text-embedding-3-small"})
    ctx = _ctx(mocks={"embeddings_output": fake})
    items = _items([{"text": "first"}, {"text": "second"}, {"text": "third"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(captured) == 3
    # First call: text = "first" (default $json.text), model = configured value
    assert captured[0][0] == "first"
    assert captured[0][1].json == {"text": "first"}
    assert captured[0][2] == "text-embedding-3-small"
    assert captured[1][0] == "second"
    assert captured[2][0] == "third"
    # Each item got its own vector, right-padded with 0.0 to 1536 dims
    assert out_items[0].json["embedding"][:3] == [1.0, 1.5, 1.25]
    assert out_items[0].json["embedding"][3] == 0.0
    assert out_items[1].json["embedding"][:3] == [2.0, 2.5, 2.25]
    assert out_items[1].json["embedding"][3] == 0.0
    assert out_items[2].json["embedding"][:3] == [3.0, 3.5, 3.25]
    assert out_items[2].json["embedding"][3] == 0.0
    # And all three are full-length
    for it in out_items:
        assert len(it.json["embedding"]) == 1536


# ── 3. stripNewLines=True strips \n ───────────────────────────────────


@pytest.mark.asyncio
async def test_strip_new_lines_default_strips_newlines() -> None:
    captured: list[str] = []

    def fake(text, item, model):
        captured.append(text)
        return [0.0]

    node = _node({})  # default stripNewLines=True
    ctx = _ctx(mocks={"embeddings_output": fake})
    items = _items([{"text": "line one\nline two\nline three"}])

    await exec_embeddings_openai(node, items, ctx=ctx)
    assert captured == ["line one line two line three"]


@pytest.mark.asyncio
async def test_strip_new_lines_false_preserves_newlines() -> None:
    captured: list[str] = []

    def fake(text, item, model):
        captured.append(text)
        return [0.0]

    node = _node({"stripNewLines": False})
    ctx = _ctx(mocks={"embeddings_output": fake})
    items = _items([{"text": "line one\nline two"}])

    await exec_embeddings_openai(node, items, ctx=ctx)
    assert captured == ["line one\nline two"]


@pytest.mark.asyncio
async def test_strip_new_lines_true_explicit_strips_newlines() -> None:
    captured: list[str] = []

    def fake(text, item, model):
        captured.append(text)
        return [0.0]

    node = _node({"stripNewLines": True})
    ctx = _ctx(mocks={"embeddings_output": fake})
    items = _items([{"text": "a\nb\nc"}])

    await exec_embeddings_openai(node, items, ctx=ctx)
    assert captured == ["a b c"]


# ── 4. parameters.text expression evaluation ──────────────────────────


@pytest.mark.asyncio
async def test_parameters_text_as_expression_evaluates_json_field() -> None:
    captured: list[str] = []

    def fake(text, item, model):
        captured.append(text)
        return [0.0]

    node = _node({"text": "={{ $json.body }}"})
    ctx = _ctx(mocks={"embeddings_output": fake})
    items = _items(
        [
            {"text": "ignored", "body": "from-body-1"},
            {"text": "ignored", "body": "from-body-2"},
        ]
    )

    await exec_embeddings_openai(node, items, ctx=ctx)
    assert captured == ["from-body-1", "from-body-2"]


@pytest.mark.asyncio
async def test_parameters_text_as_field_name_selects_field() -> None:
    captured: list[str] = []

    def fake(text, item, model):
        captured.append(text)
        return [0.0]

    node = _node({"text": "body"})
    ctx = _ctx(mocks={"embeddings_output": fake})
    items = _items([{"body": "from-body"}])

    await exec_embeddings_openai(node, items, ctx=ctx)
    assert captured == ["from-body"]


@pytest.mark.asyncio
async def test_default_text_field_used_when_parameters_text_unset() -> None:
    captured: list[str] = []

    def fake(text, item, model):
        captured.append(text)
        return [0.0]

    node = _node({})
    ctx = _ctx(mocks={"embeddings_output": fake})
    items = _items([{"text": "from-text"}])

    await exec_embeddings_openai(node, items, ctx=ctx)
    assert captured == ["from-text"]


@pytest.mark.asyncio
async def test_default_page_content_field_used_when_text_missing() -> None:
    captured: list[str] = []

    def fake(text, item, model):
        captured.append(text)
        return [0.0]

    node = _node({})
    ctx = _ctx(mocks={"embeddings_output": fake})
    items = _items([{"pageContent": "from-page"}])

    await exec_embeddings_openai(node, items, ctx=ctx)
    assert captured == ["from-page"]


# ── 5. Offline: text-embedding-3-small → 1536 dims ─────────────────────


@pytest.mark.asyncio
async def test_offline_text_embedding_3_small_produces_1536_dims() -> None:
    node = _node({"model": "text-embedding-3-small"})
    ctx = _ctx()  # no mocks
    items = _items([{"text": "hello"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out = result[0][1][0]
    assert out.json["model"] == "text-embedding-3-small"
    assert out.json["dimensions"] == 1536
    embedding = out.json["embedding"]
    assert isinstance(embedding, list)
    assert len(embedding) == 1536
    # All values normalised to [-1, 1]
    for v in embedding:
        assert isinstance(v, float)
        assert -1.0 <= v <= 1.0


# ── 6. Offline: text-embedding-3-large → 3072 dims ────────────────────


@pytest.mark.asyncio
async def test_offline_text_embedding_3_large_produces_3072_dims() -> None:
    node = _node({"model": "text-embedding-3-large"})
    ctx = _ctx()
    items = _items([{"text": "hello"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out = result[0][1][0]
    assert out.json["model"] == "text-embedding-3-large"
    assert out.json["dimensions"] == 3072
    assert len(out.json["embedding"]) == 3072


# ── 7. Offline: text-embedding-ada-002 → 1536 dims ────────────────────


@pytest.mark.asyncio
async def test_offline_text_embedding_ada_002_produces_1536_dims() -> None:
    node = _node({"model": "text-embedding-ada-002"})
    ctx = _ctx()
    items = _items([{"text": "hello"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out = result[0][1][0]
    assert out.json["model"] == "text-embedding-ada-002"
    assert out.json["dimensions"] == 1536
    assert len(out.json["embedding"]) == 1536


# ── 8. Offline: default model is text-embedding-3-small ──────────────


@pytest.mark.asyncio
async def test_offline_default_model_is_text_embedding_3_small() -> None:
    node = _node({})  # no model parameter
    ctx = _ctx()
    items = _items([{"text": "x"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out = result[0][1][0]
    assert out.json["model"] == "text-embedding-3-small"
    assert out.json["dimensions"] == 1536


# ── 9. Offline: determinism — same inputs yield same vector ───────────


@pytest.mark.asyncio
async def test_offline_same_text_and_model_yields_identical_embedding() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{"text": "deterministic"}])

    first = await exec_embeddings_openai(node, items, ctx=ctx)
    second = await exec_embeddings_openai(node, items, ctx=ctx)
    assert first[0][1][0].json["embedding"] == second[0][1][0].json["embedding"]


@pytest.mark.asyncio
async def test_offline_determinism_across_separate_items() -> None:
    """Two items with the same text get the same embedding (same model)."""
    node = _node({})
    ctx = _ctx()
    items = _items([{"text": "same"}, {"text": "same"}, {"text": "same"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    embeddings = [it.json["embedding"] for it in result[0][1]]
    assert embeddings[0] == embeddings[1] == embeddings[2]


# ── 10. Offline: different text yields different embedding ────────────


@pytest.mark.asyncio
async def test_offline_different_text_yields_different_embedding() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{"text": "alpha"}, {"text": "beta"}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    e1 = result[0][1][0].json["embedding"]
    e2 = result[0][1][1].json["embedding"]
    assert e1 != e2


@pytest.mark.asyncio
async def test_offline_different_model_yields_different_embedding() -> None:
    """Same text under two different model names should hash differently."""
    node_small = _node({"model": "text-embedding-3-small"})
    node_large = _node({"model": "text-embedding-3-large"})
    ctx = _ctx()
    items = _items([{"text": "same-text"}])

    r1 = await exec_embeddings_openai(node_small, items, ctx=ctx)
    r2 = await exec_embeddings_openai(node_large, items, ctx=ctx)
    e1 = r1[0][1][0].json["embedding"]
    e2 = r2[0][1][0].json["embedding"]
    # Compare the first 1536 elements (the common prefix of both)
    assert e1[:1536] != e2[:1536]


# ── 11. Upstream JSON is preserved on output items ─────────────────────


@pytest.mark.asyncio
async def test_upstream_json_is_merged_into_output() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{"text": "x", "id": "row-1", "extra": 42}])

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out = result[0][1][0]
    assert out.json["id"] == "row-1"
    assert out.json["extra"] == 42
    assert "embedding" in out.json
    assert "model" in out.json
    assert "dimensions" in out.json


# ── 12. Empty input text is handled (empty string → 1536-dim vector) ─


@pytest.mark.asyncio
async def test_offline_empty_text_produces_well_shaped_vector() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{}])  # no text/pageContent → ""

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out = result[0][1][0]
    assert len(out.json["embedding"]) == 1536
    # Deterministic: re-running yields the same vector
    again = await exec_embeddings_openai(node, items, ctx=ctx)
    assert out.json["embedding"] == again[0][1][0].json["embedding"]


# ── 13. Multiple items all produce one output item each ───────────────


@pytest.mark.asyncio
async def test_multiple_inputs_produce_one_output_each() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items(
        [{"text": "a"}, {"text": "b"}, {"text": "c"}, {"text": "d"}]
    )

    result = await exec_embeddings_openai(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 4
    for it in out_items:
        assert "embedding" in it.json
        assert it.json["model"] == "text-embedding-3-small"
        assert it.json["dimensions"] == 1536


# ── 14. Descriptor registration (CI invariant) ───────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.embeddingsOpenAi" in REGISTRY
    assert (
        "@n8n/n8n-nodes-langchain.embeddingsOpenAi" in SUPPORTED_NODE_TYPES
    )
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.embeddingsOpenAi"]
        == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.embeddingsOpenAi"]
    assert desc.executor.endswith(":exec_embeddings_openai")
    assert desc.category == "ai"


# ── 15. End-to-end: Manual Trigger → embeddingsOpenAi → Set ────────────


def _doc(nodes, connections):
    return {
        "name": "embeddings-openai-e2e",
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
async def test_end_to_end_manual_embeddings_openai_into_set() -> None:
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
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "vec",
                                "value": "={{ $json.embedding }}",
                                "type": "string",
                            },
                            {
                                "name": "model",
                                "value": "={{ $json.model }}",
                                "type": "string",
                            },
                            {
                                "name": "dims",
                                "value": "={{ $json.dimensions }}",
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
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    pin_data = {"Start": [{"text": "the quick brown fox"}]}
    engine = WorkflowEngine(doc)  # offline deterministic
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    embed_step = next(s for s in result.steps if s.node_name == "Embeddings")
    assert embed_step.status == "success", embed_step.error
    assert embed_step.output_count == 1
    sample = embed_step.sample_output[0]["json"]
    assert isinstance(sample["embedding"], list)
    assert len(sample["embedding"]) == 1536
    assert sample["model"] == "text-embedding-3-small"
    assert sample["dimensions"] == 1536

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    set_json = set_step.sample_output[0]["json"]
    assert set_json["model"] == "text-embedding-3-small"
    assert set_json["dims"] == 1536
    assert isinstance(set_json["vec"], list)
    assert len(set_json["vec"]) == 1536


@pytest.mark.asyncio
async def test_end_to_end_embeddings_with_mocked_output() -> None:
    """A callable mock flows through the full pipeline into the Set node."""
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
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "first",
                                "value": "={{ $json.embedding[0] }}",
                                "type": "number",
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
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )

    def fake(text, item, model):
        return [0.25, 0.5, 0.75]

    pin_data = {"Start": [{"text": "anything"}]}
    engine = WorkflowEngine(doc, mocks={"embeddings_output": fake})
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    # The mock returned [0.25, 0.5, 0.75] which is right-padded with 0.0 to 1536
    # but $json.embedding[0] is the first element.
    assert set_step.sample_output[0]["json"]["first"] == 0.25
