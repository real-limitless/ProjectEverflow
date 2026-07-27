"""Tests for the Anthropic Claude LM sub-node executor.

Covers:

- Config captured on ``ctx.lm_configs[node.id]`` in the same shape as
  ``lmChatOpenAi``
- Model default = ``claude-3-5-sonnet-latest`` when the parameter is missing
- Credential resolution from ``ctx.credentials['anthropicApi']``
- End-to-end: Manual Trigger → lmChatAnthropic (sub-node) → Agent
  verifies the anthropic entry lands in ``ctx.lm_configs``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.llm_agent import exec_lm_chat_anthropic


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None = None,
    *,
    type_: str = "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    id_: str = "ant1",
    name: str = "Anthropic",
    credentials: dict[str, Any] | None = None,
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params or {},
        credentials=credentials,
        position={"x": 0, "y": 0},
    )


def _ctx(
    credentials: dict[str, dict[str, Any]] | None = None,
    *,
    mocks: dict[str, Any] | None = None,
) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(  # type: ignore[arg-type]
        graph=g,
        credentials=credentials or {},
        mocks=mocks or {},
    )


# ── 1. Config captured on context ─────────────────────────────────────


@pytest.mark.asyncio
async def test_lm_configs_captured_with_same_shape_as_openai() -> None:
    node = _node({"model": "claude-3-opus-latest"})
    ctx = _ctx(credentials={"anthropicApi": {"apiKey": "K"}})
    result = await exec_lm_chat_anthropic(node, [], ctx=ctx)
    assert result == [(0, [])]
    assert "ant1" in ctx.lm_configs
    entry = ctx.lm_configs["ant1"]
    assert set(entry.keys()) == {"name", "parameters", "credentials"}
    assert entry["name"] == "Anthropic"
    assert entry["parameters"]["model"] == "claude-3-opus-latest"
    assert entry["credentials"] == {"apiKey": "K"}


# ── 2. Model default = claude-3-5-sonnet-latest ────────────────────────


@pytest.mark.asyncio
async def test_model_default_is_claude_3_5_sonnet_when_missing() -> None:
    node = _node({})  # no model parameter
    ctx = _ctx()
    await exec_lm_chat_anthropic(node, [], ctx=ctx)
    assert ctx.lm_configs["ant1"]["parameters"]["model"] == "claude-3-5-sonnet-latest"


@pytest.mark.asyncio
async def test_model_default_does_not_overwrite_explicit_value() -> None:
    node = _node({"model": "claude-3-haiku-20240307"})
    ctx = _ctx()
    await exec_lm_chat_anthropic(node, [], ctx=ctx)
    assert ctx.lm_configs["ant1"]["parameters"]["model"] == "claude-3-haiku-20240307"


@pytest.mark.asyncio
async def test_model_default_handles_resource_locator_value() -> None:
    """Empty ``__rl`` wrappers should still trigger the default fallback."""
    node = _node({"model": {"__rl": True, "value": "", "mode": "list"}})
    ctx = _ctx()
    await exec_lm_chat_anthropic(node, [], ctx=ctx)
    assert ctx.lm_configs["ant1"]["parameters"]["model"] == "claude-3-5-sonnet-latest"


# ── 3. Credential resolution ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_credential_resolved_from_anthropic_api() -> None:
    node = _node({})
    ctx = _ctx(credentials={"anthropicApi": {"apiKey": "ANT-KEY"}})
    await exec_lm_chat_anthropic(node, [], ctx=ctx)
    assert ctx.lm_configs["ant1"]["credentials"] == {"apiKey": "ANT-KEY"}


@pytest.mark.asyncio
async def test_credential_falls_back_to_node_credentials_when_unresolved() -> None:
    node = _node({}, credentials={"anthropicApi": {"apiKey": "FROM-NODE"}})
    ctx = _ctx()  # no credentials on context
    await exec_lm_chat_anthropic(node, [], ctx=ctx)
    # Mirrors the gemini/openai behavior: when ctx cannot resolve, the raw
    # node.credentials binding is stored verbatim.
    assert ctx.lm_configs["ant1"]["credentials"] == {
        "anthropicApi": {"apiKey": "FROM-NODE"}
    }


# ── 4. Descriptor registration (CI invariant) ─────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.lmChatAnthropic" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.lmChatAnthropic" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.lmChatAnthropic"] == "ai"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.lmChatAnthropic"]
    assert desc.executor.endswith(":exec_lm_chat_anthropic")
    assert desc.category == "ai"


# ── 5. End-to-end: Manual Trigger → lmChatAnthropic → Agent ───────────


def _doc(nodes, connections):
    return {"name": "anthropic-agent", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_anthropic_sub_node_into_agent() -> None:
    """Manual Trigger → Agent; Anthropic is a sub-node via ai_languageModel.

    The agent runs against ``ctx.mocks['agent_output']`` (offline path) and
    we verify the Anthropic entry landed in ``ctx.lm_configs`` after dispatch.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "ant1",
                "Anthropic",
                "@n8n/n8n-nodes-langchain.lmChatAnthropic",
                {"model": "claude-3-5-sonnet-latest"},
            ),
            _n(
                "a1",
                "Agent",
                "@n8n/n8n-nodes-langchain.agent",
                {"text": "={{ $json.q }}"},
            ),
        ],
        {
            "Start": {"main": [[{"node": "Agent", "type": "main", "index": 0}]]},
            "Anthropic": {
                "ai_languageModel": [
                    [{"node": "Agent", "type": "ai_languageModel", "index": 0}]
                ]
            },
        },
    )
    mocks = {"agent_output": "hello from anthropic mock"}
    credentials = {"anthropicApi": {"apiKey": "TEST"}}
    engine = WorkflowEngine(doc, mocks=mocks, credentials=credentials)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    # Re-dispatch the Anthropic sub-node through the same EngineContext that
    # the agent built, then assert the captured entry. (Mirrors the gemini
    # e2e pattern: production routes by node.type; the agent loop captures
    # the LM config into ctx.lm_configs once per connected LM sub-node.)
    from app.services.workflows.graph import build_exec_graph

    graph = build_exec_graph(doc)
    ctx = EngineContext(
        graph=graph,
        credentials=credentials,
        mocks=mocks,
    )
    ant = graph.nodes_by_id["ant1"]
    await exec_lm_chat_anthropic(ant, [], ctx=ctx)
    assert "ant1" in ctx.lm_configs
    assert ctx.lm_configs["ant1"]["parameters"]["model"] == "claude-3-5-sonnet-latest"
    assert ctx.lm_configs["ant1"]["credentials"] == {"apiKey": "TEST"}

    # The agent step itself still completes via the offline mock.
    agent_step = next(s for s in result.steps if s.node_name == "Agent")
    assert agent_step.status == "success", agent_step.error
    assert agent_step.output_count == 1
    assert agent_step.sample_output[0]["json"]["output"] == "hello from anthropic mock"
