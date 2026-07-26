"""Tests for the 3 clean-room text-AI executors.

Covers:

- ``informationExtraction`` — structured field extraction
- ``textClassifier``        — single-label classification
- ``sentimentAnalysis``     — sentiment label + confidence

Each section tests:

- Mock-driven behavior (callable or static value)
- Offline fallback (no mock)
- ``$json.<field>`` default when parameter missing
- Per-tool expression / parameter evaluation
- Descriptor registration (CI invariant)
- One end-to-end run that exercises the real engine wiring
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.text_ai import (
    exec_information_extraction,
    exec_sentiment_analysis,
    exec_text_classifier,
)


# ── Shared helpers ────────────────────────────────────────────────────


def _node(
    type_: str,
    params: dict[str, Any] | None,
    *,
    id_: str = "t1",
    name: str = "TextAI",
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


# ── 1. informationExtraction ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_extraction_mock_returns_dict() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.informationExtraction",
        {
            "text": "={{ $json.text }}",
            "schema": {"name": "person name", "age": "numeric age"},
        },
    )
    ctx = _ctx(
        mocks={
            "extraction_output": {
                "name": "Alice",
                "age": 30,
            }
        }
    )
    out = await exec_information_extraction(node, _items([{"text": "Alice is 30"}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["text"] == "Alice is 30"
    assert j["extracted"] == {"name": "Alice", "age": 30}
    assert j["schema"] == {"name": "person name", "age": "numeric age"}
    assert j["source"] == "mock"


@pytest.mark.asyncio
async def test_extraction_callable_mock_receives_args() -> None:
    captured: list[tuple[Any, ...]] = []

    def fake(text, item, params, ctx):
        captured.append((text, item, params))
        return {"name": "from-callable"}

    node = _node(
        "@n8n/n8n-nodes-langchain.informationExtraction",
        {"text": "hello", "schema": {"name": "x"}},
    )
    ctx = _ctx(mocks={"extraction_output": fake})
    out = await exec_information_extraction(node, _items([{"k": "v"}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["extracted"] == {"name": "from-callable"}
    assert captured[0][0] == "hello"
    assert captured[0][1].json == {"k": "v"}
    assert captured[0][2] == {"text": "hello", "schema": {"name": "x"}}


@pytest.mark.asyncio
async def test_extraction_offline_stub_dict() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.informationExtraction",
        {
            "text": "Some long text",
            "schema": {"name": "person", "city": "location"},
        },
    )
    ctx = _ctx()
    out = await exec_information_extraction(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "offline"
    assert j["extracted"] == {
        "name": "extracted_name",
        "city": "extracted_city",
    }
    assert j["schema"] == {"name": "person", "city": "location"}


@pytest.mark.asyncio
async def test_extraction_schema_from_list_of_field_names() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.informationExtraction",
        {"text": "x", "schema": ["title", "body"]},
    )
    ctx = _ctx()
    out = await exec_information_extraction(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["schema"] == {"title": "title", "body": "body"}
    assert j["extracted"] == {"title": "extracted_title", "body": "extracted_body"}


@pytest.mark.asyncio
async def test_extraction_default_categories_when_no_schema() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.informationExtraction",
        {"text": "anything"},
    )
    ctx = _ctx()
    out = await exec_information_extraction(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["schema"] == {}
    assert j["extracted"] == {}
    assert j["source"] == "offline"


@pytest.mark.asyncio
async def test_extraction_default_from_json_text() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.informationExtraction",
        {"schema": {"x": "y"}},
    )
    ctx = _ctx(mocks={"extraction_output": {"x": "got-text"}})
    out = await exec_information_extraction(node, _items([{"text": "from-json"}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["text"] == "from-json"
    assert j["extracted"] == {"x": "got-text"}


# ── 2. textClassifier ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classifier_mock_returns_string() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.textClassifier",
        {"text": "great service", "categories": ["happy", "sad"]},
    )
    ctx = _ctx(mocks={"classification_output": "happy"})
    out = await exec_text_classifier(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["category"] == "happy"
    assert j["source"] == "mock"
    assert j["categories"] == ["happy", "sad"]
    assert j["confidence"] == 0.8


@pytest.mark.asyncio
async def test_classifier_callable_mock() -> None:
    captured: list[tuple[Any, ...]] = []

    def fake(text, item, params, ctx):
        captured.append((text, item, params))
        return "neutral"

    node = _node(
        "@n8n/n8n-nodes-langchain.textClassifier",
        {"text": "anything"},
    )
    ctx = _ctx(mocks={"classification_output": fake})
    out = await exec_text_classifier(node, _items([{"k": 1}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["category"] == "neutral"
    assert captured[0][0] == "anything"
    assert captured[0][1].json == {"k": 1}


@pytest.mark.asyncio
async def test_classifier_offline_positive() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.textClassifier",
        {"text": "this is great"},
    )
    ctx = _ctx()
    out = await exec_text_classifier(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["category"] == "positive"
    assert j["source"] == "offline"
    assert j["categories"] == ["positive", "negative", "neutral"]


@pytest.mark.asyncio
async def test_classifier_offline_negative() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.textClassifier",
        {"text": "absolutely terrible experience"},
    )
    ctx = _ctx()
    out = await exec_text_classifier(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["category"] == "negative"
    assert j["source"] == "offline"


@pytest.mark.asyncio
async def test_classifier_offline_neutral() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.textClassifier",
        {"text": "it rained on tuesday"},
    )
    ctx = _ctx()
    out = await exec_text_classifier(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["category"] == "neutral"
    assert j["source"] == "offline"


@pytest.mark.asyncio
async def test_classifier_custom_categories_param() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.textClassifier",
        {
            "text": "great",
            "categories": ["spam", "ham"],
        },
    )
    ctx = _ctx()
    out = await exec_text_classifier(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    # The custom categories list is reflected in the output; "positive" is
    # appended because the offline heuristic returned a non-listed value.
    assert j["categories"][:2] == ["spam", "ham"]
    assert "positive" in j["categories"]


@pytest.mark.asyncio
async def test_classifier_default_from_json_text() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.textClassifier",
        {},
    )
    ctx = _ctx()
    out = await exec_text_classifier(node, _items([{"text": "love it"}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["text"] == "love it"
    assert j["category"] == "positive"


# ── 3. sentimentAnalysis ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sentiment_mock_returns_dict() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.sentimentAnalysis",
        {"text": "anything"},
    )
    ctx = _ctx(
        mocks={
            "sentiment_output": {"label": "positive", "confidence": 0.95}
        }
    )
    out = await exec_sentiment_analysis(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["label"] == "positive"
    assert j["confidence"] == 0.95
    assert j["source"] == "mock"


@pytest.mark.asyncio
async def test_sentiment_mock_returns_string_label() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.sentimentAnalysis",
        {"text": "anything"},
    )
    ctx = _ctx(mocks={"sentiment_output": "negative"})
    out = await exec_sentiment_analysis(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["label"] == "negative"
    assert j["confidence"] == 0.8
    assert j["source"] == "mock"


@pytest.mark.asyncio
async def test_sentiment_callable_mock() -> None:
    captured: list[tuple[Any, ...]] = []

    def fake(text, item, params, ctx):
        captured.append((text, item, params))
        return {"label": "neutral", "confidence": 0.42}

    node = _node(
        "@n8n/n8n-nodes-langchain.sentimentAnalysis",
        {"text": "weather talk"},
    )
    ctx = _ctx(mocks={"sentiment_output": fake})
    out = await exec_sentiment_analysis(node, _items([{"k": 1}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["label"] == "neutral"
    assert j["confidence"] == 0.42
    assert captured[0][0] == "weather talk"
    assert captured[0][1].json == {"k": 1}


@pytest.mark.asyncio
async def test_sentiment_offline_positive() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.sentimentAnalysis",
        {"text": "I love this"},
    )
    ctx = _ctx()
    out = await exec_sentiment_analysis(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["label"] == "positive"
    assert j["confidence"] == 0.8
    assert j["source"] == "offline"


@pytest.mark.asyncio
async def test_sentiment_offline_negative() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.sentimentAnalysis",
        {"text": "this is awful"},
    )
    ctx = _ctx()
    out = await exec_sentiment_analysis(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["label"] == "negative"
    assert j["confidence"] == 0.8
    assert j["source"] == "offline"


@pytest.mark.asyncio
async def test_sentiment_offline_neutral() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.sentimentAnalysis",
        {"text": "the sky is blue"},
    )
    ctx = _ctx()
    out = await exec_sentiment_analysis(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["label"] == "neutral"
    assert j["confidence"] == 0.5
    assert j["source"] == "offline"


@pytest.mark.asyncio
async def test_sentiment_default_from_json_text() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.sentimentAnalysis",
        {},
    )
    ctx = _ctx()
    out = await exec_sentiment_analysis(node, _items([{"text": "hate it"}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["text"] == "hate it"
    assert j["label"] == "negative"


# ── 4. Connected LM model propagation ────────────────────────────────


@pytest.mark.asyncio
async def test_classifier_uses_connected_lm_model() -> None:
    lm = ExecNode(
        id="lm1",
        name="OpenAI",
        type="@n8n/n8n-nodes-langchain.lmChatOpenAi",
        type_version=1,
        parameters={"model": "gpt-4o"},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node(
        "@n8n/n8n-nodes-langchain.textClassifier",
        {"text": "great"},
    )
    ctx = _ctx(
        mocks={"classification_output": "positive"},
        ai_inputs=[lm],
    )
    out = await exec_text_classifier(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["model"] == "gpt-4o"
    assert "lm1" in ctx.lm_configs


# ── 5. Descriptor registration (CI invariant) ────────────────────────


@pytest.mark.parametrize(
    "n8n_type,exec_name",
    [
        (
            "@n8n/n8n-nodes-langchain.informationExtraction",
            "exec_information_extraction",
        ),
        (
            "@n8n/n8n-nodes-langchain.textClassifier",
            "exec_text_classifier",
        ),
        (
            "@n8n/n8n-nodes-langchain.sentimentAnalysis",
            "exec_sentiment_analysis",
        ),
    ],
)
def test_descriptor_is_registered(n8n_type: str, exec_name: str) -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert n8n_type in REGISTRY, f"{n8n_type} missing from REGISTRY"
    assert n8n_type in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES[n8n_type] == "ai"
    desc = REGISTRY[n8n_type]
    assert desc.executor.endswith(f":{exec_name}")
    assert desc.category == "ai"


# ── 6. End-to-end: Manual Trigger → textClassifier (mock) → Set ────


def _doc(nodes, connections):
    return {"name": "text-ai-e2e", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_classifier_into_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "c1",
                "Classifier",
                "@n8n/n8n-nodes-langchain.textClassifier",
                {"text": "={{ $json.text }}"},
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
                                "value": "={{ $json.category }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Classifier", "type": "main", "index": 0}]]},
            "Classifier": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    mocks = {"classification_output": "positive"}
    pin_data = {"Start": [{"text": "great service"}]}
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    clf_step = next(s for s in result.steps if s.node_name == "Classifier")
    assert clf_step.status == "success", clf_step.error
    assert clf_step.output_count == 1
    assert clf_step.sample_output[0]["json"]["category"] == "positive"
    assert clf_step.sample_output[0]["json"]["source"] == "mock"

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["result"] == "positive"
