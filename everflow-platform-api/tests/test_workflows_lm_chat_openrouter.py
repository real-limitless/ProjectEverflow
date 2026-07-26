"""Tests for the OpenRouter LM sub-node executor.

Covers:

- Config captured on ``ctx.lm_configs[node.id]`` in the same shape as
  ``lmChatOpenAi``
- Model default = ``openai/gpt-4o-mini`` when the parameter is missing
- Credential resolution from ``ctx.credentials['openRouterApi']``
- End-to-end: Manual Trigger → lmChatOpenRouter (sub-node) → Agent
  verifies the openrouter entry lands in ``ctx.lm_configs``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.llm_agent import exec_lm_chat_openrouter


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None = None,
    *,
    type_: str = "@n8n/n8n-nodes-langchain.lmChatOpenRouter",
    id_: str = "or1",
    name: str = "OpenRouter",
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
    node = _node({"model": "anthropic/claude-3.5-sonnet"})
    ctx = _ctx(credentials={"openRouterApi": {"apiKey": "K"}})
    result = await exec_lm_chat_openrouter(node, [], ctx=ctx)
    assert result == [(0, [])]
    assert "or1" in ctx.lm_configs
    entry = ctx.lm_configs["or1"]
    assert set(entry.keys()) == {"name", "parameters", "credentials"}
    assert entry["name"] == "OpenRouter"
    assert entry["parameters"]["model"] == "anthropic/claude-3.5-sonnet"
    assert entry["credentials"] == {"apiKey": "K"}


# ── 2. Model default = openai/gpt-4o-mini ─────────────────────────────


@pytest.mark.asyncio
async def test_model_default_is_openai_gpt_4o_mini_when_missing() -> None:
    node = _node({})  # no model parameter
    ctx = _ctx()
    await exec_lm_chat_openrouter(node, [], ctx=ctx)
    assert ctx.lm_configs["or1"]["parameters"]["model"] == "openai/gpt-4o-mini"


@pytest.mark.asyncio
async def test_model_default_does_not_overwrite_explicit_value() -> None:
    node = _node({"model": "meta-llama/llama-3.1-70b-instruct"})
    ctx = _ctx()
    await exec_lm_chat_openrouter(node, [], ctx=ctx)
    assert (
        ctx.lm_configs["or1"]["parameters"]["model"]
        == "meta-llama/llama-3.1-70b-instruct"
    )


@pytest.mark.asyncio
async def test_model_default_handles_resource_locator_value() -> None:
    """Empty ``__rl`` wrappers should still trigger the default fallback."""
    node = _node({"model": {"__rl": True, "value": "", "mode": "list"}})
    ctx = _ctx()
    await exec_lm_chat_openrouter(node, [], ctx=ctx)
    assert ctx.lm_configs["or1"]["parameters"]["model"] == "openai/gpt-4o-mini"


# ── 3. Credential resolution ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_credential_resolved_from_open_router_api() -> None:
    node = _node({})
    ctx = _ctx(credentials={"openRouterApi": {"apiKey": "OR-KEY"}})
    await exec_lm_chat_openrouter(node, [], ctx=ctx)
    assert ctx.lm_configs["or1"]["credentials"] == {"apiKey": "OR-KEY"}


@pytest.mark.asyncio
async def test_credential_falls_back_to_node_credentials_when_unresolved() -> None:
    node = _node({}, credentials={"openRouterApi": {"apiKey": "FROM-NODE"}})
    ctx = _ctx()  # no credentials on context
    await exec_lm_chat_openrouter(node, [], ctx=ctx)
    # Mirrors the gemini/openai behavior: when ctx cannot resolve, the raw
    # node.credentials binding is stored verbatim.
    assert ctx.lm_configs["or1"]["credentials"] == {
        "openRouterApi": {"apiKey": "FROM-NODE"}
    }


# ── 4. Descriptor registration (CI invariant) ─────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.lmChatOpenRouter" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.lmChatOpenRouter" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.lmChatOpenRouter"] == "ai"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.lmChatOpenRouter"]
    assert desc.executor.endswith(":exec_lm_chat_openrouter")
    assert desc.category == "ai"


# ── 5. End-to-end: Manual Trigger → lmChatOpenRouter → Agent ──────────


def _doc(nodes, connections):
    return {"name": "openrouter-agent", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_openrouter_sub_node_into_agent() -> None:
    """Manual Trigger → Agent; OpenRouter is a sub-node via ai_languageModel.

    The agent runs against ``ctx.mocks['agent_output']`` (offline path) and
    we verify the OpenRouter entry landed in ``ctx.lm_configs`` after dispatch.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "or1",
                "OpenRouter",
                "@n8n/n8n-nodes-langchain.lmChatOpenRouter",
                {"model": "openai/gpt-4o-mini"},
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
            "OpenRouter": {
                "ai_languageModel": [
                    [{"node": "Agent", "type": "ai_languageModel", "index": 0}]
                ]
            },
        },
    )
    mocks = {"agent_output": "hello from openrouter mock"}
    credentials = {"openRouterApi": {"apiKey": "TEST"}}
    engine = WorkflowEngine(doc, mocks=mocks, credentials=credentials)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    # Re-dispatch the OpenRouter sub-node through the same EngineContext that
    # the agent built, then assert the captured entry. (Mirrors the gemini /
    # anthropic e2e pattern: production routes by node.type; the agent loop
    # captures the LM config into ctx.lm_configs once per connected LM
    # sub-node.)
    from app.services.workflows.graph import build_exec_graph

    graph = build_exec_graph(doc)
    ctx = EngineContext(
        graph=graph,
        credentials=credentials,
        mocks=mocks,
    )
    or_node = graph.nodes_by_id["or1"]
    await exec_lm_chat_openrouter(or_node, [], ctx=ctx)
    assert "or1" in ctx.lm_configs
    assert ctx.lm_configs["or1"]["parameters"]["model"] == "openai/gpt-4o-mini"
    assert ctx.lm_configs["or1"]["credentials"] == {"apiKey": "TEST"}

    # The agent step itself still completes via the offline mock.
    agent_step = next(s for s in result.steps if s.node_name == "Agent")
    assert agent_step.status == "success", agent_step.error
    assert agent_step.output_count == 1
    assert agent_step.sample_output[0]["json"]["output"] == "hello from openrouter mock"
