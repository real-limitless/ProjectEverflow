"""Tests for the Retrieval QA Chain executor (chainRetrievalQa).

Covers:

- ``ctx.mocks['chain_output']`` (static) returns the expected ``text`` per item
- ``ctx.mocks['chain_output']`` callable receives ``(question, item, source_docs)``
  and can return per-item answers
- ``ctx.mocks['agent_output']`` is honored as a fallback
- ``ctx.mocks['retriever_output']`` (static list) provides source documents
- ``ctx.mocks['retriever_output']`` callable receives ``(question, item)``
- Offline no-docs branch returns the default n8n message
- Offline with-docs branch returns the snippet (first 100 chars of up to 2 docs)
- Default field name ``$json.chatInput`` is used when ``parameters.question`` unset
- Default field name ``$json.query`` is used when ``parameters.question`` unset
- ``parameters.question`` expression is evaluated
- Connected LM populates the ``model`` field
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger → chainRetrievalQa (mocked) → Set sees
  ``text`` and ``sourceDocuments``
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.llm_agent import exec_chain_retrieval_qa


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "r1",
    name: str = "Retrieval QA",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.chainRetrievalQa",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    mocks: dict[str, Any] | None = None,
    credentials: dict[str, dict[str, Any]] | None = None,
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
        credentials=credentials or {},
        mocks=mocks or {},
    )


def _items(rows: list[dict[str, Any]]):
    from app.services.workflows.items import items_from_json_list

    return items_from_json_list(rows)


# ── 1. chain_output static mock returns expected text per item ─────────


@pytest.mark.asyncio
async def test_chain_output_static_mock_returns_text_per_item() -> None:
    node = _node({"question": "What is X?"})
    ctx = _ctx(mocks={"chain_output": "X is the answer."})
    items = _items([{"a": 1}, {"a": 2}, {"a": 3}])

    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert len(out_items) == 3
    for it in out_items:
        assert it.json["text"] == "X is the answer."
        assert it.json["question"] == "What is X?"
        assert it.json["model"] == "gpt-4o-mini"
        # No source docs → None
        assert it.json["sourceDocuments"] is None
        # Upstream JSON preserved
        assert "a" in it.json


# ── 2. chain_output callable mock receives (question, item, source_docs)


@pytest.mark.asyncio
async def test_chain_output_callable_mock_receives_args() -> None:
    captured: list[tuple[Any, Any, Any]] = []

    def fake(question, item_json, source_docs):
        captured.append((question, item_json, source_docs))
        return f"reply-for-{item_json.get('q')}"

    node = _node({"question": "={{ $json.q }}"})
    ctx = _ctx(
        mocks={
            "chain_output": fake,
            "retriever_output": [{"pageContent": "doc-1", "metadata": {}}],
        }
    )
    items = _items([{"q": "alpha"}, {"q": "beta"}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["text"] for it in out_items] == [
        "reply-for-alpha",
        "reply-for-beta",
    ]
    assert len(captured) == 2
    assert captured[0][0] == "alpha"
    assert captured[0][1] == {"q": "alpha"}
    assert captured[0][2] == [{"pageContent": "doc-1", "metadata": {}}]


# ── 3. agent_output fallback ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_output_mock_falls_through() -> None:
    node = _node({"question": "hi"})
    ctx = _ctx(mocks={"agent_output": "via-agent-fallback"})
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert result[0][1][0].json["text"] == "via-agent-fallback"


@pytest.mark.asyncio
async def test_chain_output_takes_priority_over_agent_output() -> None:
    node = _node({"question": "hi"})
    ctx = _ctx(
        mocks={
            "chain_output": "chain-wins",
            "agent_output": "agent-loses",
        }
    )
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert result[0][1][0].json["text"] == "chain-wins"


# ── 4. retriever_output static (list) provides source documents ────────


@pytest.mark.asyncio
async def test_retriever_output_list_provides_source_docs() -> None:
    docs = [
        {"pageContent": "first chunk of context", "metadata": {"src": "a"}},
        {"pageContent": "second chunk of context", "metadata": {"src": "b"}},
    ]
    captured: list[Any] = []

    def fake(question, item_json, source_docs):
        captured.append(source_docs)
        return f"q={question}-n={len(source_docs)}"

    node = _node({"question": "Q?"})
    ctx = _ctx(
        mocks={
            "chain_output": fake,
            "retriever_output": docs,
        }
    )
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["text"] == "q=Q?-n=2"
    assert out["sourceDocuments"] == docs
    assert captured[0] == docs


@pytest.mark.asyncio
async def test_retriever_output_single_dict_wrapped_as_list() -> None:
    node = _node({"question": "Q?"})
    ctx = _ctx(
        mocks={
            "chain_output": "ok",
            "retriever_output": {"pageContent": "single doc", "metadata": {}},
        }
    )
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["sourceDocuments"] == [
        {"pageContent": "single doc", "metadata": {}}
    ]


# ── 5. retriever_output callable receives (question, item) ────────────


@pytest.mark.asyncio
async def test_retriever_output_callable_receives_question_and_item() -> None:
    captured: list[tuple[Any, Any]] = []

    def fake_retrieve(question, item_json):
        captured.append((question, item_json))
        return [{"pageContent": f"doc-for-{question}", "metadata": {}}]

    node = _node({"question": "={{ $json.q }}"})
    ctx = _ctx(
        mocks={
            "chain_output": lambda q, ij, sd: f"answer:{q}-docs:{len(sd)}",
            "retriever_output": fake_retrieve,
        }
    )
    items = _items([{"q": "alpha"}, {"q": "beta"}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["text"] for it in out_items] == [
        "answer:alpha-docs:1",
        "answer:beta-docs:1",
    ]
    assert captured == [("alpha", {"q": "alpha"}), ("beta", {"q": "beta"})]
    assert out_items[0].json["sourceDocuments"] == [
        {"pageContent": "doc-for-alpha", "metadata": {}}
    ]


# ── 6. Offline: no docs → default message ─────────────────────────────


@pytest.mark.asyncio
async def test_offline_no_docs_returns_default_message() -> None:
    node = _node({"question": "What is X?"})
    ctx = _ctx()  # no mocks
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["text"] == "I don't have enough information to answer that."
    assert out["question"] == "What is X?"
    assert out["sourceDocuments"] is None


# ── 7. Offline: with docs → snippet (first 100 chars of up to 2 docs) ─


@pytest.mark.asyncio
async def test_offline_with_docs_returns_snippet_of_up_to_two() -> None:
    docs = [
        {"pageContent": "A" * 250, "metadata": {}},
        {"pageContent": "B" * 250, "metadata": {}},
        {"pageContent": "C" * 250, "metadata": {}},
    ]
    node = _node({"question": "Q?"})
    ctx = _ctx(mocks={"retriever_output": docs})
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    out = result[0][1][0].json
    # Only first 2 docs contribute; each is truncated to 100 chars.
    assert out["text"] == ("A" * 100) + " " + ("B" * 100)
    assert out["sourceDocuments"] == docs


@pytest.mark.asyncio
async def test_offline_with_one_short_doc_returns_it_unchanged() -> None:
    docs = [{"pageContent": "short doc", "metadata": {}}]
    node = _node({"question": "Q?"})
    ctx = _ctx(mocks={"retriever_output": docs})
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert result[0][1][0].json["text"] == "short doc"


# ── 8. Default field name from $json.chatInput ────────────────────────


@pytest.mark.asyncio
async def test_default_field_name_chat_input_used() -> None:
    node = _node({})  # no parameters.question
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"chatInput": "from chat"}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert result[0][1][0].json["question"] == "from chat"


# ── 9. Default field name from $json.query ─────────────────────────────


@pytest.mark.asyncio
async def test_default_field_name_query_used_when_chat_input_absent() -> None:
    node = _node({})
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"query": "from query"}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert result[0][1][0].json["question"] == "from query"


@pytest.mark.asyncio
async def test_default_field_name_question_used_as_last_resort() -> None:
    node = _node({})
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"question": "from question field"}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert result[0][1][0].json["question"] == "from question field"


@pytest.mark.asyncio
async def test_chat_input_takes_priority_over_query_and_question() -> None:
    node = _node({})
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items(
        [{"chatInput": "ci", "query": "q", "question": "qs"}]
    )
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert result[0][1][0].json["question"] == "ci"


# ── 10. parameters.question expression evaluation ──────────────────────


@pytest.mark.asyncio
async def test_parameters_question_expression_evaluated() -> None:
    node = _node({"question": "={{ $json.q }}"})
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"q": "first question"}, {"q": "second question"}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["question"] for it in out_items] == [
        "first question",
        "second question",
    ]


# ── 11. Connected LM populates model ──────────────────────────────────


@pytest.mark.asyncio
async def test_connected_lm_uses_its_model() -> None:
    lm = ExecNode(
        id="lm1",
        name="OpenAI",
        type="@n8n/n8n-nodes-langchain.lmChatOpenAi",
        type_version=1,
        parameters={"model": "gpt-4o"},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node({"question": "Q?"})
    ctx = _ctx(
        mocks={"chain_output": "ok"},
        ai_inputs=[lm],
    )
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    assert "lm1" in ctx.lm_configs
    assert ctx.lm_configs["lm1"]["parameters"]["model"] == "gpt-4o"
    assert result[0][1][0].json["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_connected_lm_used_on_offline_path_too() -> None:
    lm = ExecNode(
        id="lm1",
        name="OpenAI",
        type="@n8n/n8n-nodes-langchain.lmChatOpenAi",
        type_version=1,
        parameters={"model": "gpt-4o-mini"},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node({"question": "Q?"})
    ctx = _ctx(ai_inputs=[lm])  # no mock
    items = _items([{"x": 1}])
    result = await exec_chain_retrieval_qa(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["text"] == "I don't have enough information to answer that."
    assert out["model"] == "gpt-4o-mini"


# ── 12. Descriptor registration (CI invariant) ───────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.chainRetrievalQa" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.chainRetrievalQa" in SUPPORTED_NODE_TYPES
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.chainRetrievalQa"] == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.chainRetrievalQa"]
    assert desc.executor.endswith(":exec_chain_retrieval_qa")
    assert desc.category == "ai"


# ── 13. End-to-end: Manual Trigger → chainRetrievalQa (mocked) → Set ─


def _doc(nodes, connections):
    return {"name": "chain-retrieval-qa-e2e", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_retrieval_qa_into_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "lm1",
                "OpenAI",
                "@n8n/n8n-nodes-langchain.lmChatOpenAi",
                {"model": "gpt-4o-mini"},
            ),
            _n(
                "rv1",
                "Vector Store",
                "@n8n/n8n-nodes-langchain.vectorStoreInMemory",
                {},
            ),
            _n(
                "c1",
                "Retrieval QA",
                "@n8n/n8n-nodes-langchain.chainRetrievalQa",
                {"question": "={{ $json.q }}"},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "answer",
                                "value": "={{ $json.text }}",
                                "type": "string",
                            },
                            {
                                "name": "firstDoc",
                                "value": "={{ $json.sourceDocuments[0].pageContent }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "Retrieval QA", "type": "main", "index": 0}]]
            },
            "OpenAI": {
                "ai_languageModel": [
                    [
                        {
                            "node": "Retrieval QA",
                            "type": "ai_languageModel",
                            "index": 0,
                        }
                    ]
                ]
            },
            "Vector Store": {
                "ai_retriever": [
                    [{"node": "Retrieval QA", "type": "ai_retriever", "index": 0}]
                ]
            },
            "Retrieval QA": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    mocks = {
        "chain_output": "the answer is 42",
        "retriever_output": [
            {"pageContent": "context chunk one", "metadata": {}},
            {"pageContent": "context chunk two", "metadata": {}},
        ],
    }
    pin_data = {"Start": [{"q": "what is the answer?"}]}
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    chain_step = next(s for s in result.steps if s.node_name == "Retrieval QA")
    assert chain_step.status == "success", chain_step.error
    assert chain_step.output_count == 1
    out_json = chain_step.sample_output[0]["json"]
    assert out_json["text"] == "the answer is 42"
    assert out_json["question"] == "what is the answer?"
    assert out_json["model"] == "gpt-4o-mini"
    assert out_json["sourceDocuments"] == mocks["retriever_output"]

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["answer"] == "the answer is 42"
    assert (
        set_step.sample_output[0]["json"]["firstDoc"] == "context chunk one"
    )
