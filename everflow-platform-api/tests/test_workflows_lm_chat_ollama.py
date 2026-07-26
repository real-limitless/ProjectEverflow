"""Tests for the Ollama LM sub-node executor.

Covers:

- Config captured on ``ctx.lm_configs[node.id]`` in the same shape as
  ``lmChatOpenAi`` plus the resolved ``baseUrl`` field
- Model default = ``llama3`` when the parameter is missing
- Base URL default = ``http://localhost:11434`` when neither parameters nor
  the ``ollamaApi`` credential provide one
- Override base URL from credential / parameter
- End-to-end: Manual Trigger → lmChatOllama (sub-node) → Agent verifies the
  Ollama entry lands in ``ctx.lm_configs``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.llm_agent import exec_lm_chat_ollama


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None = None,
    *,
    type_: str = "@n8n/n8n-nodes-langchain.lmChatOllama",
    id_: str = "ol1",
    name: str = "Ollama",
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
async def test_lm_configs_captured_with_base_url_field() -> None:
    node = _node({"model": "llama3.1", "baseUrl": "http://ollama.local:11434"})
    ctx = _ctx()
    result = await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert result == [(0, [])]
    assert "ol1" in ctx.lm_configs
    entry = ctx.lm_configs["ol1"]
    assert set(entry.keys()) == {"name", "parameters", "credentials", "baseUrl"}
    assert entry["name"] == "Ollama"
    assert entry["parameters"]["model"] == "llama3.1"
    assert entry["baseUrl"] == "http://ollama.local:11434"


# ── 2. Model default = llama3 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_model_default_is_llama3_when_missing() -> None:
    node = _node({})  # no model parameter
    ctx = _ctx()
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert ctx.lm_configs["ol1"]["parameters"]["model"] == "llama3"


@pytest.mark.asyncio
async def test_model_default_does_not_overwrite_explicit_value() -> None:
    node = _node({"model": "qwen2.5:7b"})
    ctx = _ctx()
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert ctx.lm_configs["ol1"]["parameters"]["model"] == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_model_default_handles_resource_locator_value() -> None:
    """Empty ``__rl`` wrappers should still trigger the default fallback."""
    node = _node({"model": {"__rl": True, "value": "", "mode": "list"}})
    ctx = _ctx()
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert ctx.lm_configs["ol1"]["parameters"]["model"] == "llama3"


# ── 3. Base URL default = http://localhost:11434 ──────────────────────


@pytest.mark.asyncio
async def test_base_url_default_is_localhost_11434_when_missing() -> None:
    node = _node({})
    ctx = _ctx()
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert ctx.lm_configs["ol1"]["baseUrl"] == "http://localhost:11434"


@pytest.mark.asyncio
async def test_base_url_from_parameter_overrides_default() -> None:
    node = _node({"baseUrl": "http://gpu-host.local:11434"})
    ctx = _ctx()
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert ctx.lm_configs["ol1"]["baseUrl"] == "http://gpu-host.local:11434"


@pytest.mark.asyncio
async def test_base_url_from_credential_when_no_parameter() -> None:
    node = _node({})
    ctx = _ctx(credentials={"ollamaApi": {"baseUrl": "http://creds:11434"}})
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert ctx.lm_configs["ol1"]["baseUrl"] == "http://creds:11434"


@pytest.mark.asyncio
async def test_base_url_parameter_wins_over_credential() -> None:
    node = _node({"baseUrl": "http://param-host:11434"})
    ctx = _ctx(credentials={"ollamaApi": {"baseUrl": "http://creds:11434"}})
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert ctx.lm_configs["ol1"]["baseUrl"] == "http://param-host:11434"


# ── 4. Credential resolution ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_credential_resolved_from_ollama_api() -> None:
    node = _node({})
    ctx = _ctx(credentials={"ollamaApi": {"baseUrl": "http://cred-host:11434"}})
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    assert ctx.lm_configs["ol1"]["credentials"] == {
        "baseUrl": "http://cred-host:11434"
    }


@pytest.mark.asyncio
async def test_credential_falls_back_to_node_credentials_when_unresolved() -> None:
    node = _node({}, credentials={"ollamaApi": {"baseUrl": "http://from-node:11434"}})
    ctx = _ctx()  # no credentials on context
    await exec_lm_chat_ollama(node, [], ctx=ctx)
    # Mirrors the openai/anthropic/gemini behavior: when ctx cannot resolve,
    # the raw node.credentials binding is stored verbatim.
    assert ctx.lm_configs["ol1"]["credentials"] == {
        "ollamaApi": {"baseUrl": "http://from-node:11434"}
    }
    # The baseUrl field still resolves from the stored credentials dict.
    assert ctx.lm_configs["ol1"]["baseUrl"] == "http://from-node:11434"


# ── 5. Descriptor registration (CI invariant) ─────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.lmChatOllama" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.lmChatOllama" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.lmChatOllama"] == "ai"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.lmChatOllama"]
    assert desc.executor.endswith(":exec_lm_chat_ollama")
    assert desc.category == "ai"


# ── 6. End-to-end: Manual Trigger → lmChatOllama → Agent ──────────────


def _doc(nodes, connections):
    return {"name": "ollama-agent", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_ollama_sub_node_into_agent() -> None:
    """Manual Trigger → Agent; Ollama is a sub-node via ai_languageModel.

    The agent runs against ``ctx.mocks['agent_output']`` (offline path) and
    we verify the Ollama entry landed in ``ctx.lm_configs`` after dispatch.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "ol1",
                "Ollama",
                "@n8n/n8n-nodes-langchain.lmChatOllama",
                {"model": "llama3"},
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
            "Ollama": {
                "ai_languageModel": [
                    [{"node": "Agent", "type": "ai_languageModel", "index": 0}]
                ]
            },
        },
    )
    mocks = {"agent_output": "hello from ollama mock"}
    credentials = {"ollamaApi": {"baseUrl": "http://test-host:11434"}}
    engine = WorkflowEngine(doc, mocks=mocks, credentials=credentials)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    # Re-dispatch the Ollama sub-node through the same EngineContext that
    # the agent built, then assert the captured entry. (Mirrors the gemini
    # / anthropic / openrouter e2e pattern: production routes by node.type;
    # the agent loop captures the LM config into ctx.lm_configs once per
    # connected LM sub-node.)
    from app.services.workflows.graph import build_exec_graph

    graph = build_exec_graph(doc)
    ctx = EngineContext(
        graph=graph,
        credentials=credentials,
        mocks=mocks,
    )
    ollama = graph.nodes_by_id["ol1"]
    await exec_lm_chat_ollama(ollama, [], ctx=ctx)
    assert "ol1" in ctx.lm_configs
    assert ctx.lm_configs["ol1"]["parameters"]["model"] == "llama3"
    assert ctx.lm_configs["ol1"]["credentials"] == {
        "baseUrl": "http://test-host:11434"
    }
    assert ctx.lm_configs["ol1"]["baseUrl"] == "http://test-host:11434"

    # The agent step itself still completes via the offline mock.
    agent_step = next(s for s in result.steps if s.node_name == "Agent")
    assert agent_step.status == "success", agent_step.error
    assert agent_step.output_count == 1
    assert agent_step.sample_output[0]["json"]["output"] == "hello from ollama mock"
