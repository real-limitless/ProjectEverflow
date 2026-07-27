"""Tests for the Summarization Chain executor (chainSummarization).

Covers:

- ``ctx.mocks['chain_output']`` returns the expected ``summary`` per item
- ``ctx.mocks['agent_output']`` is honored as a fallback
- Offline extractive summary picks the first 2 sentences
- Offline extractive summary falls back to the first 500 chars when no
  sentence boundary is present
- Empty / whitespace-only input yields an empty summary
- ``parameters.text`` is evaluated as an n8n expression (``$json.field``)
- Default field name ``$json.text`` is used when ``parameters.text`` is unset
- Connected LM populates the ``model`` field on the output item
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger → chainSummarization (mocked) → Set sees summary
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.llm_agent import exec_chain_summarization


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "s1",
    name: str = "Summarize",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.chainSummarization",
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


# ── 1. chain_output mock returns expected summary per item ──────────────


@pytest.mark.asyncio
async def test_chain_output_mock_returns_summary_per_item() -> None:
    node = _node({"text": "Some long text."})
    ctx = _ctx(mocks={"chain_output": "mocked summary"})
    items = _items([{"a": 1}, {"a": 2}, {"a": 3}])

    result = await exec_chain_summarization(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert len(out_items) == 3
    for it in out_items:
        assert it.json["summary"] == "mocked summary"
        assert it.json["model"] == "gpt-4o-mini"
        assert it.json["sourceLength"] == len("Some long text.")
        # Upstream JSON is preserved
        assert "a" in it.json


@pytest.mark.asyncio
async def test_chain_output_callable_mock_receives_text_and_item() -> None:
    captured: list[tuple[Any, Any]] = []

    def fake(text, item_json):
        captured.append((text, item_json))
        return f"summary-for-{item_json.get('q')}"

    node = _node({"text": "={{ $json.body }}"})
    ctx = _ctx(mocks={"chain_output": fake})
    items = _items([{"q": "alpha", "body": "first doc"}, {"q": "beta", "body": "second doc"}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["summary"] for it in out_items] == [
        "summary-for-alpha",
        "summary-for-beta",
    ]
    assert len(captured) == 2
    assert captured[0][0] == "first doc"
    assert captured[0][1] == {"q": "alpha", "body": "first doc"}


# ── 2. agent_output mock fallback ──────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_output_mock_falls_through_for_summarization() -> None:
    node = _node({"text": "hi"})
    ctx = _ctx(mocks={"agent_output": "via-agent-fallback"})
    items = _items([{"x": 1}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    assert result[0][1][0].json["summary"] == "via-agent-fallback"


# ── 3. Offline extractive summary — first 2 sentences ─────────────────


@pytest.mark.asyncio
async def test_offline_extractive_picks_first_two_sentences() -> None:
    text = (
        "First sentence about weather. "
        "Second sentence about sports. "
        "Third sentence about politics. "
        "Fourth sentence about food."
    )
    node = _node({"text": text})
    ctx = _ctx()  # no mocks
    items = _items([{"x": 1}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["summary"] == "First sentence about weather. Second sentence about sports."
    assert out["sourceLength"] == len(text)


@pytest.mark.asyncio
async def test_offline_extractive_handles_exclamation_and_question_marks() -> None:
    text = "What is the answer? The answer is 42! More detail follows here."
    node = _node({"text": text})
    ctx = _ctx()
    items = _items([{"x": 1}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["summary"] == "What is the answer? The answer is 42!"


# ── 4. Offline extractive — first 500 chars when no sentence boundary ─


@pytest.mark.asyncio
async def test_offline_extractive_falls_back_to_500_chars() -> None:
    # No sentence terminators at all — should be truncated to first 500 chars
    text = "x" + " " * 10
    text = (text * 60)  # 60 * 11 = 660 chars, no '.', '!', or '?'
    assert "." not in text and "!" not in text and "?" not in text
    node = _node({"text": text})
    ctx = _ctx()
    items = _items([{"x": 1}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert len(out["summary"]) == 500
    assert out["summary"] == text[:500]


# ── 5. Empty / whitespace input ──────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_extractive_empty_input_yields_empty_summary() -> None:
    node = _node({"text": ""})
    ctx = _ctx()
    items = _items([{"x": 1}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["summary"] == ""
    assert out["sourceLength"] == 0


@pytest.mark.asyncio
async def test_offline_extractive_whitespace_only_input_yields_empty_summary() -> None:
    node = _node({"text": "   \n  \t  "})
    ctx = _ctx()
    items = _items([{"x": 1}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["summary"] == ""


# ── 6. Text expression evaluation (`$json.text`) ─────────────────────


@pytest.mark.asyncio
async def test_text_expression_evaluates_json_field() -> None:
    text = "Sentence one. Sentence two. Sentence three."
    node = _node({"text": "={{ $json.text }}"})
    ctx = _ctx()  # offline
    items = _items([{"text": text}, {"text": "Other. Things. Here."}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out_items = result[0][1]
    assert out_items[0].json["summary"] == "Sentence one. Sentence two."
    assert out_items[0].json["sourceLength"] == len(text)
    assert out_items[1].json["summary"] == "Other. Things."
    # Upstream fields are preserved
    assert out_items[0].json["text"] == text


@pytest.mark.asyncio
async def test_text_expression_with_mock() -> None:
    node = _node({"text": "={{ $json.body }}"})
    ctx = _ctx(
        mocks={"chain_output": lambda text, ij: f"mocked({len(text)})"}
    )
    items = _items([{"body": "abcdefghij"}, {"body": "x" * 200}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out_items = result[0][1]
    assert out_items[0].json["summary"] == "mocked(10)"
    assert out_items[0].json["sourceLength"] == 10
    assert out_items[1].json["summary"] == "mocked(200)"
    assert out_items[1].json["sourceLength"] == 200


# ── 7. Default field name `text` from item ───────────────────────────


@pytest.mark.asyncio
async def test_default_text_field_used_when_parameter_unset() -> None:
    text = "Default field. Used as text source. Extra sentence."
    node = _node({})  # no parameters.text
    ctx = _ctx()
    items = _items([{"text": text}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["summary"] == "Default field. Used as text source."
    assert out["sourceLength"] == len(text)


# ── 8. Connected LM populates model on output ────────────────────────


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
    node = _node({"text": "hi."})
    ctx = _ctx(
        mocks={"chain_output": "ok"},
        ai_inputs=[lm],
    )
    items = _items([{"x": 1}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    assert "lm1" in ctx.lm_configs
    assert ctx.lm_configs["lm1"]["parameters"]["model"] == "gpt-4o"
    assert result[0][1][0].json["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_offline_path_uses_connected_lm_model() -> None:
    lm = ExecNode(
        id="lm1",
        name="OpenAI",
        type="@n8n/n8n-nodes-langchain.lmChatOpenAi",
        type_version=1,
        parameters={"model": "gpt-4o-mini"},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node({"text": "One. Two. Three."})
    ctx = _ctx(ai_inputs=[lm])  # no mock → offline
    items = _items([{"x": 1}])
    result = await exec_chain_summarization(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["summary"] == "One. Two."
    assert out["model"] == "gpt-4o-mini"


# ── 9. Descriptor registration (CI invariant) ────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.chainSummarization" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.chainSummarization" in SUPPORTED_NODE_TYPES
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.chainSummarization"] == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.chainSummarization"]
    assert desc.executor.endswith(":exec_chain_summarization")
    assert desc.category == "ai"


# ── 10. End-to-end: Manual Trigger → chainSummarization (mocked) → Set ──


def _doc(nodes, connections):
    return {"name": "chain-summarization-e2e", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_summarization_into_set() -> None:
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
                "c1",
                "Summarize",
                "@n8n/n8n-nodes-langchain.chainSummarization",
                {"text": "={{ $json.body }}"},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "summary",
                                "value": "={{ $json.summary }}",
                                "type": "string",
                            },
                            {
                                "name": "model",
                                "value": "={{ $json.model }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Summarize", "type": "main", "index": 0}]]},
            "OpenAI": {
                "ai_languageModel": [
                    [{"node": "Summarize", "type": "ai_languageModel", "index": 0}]
                ]
            },
            "Summarize": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    mocks = {"chain_output": "the consolidated summary"}
    pin_data = {
        "Start": [{"body": "Sentence one. Sentence two. Sentence three."}]
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    chain_step = next(s for s in result.steps if s.node_name == "Summarize")
    assert chain_step.status == "success", chain_step.error
    assert chain_step.output_count == 1
    assert chain_step.sample_output[0]["json"]["summary"] == "the consolidated summary"
    assert chain_step.sample_output[0]["json"]["model"] == "gpt-4o-mini"
    # sourceLength should reflect the input text length
    assert chain_step.sample_output[0]["json"]["sourceLength"] == len(
        "Sentence one. Sentence two. Sentence three."
    )

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["summary"] == "the consolidated summary"
    assert set_step.sample_output[0]["json"]["model"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_end_to_end_summarization_offline_extractive() -> None:
    """No mock → offline extractive summary flows through to downstream Set."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "c1",
                "Summarize",
                "@n8n/n8n-nodes-langchain.chainSummarization",
                {},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "summary",
                                "value": "={{ $json.summary }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Summarize", "type": "main", "index": 0}]]},
            "Summarize": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    pin_data = {
        "Start": [{"text": "Alpha sentence. Beta sentence. Gamma sentence."}]
    }
    engine = WorkflowEngine(doc)  # no mocks
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    chain_step = next(s for s in result.steps if s.node_name == "Summarize")
    assert chain_step.status == "success", chain_step.error
    assert (
        chain_step.sample_output[0]["json"]["summary"]
        == "Alpha sentence. Beta sentence."
    )

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert (
        set_step.sample_output[0]["json"]["summary"]
        == "Alpha sentence. Beta sentence."
    )
