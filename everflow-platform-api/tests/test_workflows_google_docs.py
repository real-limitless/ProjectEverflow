"""Tests for the Google Docs node executor (``n8n-nodes-base.googleDocs``).

Covers:

- ``docs_response`` dict mock → envelope used verbatim (create/read/update)
- ``docs_response`` callable mock receives
  ``(operation, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline synthetic responses for create (documentId/title/body), read
  (body text), and update (revisionId='2')
- ``title``/``content``/``documentId`` defaults from ``$json``
- ``operation='create'`` reflected in payload
- Empty ``documentId`` for read/update → no item emitted
- End-to-end: Manual Trigger → googleDocs (create mock) → Set sees
  ``documentId``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.google_docs import (
    DOCS_OPERATIONS,
    exec_google_docs,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.googleDocs",
    id_: str = "gd1",
    name: str = "Google Docs",
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


# ── 1. docs_response dict mock (create) ───────────────────────────────


@pytest.mark.asyncio
async def test_docs_response_dict_mock_is_used_verbatim_for_create() -> None:
    node = _node(
        {
            "operation": "create",
            "title": "Hello Doc",
            "content": "Hello world",
        }
    )
    ctx = _ctx(
        {
            "docs_response": {
                "documentId": "fixed-doc-1",
                "title": "Hello Doc",
                "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": "Hello world"}}]}}]},
                "revisionId": "5",
            }
        }
    )
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    p = out[0].json
    assert p["documentId"] == "fixed-doc-1"
    assert p["title"] == "Hello Doc"
    assert p["revisionId"] == "5"
    assert p["source"] == "googleDocs"
    assert "body" in p
    assert "mockSource" not in p


# ── 2. docs_response callable mock signature ──────────────────────────


@pytest.mark.asyncio
async def test_docs_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "documentId": "cb-doc-1",
            "title": params.get("title"),
            "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": params.get("content")}}]}}]},
            "revisionId": "1",
        }

    node = _node(
        {
            "operation": "create",
            "title": "From Param",
            "content": "Body from param",
            "extra": "keep",
        }
    )
    ctx = _ctx({"docs_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_google_docs(node, [item], ctx=ctx))

    assert captured["operation"] == "create"
    assert captured["params"]["title"] == "From Param"
    assert captured["params"]["content"] == "Body from param"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["documentId"] == "cb-doc-1"
    assert out[0].json["title"] == "From Param"


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "read",
            "documentId": "doc-http",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "documentId": "doc-http",
                    "title": "From HTTP",
                    "body": {"content": "Hello from http"},
                    "revisionId": "7",
                },
            }
        }
    )
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    p = out[0].json
    assert p["documentId"] == "doc-http"
    assert p["title"] == "From HTTP"
    assert "Hello from http" in p["body"]
    assert p["revisionId"] == "7"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "googleDocs"


# ── 4. Offline synthetic response — create ────────────────────────────


@pytest.mark.asyncio
async def test_offline_create_synthesizes_document_id_and_body() -> None:
    node = _node(
        {
            "operation": "create",
            "title": "My Doc",
            "content": "First paragraph",
        }
    )
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["documentId"].startswith("mock_doc_")
    assert p["title"] == "My Doc"
    assert p["revisionId"] == "1"
    assert p["source"] == "googleDocs"
    assert p["mockSource"] == "offline"
    body = p["body"]
    assert isinstance(body, dict)
    assert "content" in body
    first_para = body["content"][0]["paragraph"]["elements"][0]["textRun"]["content"]
    assert first_para == "First paragraph"


# ── 5. Offline synthetic response — read ──────────────────────────────


@pytest.mark.asyncio
async def test_offline_read_returns_body_text() -> None:
    node = _node({"operation": "read", "documentId": "doc-offline-1"})
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["documentId"] == "doc-offline-1"
    assert p["title"] == "Mock Document"
    assert p["body"] == "Mock document content here."
    assert p["revisionId"] == "1"
    assert p["source"] == "googleDocs"
    assert p["mockSource"] == "offline"


# ── 6. Offline synthetic response — update ────────────────────────────


@pytest.mark.asyncio
async def test_offline_update_returns_revision_two() -> None:
    node = _node(
        {
            "operation": "update",
            "documentId": "doc-upd-1",
            "content": "appended text",
            "replaceAll": True,
        }
    )
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["documentId"] == "doc-upd-1"
    assert p["revisionId"] == "2"
    assert p["replaceAll"] is True
    assert "updatedAt" in p
    assert p["source"] == "googleDocs"
    assert p["mockSource"] == "offline"


# ── 7. operation='create' reflected ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_operation_reflected_in_payload() -> None:
    node = _node(
        {
            "operation": "create",
            "title": "Reflected",
            "content": "Hello",
        }
    )
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    p = out[0].json
    assert p["operation"] == "create"
    assert p["source"] == "googleDocs"
    assert "documentId" in p
    assert "title" in p
    assert "body" in p
    assert "revisionId" in p


# ── 8. documentId default from $json ──────────────────────────────────


@pytest.mark.asyncio
async def test_document_id_defaults_from_json() -> None:
    node = _node({"operation": "read"})
    item = ExecutionItem(json={"documentId": "json-doc-1"})
    out = _out_items(await exec_google_docs(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["documentId"] == "json-doc-1"


@pytest.mark.asyncio
async def test_document_id_falls_back_to_id_key() -> None:
    node = _node({"operation": "read"})
    item = ExecutionItem(json={"id": "json-id-1"})
    out = _out_items(await exec_google_docs(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["documentId"] == "json-id-1"


# ── 9. title default from $json ───────────────────────────────────────


@pytest.mark.asyncio
async def test_title_defaults_from_json_title() -> None:
    node = _node({"operation": "create", "content": "x"})
    item = ExecutionItem(json={"title": "Json Title"})
    out = _out_items(await exec_google_docs(node, [item], ctx=_ctx()))
    assert out[0].json["title"] == "Json Title"


@pytest.mark.asyncio
async def test_title_defaults_from_json_name() -> None:
    node = _node({"operation": "create", "content": "x"})
    item = ExecutionItem(json={"name": "Json Name"})
    out = _out_items(await exec_google_docs(node, [item], ctx=_ctx()))
    assert out[0].json["title"] == "Json Name"


# ── 10. content default from $json ────────────────────────────────────


@pytest.mark.asyncio
async def test_content_defaults_from_json_content() -> None:
    node = _node({"operation": "create", "title": "T"})
    item = ExecutionItem(json={"content": "Json Content"})
    out = _out_items(await exec_google_docs(node, [item], ctx=_ctx()))
    body = out[0].json["body"]
    first_para = body["content"][0]["paragraph"]["elements"][0]["textRun"]["content"]
    assert first_para == "Json Content"


@pytest.mark.asyncio
async def test_content_defaults_from_json_text() -> None:
    node = _node({"operation": "create", "title": "T"})
    item = ExecutionItem(json={"text": "Json Text"})
    out = _out_items(await exec_google_docs(node, [item], ctx=_ctx()))
    body = out[0].json["body"]
    first_para = body["content"][0]["paragraph"]["elements"][0]["textRun"]["content"]
    assert first_para == "Json Text"


# ── 11. Empty documentId for read → no item ───────────────────────────


@pytest.mark.asyncio
async def test_empty_document_id_for_read_skips_item() -> None:
    node = _node({"operation": "read", "documentId": ""})
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_document_id_for_update_skips_item() -> None:
    node = _node(
        {"operation": "update", "documentId": "", "content": "x"}
    )
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_document_id_when_only_in_json_skips_item() -> None:
    node = _node({"operation": "read"})
    item = ExecutionItem(json={"documentId": "", "id": ""})
    out = _out_items(await exec_google_docs(node, [item], ctx=_ctx()))
    assert out == []


# ── 12. Unsupported operation raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "delete", "documentId": "x"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 13. Default operation is read ─────────────────────────────────────


@pytest.mark.asyncio
async def test_default_operation_is_read() -> None:
    node = _node({"documentId": "doc-default"})
    out = _out_items(
        await exec_google_docs(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    p = out[0].json
    assert p["operation"] == "read"
    assert "body" in p
    assert "title" in p


# ── 14. Descriptor registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.googleDocs" in REGISTRY
    assert "n8n-nodes-base.googleDocs" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.googleDocs"] == "output"
    desc = REGISTRY["n8n-nodes-base.googleDocs"]
    assert desc.executor.endswith(":exec_google_docs")
    assert desc.category == "output"
    assert set(DOCS_OPERATIONS) == {"create", "read", "update"}


# ── 15. End-to-end: Manual Trigger → googleDocs (create mock) → Set ──


def _doc(nodes, connections):
    return {"name": "gd-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_google_docs_set_sees_document_id() -> None:
    """Manual Trigger → googleDocs (create with docs_response mock) → Set."""
    mocks = {
        "docs_response": {
            "documentId": "e2e-doc-1",
            "title": "E2E Title",
            "body": {"content": [{"paragraph": {"elements": [{"textRun": {"content": "E2E body"}}]}}]},
            "revisionId": "1",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "g1",
                "Docs",
                "n8n-nodes-base.googleDocs",
                {
                    "operation": "create",
                    "title": "E2E Title",
                    "content": "E2E body",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_doc_id", "value": "={{ $json.documentId }}", "type": "string"},
                            {"name": "result_title", "value": "={{ $json.title }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Docs", "type": "main", "index": 0}]]},
            "Docs": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    docs_step = next(s for s in result.steps if s.node_name == "Docs")
    assert docs_step.status == "success", docs_step.error
    assert docs_step.output_count == 1
    first = docs_step.sample_output[0]
    assert first["json"]["documentId"] == "e2e-doc-1"
    assert first["json"]["title"] == "E2E Title"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_doc_id") == "e2e-doc-1"
    assert fjson.get("result_title") == "E2E Title"
    assert fjson.get("result_source") == "googleDocs"
