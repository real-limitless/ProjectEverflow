"""Tests for the LLM chat provider family: Groq, DeepSeek, xAI Grok,
Azure OpenAI, and Mistral Cloud.

Covers (per provider):

- Config captured on ``ctx.lm_configs[node.id]`` in the same shape as
  ``lmChatOpenAi``
- Model default when the parameter is missing
- Credential resolution from the per-provider credential key
- Azure OpenAI also resolves ``endpoint`` and ``deployment``
- End-to-end: Manual Trigger → provider sub-node → Agent
  verifies the entry lands in ``ctx.lm_configs``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.llm_agent import (
    exec_lm_chat_azure_openai,
    exec_lm_chat_deepseek,
    exec_lm_chat_groq,
    exec_lm_chat_mistral_cloud,
    exec_lm_chat_xai_grok,
)


# ── Shared helpers ────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    type_: str,
    id_: str,
    name: str,
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


# ======================================================================
# Groq
# ======================================================================


@pytest.mark.asyncio
async def test_groq_captured_with_same_shape_as_openai() -> None:
    node = _node(
        {"model": "llama-3.1-8b-instant"},
        type_="@n8n/n8n-nodes-langchain.lmChatGroq",
        id_="groq1",
        name="Groq",
    )
    ctx = _ctx(credentials={"groqApi": {"apiKey": "K"}})
    result = await exec_lm_chat_groq(node, [], ctx=ctx)
    assert result == [(0, [])]
    assert "groq1" in ctx.lm_configs
    entry = ctx.lm_configs["groq1"]
    assert set(entry.keys()) == {"name", "parameters", "credentials"}
    assert entry["name"] == "Groq"
    assert entry["parameters"]["model"] == "llama-3.1-8b-instant"
    assert entry["credentials"] == {"apiKey": "K"}


@pytest.mark.asyncio
async def test_groq_model_default_is_llama_3_1_70b_versatile() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatGroq",
        id_="groq1",
        name="Groq",
    )
    ctx = _ctx()
    await exec_lm_chat_groq(node, [], ctx=ctx)
    assert (
        ctx.lm_configs["groq1"]["parameters"]["model"]
        == "llama-3.1-70b-versatile"
    )


@pytest.mark.asyncio
async def test_groq_model_default_does_not_overwrite_explicit_value() -> None:
    node = _node(
        {"model": "mixtral-8x7b-32768"},
        type_="@n8n/n8n-nodes-langchain.lmChatGroq",
        id_="groq1",
        name="Groq",
    )
    ctx = _ctx()
    await exec_lm_chat_groq(node, [], ctx=ctx)
    assert ctx.lm_configs["groq1"]["parameters"]["model"] == "mixtral-8x7b-32768"


@pytest.mark.asyncio
async def test_groq_model_default_handles_resource_locator_value() -> None:
    node = _node(
        {"model": {"__rl": True, "value": "", "mode": "list"}},
        type_="@n8n/n8n-nodes-langchain.lmChatGroq",
        id_="groq1",
        name="Groq",
    )
    ctx = _ctx()
    await exec_lm_chat_groq(node, [], ctx=ctx)
    assert (
        ctx.lm_configs["groq1"]["parameters"]["model"]
        == "llama-3.1-70b-versatile"
    )


@pytest.mark.asyncio
async def test_groq_credential_resolved_from_groq_api() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatGroq",
        id_="groq1",
        name="Groq",
    )
    ctx = _ctx(credentials={"groqApi": {"apiKey": "GROQ-KEY"}})
    await exec_lm_chat_groq(node, [], ctx=ctx)
    assert ctx.lm_configs["groq1"]["credentials"] == {"apiKey": "GROQ-KEY"}


@pytest.mark.asyncio
async def test_groq_credential_falls_back_to_node_credentials_when_unresolved() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatGroq",
        id_="groq1",
        name="Groq",
        credentials={"groqApi": {"apiKey": "FROM-NODE"}},
    )
    ctx = _ctx()
    await exec_lm_chat_groq(node, [], ctx=ctx)
    assert ctx.lm_configs["groq1"]["credentials"] == {
        "groqApi": {"apiKey": "FROM-NODE"}
    }


def test_groq_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.lmChatGroq" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.lmChatGroq" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.lmChatGroq"] == "ai"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.lmChatGroq"]
    assert desc.executor.endswith(":exec_lm_chat_groq")
    assert desc.category == "ai"


# ======================================================================
# DeepSeek
# ======================================================================


@pytest.mark.asyncio
async def test_deepseek_captured_with_same_shape_as_openai() -> None:
    node = _node(
        {"model": "deepseek-coder"},
        type_="@n8n/n8n-nodes-langchain.lmChatDeepSeek",
        id_="ds1",
        name="DeepSeek",
    )
    ctx = _ctx(credentials={"deepseekApi": {"apiKey": "K"}})
    result = await exec_lm_chat_deepseek(node, [], ctx=ctx)
    assert result == [(0, [])]
    assert "ds1" in ctx.lm_configs
    entry = ctx.lm_configs["ds1"]
    assert set(entry.keys()) == {"name", "parameters", "credentials"}
    assert entry["name"] == "DeepSeek"
    assert entry["parameters"]["model"] == "deepseek-coder"
    assert entry["credentials"] == {"apiKey": "K"}


@pytest.mark.asyncio
async def test_deepseek_model_default_is_deepseek_chat() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatDeepSeek",
        id_="ds1",
        name="DeepSeek",
    )
    ctx = _ctx()
    await exec_lm_chat_deepseek(node, [], ctx=ctx)
    assert ctx.lm_configs["ds1"]["parameters"]["model"] == "deepseek-chat"


@pytest.mark.asyncio
async def test_deepseek_model_default_does_not_overwrite_explicit_value() -> None:
    node = _node(
        {"model": "deepseek-reasoner"},
        type_="@n8n/n8n-nodes-langchain.lmChatDeepSeek",
        id_="ds1",
        name="DeepSeek",
    )
    ctx = _ctx()
    await exec_lm_chat_deepseek(node, [], ctx=ctx)
    assert ctx.lm_configs["ds1"]["parameters"]["model"] == "deepseek-reasoner"


@pytest.mark.asyncio
async def test_deepseek_credential_resolved_from_deepseek_api() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatDeepSeek",
        id_="ds1",
        name="DeepSeek",
    )
    ctx = _ctx(credentials={"deepseekApi": {"apiKey": "DS-KEY"}})
    await exec_lm_chat_deepseek(node, [], ctx=ctx)
    assert ctx.lm_configs["ds1"]["credentials"] == {"apiKey": "DS-KEY"}


@pytest.mark.asyncio
async def test_deepseek_credential_falls_back_to_node_credentials_when_unresolved() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatDeepSeek",
        id_="ds1",
        name="DeepSeek",
        credentials={"deepseekApi": {"apiKey": "FROM-NODE"}},
    )
    ctx = _ctx()
    await exec_lm_chat_deepseek(node, [], ctx=ctx)
    assert ctx.lm_configs["ds1"]["credentials"] == {
        "deepseekApi": {"apiKey": "FROM-NODE"}
    }


def test_deepseek_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.lmChatDeepSeek" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.lmChatDeepSeek" in SUPPORTED_NODE_TYPES
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.lmChatDeepSeek"] == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.lmChatDeepSeek"]
    assert desc.executor.endswith(":exec_lm_chat_deepseek")
    assert desc.category == "ai"


# ======================================================================
# xAI Grok
# ======================================================================


@pytest.mark.asyncio
async def test_xai_grok_captured_with_same_shape_as_openai() -> None:
    node = _node(
        {"model": "grok-2-vision-latest"},
        type_="@n8n/n8n-nodes-langchain.lmChatXAiGrok",
        id_="xai1",
        name="xAI",
    )
    ctx = _ctx(credentials={"xaiApi": {"apiKey": "K"}})
    result = await exec_lm_chat_xai_grok(node, [], ctx=ctx)
    assert result == [(0, [])]
    assert "xai1" in ctx.lm_configs
    entry = ctx.lm_configs["xai1"]
    assert set(entry.keys()) == {"name", "parameters", "credentials"}
    assert entry["name"] == "xAI"
    assert entry["parameters"]["model"] == "grok-2-vision-latest"
    assert entry["credentials"] == {"apiKey": "K"}


@pytest.mark.asyncio
async def test_xai_grok_model_default_is_grok_2_latest() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatXAiGrok",
        id_="xai1",
        name="xAI",
    )
    ctx = _ctx()
    await exec_lm_chat_xai_grok(node, [], ctx=ctx)
    assert ctx.lm_configs["xai1"]["parameters"]["model"] == "grok-2-latest"


@pytest.mark.asyncio
async def test_xai_grok_model_default_does_not_overwrite_explicit_value() -> None:
    node = _node(
        {"model": "grok-beta"},
        type_="@n8n/n8n-nodes-langchain.lmChatXAiGrok",
        id_="xai1",
        name="xAI",
    )
    ctx = _ctx()
    await exec_lm_chat_xai_grok(node, [], ctx=ctx)
    assert ctx.lm_configs["xai1"]["parameters"]["model"] == "grok-beta"


@pytest.mark.asyncio
async def test_xai_grok_credential_resolved_from_xai_api() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatXAiGrok",
        id_="xai1",
        name="xAI",
    )
    ctx = _ctx(credentials={"xaiApi": {"apiKey": "XAI-KEY"}})
    await exec_lm_chat_xai_grok(node, [], ctx=ctx)
    assert ctx.lm_configs["xai1"]["credentials"] == {"apiKey": "XAI-KEY"}


@pytest.mark.asyncio
async def test_xai_grok_credential_falls_back_to_node_credentials_when_unresolved() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatXAiGrok",
        id_="xai1",
        name="xAI",
        credentials={"xaiApi": {"apiKey": "FROM-NODE"}},
    )
    ctx = _ctx()
    await exec_lm_chat_xai_grok(node, [], ctx=ctx)
    assert ctx.lm_configs["xai1"]["credentials"] == {
        "xaiApi": {"apiKey": "FROM-NODE"}
    }


def test_xai_grok_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.lmChatXAiGrok" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.lmChatXAiGrok" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.lmChatXAiGrok"] == "ai"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.lmChatXAiGrok"]
    assert desc.executor.endswith(":exec_lm_chat_xai_grok")
    assert desc.category == "ai"


# ======================================================================
# Azure OpenAI
# ======================================================================


@pytest.mark.asyncio
async def test_azure_openai_captured_with_same_shape_as_openai() -> None:
    node = _node(
        {
            "model": "gpt-4o",
            "endpoint": "https://my-resource.openai.azure.com",
            "deployment": "my-gpt4o-deployment",
        },
        type_="@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
        id_="az1",
        name="Azure",
    )
    ctx = _ctx(
        credentials={
            "azureOpenAiApi": {
                "apiKey": "K",
                "endpoint": "https://my-resource.openai.azure.com",
                "deployment": "my-gpt4o-deployment",
            }
        }
    )
    result = await exec_lm_chat_azure_openai(node, [], ctx=ctx)
    assert result == [(0, [])]
    assert "az1" in ctx.lm_configs
    entry = ctx.lm_configs["az1"]
    assert entry["name"] == "Azure"
    assert entry["parameters"]["model"] == "gpt-4o"
    assert entry["credentials"]["apiKey"] == "K"
    assert entry["endpoint"] == "https://my-resource.openai.azure.com"
    assert entry["deployment"] == "my-gpt4o-deployment"


@pytest.mark.asyncio
async def test_azure_openai_model_default_is_gpt_4o() -> None:
    node = _node(
        {
            "endpoint": "https://r.openai.azure.com",
            "deployment": "deploy",
        },
        type_="@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
        id_="az1",
        name="Azure",
    )
    ctx = _ctx()
    await exec_lm_chat_azure_openai(node, [], ctx=ctx)
    assert ctx.lm_configs["az1"]["parameters"]["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_azure_openai_model_default_does_not_overwrite_explicit_value() -> None:
    node = _node(
        {
            "model": "gpt-4-turbo",
            "endpoint": "https://r.openai.azure.com",
            "deployment": "deploy",
        },
        type_="@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
        id_="az1",
        name="Azure",
    )
    ctx = _ctx()
    await exec_lm_chat_azure_openai(node, [], ctx=ctx)
    assert ctx.lm_configs["az1"]["parameters"]["model"] == "gpt-4-turbo"


@pytest.mark.asyncio
async def test_azure_openai_resolves_endpoint_and_deployment_from_credentials() -> None:
    """When the params omit endpoint/deployment, the resolved credential
    should populate the top-level fields so the agent loop can address
    the deployment without re-parsing the credential dict."""
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
        id_="az1",
        name="Azure",
    )
    ctx = _ctx(
        credentials={
            "azureOpenAiApi": {
                "apiKey": "AZ-KEY",
                "endpoint": "https://resolved.openai.azure.com",
                "deployment": "resolved-deploy",
            }
        }
    )
    await exec_lm_chat_azure_openai(node, [], ctx=ctx)
    assert (
        ctx.lm_configs["az1"]["endpoint"] == "https://resolved.openai.azure.com"
    )
    assert ctx.lm_configs["az1"]["deployment"] == "resolved-deploy"
    assert ctx.lm_configs["az1"]["credentials"]["apiKey"] == "AZ-KEY"


@pytest.mark.asyncio
async def test_azure_openai_endpoint_and_deployment_empty_when_not_provided() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
        id_="az1",
        name="Azure",
    )
    ctx = _ctx()
    await exec_lm_chat_azure_openai(node, [], ctx=ctx)
    assert ctx.lm_configs["az1"]["endpoint"] == ""
    assert ctx.lm_configs["az1"]["deployment"] == ""


@pytest.mark.asyncio
async def test_azure_openai_credential_falls_back_to_node_credentials_when_unresolved() -> None:
    node = _node(
        {"endpoint": "https://x.openai.azure.com", "deployment": "d"},
        type_="@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
        id_="az1",
        name="Azure",
        credentials={"azureOpenAiApi": {"apiKey": "FROM-NODE"}},
    )
    ctx = _ctx()
    await exec_lm_chat_azure_openai(node, [], ctx=ctx)
    # Raw node.credentials binding is stored when ctx cannot resolve
    assert ctx.lm_configs["az1"]["credentials"] == {
        "azureOpenAiApi": {"apiKey": "FROM-NODE"}
    }


def test_azure_openai_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.lmChatAzureOpenAi" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.lmChatAzureOpenAi" in SUPPORTED_NODE_TYPES
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.lmChatAzureOpenAi"] == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.lmChatAzureOpenAi"]
    assert desc.executor.endswith(":exec_lm_chat_azure_openai")
    assert desc.category == "ai"


# ======================================================================
# Mistral Cloud
# ======================================================================


@pytest.mark.asyncio
async def test_mistral_captured_with_same_shape_as_openai() -> None:
    node = _node(
        {"model": "mistral-small-latest"},
        type_="@n8n/n8n-nodes-langchain.lmChatMistralCloud",
        id_="mist1",
        name="Mistral",
    )
    ctx = _ctx(credentials={"mistralApi": {"apiKey": "K"}})
    result = await exec_lm_chat_mistral_cloud(node, [], ctx=ctx)
    assert result == [(0, [])]
    assert "mist1" in ctx.lm_configs
    entry = ctx.lm_configs["mist1"]
    assert set(entry.keys()) == {"name", "parameters", "credentials"}
    assert entry["name"] == "Mistral"
    assert entry["parameters"]["model"] == "mistral-small-latest"
    assert entry["credentials"] == {"apiKey": "K"}


@pytest.mark.asyncio
async def test_mistral_model_default_is_mistral_large_latest() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatMistralCloud",
        id_="mist1",
        name="Mistral",
    )
    ctx = _ctx()
    await exec_lm_chat_mistral_cloud(node, [], ctx=ctx)
    assert (
        ctx.lm_configs["mist1"]["parameters"]["model"] == "mistral-large-latest"
    )


@pytest.mark.asyncio
async def test_mistral_model_default_does_not_overwrite_explicit_value() -> None:
    node = _node(
        {"model": "open-mistral-7b"},
        type_="@n8n/n8n-nodes-langchain.lmChatMistralCloud",
        id_="mist1",
        name="Mistral",
    )
    ctx = _ctx()
    await exec_lm_chat_mistral_cloud(node, [], ctx=ctx)
    assert ctx.lm_configs["mist1"]["parameters"]["model"] == "open-mistral-7b"


@pytest.mark.asyncio
async def test_mistral_credential_resolved_from_mistral_api() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatMistralCloud",
        id_="mist1",
        name="Mistral",
    )
    ctx = _ctx(credentials={"mistralApi": {"apiKey": "MIST-KEY"}})
    await exec_lm_chat_mistral_cloud(node, [], ctx=ctx)
    assert ctx.lm_configs["mist1"]["credentials"] == {"apiKey": "MIST-KEY"}


@pytest.mark.asyncio
async def test_mistral_credential_falls_back_to_node_credentials_when_unresolved() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.lmChatMistralCloud",
        id_="mist1",
        name="Mistral",
        credentials={"mistralApi": {"apiKey": "FROM-NODE"}},
    )
    ctx = _ctx()
    await exec_lm_chat_mistral_cloud(node, [], ctx=ctx)
    assert ctx.lm_configs["mist1"]["credentials"] == {
        "mistralApi": {"apiKey": "FROM-NODE"}
    }


def test_mistral_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.lmChatMistralCloud" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.lmChatMistralCloud" in SUPPORTED_NODE_TYPES
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.lmChatMistralCloud"] == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.lmChatMistralCloud"]
    assert desc.executor.endswith(":exec_lm_chat_mistral_cloud")
    assert desc.category == "ai"


# ======================================================================
# End-to-end: Manual Trigger → provider sub-node → Agent
# ======================================================================


def _doc(nodes, connections, name: str = "provider-agent"):
    return {"name": name, "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


async def _assert_e2e_provider(
    *,
    sub_id: str,
    sub_name: str,
    sub_type: str,
    sub_params: dict[str, Any],
    exec_fn,
    credentials: dict[str, Any],
    expected_model: str,
    expected_creds: dict[str, Any],
) -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(sub_id, sub_name, sub_type, sub_params),
            _n(
                "a1",
                "Agent",
                "@n8n/n8n-nodes-langchain.agent",
                {"text": "={{ $json.q }}"},
            ),
        ],
        {
            "Start": {"main": [[{"node": "Agent", "type": "main", "index": 0}]]},
            sub_name: {
                "ai_languageModel": [
                    [{"node": "Agent", "type": "ai_languageModel", "index": 0}]
                ]
            },
        },
    )
    mocks = {"agent_output": f"hello from {sub_name} mock"}
    engine = WorkflowEngine(doc, mocks=mocks, credentials=credentials)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    from app.services.workflows.graph import build_exec_graph

    graph = build_exec_graph(doc)
    ctx = EngineContext(graph=graph, credentials=credentials, mocks=mocks)
    sub = graph.nodes_by_id[sub_id]
    await exec_fn(sub, [], ctx=ctx)
    assert sub_id in ctx.lm_configs
    assert ctx.lm_configs[sub_id]["parameters"]["model"] == expected_model
    assert ctx.lm_configs[sub_id]["credentials"] == expected_creds

    agent_step = next(s for s in result.steps if s.node_name == "Agent")
    assert agent_step.status == "success", agent_step.error
    assert agent_step.output_count == 1
    assert (
        agent_step.sample_output[0]["json"]["output"]
        == f"hello from {sub_name} mock"
    )


@pytest.mark.asyncio
async def test_end_to_end_manual_groq_sub_node_into_agent() -> None:
    await _assert_e2e_provider(
        sub_id="groq1",
        sub_name="Groq",
        sub_type="@n8n/n8n-nodes-langchain.lmChatGroq",
        sub_params={"model": "llama-3.1-70b-versatile"},
        exec_fn=exec_lm_chat_groq,
        credentials={"groqApi": {"apiKey": "TEST"}},
        expected_model="llama-3.1-70b-versatile",
        expected_creds={"apiKey": "TEST"},
    )


@pytest.mark.asyncio
async def test_end_to_end_manual_deepseek_sub_node_into_agent() -> None:
    await _assert_e2e_provider(
        sub_id="ds1",
        sub_name="DeepSeek",
        sub_type="@n8n/n8n-nodes-langchain.lmChatDeepSeek",
        sub_params={"model": "deepseek-chat"},
        exec_fn=exec_lm_chat_deepseek,
        credentials={"deepseekApi": {"apiKey": "TEST"}},
        expected_model="deepseek-chat",
        expected_creds={"apiKey": "TEST"},
    )


@pytest.mark.asyncio
async def test_end_to_end_manual_xai_grok_sub_node_into_agent() -> None:
    await _assert_e2e_provider(
        sub_id="xai1",
        sub_name="xAI",
        sub_type="@n8n/n8n-nodes-langchain.lmChatXAiGrok",
        sub_params={"model": "grok-2-latest"},
        exec_fn=exec_lm_chat_xai_grok,
        credentials={"xaiApi": {"apiKey": "TEST"}},
        expected_model="grok-2-latest",
        expected_creds={"apiKey": "TEST"},
    )


@pytest.mark.asyncio
async def test_end_to_end_manual_azure_openai_sub_node_into_agent() -> None:
    await _assert_e2e_provider(
        sub_id="az1",
        sub_name="Azure",
        sub_type="@n8n/n8n-nodes-langchain.lmChatAzureOpenAi",
        sub_params={
            "model": "gpt-4o",
            "endpoint": "https://my-resource.openai.azure.com",
            "deployment": "my-gpt4o-deployment",
        },
        exec_fn=exec_lm_chat_azure_openai,
        credentials={
            "azureOpenAiApi": {
                "apiKey": "TEST",
                "endpoint": "https://my-resource.openai.azure.com",
                "deployment": "my-gpt4o-deployment",
            }
        },
        expected_model="gpt-4o",
        expected_creds={
            "apiKey": "TEST",
            "endpoint": "https://my-resource.openai.azure.com",
            "deployment": "my-gpt4o-deployment",
        },
    )


@pytest.mark.asyncio
async def test_end_to_end_manual_mistral_sub_node_into_agent() -> None:
    await _assert_e2e_provider(
        sub_id="mist1",
        sub_name="Mistral",
        sub_type="@n8n/n8n-nodes-langchain.lmChatMistralCloud",
        sub_params={"model": "mistral-large-latest"},
        exec_fn=exec_lm_chat_mistral_cloud,
        credentials={"mistralApi": {"apiKey": "TEST"}},
        expected_model="mistral-large-latest",
        expected_creds={"apiKey": "TEST"},
    )
