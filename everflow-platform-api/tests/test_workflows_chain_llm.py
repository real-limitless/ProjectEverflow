"""Tests for the Basic LLM Chain executor (chainLlm).

Covers:

- ``ctx.mocks['chain_output']`` returns the expected ``text`` per input item
- ``ctx.mocks['agent_output']`` is honored as a fallback for parity
- ``parameters.prompt`` is evaluated as an n8n expression (``$json.field``)
- ``parameters.messages`` list shape works without a prompt
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger → chainLlm (mocked) → Set sees ``text``
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.llm_agent import exec_chain_llm


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "c1",
    name: str = "Chain",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.chainLlm",
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


# ── 1. chain_output mock returns expected text per item ────────────────


@pytest.mark.asyncio
async def test_chain_output_mock_returns_text_per_item() -> None:
    node = _node({"prompt": "Hello"})
    ctx = _ctx(mocks={"chain_output": "mocked completion"})
    items = _items([{"a": 1}, {"a": 2}, {"a": 3}])

    result = await exec_chain_llm(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert len(out_items) == 3
    for it in out_items:
        assert it.json["text"] == "mocked completion"
        assert it.json["model"] == "gpt-4o-mini"
        assert "usage" in it.json


@pytest.mark.asyncio
async def test_chain_output_callable_mock_receives_prompt_and_item() -> None:
    captured: list[tuple[Any, Any, Any]] = []

    def fake(prompt, item_json, messages):
        captured.append((prompt, item_json, messages))
        return f"reply-for-{item_json.get('q')}"

    node = _node({"prompt": "={{ $json.q }}"})
    ctx = _ctx(mocks={"chain_output": fake})
    items = _items([{"q": "alpha"}, {"q": "beta"}])
    result = await exec_chain_llm(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["text"] for it in out_items] == ["reply-for-alpha", "reply-for-beta"]
    assert len(captured) == 2
    assert captured[0][0] == "alpha"
    assert captured[0][1] == {"q": "alpha"}
    assert captured[0][2] == [{"role": "user", "content": "alpha"}]


# ── 2. agent_output mock fallback ─────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_output_mock_falls_through_for_chain() -> None:
    node = _node({"prompt": "Hi"})
    ctx = _ctx(mocks={"agent_output": "via-agent-fallback"})
    items = _items([{"x": 1}])
    result = await exec_chain_llm(node, items, ctx=ctx)
    assert result[0][1][0].json["text"] == "via-agent-fallback"


# ── 3. prompt template evaluation with $json.field ─────────────────────


@pytest.mark.asyncio
async def test_prompt_template_evaluates_json_field() -> None:
    node = _node({"prompt": "Summarize: {{ $json.topic }}"})
    ctx = _ctx(mocks={"chain_output": "ok"})
    items = _items([{"topic": "weather"}, {"topic": "sports"}])
    result = await exec_chain_llm(node, items, ctx=ctx)

    # The mock returns a constant; what we verify here is that the per-item
    # context survives and the upstream JSON is merged.
    assert [it.json["text"] for it in result[0][1]] == ["ok", "ok"]
    assert [it.json["topic"] for it in result[0][1]] == ["weather", "sports"]


@pytest.mark.asyncio
async def test_prompt_template_evaluates_with_rl_value_form() -> None:
    """``parameters.prompt`` is a string; n8n ``__rl`` wrappers are not used for
    the chain's text field. The plain-string form is what reaches us.
    """
    node = _node({"prompt": "={{ $json.q }}"})
    ctx = _ctx(mocks={"chain_output": lambda prompt, ij, msgs: f"got:{prompt}"})
    items = _items([{"q": "ping"}])
    result = await exec_chain_llm(node, items, ctx=ctx)
    assert result[0][1][0].json["text"] == "got:ping"


# ── 4. messages list shape (no prompt required) ────────────────────────


@pytest.mark.asyncio
async def test_messages_list_used_when_provided() -> None:
    node = _node(
        {
            "messages": [
                {"role": "system", "content": "You are terse."},
                {"role": "user", "content": "={{ $json.q }}"},
            ]
        }
    )
    ctx = _ctx(mocks={"chain_output": "short"})

    def echo(prompt, ij, msgs):
        return f"msgs={len(msgs)}:{msgs[1]['content']}"

    ctx.mocks["chain_output"] = echo
    items = _items([{"q": "ping"}])
    result = await exec_chain_llm(node, items, ctx=ctx)
    assert result[0][1][0].json["text"] == "msgs=2:ping"


@pytest.mark.asyncio
async def test_messages_list_supports_expressions_per_field() -> None:
    node = _node(
        {
            "messages": [
                {"role": "system", "content": "=ctx={{ $json.context }}"},
                {"role": "user", "content": "=ask={{ $json.q }}"},
            ]
        }
    )
    ctx = _ctx(mocks={"chain_output": "ok"})

    def echo(prompt, ij, msgs):
        return msgs[-1]["content"]

    ctx.mocks["chain_output"] = echo
    items = _items([{"q": "what?", "context": "weather"}])
    result = await exec_chain_llm(node, items, ctx=ctx)
    assert result[0][1][0].json["text"] == "ask=what?"


# ── 5. Connected LM populates model + credentials ─────────────────────


@pytest.mark.asyncio
async def test_connected_lm_uses_its_model_and_creds() -> None:
    lm = ExecNode(
        id="lm1",
        name="OpenAI",
        type="@n8n/n8n-nodes-langchain.lmChatOpenAi",
        type_version=1,
        parameters={"model": "gpt-4o"},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node({"prompt": "hi"})
    ctx = _ctx(
        mocks={"chain_output": "ok"},
        credentials={"openAiApi": {"apiKey": "K"}},
        ai_inputs=[lm],
    )
    items = _items([{"x": 1}])
    result = await exec_chain_llm(node, items, ctx=ctx)
    assert "lm1" in ctx.lm_configs
    assert ctx.lm_configs["lm1"]["parameters"]["model"] == "gpt-4o"
    assert result[0][1][0].json["model"] == "gpt-4o"


# ── 6. Offline fallback when no credential + no mock ──────────────────


@pytest.mark.asyncio
async def test_offline_fallback_when_no_credential_and_no_mock() -> None:
    node = _node({"prompt": "Hello"})
    ctx = _ctx()  # no mocks, no creds
    items = _items([{"x": 1}])
    result = await exec_chain_llm(node, items, ctx=ctx)
    assert "[offline chainLlm]" in result[0][1][0].json["text"]


# ── 7. Descriptor registration (CI invariant) ──────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.chainLlm" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.chainLlm" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.chainLlm"] == "ai"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.chainLlm"]
    assert desc.executor.endswith(":exec_chain_llm")
    assert desc.category == "ai"


# ── 8. End-to-end: Manual Trigger → chainLlm (mocked) → Set sees text ──


def _doc(nodes, connections):
    return {"name": "chain-llm-e2e", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_chain_llm_into_set() -> None:
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
                "Chain",
                "@n8n/n8n-nodes-langchain.chainLlm",
                {"prompt": "={{ $json.q }}"},
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
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Chain", "type": "main", "index": 0}]]},
            "OpenAI": {
                "ai_languageModel": [
                    [{"node": "Chain", "type": "ai_languageModel", "index": 0}]
                ]
            },
            "Chain": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    mocks = {"chain_output": "the answer is 42"}
    pin_data = {"Start": [{"q": "what is the answer?"}]}
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    chain_step = next(s for s in result.steps if s.node_name == "Chain")
    assert chain_step.status == "success", chain_step.error
    assert chain_step.output_count == 1
    assert chain_step.sample_output[0]["json"]["text"] == "the answer is 42"
    assert chain_step.sample_output[0]["json"]["model"] == "gpt-4o-mini"

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["answer"] == "the answer is 42"
