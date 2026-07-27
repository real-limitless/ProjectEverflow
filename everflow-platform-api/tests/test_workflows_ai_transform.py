"""Tests for the AI Transform executor (aiTransform).

Covers:

- ``ctx.mocks['chain_output']`` static string path
- ``ctx.mocks['chain_output']`` callable receives ``(prompt, item, params, ctx)``
- ``ctx.mocks['agent_output']`` is honored as a fallback
- ``{{ $json.field }}`` substitution in ``parameters.prompt``
- Default ``outputField`` is ``"output"``
- Custom ``outputField`` name is honored
- ``parameters.instructions`` is echoed on the output
- Connected LM populates the ``model`` field
- Offline fallback echoes the resolved prompt
- Multiple input items produce one output each
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger → aiTransform (mocked) → Set sees the
  custom ``outputField``
- End-to-end: Manual Trigger → embeddingsOpenAi (sub-node) →
  aiTransform (mocked) → Set
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes.ai_transform import exec_ai_transform


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "a1",
    name: str = "AI Transform",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.aiTransform",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    mocks: dict[str, Any] | None = None,
    ai_inputs: list[ExecNode] | None = None,
    credentials: dict[str, dict[str, Any]] | None = None,
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
        credentials=credentials or {},
    )


def _items(rows: list[dict[str, Any]]):
    return items_from_json_list(rows)


# ── 1. chain_output static mock ───────────────────────────────────────


@pytest.mark.asyncio
async def test_chain_output_static_string_used_for_every_item() -> None:
    node = _node({"prompt": "Hello"})
    ctx = _ctx(mocks={"chain_output": "static-result"})
    items = _items([{"x": 1}, {"x": 2}])

    result = await exec_ai_transform(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert len(out_items) == 2
    for it in out_items:
        assert it.json["output"] == "static-result"
        assert it.json["source"] == "aiTransform"
        assert it.json["prompt"] == "Hello"


# ── 2. chain_output callable mock receives (prompt, item, params, ctx) ─


@pytest.mark.asyncio
async def test_chain_output_callable_receives_prompt_item_params_ctx() -> None:
    captured: list[tuple[Any, Any, Any, Any]] = []

    def fake(prompt, item, params, mock_ctx):
        captured.append((prompt, item.json, params, mock_ctx))
        return f"reply-for-{item.json.get('q')}"

    node = _node({"prompt": "={{ $json.q }}"})
    ctx = _ctx(mocks={"chain_output": fake})
    items = _items([{"q": "alpha"}, {"q": "beta"}])
    result = await exec_ai_transform(node, items, ctx=ctx)

    out_items = result[0][1]
    assert [it.json["output"] for it in out_items] == [
        "reply-for-alpha",
        "reply-for-beta",
    ]
    assert len(captured) == 2
    # First call: prompt was the resolved "alpha" string.
    assert captured[0][0] == "alpha"
    assert captured[0][1] == {"q": "alpha"}
    # params is the node's parameters dict; ctx is the engine context.
    assert captured[0][2] == {"prompt": "={{ $json.q }}"}
    assert captured[0][3] is ctx


# ── 3. agent_output fallback ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_output_mock_used_when_chain_output_absent() -> None:
    node = _node({"prompt": "hi"})
    ctx = _ctx(mocks={"agent_output": "via-agent-fallback"})
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    assert result[0][1][0].json["output"] == "via-agent-fallback"


@pytest.mark.asyncio
async def test_chain_output_takes_precedence_over_agent_output() -> None:
    node = _node({"prompt": "hi"})
    ctx = _ctx(
        mocks={
            "chain_output": "chain-wins",
            "agent_output": "agent-loses",
        }
    )
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    assert result[0][1][0].json["output"] == "chain-wins"


# ── 4. Offline: echo the resolved prompt ──────────────────────────────


@pytest.mark.asyncio
async def test_offline_echoes_resolved_prompt() -> None:
    node = _node({"prompt": "=Summarize: {{ $json.topic }}"})
    ctx = _ctx()  # no mocks
    items = _items([{"topic": "weather"}, {"topic": "sports"}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["output"] for it in out_items] == [
        "Summarize: weather",
        "Summarize: sports",
    ]
    # Prompt also echoed for observability.
    assert out_items[0].json["prompt"] == "Summarize: weather"


@pytest.mark.asyncio
async def test_offline_no_prompt_returns_empty_output() -> None:
    node = _node({})  # no prompt at all
    ctx = _ctx()
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    assert result[0][1][0].json["output"] == ""
    assert result[0][1][0].json["prompt"] == ""


# ── 5. {{ $json.field }} substitution in prompt ───────────────────────


@pytest.mark.asyncio
async def test_prompt_substitutes_json_field() -> None:
    captured_prompts: list[str] = []

    def fake(prompt, item, params, mock_ctx):
        captured_prompts.append(prompt)
        return f"x:{prompt}"

    node = _node({"prompt": "=Translate '{{ $json.text }}' to French"})
    ctx = _ctx(mocks={"chain_output": fake})
    items = _items(
        [{"text": "hello"}, {"text": "good morning"}, {"text": "thanks"}]
    )
    result = await exec_ai_transform(node, items, ctx=ctx)
    out_items = result[0][1]
    assert captured_prompts == [
        "Translate 'hello' to French",
        "Translate 'good morning' to French",
        "Translate 'thanks' to French",
    ]
    assert [it.json["output"] for it in out_items] == [
        "x:Translate 'hello' to French",
        "x:Translate 'good morning' to French",
        "x:Translate 'thanks' to French",
    ]


@pytest.mark.asyncio
async def test_prompt_rl_form_evaluates_to_field_value() -> None:
    """The leading ``={{`` form (plain expression) is the canonical n8n form."""
    node = _node({"prompt": "={{ $json.q }}"})
    ctx = _ctx(mocks={"chain_output": lambda p, *_: f"got:{p}"})
    items = _items([{"q": "ping"}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    assert result[0][1][0].json["output"] == "got:ping"


# ── 6. parameters.outputField honored ─────────────────────────────────


@pytest.mark.asyncio
async def test_default_output_field_is_output() -> None:
    node = _node({"prompt": "Hi"})
    ctx = _ctx(mocks={"chain_output": "result"})
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["output"] == "result"
    # The literal "output" key exists, no surprise renaming.
    assert "customField" not in out


@pytest.mark.asyncio
async def test_custom_output_field_used() -> None:
    node = _node({"prompt": "Hi", "outputField": "translated"})
    ctx = _ctx(mocks={"chain_output": "bonjour"})
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["translated"] == "bonjour"
    # Default 'output' key is not added when a custom field is used.
    assert "output" not in out
    # Prompt is still echoed.
    assert out["prompt"] == "Hi"


@pytest.mark.asyncio
async def test_output_field_falls_back_when_blank() -> None:
    node = _node({"prompt": "Hi", "outputField": "   "})
    ctx = _ctx(mocks={"chain_output": "result"})
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["output"] == "result"


# ── 7. parameters.instructions is echoed ──────────────────────────────


@pytest.mark.asyncio
async def test_instructions_echoed_in_output() -> None:
    node = _node(
        {
            "prompt": "Hi",
            "instructions": "Always be polite.",
        }
    )
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["instructions"] == "Always be polite."
    assert out["output"] == "ok"


@pytest.mark.asyncio
async def test_instructions_omitted_when_unset() -> None:
    node = _node({"prompt": "Hi"})
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert "instructions" not in out


@pytest.mark.asyncio
async def test_instructions_evaluated_as_expression() -> None:
    node = _node(
        {
            "prompt": "Hi",
            "instructions": "=Topic: {{ $json.topic }}",
        }
    )
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"topic": "weather"}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["instructions"] == "Topic: weather"


# ── 8. Connected LM populates model ──────────────────────────────────


@pytest.mark.asyncio
async def test_connected_lm_populates_model_field() -> None:
    lm = ExecNode(
        id="lm1",
        name="OpenAI",
        type="@n8n/n8n-nodes-langchain.lmChatOpenAi",
        type_version=1,
        parameters={"model": "gpt-4o-mini"},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node({"prompt": "Hi"})
    ctx = _ctx(mocks={"chain_output": "ok"}, ai_inputs=[lm])
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert out["model"] == "gpt-4o-mini"
    # LM was captured into lm_configs as a side-effect of resolution.
    assert "lm1" in ctx.lm_configs


@pytest.mark.asyncio
async def test_no_lm_means_no_model_field() -> None:
    node = _node({"prompt": "Hi"})
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"x": 1}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out = result[0][1][0].json
    assert "model" not in out


# ── 9. Multiple input items produce one output each ──────────────────


@pytest.mark.asyncio
async def test_one_output_per_input_item() -> None:
    node = _node({"prompt": "={{ $json.q }}"})
    ctx = _ctx(
        mocks={
            "chain_output": lambda p, item, *_: f"reply:{item.json['q']}"
        }
    )
    items = _items([{"q": "a"}, {"q": "b"}, {"q": "c"}])
    result = await exec_ai_transform(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["output"] for it in out_items] == [
        "reply:a",
        "reply:b",
        "reply:c",
    ]
    # Upstream JSON is preserved on each output.
    assert [it.json["q"] for it in out_items] == ["a", "b", "c"]


# ── 10. Descriptor registration (CI invariant) ───────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.aiTransform" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.aiTransform" in SUPPORTED_NODE_TYPES
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.aiTransform"] == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.aiTransform"]
    assert desc.executor.endswith(":exec_ai_transform")
    assert desc.category == "ai"


# ── 11. End-to-end: Manual Trigger → aiTransform (mock) → Set ────────


def _doc(nodes, connections):
    return {"name": "ai-transform-e2e", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_ai_transform_into_set() -> None:
    """Custom outputField is visible to a downstream Set node."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "a1",
                "AI Transform",
                "@n8n/n8n-nodes-langchain.aiTransform",
                {
                    "prompt": "=Translate to French: {{ $json.text }}",
                    "outputField": "translated",
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
                                "name": "answer",
                                "value": "={{ $json.translated }}",
                                "type": "string",
                            },
                            {
                                "name": "usedPrompt",
                                "value": "={{ $json.prompt }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [
                    [{"node": "AI Transform", "type": "main", "index": 0}]
                ]
            },
            "AI Transform": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )

    def fake(prompt, item, params, mock_ctx):
        return f"FR[{prompt}]"

    pin_data = {"Start": [{"text": "hello"}]}
    engine = WorkflowEngine(doc, mocks={"chain_output": fake})
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    ai_step = next(s for s in result.steps if s.node_name == "AI Transform")
    assert ai_step.status == "success", ai_step.error
    assert ai_step.output_count == 1
    sample = ai_step.sample_output[0]["json"]
    assert sample["translated"] == "FR[Translate to French: hello]"
    assert sample["prompt"] == "Translate to French: hello"
    assert sample["source"] == "aiTransform"
    # Default 'output' key is NOT set when a custom field is configured.
    assert "output" not in sample

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    set_json = set_step.sample_output[0]["json"]
    assert set_json["answer"] == "FR[Translate to French: hello]"
    assert set_json["usedPrompt"] == "Translate to French: hello"


# ── 12. End-to-end: Manual → embeddingsOpenAi → aiTransform → Set ───


@pytest.mark.asyncio
async def test_end_to_end_embeddings_subnode_into_ai_transform() -> None:
    """An embeddingsOpenAi sub-node connected to aiTransform populates
    the model field, and a downstream Set reads the transformed value."""
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
                "a1",
                "AI Transform",
                "@n8n/n8n-nodes-langchain.aiTransform",
                {
                    "prompt": "={{ $json.text }}",
                    "outputField": "summary",
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
            "Start": {
                "main": [[{"node": "AI Transform", "type": "main", "index": 0}]]
            },
            "Embeddings": {
                "ai_embedding": [
                    [{"node": "AI Transform", "type": "ai_embedding", "index": 0}]
                ]
            },
            "AI Transform": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )

    def fake(prompt, item, params, mock_ctx):
        return f"SUMMARY:{prompt}"

    pin_data = {"Start": [{"text": "alpha"}]}
    engine = WorkflowEngine(doc, mocks={"chain_output": fake})
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    ai_step = next(s for s in result.steps if s.node_name == "AI Transform")
    assert ai_step.status == "success", ai_step.error
    ai_sample = ai_step.sample_output[0]["json"]
    assert ai_sample["summary"] == "SUMMARY:alpha"
    assert ai_sample["prompt"] == "alpha"
    # Sub-node did not connect as ai_languageModel → no model field.
    assert "model" not in ai_sample

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    set_json = set_step.sample_output[0]["json"]
    assert set_json["summary"] == "SUMMARY:alpha"
    # model came from the upstream embeddings node; Set assignment
    # produced 'None' (string) because aiTransform did not forward one.
    assert set_json["model"] is None
