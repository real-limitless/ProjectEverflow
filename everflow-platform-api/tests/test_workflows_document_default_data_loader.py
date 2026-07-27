"""Tests for the Default Document Loader executor (documentDefaultDataLoader).

Covers:

- ``ctx.mocks['document_output']`` returning a list of docs
- ``ctx.mocks['document_output']`` as a callable that receives ``(item, params)``
- ``ctx.mocks['loader_output']`` fallback mock
- Offline extraction order: ``$json.text`` → ``pageContent``
- Offline extraction order: ``$json.content`` → ``pageContent``
- Offline extraction: binary ``data`` (base64) → UTF-8 ``pageContent``
- Offline extraction: missing all → JSON-serialized ``item.json``
- ``parameters.options.metadata`` merged into output metadata
- Connected text splitter with ``chunkSize`` splits into multiple chunks
- Multiple inputs produce multiple documents
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger → documentDefaultDataLoader → Set sees
  ``pageContent`` and ``metadata``
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem, items_from_json_list
from app.services.workflows.nodes.llm_agent import exec_document_default_data_loader


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "d1",
    name: str = "Document Loader",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.documentDefaultDataLoader",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    mocks: dict[str, Any] | None = None,
    ai_inputs: list[ExecNode] | None = None,
    lm_configs: dict[str, Any] | None = None,
) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: list(ai_inputs or [])
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    ctx = EngineContext(  # type: ignore[arg-type]
        graph=g,
        mocks=mocks or {},
    )
    if lm_configs:
        ctx.lm_configs.update(lm_configs)
    return ctx


def _items(rows: list[dict[str, Any]] | None = None) -> list[ExecutionItem]:
    return items_from_json_list(rows or [])


# ── 1. document_output mock returns list of docs ──────────────────────


@pytest.mark.asyncio
async def test_document_output_mock_list_of_docs() -> None:
    node = _node({"text": "ignored when mock is set"})
    ctx = _ctx(
        mocks={
            "document_output": [
                {"pageContent": "doc-1", "metadata": {"origin": "mock"}},
                {"pageContent": "doc-2", "metadata": {"origin": "mock"}},
            ]
        }
    )
    items = _items([{"text": "alpha"}, {"text": "beta"}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    # Two items × two docs each = four output items
    assert len(out_items) == 4
    assert [it.json["pageContent"] for it in out_items] == [
        "doc-1",
        "doc-2",
        "doc-1",
        "doc-2",
    ]
    for it in out_items:
        assert it.json["metadata"] == {"origin": "mock"}


# ── 2. document_output callable mock receives (item, params) ─────────


@pytest.mark.asyncio
async def test_document_output_callable_mock_receives_item_and_params() -> None:
    captured: list[tuple[Any, Any]] = []

    def fake(item, params):
        captured.append((item, params))
        return [{"pageContent": f"loaded-{item.json.get('q')}", "metadata": {"k": 1}}]

    node = _node({"text": "={{ $json.q }}"})
    ctx = _ctx(mocks={"document_output": fake})
    items = _items([{"q": "alpha"}, {"q": "beta"}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["pageContent"] for it in out_items] == [
        "loaded-alpha",
        "loaded-beta",
    ]
    assert len(captured) == 2
    # The captured item is the upstream ExecutionItem, with the original JSON
    assert captured[0][0].json == {"q": "alpha"}
    # And the params dict is the node's full parameters
    assert captured[0][1] == {"text": "={{ $json.q }}"}
    assert captured[1][0].json == {"q": "beta"}


# ── 3. loader_output mock fallback ───────────────────────────────────


@pytest.mark.asyncio
async def test_loader_output_mock_falls_through() -> None:
    node = _node({})
    ctx = _ctx(mocks={"loader_output": [{"pageContent": "from-loader"}]})
    items = _items([{"text": "ignored"}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 1
    assert out_items[0].json["pageContent"] == "from-loader"


@pytest.mark.asyncio
async def test_document_output_takes_precedence_over_loader_output() -> None:
    node = _node({})
    ctx = _ctx(
        mocks={
            "document_output": [{"pageContent": "doc"}],
            "loader_output": [{"pageContent": "loader"}],
        }
    )
    items = _items([{"text": "x"}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    assert result[0][1][0].json["pageContent"] == "doc"


@pytest.mark.asyncio
async def test_loader_output_callable_mock() -> None:
    def fake(item, params):
        return [{"pageContent": f"v-{item.json['k']}", "metadata": {}}]

    node = _node({})
    ctx = _ctx(mocks={"loader_output": fake})
    items = _items([{"k": 1}, {"k": 2}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["pageContent"] for it in out_items] == ["v-1", "v-2"]


# ── 4. Offline: $json.text → pageContent ─────────────────────────────


@pytest.mark.asyncio
async def test_offline_extracts_text_field_as_page_content() -> None:
    node = _node({})  # no parameters.text → offline default order
    ctx = _ctx()  # no mocks
    items = _items([{"text": "hello"}, {"text": "world"}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 2
    assert [it.json["pageContent"] for it in out_items] == ["hello", "world"]
    for it in out_items:
        assert it.json["metadata"]["source"] == "documentDefaultDataLoader"
        assert it.json["metadata"]["itemIndex"] in (0, 1)


# ── 5. Offline: $json.content → pageContent ──────────────────────────


@pytest.mark.asyncio
async def test_offline_falls_back_to_content_field() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{"content": "from-content"}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    assert result[0][1][0].json["pageContent"] == "from-content"


@pytest.mark.asyncio
async def test_text_field_wins_over_content_field_when_both_present() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{"text": "from-text", "content": "from-content"}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    assert result[0][1][0].json["pageContent"] == "from-text"


# ── 6. Offline: binary data → base64-decoded UTF-8 ───────────────────


@pytest.mark.asyncio
async def test_offline_decodes_binary_via_json_wire_shape() -> None:
    """The wire shape is ``item.json['binary'][key]['data']`` base64."""
    encoded = base64.b64encode("binary-content".encode("utf-8")).decode("ascii")
    item = ExecutionItem(
        json={"binary": {"data": {"data": encoded, "mimeType": "text/plain"}}},
    )
    node = _node({})
    ctx = _ctx()

    result = await exec_document_default_data_loader(node, [item], ctx=ctx)
    out = result[0][1][0]
    assert out.json["pageContent"] == "binary-content"


@pytest.mark.asyncio
async def test_offline_decodes_binary_via_native_binaryfile() -> None:
    """The engine's native ``item.binary`` carries ``BinaryFile`` instances."""
    bf = BinaryFile.from_bytes(
        b"native-binary-content",
        file_name="note.txt",
        mime_type="text/plain",
    )
    item = ExecutionItem(json={}, binary={"data": bf})
    node = _node({})
    ctx = _ctx()

    result = await exec_document_default_data_loader(node, [item], ctx=ctx)
    assert result[0][1][0].json["pageContent"] == "native-binary-content"


# ── 7. Offline: missing all → JSON-serialized item.json ──────────────


@pytest.mark.asyncio
async def test_offline_falls_back_to_json_dump_when_no_source() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{"alpha": 1, "beta": "two"}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out = result[0][1][0]
    assert out.json["pageContent"] == '{"alpha": 1, "beta": "two"}'


@pytest.mark.asyncio
async def test_offline_handles_empty_item() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out = result[0][1][0]
    # Empty dict JSON-serializes to "{}"
    assert out.json["pageContent"] == "{}"
    assert out.json["metadata"]["source"] == "documentDefaultDataLoader"


# ── 8. options.metadata merged into metadata ────────────────────────


@pytest.mark.asyncio
async def test_options_metadata_merged_into_document_metadata() -> None:
    node = _node({"options": {"metadata": {"source": "user-supplied", "tag": "v1"}}})
    ctx = _ctx()
    items = _items([{"text": "hi"}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out = result[0][1][0]
    assert out.json["metadata"]["source"] == "user-supplied"
    assert out.json["metadata"]["tag"] == "v1"
    # itemIndex is still injected alongside user metadata
    assert out.json["metadata"]["itemIndex"] == 0


@pytest.mark.asyncio
async def test_metadata_omitted_when_options_metadata_absent() -> None:
    node = _node({"options": {}})
    ctx = _ctx()
    items = _items([{"text": "hi"}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    meta = result[0][1][0].json["metadata"]
    assert meta == {"source": "documentDefaultDataLoader", "itemIndex": 0}


# ── 9. Connected text splitter with chunkSize splits into chunks ───


@pytest.mark.asyncio
async def test_text_splitter_chunk_size_splits_into_chunks() -> None:
    splitter = ExecNode(
        id="sp1",
        name="Recursive Splitter",
        type="@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter",
        type_version=1,
        parameters={"chunkSize": 100, "chunkOverlap": 0},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    # 250 chars total, chunkSize 100 → 3 chunks (100 + 100 + 50)
    payload = "x" * 250
    node = _node({})
    ctx = _ctx(ai_inputs=[splitter])
    items = _items([{"text": payload}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 3
    assert [len(it.json["pageContent"]) for it in out_items] == [100, 100, 50]
    for idx, it in enumerate(out_items):
        assert it.json["pageContent"] == "x" * [100, 100, 50][idx]
        assert it.json["metadata"]["chunkIndex"] == idx
        assert it.json["metadata"]["source"] == "documentDefaultDataLoader"
        assert it.json["metadata"]["itemIndex"] == 0

    # Splitter config captured on ctx.lm_configs
    assert "sp1" in ctx.lm_configs
    assert ctx.lm_configs["sp1"]["parameters"]["chunkSize"] == 100


@pytest.mark.asyncio
async def test_text_splitter_uses_existing_lm_config_when_present() -> None:
    """If a prior pass already populated the splitter's config, we reuse it."""
    splitter = ExecNode(
        id="sp1",
        name="Splitter",
        type="@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter",
        type_version=1,
        parameters={},  # no chunkSize on the node itself
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node({})
    ctx = _ctx(
        ai_inputs=[splitter],
        lm_configs={
            "sp1": {
                "name": "Splitter",
                "type": splitter.type,
                "parameters": {"chunkSize": 50},
            }
        },
    )
    items = _items([{"text": "a" * 120}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    # 120 / 50 = 3 chunks (50, 50, 20)
    assert [len(it.json["pageContent"]) for it in out_items] == [50, 50, 20]
    assert [it.json["metadata"]["chunkIndex"] for it in out_items] == [0, 1, 2]


@pytest.mark.asyncio
async def test_no_chunking_when_text_fits_in_chunk_size() -> None:
    splitter = ExecNode(
        id="sp1",
        name="Splitter",
        type="@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter",
        type_version=1,
        parameters={"chunkSize": 1000},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node({})
    ctx = _ctx(ai_inputs=[splitter])
    items = _items([{"text": "short text"}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 1
    assert out_items[0].json["pageContent"] == "short text"
    # chunkIndex is not added when no chunking is required
    assert "chunkIndex" not in out_items[0].json["metadata"]


@pytest.mark.asyncio
async def test_text_splitter_without_chunk_size_is_a_no_op() -> None:
    splitter = ExecNode(
        id="sp1",
        name="Splitter",
        type="@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter",
        type_version=1,
        parameters={"chunkOverlap": 10},  # no chunkSize
        credentials=None,
        position={"x": 0, "y": 0},
    )
    node = _node({})
    ctx = _ctx(ai_inputs=[splitter])
    items = _items([{"text": "abcdefghij" * 50}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    # Without chunkSize the splitter is treated as not configured → 1 document
    assert len(out_items) == 1
    assert "chunkIndex" not in out_items[0].json["metadata"]


# ── 10. Multiple inputs produce multiple documents ──────────────────


@pytest.mark.asyncio
async def test_multiple_inputs_produce_one_document_each_offline() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items(
        [{"text": "a"}, {"text": "b"}, {"text": "c"}, {"text": "d"}, {"text": "e"}]
    )
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 5
    assert [it.json["pageContent"] for it in out_items] == ["a", "b", "c", "d", "e"]
    assert [it.json["metadata"]["itemIndex"] for it in out_items] == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_multiple_inputs_each_chunked() -> None:
    splitter = ExecNode(
        id="sp1",
        name="Splitter",
        type="@n8n/n8n-n8n-nodes-langchain.textSplitterRecursiveCharacter",  # intentional typo? no, fixed below
        type_version=1,
        parameters={"chunkSize": 10},
        credentials=None,
        position={"x": 0, "y": 0},
    )
    # Correct the type from the typo above so the test actually wires up.
    splitter.type = "@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter"
    node = _node({})
    ctx = _ctx(ai_inputs=[splitter])
    items = _items([{"text": "x" * 25}, {"text": "y" * 12}])

    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    out_items = result[0][1]
    # 25/10 = 3 chunks; 12/10 = 2 chunks → 5 output items
    assert len(out_items) == 5
    assert [len(it.json["pageContent"]) for it in out_items] == [10, 10, 5, 10, 2]
    assert [it.json["metadata"]["itemIndex"] for it in out_items] == [0, 0, 0, 1, 1]


# ── 11. parameters.text as expression overrides default order ───────


@pytest.mark.asyncio
async def test_parameters_text_as_expression_overrides_field() -> None:
    node = _node({"text": "={{ $json.body }}"})
    ctx = _ctx()
    items = _items([{"text": "wrong", "body": "right"}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    assert result[0][1][0].json["pageContent"] == "right"


@pytest.mark.asyncio
async def test_parameters_text_as_field_name_overrides_default() -> None:
    node = _node({"text": "body"})
    ctx = _ctx()
    items = _items([{"text": "wrong", "body": "right"}])
    result = await exec_document_default_data_loader(node, items, ctx=ctx)
    assert result[0][1][0].json["pageContent"] == "right"


# ── 12. Descriptor registration (CI invariant) ──────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert (
        "@n8n/n8n-nodes-langchain.documentDefaultDataLoader" in REGISTRY
    )
    assert (
        "@n8n/n8n-nodes-langchain.documentDefaultDataLoader" in SUPPORTED_NODE_TYPES
    )
    assert (
        SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.documentDefaultDataLoader"]
        == "ai"
    )
    desc = REGISTRY["@n8n/n8n-nodes-langchain.documentDefaultDataLoader"]
    assert desc.executor.endswith(":exec_document_default_data_loader")
    assert desc.category == "ai"


# ── 13. End-to-end: Manual Trigger → doc loader → Set sees pageContent ─


def _doc(nodes, connections):
    return {"name": "doc-default-loader-e2e", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_doc_loader_into_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "d1",
                "Document Loader",
                "@n8n/n8n-nodes-langchain.documentDefaultDataLoader",
                {},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "page",
                                "value": "={{ $json.pageContent }}",
                                "type": "string",
                            },
                            {
                                "name": "src",
                                "value": "={{ $json.metadata.source }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "Document Loader", "type": "main", "index": 0}]]
            },
            "Document Loader": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    mocks = {
        "document_output": [
            {
                "pageContent": "loaded-doc",
                "metadata": {"source": "documentDefaultDataLoader"},
            }
        ]
    }
    pin_data = {"Start": [{"text": "anything"}]}
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    loader_step = next(
        s for s in result.steps if s.node_name == "Document Loader"
    )
    assert loader_step.status == "success", loader_step.error
    assert loader_step.output_count == 1
    assert loader_step.sample_output[0]["json"]["pageContent"] == "loaded-doc"
    assert (
        loader_step.sample_output[0]["json"]["metadata"]["source"]
        == "documentDefaultDataLoader"
    )

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["page"] == "loaded-doc"
    assert set_step.sample_output[0]["json"]["src"] == "documentDefaultDataLoader"


@pytest.mark.asyncio
async def test_end_to_end_offline_doc_loader_into_set() -> None:
    """No mocks → offline extraction flows through to the downstream Set."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "d1",
                "Document Loader",
                "@n8n/n8n-nodes-langchain.documentDefaultDataLoader",
                {},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "page",
                                "value": "={{ $json.pageContent }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "Document Loader", "type": "main", "index": 0}]]
            },
            "Document Loader": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    pin_data = {"Start": [{"text": "the answer is 42"}]}
    engine = WorkflowEngine(doc)  # no mocks
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    loader_step = next(
        s for s in result.steps if s.node_name == "Document Loader"
    )
    assert loader_step.status == "success", loader_step.error
    assert loader_step.sample_output[0]["json"]["pageContent"] == "the answer is 42"

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["page"] == "the answer is 42"
