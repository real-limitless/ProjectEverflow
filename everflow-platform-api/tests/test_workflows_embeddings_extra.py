"""Tests for embeddings extra executors (Cohere, Azure OpenAI, HuggingFace, Mistral).

Covers for EACH provider:
- Mock dict used verbatim
- Mock callable receives args
- Offline produces deterministic vector with ``source`` field
- Credential present but http mock returns body (real HTTP path via ctx.mocks['http'])

Plus descriptor registration and an end-to-end workflow test.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes.embeddings_extra import (
    exec_embeddings_azure_openai,
    exec_embeddings_cohere,
    exec_embeddings_huggingface,
    exec_embeddings_mistral,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    type_: str = "@n8n/n8n-nodes-langchain.embeddingsCohere",
    id_: str = "n1",
    name: str = "Embed",
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
    mocks: dict[str, Any] | None = None,
    credentials: dict[str, Any] | None = None,
) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(
        graph=g,
        mocks=mocks or {},
        credentials=credentials or {},
    )


def _out_items(result):
    out = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── Cohere ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cohere_mock_dict_used_verbatim() -> None:
    node = _node({})
    ctx = _ctx(
        mocks={
            "embeddings_cohere_response": {
                "data": [{"embedding": [0.1, 0.2, 0.3]}]
            }
        }
    )
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_cohere(node, items, ctx=ctx)
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["embedding"] == [0.1, 0.2, 0.3]
    assert out[0].json["model"] == "embed-english-v3.0"
    assert out[0].json["source"] == "cohere"


@pytest.mark.asyncio
async def test_cohere_mock_callable_receives_args() -> None:
    captured: list[tuple[Any, Any, Any, Any]] = []

    def fake(text, params, item, ctx):
        captured.append((text, params, item, ctx))
        return [0.5, 0.6, 0.7]

    node = _node({"model": "embed-english-v3.0"})
    ctx = _ctx(mocks={"embeddings_cohere_response": fake})
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_cohere(node, items, ctx=ctx)
    out = _out_items(result)
    assert len(captured) == 1
    assert captured[0][0] == "hello"
    assert captured[0][1] == {"model": "embed-english-v3.0"}
    assert captured[0][2].json == {"text": "hello"}
    assert out[0].json["embedding"] == [0.5, 0.6, 0.7]


@pytest.mark.asyncio
async def test_cohere_offline_deterministic_vector() -> None:
    node = _node({})
    ctx = _ctx()
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_cohere(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "cohere"
    assert isinstance(out[0].json["embedding"], list)
    assert len(out[0].json["embedding"]) == 1536
    for v in out[0].json["embedding"]:
        assert -1.0 <= v <= 1.0
    result2 = await exec_embeddings_cohere(node, items, ctx=ctx)
    out2 = _out_items(result2)
    assert out[0].json["embedding"] == out2[0].json["embedding"]


@pytest.mark.asyncio
async def test_cohere_credential_http_mock() -> None:
    node = _node({})
    ctx = _ctx(
        mocks={
            "http": {
                "POST https://api.cohere.ai/v1/embed": {
                    "data": [{"embedding": [0.8, 0.9]}]
                }
            }
        },
        credentials={"cohereApi": {"apiKey": "test-key"}},
    )
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_cohere(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["embedding"] == [0.8, 0.9]
    assert out[0].json["source"] == "cohere"


# ── Azure OpenAI ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_azure_mock_dict_used_verbatim() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.embeddingsAzureOpenAi",
    )
    ctx = _ctx(
        mocks={"embeddings_azure_response": {"embedding": [0.1, 0.2]}}
    )
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_azure_openai(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["embedding"] == [0.1, 0.2]
    assert out[0].json["model"] == "text-embedding-3-small"
    assert out[0].json["source"] == "azureOpenAi"


@pytest.mark.asyncio
async def test_azure_mock_callable_receives_args() -> None:
    captured: list[tuple[Any, Any, Any, Any]] = []

    def fake(text, params, item, ctx):
        captured.append((text, params, item, ctx))
        return [0.4, 0.5]

    node = _node(
        {"model": "text-embedding-3-small"},
        type_="@n8n/n8n-nodes-langchain.embeddingsAzureOpenAi",
    )
    ctx = _ctx(mocks={"embeddings_azure_response": fake})
    items = items_from_json_list([{"text": "azure text"}])
    result = await exec_embeddings_azure_openai(node, items, ctx=ctx)
    out = _out_items(result)
    assert len(captured) == 1
    assert captured[0][0] == "azure text"
    assert out[0].json["embedding"] == [0.4, 0.5]


@pytest.mark.asyncio
async def test_azure_offline_deterministic_vector() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.embeddingsAzureOpenAi",
    )
    ctx = _ctx()
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_azure_openai(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "azureOpenAi"
    assert len(out[0].json["embedding"]) == 1536
    result2 = await exec_embeddings_azure_openai(node, items, ctx=ctx)
    assert (
        _out_items(result)[0].json["embedding"]
        == _out_items(result2)[0].json["embedding"]
    )


@pytest.mark.asyncio
async def test_azure_credential_http_mock() -> None:
    node = _node(
        {"deploymentName": "my-deploy", "resourceName": "my-resource"},
        type_="@n8n/n8n-nodes-langchain.embeddingsAzureOpenAi",
    )
    ctx = _ctx(
        mocks={
            "http": {
                "POST https://my-resource.openai.azure.com/openai/deployments/my-deploy/embeddings?api-version=2024-02-01": {
                    "data": [{"embedding": [0.7, 0.8, 0.9]}]
                }
            }
        },
        credentials={"azureOpenAiApi": {"apiKey": "test-key"}},
    )
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_azure_openai(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["embedding"] == [0.7, 0.8, 0.9]
    assert out[0].json["source"] == "azureOpenAi"


# ── HuggingFace ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hf_mock_dict_used_verbatim() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.embeddingsHuggingFace",
    )
    ctx = _ctx(mocks={"embeddings_hf_response": [0.1, 0.2, 0.3]})
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_huggingface(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["embedding"] == [0.1, 0.2, 0.3]
    assert out[0].json["model"] == "sentence-transformers/all-MiniLM-L6-v2"
    assert out[0].json["source"] == "huggingFace"


@pytest.mark.asyncio
async def test_hf_mock_callable_receives_args() -> None:
    captured: list[tuple[Any, Any, Any, Any]] = []

    def fake(text, params, item, ctx):
        captured.append((text, params, item, ctx))
        return [0.3, 0.4]

    node = _node(
        {"model": "sentence-transformers/all-MiniLM-L6-v2"},
        type_="@n8n/n8n-nodes-langchain.embeddingsHuggingFace",
    )
    ctx = _ctx(mocks={"embeddings_hf_response": fake})
    items = items_from_json_list([{"text": "hf text"}])
    result = await exec_embeddings_huggingface(node, items, ctx=ctx)
    out = _out_items(result)
    assert len(captured) == 1
    assert captured[0][0] == "hf text"
    assert out[0].json["embedding"] == [0.3, 0.4]


@pytest.mark.asyncio
async def test_hf_offline_deterministic_vector() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.embeddingsHuggingFace",
    )
    ctx = _ctx()
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_huggingface(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "huggingFace"
    assert len(out[0].json["embedding"]) == 1536
    result2 = await exec_embeddings_huggingface(node, items, ctx=ctx)
    assert (
        _out_items(result)[0].json["embedding"]
        == _out_items(result2)[0].json["embedding"]
    )


@pytest.mark.asyncio
async def test_hf_credential_http_mock() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.embeddingsHuggingFace",
    )
    ctx = _ctx(
        mocks={
            "http": {
                "POST https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2": [
                    0.6,
                    0.7,
                ]
            }
        },
        credentials={"huggingFaceApi": {"apiKey": "test-key"}},
    )
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_huggingface(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["embedding"] == [0.6, 0.7]
    assert out[0].json["source"] == "huggingFace"


# ── Mistral ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mistral_mock_dict_used_verbatim() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.embeddingsMistral",
    )
    ctx = _ctx(
        mocks={
            "embeddings_mistral_response": {
                "data": [{"embedding": [0.1, 0.2]}]
            }
        }
    )
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_mistral(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["embedding"] == [0.1, 0.2]
    assert out[0].json["model"] == "mistral-embed"
    assert out[0].json["source"] == "mistral"


@pytest.mark.asyncio
async def test_mistral_mock_callable_receives_args() -> None:
    captured: list[tuple[Any, Any, Any, Any]] = []

    def fake(text, params, item, ctx):
        captured.append((text, params, item, ctx))
        return [0.2, 0.3]

    node = _node(
        {"model": "mistral-embed"},
        type_="@n8n/n8n-nodes-langchain.embeddingsMistral",
    )
    ctx = _ctx(mocks={"embeddings_mistral_response": fake})
    items = items_from_json_list([{"text": "mistral text"}])
    result = await exec_embeddings_mistral(node, items, ctx=ctx)
    out = _out_items(result)
    assert len(captured) == 1
    assert captured[0][0] == "mistral text"
    assert out[0].json["embedding"] == [0.2, 0.3]


@pytest.mark.asyncio
async def test_mistral_offline_deterministic_vector() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.embeddingsMistral",
    )
    ctx = _ctx()
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_mistral(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["source"] == "mistral"
    assert len(out[0].json["embedding"]) == 1536
    result2 = await exec_embeddings_mistral(node, items, ctx=ctx)
    assert (
        _out_items(result)[0].json["embedding"]
        == _out_items(result2)[0].json["embedding"]
    )


@pytest.mark.asyncio
async def test_mistral_credential_http_mock() -> None:
    node = _node(
        {},
        type_="@n8n/n8n-nodes-langchain.embeddingsMistral",
    )
    ctx = _ctx(
        mocks={
            "http": {
                "POST https://api.mistral.ai/v1/embeddings": {
                    "data": [{"embedding": [0.5, 0.6]}]
                }
            }
        },
        credentials={"mistralApi": {"apiKey": "test-key"}},
    )
    items = items_from_json_list([{"text": "hello"}])
    result = await exec_embeddings_mistral(node, items, ctx=ctx)
    out = _out_items(result)
    assert out[0].json["embedding"] == [0.5, 0.6]
    assert out[0].json["source"] == "mistral"


# ── Descriptor registration ──────────────────────────────────────────


def test_descriptors_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    for ntype in (
        "@n8n/n8n-nodes-langchain.embeddingsCohere",
        "@n8n/n8n-nodes-langchain.embeddingsAzureOpenAi",
        "@n8n/n8n-nodes-langchain.embeddingsHuggingFace",
        "@n8n/n8n-nodes-langchain.embeddingsMistral",
    ):
        assert ntype in REGISTRY
        assert ntype in SUPPORTED_NODE_TYPES
        assert SUPPORTED_NODE_TYPES[ntype] == "ai"
        desc = REGISTRY[ntype]
        assert desc.category == "ai"


# ── End-to-end ───────────────────────────────────────────────────────


def _doc(nodes, connections):
    return {
        "name": "embeddings-extra-e2e",
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
async def test_e2e_cohere_offline_into_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "e1",
                "Embed",
                "@n8n/n8n-nodes-langchain.embeddingsCohere",
                {"model": "embed-english-v3.0"},
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
                                "value": "={{ $json.source }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Embed", "type": "main", "index": 0}]]},
            "Embed": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    pin_data = {"Start": [{"text": "the quick brown fox"}]}
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    embed_step = next(s for s in result.steps if s.node_name == "Embed")
    assert embed_step.status == "success", embed_step.error
    assert embed_step.output_count == 1
    sample = embed_step.sample_output[0]["json"]
    assert isinstance(sample["embedding"], list)
    assert len(sample["embedding"]) == 1536
    assert sample["source"] == "cohere"

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["result"] == "cohere"