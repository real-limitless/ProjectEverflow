"""Tests for the Recursive Character Text Splitter executor
(``textSplitterRecursiveCharacter``).

Covers:

- ``ctx.mocks['splitter_output']`` returning a list of strings
- ``ctx.mocks['splitter_output']`` as a callable that receives
  ``(text, params)``
- ``ctx.mocks['splitter_output']`` returning ``{pageContent}`` documents
- ``ctx.mocks['document_output']`` mock with ``pageContent`` documents
- Offline: default ``chunkSize=1000`` / ``chunkOverlap=200`` splits long text
- Offline: custom ``chunkSize=100`` / ``chunkOverlap=10`` produces sized chunks
- Offline: text shorter than ``chunkSize`` yields 1 chunk
- Offline: empty text yields 0 chunks
- ``parameters.text`` is evaluated as an n8n expression (``$json.x``)
- Multiple input items are each split independently
- ``separators: ["\\n\\n"]`` produces paragraph-level chunks
- ``parameters.options.chunkSize/chunkOverlap`` fallback
- Descriptor registration (CI invariant)
- End-to-end: Manual Trigger → textSplitterRecursiveCharacter → Set sees
  ``text`` and ``chunkIndex``
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes.llm_agent import exec_text_splitter_recursive_character


# ── Helpers ────────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None,
    *,
    id_: str = "sp1",
    name: str = "Recursive Splitter",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    mocks: dict[str, Any] | None = None,
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
        mocks=mocks or {},
    )


def _items(rows: list[dict[str, Any]] | None = None):
    return items_from_json_list(rows or [])


# ── 1. splitter_output mock returns a list of strings ─────────────────


@pytest.mark.asyncio
async def test_splitter_output_mock_list_of_strings() -> None:
    node = _node({})
    ctx = _ctx(
        mocks={"splitter_output": ["alpha", "beta", "gamma"]}
    )
    items = _items([{"text": "ignored when mock is set"}])

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    assert len(result) == 1 and result[0][0] == 0
    out_items = result[0][1]
    assert [it.json["text"] for it in out_items] == ["alpha", "beta", "gamma"]
    assert [it.json["chunkIndex"] for it in out_items] == [0, 1, 2]
    for it in out_items:
        assert it.json["source"] == "textSplitterRecursiveCharacter"
        assert it.json["totalChunks"] == 3


# ── 2. splitter_output callable mock receives (text, params) ──────────


@pytest.mark.asyncio
async def test_splitter_output_callable_mock_receives_text_and_params() -> None:
    captured: list[tuple[Any, Any]] = []

    def fake(text, params):
        captured.append((text, params))
        # Return one chunk per word so the test can assert deterministically.
        return text.split()

    node = _node({"chunkSize": 50, "chunkOverlap": 5})
    ctx = _ctx(mocks={"splitter_output": fake})
    items = _items([{"text": "hello world foo"}])

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["text"] for it in out_items] == ["hello", "world", "foo"]
    assert [it.json["chunkIndex"] for it in out_items] == [0, 1, 2]
    assert out_items[0].json["totalChunks"] == 3

    assert len(captured) == 1
    text, params = captured[0]
    assert text == "hello world foo"
    assert params == {
        "chunkSize": 50,
        "chunkOverlap": 5,
        "separators": ["\n\n", "\n", " ", ""],
    }


@pytest.mark.asyncio
async def test_splitter_output_callable_returning_single_string() -> None:
    node = _node({})
    ctx = _ctx(mocks={"splitter_output": lambda text, params: "single-chunk"})
    items = _items([{"text": "anything"}])
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 1
    assert out_items[0].json["text"] == "single-chunk"
    assert out_items[0].json["totalChunks"] == 1


@pytest.mark.asyncio
async def test_splitter_output_with_page_content_documents() -> None:
    """Mock can also return ``{pageContent}`` docs (LangChain-style)."""
    node = _node({})
    ctx = _ctx(
        mocks={
            "splitter_output": [
                {"pageContent": "doc-1", "metadata": {"src": "a"}},
                {"pageContent": "doc-2", "metadata": {"src": "b"}},
            ]
        }
    )
    items = _items([{"text": "ignored"}])
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["text"] for it in out_items] == ["doc-1", "doc-2"]


# ── 3. document_output mock with pageContent ─────────────────────────


@pytest.mark.asyncio
async def test_document_output_mock_used_when_no_splitter_mock() -> None:
    node = _node({})
    ctx = _ctx(
        mocks={
            "document_output": [
                {"pageContent": "from-doc-1", "metadata": {}},
                {"pageContent": "from-doc-2", "metadata": {}},
                {"pageContent": "from-doc-3", "metadata": {}},
            ]
        }
    )
    items = _items([{"text": "ignored"}])
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert [it.json["text"] for it in out_items] == [
        "from-doc-1",
        "from-doc-2",
        "from-doc-3",
    ]
    assert out_items[0].json["chunkIndex"] == 0
    assert out_items[-1].json["totalChunks"] == 3


@pytest.mark.asyncio
async def test_splitter_output_wins_over_document_output() -> None:
    node = _node({})
    ctx = _ctx(
        mocks={
            "splitter_output": ["via-splitter"],
            "document_output": [{"pageContent": "via-doc"}],
        }
    )
    items = _items([{"text": "x"}])
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert out_items[0].json["text"] == "via-splitter"


# ── 4. Offline: default chunkSize/chunkOverlap splits long text ───────


@pytest.mark.asyncio
async def test_offline_default_chunk_size_splits_long_text() -> None:
    # 2500 chars > default chunkSize=1000 → at least 3 chunks
    payload = "x" * 2500
    node = _node({})  # no parameters → defaults
    ctx = _ctx()
    items = _items([{"text": payload}])

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) >= 3
    for idx, it in enumerate(out_items):
        assert it.json["chunkIndex"] == idx
        assert it.json["source"] == "textSplitterRecursiveCharacter"
        assert it.json["totalChunks"] == len(out_items)
        assert len(it.json["text"]) <= 1000
    # Concatenating chunk text (which overlaps by ``chunkOverlap``) must
    # cover the full payload when we drop the overlap region. The simpler
    # check: every chunk starts at a position covered by the running
    # non-overlap "head" of the previous chunks.
    head = out_items[0].json["text"]
    for prev, nxt in zip(out_items, out_items[1:]):
        prev_text = prev.json["text"]
        nxt_text = nxt.json["text"]
        # Overlap of 200 means the last 200 chars of the previous chunk
        # equal the first 200 chars of the next chunk.
        assert prev_text[-200:] == nxt_text[:200]
    # And the final chunk ends the original payload.
    assert out_items[-1].json["text"].endswith("x" * 200)


# ── 5. Offline: custom chunkSize=100 chunkOverlap=10 ─────────────────


@pytest.mark.asyncio
async def test_offline_custom_chunk_size_and_overlap() -> None:
    payload = "abcdefghij" * 30  # 300 chars
    node = _node({"chunkSize": 100, "chunkOverlap": 10})
    ctx = _ctx()
    items = _items([{"text": payload}])

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # Every chunk must be within the configured size, and overlap must be
    # carried (visible as trailing chars of chunk N reappearing in chunk N+1).
    for it in out_items:
        assert len(it.json["text"]) <= 100
    # The first chunk should be the configured 100 chars.
    assert len(out_items[0].json["text"]) == 100
    # Overlap of 10: the last 10 chars of chunk 0 should be the first 10 of
    # chunk 1 (since separators are joins of contiguous substrings).
    first_tail = out_items[0].json["text"][-10:]
    second_head = out_items[1].json["text"][:10]
    assert first_tail == second_head
    # totalChunks is correct
    for idx, it in enumerate(out_items):
        assert it.json["totalChunks"] == len(out_items)
        assert it.json["chunkIndex"] == idx


# ── 6. Offline: text shorter than chunkSize yields 1 chunk ────────────


@pytest.mark.asyncio
async def test_offline_short_text_yields_single_chunk() -> None:
    node = _node({"chunkSize": 1000, "chunkOverlap": 200})
    ctx = _ctx()
    items = _items([{"text": "short text"}])

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 1
    assert out_items[0].json["text"] == "short text"
    assert out_items[0].json["chunkIndex"] == 0
    assert out_items[0].json["totalChunks"] == 1
    assert out_items[0].json["chunkSize"] == len("short text")


# ── 7. Offline: empty text yields 0 chunks ────────────────────────────


@pytest.mark.asyncio
async def test_offline_empty_text_yields_no_chunks() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{"text": ""}, {"text": "non-empty"}])

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # Only the non-empty item yields a chunk.
    assert len(out_items) == 1
    assert out_items[0].json["text"] == "non-empty"


@pytest.mark.asyncio
async def test_offline_all_empty_text_yields_no_chunks() -> None:
    node = _node({})
    ctx = _ctx()
    items = _items([{"text": ""}, {"text": ""}])
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert out_items == []


# ── 8. parameters.text expression evaluation ──────────────────────────


@pytest.mark.asyncio
async def test_parameters_text_expression_evaluates_json_field() -> None:
    node = _node({"text": "={{ $json.body }}", "chunkSize": 50, "chunkOverlap": 0})
    ctx = _ctx()
    items = _items(
        [
            {"text": "ignored", "body": "abcdefghij" * 10},  # 100 chars
            {"text": "ignored", "body": "short"},
        ]
    )

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # First item: 100 / 50 = 2 chunks
    assert len(out_items) == 3
    assert out_items[0].json["text"] == "abcdefghij" * 5
    assert out_items[1].json["text"] == "abcdefghij" * 5
    assert out_items[2].json["text"] == "short"


@pytest.mark.asyncio
async def test_parameters_text_as_field_name() -> None:
    """Plain string ``text`` is treated as a JSON field name."""
    node = _node({"text": "body", "chunkSize": 100, "chunkOverlap": 0})
    ctx = _ctx()
    items = _items([{"text": "wrong", "body": "abc" * 40}])  # 120 chars
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # 120 chars with chunkSize 100, no overlap → 2 chunks (100 + 20).
    assert len(out_items) == 2
    assert len(out_items[0].json["text"]) == 100
    assert len(out_items[1].json["text"]) == 20
    # Reconstructing the body field must produce the original 120 chars.
    assert "".join(it.json["text"] for it in out_items) == "abc" * 40


@pytest.mark.asyncio
async def test_falls_back_to_page_content_field() -> None:
    node = _node({"chunkSize": 100, "chunkOverlap": 0})
    ctx = _ctx()
    items = _items([{"pageContent": "from-page"}])  # no `text` field
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 1
    assert out_items[0].json["text"] == "from-page"


# ── 9. Multiple input items each split independently ─────────────────


@pytest.mark.asyncio
async def test_multiple_items_each_split_independently() -> None:
    node = _node({"chunkSize": 10, "chunkOverlap": 0})
    ctx = _ctx()
    items = _items(
        [
            {"text": "x" * 25},  # → 3 chunks
            {"text": "y" * 12},  # → 2 chunks
            {"text": "short"},  # → 1 chunk
        ]
    )
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 6
    lengths = [len(it.json["text"]) for it in out_items]
    assert lengths == [10, 10, 5, 10, 2, 5]
    # totalChunks reflects per-item counts
    assert [it.json["totalChunks"] for it in out_items] == [3, 3, 3, 2, 2, 1]
    # chunkIndex is per-item
    assert [it.json["chunkIndex"] for it in out_items] == [0, 1, 2, 0, 1, 0]


# ── 10. Separators: ["\n\n"] produces paragraph-level chunks ─────────


@pytest.mark.asyncio
async def test_separators_paragraph_level_chunks() -> None:
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    node = _node(
        {
            "chunkSize": 15,
            "chunkOverlap": 0,
            "separators": ["\n\n", " "],
        }
    )
    ctx = _ctx()
    items = _items([{"text": text}])

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # The first-level split on "\n\n" yields 3 paragraph pieces (each
    # with the trailing separator preserved). chunkSize 15 then
    # sub-splits the longer ones on " ". All chunks fit within 15.
    joined = "".join(it.json["text"] for it in out_items)
    # Trailing separator may cause a final newline to be appended.
    assert joined.rstrip() == text
    for it in out_items:
        assert len(it.json["text"]) <= 15
    # And each chunk is a non-empty substring that survives the join.
    assert len(out_items) >= 3


@pytest.mark.asyncio
async def test_separators_hierarchy_falls_back_to_space() -> None:
    """With no newlines the splitter must still break on spaces."""
    text = "alpha beta gamma delta epsilon"
    node = _node(
        {
            "chunkSize": 12,
            "chunkOverlap": 0,
            "separators": ["\n\n", "\n", " "],
        }
    )
    ctx = _ctx()
    items = _items([{"text": text}])

    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # All chunks must be within size limit.
    for it in out_items:
        assert len(it.json["text"]) <= 12
    # The splitter preserves separator suffixes on each piece, so the
    # concatenated text (modulo the final chunk's tail) reconstructs the
    # original — strip trailing whitespace to be tolerant of that suffix.
    joined = "".join(it.json["text"] for it in out_items)
    assert joined == text


# ── 11. options.chunkSize / options.chunkOverlap fallback ─────────────


@pytest.mark.asyncio
async def test_options_chunk_size_fallback() -> None:
    node = _node(
        {"options": {"chunkSize": 7, "chunkOverlap": 0}}
    )
    ctx = _ctx()
    items = _items([{"text": "abcdefghij" * 5}])  # 50 chars
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # Top-level chunkSize absent → falls back to options.chunkSize=7.
    assert all(len(it.json["text"]) <= 7 for it in out_items)
    assert len(out_items) >= 5


@pytest.mark.asyncio
async def test_top_level_chunk_size_wins_over_options() -> None:
    node = _node(
        {
            "chunkSize": 5,
            "chunkOverlap": 0,
            "options": {"chunkSize": 100, "chunkOverlap": 0},
        }
    )
    ctx = _ctx()
    items = _items([{"text": "abcdefghij" * 3}])  # 30 chars
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert all(len(it.json["text"]) <= 5 for it in out_items)


@pytest.mark.asyncio
async def test_invalid_chunk_size_falls_back_to_default() -> None:
    node = _node({"chunkSize": "not-a-number"})
    ctx = _ctx()
    items = _items([{"text": "hello"}])
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # Default chunkSize 1000; "hello" fits → 1 chunk
    assert len(out_items) == 1
    assert out_items[0].json["text"] == "hello"


# ── 12. Overlap is clamped to chunkSize - 1 ───────────────────────────


@pytest.mark.asyncio
async def test_overlap_clamps_to_chunk_size() -> None:
    node = _node({"chunkSize": 20, "chunkOverlap": 100})
    ctx = _ctx()
    items = _items([{"text": "abcdefghij" * 4}])  # 40 chars
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    # overlap cannot exceed chunkSize-1 → chunk_overlap effective = 19
    for it in out_items:
        assert len(it.json["text"]) <= 20


# ── 13. Output shape / metadata ───────────────────────────────────────


@pytest.mark.asyncio
async def test_output_shape_includes_required_fields() -> None:
    node = _node({"chunkSize": 5, "chunkOverlap": 0})
    ctx = _ctx()
    items = _items([{"text": "abcdefghij", "extra": "value"}])
    result = await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    out_items = result[0][1]
    assert len(out_items) == 2
    for idx, it in enumerate(out_items):
        assert set(
            ["text", "chunkIndex", "chunkSize", "source", "totalChunks"]
        ).issubset(it.json.keys())
        assert it.json["source"] == "textSplitterRecursiveCharacter"
        assert it.json["chunkIndex"] == idx
        assert it.json["totalChunks"] == 2
        # Upstream fields are preserved
        assert it.json["extra"] == "value"


@pytest.mark.asyncio
async def test_captures_params_on_lm_configs() -> None:
    node = _node(
        {"chunkSize": 42, "chunkOverlap": 7, "separators": ["\n", " "]}
    )
    ctx = _ctx()
    items = _items([{"text": "x"}])
    await exec_text_splitter_recursive_character(node, items, ctx=ctx)
    assert "sp1" in ctx.lm_configs
    assert ctx.lm_configs["sp1"]["parameters"]["chunkSize"] == 42
    assert ctx.lm_configs["sp1"]["parameters"]["chunkOverlap"] == 7
    assert ctx.lm_configs["sp1"]["parameters"]["separators"] == ["\n", " "]


# ── 14. Descriptor registration (CI invariant) ────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert (
        "@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter" in REGISTRY
    )
    assert (
        "@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter"
        in SUPPORTED_NODE_TYPES
    )
    assert (
        SUPPORTED_NODE_TYPES[
            "@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter"
        ]
        == "ai"
    )
    desc = REGISTRY[
        "@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter"
    ]
    assert desc.executor.endswith(":exec_text_splitter_recursive_character")
    assert desc.category == "ai"


# ── 15. End-to-end: Manual Trigger → splitter → Set ───────────────────


def _doc(nodes, connections):
    return {
        "name": "text-splitter-recursive-e2e",
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
async def test_end_to_end_manual_splitter_into_set_with_mock() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "sp1",
                "Recursive Splitter",
                "@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter",
                {"chunkSize": 50, "chunkOverlap": 0},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "first",
                                "value": "={{ $json.text }}",
                                "type": "string",
                            },
                            {
                                "name": "idx",
                                "value": "={{ $json.chunkIndex }}",
                                "type": "number",
                            },
                            {
                                "name": "src",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "Recursive Splitter", "type": "main", "index": 0}]]
            },
            "Recursive Splitter": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    mocks = {
        "splitter_output": ["chunk-1", "chunk-2"],
    }
    pin_data = {"Start": [{"text": "ignored by mock"}]}
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    splitter_step = next(
        s for s in result.steps if s.node_name == "Recursive Splitter"
    )
    assert splitter_step.status == "success", splitter_step.error
    assert splitter_step.output_count == 2
    assert splitter_step.sample_output[0]["json"]["text"] == "chunk-1"
    assert splitter_step.sample_output[0]["json"]["chunkIndex"] == 0
    assert (
        splitter_step.sample_output[0]["json"]["source"]
        == "textSplitterRecursiveCharacter"
    )
    assert splitter_step.sample_output[0]["json"]["totalChunks"] == 2

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    # The Set node ran on each chunk.
    outputs = [s["json"] for s in set_step.sample_output]
    assert len(outputs) == 2
    assert outputs[0]["first"] == "chunk-1"
    assert outputs[0]["idx"] == 0
    assert outputs[0]["src"] == "textSplitterRecursiveCharacter"
    assert outputs[1]["first"] == "chunk-2"
    assert outputs[1]["idx"] == 1


@pytest.mark.asyncio
async def test_end_to_end_offline_splitter_into_set() -> None:
    """No mocks → offline recursive split flows through to downstream Set."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "sp1",
                "Recursive Splitter",
                "@n8n/n8n-nodes-langchain.textSplitterRecursiveCharacter",
                {
                    "chunkSize": 10,
                    "chunkOverlap": 0,
                    "separators": [" "],
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
                                "name": "first_chunk",
                                "value": "={{ $json.text }}",
                                "type": "string",
                            },
                            {
                                "name": "first_index",
                                "value": "={{ $json.chunkIndex }}",
                                "type": "number",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "Recursive Splitter", "type": "main", "index": 0}]]
            },
            "Recursive Splitter": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    pin_data = {"Start": [{"text": "alpha beta gamma delta epsilon"}]}
    engine = WorkflowEngine(doc)  # no mocks
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    splitter_step = next(
        s for s in result.steps if s.node_name == "Recursive Splitter"
    )
    assert splitter_step.status == "success", splitter_step.error
    # The splitter must have produced multiple chunks; capture the first.
    first_text = splitter_step.sample_output[0]["json"]["text"]
    assert len(first_text) <= 10
    assert splitter_step.sample_output[0]["json"]["chunkIndex"] == 0
    assert (
        splitter_step.sample_output[0]["json"]["source"]
        == "textSplitterRecursiveCharacter"
    )
    total = splitter_step.sample_output[0]["json"]["totalChunks"]
    assert total >= 2

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    # The engine caps sample_output to the first 3 items, so compare against
    # the step's output_count rather than len(sample_output).
    assert set_step.output_count == total
    outputs = [s["json"] for s in set_step.sample_output]
    assert outputs[0]["first_chunk"] == first_text
    assert outputs[0]["first_index"] == 0
