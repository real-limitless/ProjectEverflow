"""Tests for the Markdown node executor (n8n-nodes-base.markdown)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import (
    _convert_html_to_markdown,
    _convert_markdown_to_html,
    _convert_markdown_to_text,
    exec_markdown,
)


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="m1",
        name="Markdown",
        type="n8n-nodes-base.markdown",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx() -> EngineContext:
    g = type("G", (), {})()
    g.trigger_nodes = lambda preferred=None: []  # type: ignore
    return EngineContext(graph=g)  # type: ignore[arg-type]


def _doc(nodes, connections):
    return {"name": "markdown-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


def _result_items(result):
    out = []
    for _idx, items in result:
        for it in items:
            out.append(it.json)
    return out


# ── convertHtmlToMarkdown ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_convert_html_to_markdown_basic() -> None:
    items = [ExecutionItem(json={"html": (
        "<h1>Title</h1>"
        "<p>Hello <strong>world</strong> and <em>italic</em>.</p>"
        "<ul><li>one</li><li>two</li></ul>"
    )})]
    out = await exec_markdown(_node({"action": "convertHtmlToMarkdown"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert len(rendered) == 1
    md = rendered[0]["markdown"]
    assert "# Title" in md
    assert "**world**" in md
    assert "*italic*" in md
    assert "- one" in md
    assert "- two" in md


@pytest.mark.asyncio
async def test_convert_html_to_markdown_links_and_code() -> None:
    items = [ExecutionItem(json={"html": (
        '<p>Run <code>make build</code> then visit '
        '<a href="https://docs.example">docs</a>.</p>'
    )})]
    out = await exec_markdown(_node({"action": "convertHtmlToMarkdown"}), items, ctx=_ctx())
    md = _result_items(out)[0]["markdown"]
    assert "`make build`" in md
    assert "[docs](https://docs.example)" in md


@pytest.mark.asyncio
async def test_convert_html_to_markdown_headings_levels() -> None:
    items = [ExecutionItem(json={"html": (
        "<h1>one</h1><h2>two</h2><h3>three</h3><h6>six</h6>"
    )})]
    out = await exec_markdown(_node({"action": "convertHtmlToMarkdown"}), items, ctx=_ctx())
    md = _result_items(out)[0]["markdown"]
    assert "# one" in md
    assert "## two" in md
    assert "### three" in md
    assert "###### six" in md


@pytest.mark.asyncio
async def test_convert_html_to_markdown_blockquote() -> None:
    items = [ExecutionItem(json={"html": "<blockquote>quoted text</blockquote>"})]
    out = await exec_markdown(_node({"action": "convertHtmlToMarkdown"}), items, ctx=_ctx())
    md = _result_items(out)[0]["markdown"]
    assert "> quoted text" in md


@pytest.mark.asyncio
async def test_convert_html_to_markdown_pre_block() -> None:
    items = [ExecutionItem(json={"html": (
        "<pre>plain code\nwith two lines</pre>"
    )})]
    out = await exec_markdown(_node({"action": "convertHtmlToMarkdown"}), items, ctx=_ctx())
    md = _result_items(out)[0]["markdown"]
    assert "```" in md
    assert "plain code" in md
    assert "with two lines" in md


@pytest.mark.asyncio
async def test_convert_html_to_markdown_ordered_list() -> None:
    items = [ExecutionItem(json={"html": (
        "<ol><li>first</li><li>second</li></ol>"
    )})]
    out = await exec_markdown(_node({"action": "convertHtmlToMarkdown"}), items, ctx=_ctx())
    md = _result_items(out)[0]["markdown"]
    assert "1. first" in md
    assert "2. second" in md


@pytest.mark.asyncio
async def test_convert_html_to_markdown_one_item_per_input() -> None:
    items = [
        ExecutionItem(json={"html": "<p>one</p>"}),
        ExecutionItem(json={"html": "<p>two</p>"}),
        ExecutionItem(json={"html": ""}),
    ]
    out = await exec_markdown(_node({"action": "convertHtmlToMarkdown"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert [r["markdown"] for r in rendered] == ["one", "two", ""]


# ── convertMarkdownToHtml (delegates to html node helper) ─────────────


@pytest.mark.asyncio
async def test_convert_markdown_to_html_basic() -> None:
    items = [ExecutionItem(json={"markdown": (
        "# Title\n\n"
        "Hello **world** and *italic*.\n\n"
        "- one\n- two\n"
    )})]
    out = await exec_markdown(_node({"action": "convertMarkdownToHtml"}), items, ctx=_ctx())
    html = _result_items(out)[0]["html"]
    assert "<h1>Title</h1>" in html
    assert "<strong>world</strong>" in html
    assert "<em>italic</em>" in html
    assert "<ul>" in html and "<li>one</li>" in html and "<li>two</li>" in html


@pytest.mark.asyncio
async def test_convert_markdown_to_html_links_and_code() -> None:
    items = [ExecutionItem(json={"markdown": (
        "Run `make build` then visit [docs](https://docs.example)."
    )})]
    out = await exec_markdown(_node({"action": "convertMarkdownToHtml"}), items, ctx=_ctx())
    html = _result_items(out)[0]["html"]
    assert "<code>make build</code>" in html
    assert '<a href="https://docs.example">docs</a>' in html


@pytest.mark.asyncio
async def test_convert_markdown_to_html_matches_html_node() -> None:
    """The markdown node's convertMarkdownToHtml must agree with the
    HTML node's convertMarkdownToHtml — both use the shared helper."""
    source = "# H\n\n**bold** and `code`\n\n- a\n- b\n"
    items = [ExecutionItem(json={"markdown": source})]
    out = await exec_markdown(_node({"action": "convertMarkdownToHtml"}), items, ctx=_ctx())
    rendered = _result_items(out)[0]["html"]
    assert rendered == _convert_markdown_to_html(source)


# ── convertToText ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_convert_to_text_strips_markdown() -> None:
    items = [ExecutionItem(json={"markdown": (
        "# Title\n\n"
        "Hello **world** and *italic*.\n\n"
        "- one\n- two\n"
    )})]
    out = await exec_markdown(_node({"action": "convertToText"}), items, ctx=_ctx())
    text = _result_items(out)[0]["text"]
    assert "Title" in text
    assert "Hello world and italic." in text
    assert "- one" in text
    assert "- two" in text
    assert "**" not in text
    assert "# " not in text  # heading marker gone


@pytest.mark.asyncio
async def test_convert_to_text_flattens_links() -> None:
    items = [ExecutionItem(json={"markdown": "See [docs](https://docs.example)."})]
    out = await exec_markdown(_node({"action": "convertToText"}), items, ctx=_ctx())
    text = _result_items(out)[0]["text"]
    assert text == "See docs (https://docs.example)."


@pytest.mark.asyncio
async def test_convert_to_text_handles_code_fences() -> None:
    items = [ExecutionItem(json={"markdown": (
        "Before\n```\nfoo bar\nbaz\n```\nAfter"
    )})]
    out = await exec_markdown(_node({"action": "convertToText"}), items, ctx=_ctx())
    text = _result_items(out)[0]["text"]
    assert "foo bar" in text
    assert "baz" in text
    assert "```" not in text


@pytest.mark.asyncio
async def test_convert_to_text_handles_inline_code() -> None:
    items = [ExecutionItem(json={"markdown": "Run `make build` first."})]
    out = await exec_markdown(_node({"action": "convertToText"}), items, ctx=_ctx())
    text = _result_items(out)[0]["text"]
    assert text == "Run make build first."
    assert "`" not in text


@pytest.mark.asyncio
async def test_convert_to_text_collapses_blank_lines() -> None:
    items = [ExecutionItem(json={"markdown": "a\n\n\n\n\nb"})]
    out = await exec_markdown(_node({"action": "convertToText"}), items, ctx=_ctx())
    text = _result_items(out)[0]["text"]
    assert text == "a\n\nb"


# ── Round-trip-ish ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_html_markdown_html_basic_equivalence() -> None:
    """HTML → Markdown → HTML should preserve the high-level structure."""
    html_in = (
        "<h1>Title</h1>"
        "<p>Hello <strong>world</strong>!</p>"
        "<ul><li>one</li><li>two</li></ul>"
    )
    items = [ExecutionItem(json={"html": html_in})]
    md_out = await exec_markdown(
        _node({"action": "convertHtmlToMarkdown"}), items, ctx=_ctx()
    )
    md = _result_items(md_out)[0]["markdown"]

    md_items = [ExecutionItem(json={"markdown": md})]
    html_out = await exec_markdown(
        _node({"action": "convertMarkdownToHtml"}), md_items, ctx=_ctx()
    )
    html_back = _result_items(html_out)[0]["html"]

    # Each top-level construct round-trips intact.
    assert "<h1>Title</h1>" in html_back
    assert "<strong>world</strong>" in html_back
    assert "<ul>" in html_back
    assert "<li>one</li>" in html_back
    assert "<li>two</li>" in html_back


@pytest.mark.asyncio
async def test_markdown_html_markdown_text_stable() -> None:
    """Markdown → HTML → Markdown → Text converges to the same plain text."""
    md_in = (
        "# Title\n\n"
        "Hello **world** and *italic*.\n\n"
        "- one\n- two\n"
    )
    md_items = [ExecutionItem(json={"markdown": md_in})]
    html_out = await exec_markdown(
        _node({"action": "convertMarkdownToHtml"}), md_items, ctx=_ctx()
    )
    html = _result_items(html_out)[0]["html"]

    html_items = [ExecutionItem(json={"html": html})]
    md2_out = await exec_markdown(
        _node({"action": "convertHtmlToMarkdown"}), html_items, ctx=_ctx()
    )
    md2 = _result_items(md2_out)[0]["markdown"]

    md2_items = [ExecutionItem(json={"markdown": md2})]
    text_out = await exec_markdown(
        _node({"action": "convertToText"}), md2_items, ctx=_ctx()
    )
    text2 = _result_items(text_out)[0]["text"]

    text_in_items = [ExecutionItem(json={"markdown": md_in})]
    text_in_out = await exec_markdown(
        _node({"action": "convertToText"}), text_in_items, ctx=_ctx()
    )
    text_in = _result_items(text_in_out)[0]["text"]

    assert text2 == text_in


# ── Custom dataProperty ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_convert_uses_custom_data_property() -> None:
    items = [ExecutionItem(json={"raw": "<p>hello</p>"})]
    out = await exec_markdown(
        _node({"action": "convertHtmlToMarkdown", "dataProperty": "raw"}),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    # ``dataProperty`` is both input and output — the same field is
    # overwritten with the Markdown result.
    assert rendered[0]["raw"] == "hello"


# ── Unknown action ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_action_raises() -> None:
    items = [ExecutionItem(json={"html": "<p>x</p>"})]
    node = _node({"action": "scrub"})
    with pytest.raises(ValueError, match="unsupported action"):
        await exec_markdown(node, items, ctx=_ctx())


# ── Direct helper coverage ───────────────────────────────────────────


def test_helper_html_to_markdown_br_emits_linebreak() -> None:
    md = _convert_html_to_markdown("<p>line one<br>line two</p>")
    assert "line one" in md
    assert "line two" in md


def test_helper_markdown_to_text_keeps_blockquote_marker() -> None:
    text = _convert_markdown_to_text("> quoted\n> line two")
    assert "quoted" in text
    assert "line two" in text
    # ``>`` is stripped (the helper is plain text, not a marker).
    assert ">" not in text


# ── Descriptor & end-to-end ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.markdown" in REGISTRY
    assert "n8n-nodes-base.markdown" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.markdown"] == "transform"
    desc = REGISTRY["n8n-nodes-base.markdown"]
    assert desc.executor.endswith(":exec_markdown")
    assert desc.category == "transform"


@pytest.mark.asyncio
async def test_end_to_end_manual_markdown_set() -> None:
    """Manual (pinned HTML) → Markdown → Set sees the markdown field."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("m1", "Md", "n8n-nodes-base.markdown", {
                "action": "convertHtmlToMarkdown",
                "dataProperty": "html",
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "first_line", "value": "={{ $json.html }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Md", "type": "main", "index": 0}]]},
            "Md": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    pinned_html = (
        "<h1>Title</h1><p>Hello <strong>world</strong>!</p>"
        "<ul><li>one</li><li>two</li></ul>"
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(
        trigger="manual",
        pin_data={"Start": [{"html": pinned_html}]},
    )
    assert result.status == "success", result.error_message

    md_step = next(s for s in result.steps if s.node_name == "Md")
    assert md_step.status == "success"
    assert md_step.output_count == 1

    final = result.final_items
    assert final, "expected at least one final item"
    seen = []
    for item in final:
        if not isinstance(item, dict):
            continue
        fjson = item.get("json")
        if isinstance(fjson, dict):
            seen.append(fjson.get("first_line"))
    assert any(isinstance(v, str) and "# Title" in v for v in seen)
    assert any(isinstance(v, str) and "**world**" in v for v in seen)
    assert any(isinstance(v, str) and "- one" in v for v in seen)
