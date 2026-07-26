"""Tests for the OpenAI actions node executor (``@n8n/n8n-nodes-langchain.openAi``).

Covers:

- textCompletion via mock returns text
- imageGeneration returns N items for N=2
- analyzeImage via mock returns analysis
- transcription via mock with binary on the input item
- End-to-end: Manual Trigger → openAi (textCompletion) → Set sees ``text`` field
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem
from app.services.workflows.nodes.openai import (
    OPENAI_OPERATIONS,
    exec_openai,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "@n8n/n8n-nodes-langchain.openAi",
    id_: str = "oai1",
    name: str = "OpenAI",
    credentials: dict[str, Any] | None = None,
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params,
        credentials=credentials,
        position={"x": 0, "y": 0},
    )


def _ctx(mocks: dict[str, Any] | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {})  # type: ignore[arg-type]


def _out_items(result) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── 1. textCompletion via mock ───────────────────────────────────────


@pytest.mark.asyncio
async def test_text_completion_via_mock_returns_text() -> None:
    node = _node(
        {
            "operation": "textCompletion",
            "prompt": "Hello, world!",
            "model": "gpt-3.5-turbo-instruct",
        }
    )
    ctx = _ctx(
        {
            "openai": {
                "textCompletion": {
                    "text": "Hello back!",
                    "model": "gpt-3.5-turbo-instruct",
                    "usage": {"total_tokens": 7},
                }
            }
        }
    )
    out = _out_items(await exec_openai(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    payload = out[0].json
    assert payload["text"] == "Hello back!"
    assert payload["model"] == "gpt-3.5-turbo-instruct"
    assert payload["usage"] == {"total_tokens": 7}


@pytest.mark.asyncio
async def test_text_completion_default_model_when_unspecified() -> None:
    node = _node({"operation": "textCompletion", "prompt": "Hi"})
    ctx = _ctx(
        {"openai": {"textCompletion": {"text": "ok", "usage": {}}}}
    )
    out = _out_items(await exec_openai(node, [ExecutionItem(json={})], ctx=ctx))
    assert out[0].json["model"] == "gpt-3.5-turbo-instruct"
    assert out[0].json["text"] == "ok"


# ── 2. imageGeneration returns N items ───────────────────────────────


@pytest.mark.asyncio
async def test_image_generation_returns_n_items() -> None:
    node = _node(
        {
            "operation": "imageGeneration",
            "prompt": "A red cat",
            "size": "512x512",
            "n": 2,
        }
    )
    ctx = _ctx(
        {
            "openai": {
                "imageGeneration": {
                    "data": [
                        {"url": "https://example.com/a.png", "revised_prompt": "red cat A"},
                        {"url": "https://example.com/b.png", "revised_prompt": "red cat B"},
                    ]
                }
            }
        }
    )
    out = _out_items(await exec_openai(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 2
    assert out[0].json["url"] == "https://example.com/a.png"
    assert out[0].json["revisedPrompt"] == "red cat A"
    assert out[1].json["url"] == "https://example.com/b.png"
    assert out[1].json["revisedPrompt"] == "red cat B"


@pytest.mark.asyncio
async def test_image_generation_handles_b64_json_payload() -> None:
    node = _node({"operation": "imageGeneration", "prompt": "x", "n": 1})
    ctx = _ctx(
        {
            "openai": {
                "imageGeneration": {"data": [{"b64_json": "BASE64"}]}
            }
        }
    )
    out = _out_items(await exec_openai(node, [ExecutionItem(json={})], ctx=ctx))
    assert out[0].json["b64_json"] == "BASE64"
    assert out[0].json["url"] is None


# ── 3. analyzeImage via mock ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_image_via_mock_returns_analysis() -> None:
    node = _node(
        {
            "operation": "analyzeImage",
            "text": "Describe this picture",
            "imageUrl": "https://example.com/cat.png",
        }
    )
    ctx = _ctx(
        {
            "openai": {
                "analyzeImage": {
                    "analysis": "A small orange kitten sits on a windowsill.",
                    "usage": {"prompt_tokens": 12, "completion_tokens": 8},
                }
            }
        }
    )
    out = _out_items(await exec_openai(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    payload = out[0].json
    assert payload["analysis"] == "A small orange kitten sits on a windowsill."
    assert payload["usage"] == {"prompt_tokens": 12, "completion_tokens": 8}


@pytest.mark.asyncio
async def test_analyze_image_falls_back_to_choices_content() -> None:
    """When the mock uses the chat-completions payload shape, unwrap content."""
    node = _node(
        {
            "operation": "analyzeImage",
            "text": "what?",
            "imageUrl": "https://example.com/x.png",
        }
    )
    ctx = _ctx(
        {
            "openai": {
                "analyzeImage": {
                    "choices": [
                        {"message": {"content": "It is a banana."}}
                    ],
                    "usage": {"total_tokens": 9},
                }
            }
        }
    )
    out = _out_items(await exec_openai(node, [ExecutionItem(json={})], ctx=ctx))
    assert out[0].json["analysis"] == "It is a banana."
    assert out[0].json["usage"] == {"total_tokens": 9}


# ── 4. transcription via mock with binary input ──────────────────────


@pytest.mark.asyncio
async def test_transcription_via_mock_reads_binary_and_returns_text() -> None:
    node = _node(
        {"operation": "transcription", "binaryPropertyName": "data"}
    )
    item = ExecutionItem(
        json={},
        binary={
            "data": BinaryFile.from_bytes(
                b"FAKE-WAV-BYTES", file_name="hello.wav", mime_type="audio/wav"
            )
        },
    )
    ctx = _ctx({"openai": {"transcription": {"text": "Hello there", "language": "en"}}})
    out = _out_items(await exec_openai(node, [item], ctx=ctx))
    assert len(out) == 1
    payload = out[0].json
    assert payload["text"] == "Hello there"
    assert payload["language"] == "en"


# ── 5. No-credential offline fallback (no mock, no key) ──────────────


@pytest.mark.asyncio
async def test_text_completion_offline_fallback_when_no_credential_or_mock() -> None:
    node = _node({"operation": "textCompletion", "prompt": "hi"})
    out = _out_items(await exec_openai(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert "error" in out[0].json
    assert out[0].json["text"] == ""


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "embeddings"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_openai(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 6. Descriptor registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.openAi" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.openAi" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.openAi"] == "ai"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.openAi"]
    assert desc.executor.endswith(":exec_openai")
    assert desc.category == "ai"
    assert set(OPENAI_OPERATIONS) == {
        "textCompletion",
        "imageGeneration",
        "transcription",
        "analyzeImage",
    }


# ── 7. End-to-end: Manual Trigger → openAi → Set sees text field ────


def _doc(nodes, connections):
    return {"name": "openai-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_openai_text_completion_set() -> None:
    """Manual Trigger → openAi (textCompletion via mock) → Set pulls ``text``."""
    mocks = {
        "openai": {
            "textCompletion": {
                "text": "Mocked completion",
                "model": "gpt-3.5-turbo-instruct",
                "usage": {"total_tokens": 3},
            }
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("a1", "OpenAI", "@n8n/n8n-nodes-langchain.openAi", {
                "operation": "textCompletion",
                "prompt": "Say hi",
                "model": "gpt-3.5-turbo-instruct",
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "result", "value": "={{ $json.text }}", "type": "string"},
                    {"name": "used_model", "value": "={{ $json.model }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "OpenAI", "type": "main", "index": 0}]]},
            "OpenAI": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    openai_step = next(s for s in result.steps if s.node_name == "OpenAI")
    assert openai_step.status == "success", openai_step.error
    assert openai_step.output_count == 1
    sample = openai_step.sample_output[0]
    assert sample["json"]["text"] == "Mocked completion"
    assert sample["json"]["model"] == "gpt-3.5-turbo-instruct"

    # The downstream Set pulled the text from the openAi output.
    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result") == "Mocked completion"
    assert fjson.get("used_model") == "gpt-3.5-turbo-instruct"
