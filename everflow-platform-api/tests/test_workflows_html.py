"""Tests for the HTML node executor (n8n-nodes-base.html)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import exec_html


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="h1",
        name="Html",
        type="n8n-nodes-base.html",
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
    return {"name": "html-test", "nodes": nodes, "connections": connections}


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


# ── htmlToText ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_html_to_text_strips_tags_and_preserves_whitespace() -> None:
    items = [ExecutionItem(json={"html": "<p>Hello <b>world</b>!</p><p>Line 2</p>"})]
    out = await exec_html(_node({"action": "htmlToText"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert len(rendered) == 1
    assert "Hello world!" in rendered[0]["text"]
    assert "<p>" not in rendered[0]["text"]


@pytest.mark.asyncio
async def test_html_to_text_decodes_entities() -> None:
    items = [ExecutionItem(json={"html": "<p>Tom &amp; Jerry &lt;3</p>"})]
    out = await exec_html(_node({"action": "htmlToText"}), items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert "Tom & Jerry <3" in rendered["text"]


@pytest.mark.asyncio
async def test_html_to_text_one_item_per_input() -> None:
    items = [
        ExecutionItem(json={"html": "<p>one</p>"}),
        ExecutionItem(json={"html": "<p>two</p>"}),
        ExecutionItem(json={"html": ""}),
    ]
    out = await exec_html(_node({"action": "htmlToText"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert [r["text"] for r in rendered] == ["one", "two", ""]


@pytest.mark.asyncio
async def test_html_to_text_custom_data_property() -> None:
    """``dataProperty`` names the input field; the same name receives the
    stripped-text output (per the clean-room design where ``dataProperty``
    is the single channel the user wires up)."""
    items = [ExecutionItem(json={"raw": "<p>payload</p>"})]
    node = _node({
        "action": "htmlToText",
        "dataProperty": "raw",
    })
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    # The input HTML is read from "raw" and the stripped text is written
    # back into the same field, leaving "raw" holding the plain string.
    assert "payload" in rendered[0]["raw"]


# ── extractHtmlContent ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_html_content_by_tag() -> None:
    items = [ExecutionItem(json={"html": "<div><p>alpha</p><p>beta</p></div>"})]
    node = _node({"action": "extractHtmlContent", "cssQuery": "p"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert [r["text"] for r in rendered] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_extract_html_content_by_class() -> None:
    items = [ExecutionItem(json={"html": '<p class="lead">first</p><p>second</p>'})]
    node = _node({"action": "extractHtmlContent", "cssQuery": ".lead"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert len(rendered) == 1
    assert "first" in rendered[0]["text"]


@pytest.mark.asyncio
async def test_extract_html_content_by_tag_class() -> None:
    items = [ExecutionItem(json={
        "html": '<p class="lead">lead</p><span class="lead">nope</span>',
    })]
    node = _node({"action": "extractHtmlContent", "cssQuery": "p.lead"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert len(rendered) == 1
    assert "lead" in rendered[0]["text"]


@pytest.mark.asyncio
async def test_extract_html_content_by_id() -> None:
    items = [ExecutionItem(json={"html": '<div id="hero">hi</div><div>bye</div>'})]
    node = _node({"action": "extractHtmlContent", "cssQuery": "#hero"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert len(rendered) == 1
    assert "hi" in rendered[0]["text"]


@pytest.mark.asyncio
async def test_extract_html_content_no_match_yields_no_items() -> None:
    items = [ExecutionItem(json={"html": "<p>only</p>"})]
    node = _node({"action": "extractHtmlContent", "cssQuery": ".missing"})
    out = await exec_html(node, items, ctx=_ctx())
    assert _result_items(out) == []


@pytest.mark.asyncio
async def test_extract_html_content_missing_selector_raises() -> None:
    items = [ExecutionItem(json={"html": "<p>x</p>"})]
    node = _node({"action": "extractHtmlContent"})
    with pytest.raises(ValueError, match="cssQuery"):
        await exec_html(node, items, ctx=_ctx())


# ── extractHtmlLinkUrls ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_link_urls_returns_hrefs() -> None:
    items = [ExecutionItem(json={"html": (
        '<a href="https://a.example">A</a>'
        '<a href="/local">B</a>'
        '<a>no href</a>'
        '<a href="">empty</a>'
    )})]
    node = _node({"action": "extractHtmlLinkUrls"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert [r["url"] for r in rendered] == ["https://a.example", "/local"]


@pytest.mark.asyncio
async def test_extract_link_urls_empty_html_yields_no_items() -> None:
    items = [ExecutionItem(json={"html": ""})]
    node = _node({"action": "extractHtmlLinkUrls"})
    out = await exec_html(node, items, ctx=_ctx())
    assert _result_items(out) == []


# ── convertMarkdownToHtml ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_convert_markdown_to_html_basic() -> None:
    items = [ExecutionItem(json={"markdown": (
        "# Title\n\n"
        "Hello **world** and *italic*.\n\n"
        "- one\n- two\n"
    )})]
    node = _node({"action": "convertMarkdownToHtml"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    html = rendered[0]["html"]
    assert "<h1>Title</h1>" in html
    assert "<strong>world</strong>" in html
    assert "<em>italic</em>" in html
    assert "<ul>" in html and "<li>one</li>" in html and "<li>two</li>" in html


@pytest.mark.asyncio
async def test_convert_markdown_to_html_links_and_code() -> None:
    items = [ExecutionItem(json={"markdown": (
        "Run `make build` then visit [docs](https://docs.example)."
    )})]
    node = _node({"action": "convertMarkdownToHtml"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    html = rendered[0]["html"]
    assert '<code>make build</code>' in html
    assert '<a href="https://docs.example">docs</a>' in html


@pytest.mark.asyncio
async def test_convert_markdown_to_html_fenced_code_block() -> None:
    items = [ExecutionItem(json={"markdown": (
        "```\nplain <text> & ampersand\n```\n"
    )})]
    node = _node({"action": "convertMarkdownToHtml"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    html = rendered[0]["html"]
    assert "<pre><code>" in html
    assert "&amp;" in html  # entity escaped
    assert "<text>" not in html  # raw < not emitted


# ── extractHtmlAttribute ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_html_attribute_returns_values() -> None:
    items = [ExecutionItem(json={"html": (
        '<a href="https://a.example">A</a>'
        '<a href="https://b.example" class="x">B</a>'
        '<a>no href</a>'
    )})]
    node = _node({"action": "extractHtmlAttribute", "cssQuery": "a", "attribute": "href"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert [r["attribute"] for r in rendered] == [
        "https://a.example",
        "https://b.example",
    ]


@pytest.mark.asyncio
async def test_extract_html_attribute_class_with_tag_prefix() -> None:
    items = [ExecutionItem(json={"html": (
        '<div class="note">A</div><div class="note other">B</div>'
        '<span class="note">C</span>'
    )})]
    node = _node({"action": "extractHtmlAttribute", "cssQuery": "div.note", "attribute": "class"})
    out = await exec_html(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert [r["attribute"] for r in rendered] == ["note", "note other"]


@pytest.mark.asyncio
async def test_extract_html_attribute_missing_attribute_param_raises() -> None:
    items = [ExecutionItem(json={"html": "<p>x</p>"})]
    node = _node({"action": "extractHtmlAttribute", "cssQuery": "p"})
    with pytest.raises(ValueError, match="attribute"):
        await exec_html(node, items, ctx=_ctx())


# ── Selector edge cases ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_selector_raises() -> None:
    items = [ExecutionItem(json={"html": "<p>x</p>"})]
    node = _node({"action": "extractHtmlContent", "cssQuery": "p span"})
    with pytest.raises(ValueError, match="unsupported CSS selector"):
        await exec_html(node, items, ctx=_ctx())


@pytest.mark.asyncio
async def test_unknown_action_raises() -> None:
    items = [ExecutionItem(json={"html": "<p>x</p>"})]
    node = _node({"action": "scrub"})
    with pytest.raises(ValueError, match="unsupported action"):
        await exec_html(node, items, ctx=_ctx())


# ── Descriptor & end-to-end ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.html" in REGISTRY
    assert "n8n-nodes-base.html" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.html"] == "transform"
    desc = REGISTRY["n8n-nodes-base.html"]
    assert desc.executor.endswith(":exec_html")
    assert desc.category == "transform"


@pytest.mark.asyncio
async def test_end_to_end_manual_html_set() -> None:
    """Manual with pinned HTML → html (extractHtmlContent) → Set sees fields."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("h1", "Extract", "n8n-nodes-base.html", {
                "action": "extractHtmlContent",
                "cssQuery": "li.item",
                "dataProperty": "html",
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "first", "value": "={{ $json.text }}", "type": "string"},
                    {"name": "inner", "value": "={{ $json.inner }}", "type": "string"},
                    {"name": "saw_alpha", "value": "={{ $json.text }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Extract", "type": "main", "index": 0}]]},
            "Extract": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    pinned_html = (
        '<ul><li class="item">alpha</li>'
        '<li class="item">beta</li>'
        '<li>other</li></ul>'
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(
        trigger="manual",
        pin_data={"Start": [{"html": pinned_html}]},
    )
    assert result.status == "success", result.error_message

    extract_step = next(s for s in result.steps if s.node_name == "Extract")
    assert extract_step.status == "success"
    assert extract_step.output_count == 2

    final = result.final_items
    assert final, "expected at least one final item"
    # Downstream runs once per upstream item; both items should expose the
    # extracted ``text`` field. Take either of the final items to verify.
    seen_texts = set()
    for item in final:
        if not isinstance(item, dict):
            continue
        fjson = item.get("json")
        if isinstance(fjson, dict):
            seen_texts.add(fjson.get("first"))
    assert seen_texts == {"alpha", "beta"}
