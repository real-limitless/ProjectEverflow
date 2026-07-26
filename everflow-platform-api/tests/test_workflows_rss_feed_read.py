"""Tests for the ``n8n-nodes-base.rssFeedRead`` clean-room executor.

Covers:

- RSS 2.0 mock feed (3 items) → 3 output items with the right fields
- Atom feed (XMLNS atom) → entries emitted with ``published`` / ``author``
- Missing ``url`` parameter → error
- SSRF guard: ``http://127.0.0.1`` with no mocks → rejected
- End-to-end: Manual Trigger → rssFeedRead (mocked) → Set sees title/link
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes import http as http_node


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    *,
    params: dict[str, Any],
    continue_on_fail: bool = False,
) -> ExecNode:
    return ExecNode(
        id="r1",
        name="RSS",
        type="n8n-nodes-base.rssFeedRead",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
        retry_on_fail=False,
        max_tries=None,
        continue_on_fail=continue_on_fail,
        disabled=False,
    )


def _ctx(mocks: dict[str, Any] | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.nodes_by_id = {}
    g.out_edges = {}
    return EngineContext(graph=g, mocks=mocks or {})


RSS_2_0_FEED = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<rss version=\"2.0\"
     xmlns:dc=\"http://purl.org/dc/elements/1.1/\">
  <channel>
    <title>Example Feed</title>
    <link>https://example.com/</link>
    <description>A sample feed</description>
    <item>
      <title>First post</title>
      <link>https://example.com/posts/1</link>
      <description>&lt;p&gt;Hello &amp; welcome.&lt;/p&gt;</description>
      <pubDate>Mon, 01 Jan 2024 12:00:00 +0000</pubDate>
      <dc:creator>Alice</dc:creator>
    </item>
    <item>
      <title>Second post</title>
      <link>https://example.com/posts/2</link>
      <description>Plain text description with no markup.</description>
      <pubDate>Tue, 02 Jan 2024 09:30:00 +0000</pubDate>
      <creator>Bob</creator>
    </item>
    <item>
      <title>Third post</title>
      <link>https://example.com/posts/3</link>
      <description>&lt;div&gt;&lt;p&gt;Some &lt;b&gt;rich&lt;/b&gt; HTML &amp;mdash; content here.&lt;/p&gt;&lt;/div&gt;</description>
      <pubDate>Wed, 03 Jan 2024 18:15:00 +0000</pubDate>
      <author>Carol</author>
    </item>
  </channel>
</rss>
"""


ATOM_FEED = """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<feed xmlns=\"http://www.w3.org/2005/Atom\">
  <title>Atom Example</title>
  <link href=\"https://example.com/atom\" rel=\"alternate\"/>
  <updated>2024-01-04T00:00:00Z</updated>
  <entry>
    <title>Atom post one</title>
    <link href=\"https://example.com/atom/1\" rel=\"alternate\"/>
    <id>tag:example.com,2024:atom-1</id>
    <published>2024-01-01T12:00:00Z</published>
    <updated>2024-01-01T12:00:00Z</updated>
    <summary type=\"html\">&lt;p&gt;First &lt;em&gt;atom&lt;/em&gt; entry.&lt;/p&gt;</summary>
    <author><name>Dave</name></author>
  </entry>
  <entry>
    <title>Atom post two</title>
    <link href=\"https://example.com/atom/2\" rel=\"self\"/>
    <id>tag:example.com,2024:atom-2</id>
    <published>2024-01-02T12:00:00Z</published>
    <summary>Second atom entry, plain text.</summary>
    <author><name>Eve</name></author>
  </entry>
</feed>
"""


# ── 1. RSS 2.0 mock feed with 3 items → 3 output items ────────────────


@pytest.mark.asyncio
async def test_rss_2_0_mock_three_items() -> None:
    node = _node(
        params={"url": "https://example.com/feed.rss"},
    )
    ctx = _ctx(
        {
            "rss": {
                "https://example.com/feed.rss": RSS_2_0_FEED,
            }
        }
    )
    result = await http_node.exec_rss_feed_read(node, [ExecutionItem(json={})], ctx=ctx)
    assert len(result) == 1
    _, out_items = result[0]
    assert len(out_items) == 3

    first = out_items[0].json
    assert first["title"] == "First post"
    assert first["link"] == "https://example.com/posts/1"
    assert first["pubDate"] == "Mon, 01 Jan 2024 12:00:00 +0000"
    assert first["creator"] == "Alice"
    assert first["contentSnippet"] == "Hello & welcome."
    assert first["url"] == "https://example.com/feed.rss"
    assert first["feedTitle"] == "Example Feed"

    second = out_items[1].json
    assert second["title"] == "Second post"
    assert second["creator"] == "Bob"
    assert second["contentSnippet"] == "Plain text description with no markup."

    third = out_items[2].json
    assert third["title"] == "Third post"
    # ``author`` element fallback (when ``dc:creator`` and ``creator`` are absent).
    assert third["creator"] == "Carol"
    # HTML stripped, entities decoded, whitespace collapsed.
    assert third["contentSnippet"] == "Some rich HTML — content here."


# ── 2. Atom feed (XMLNS atom) → entries emitted ──────────────────────


@pytest.mark.asyncio
async def test_atom_feed_entries_emitted() -> None:
    node = _node(
        params={"url": "https://example.com/feed.atom"},
    )
    ctx = _ctx(
        {
            "rss": {
                "https://example.com/feed.atom": ATOM_FEED,
            }
        }
    )
    result = await http_node.exec_rss_feed_read(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    assert len(out_items) == 2

    first = out_items[0].json
    assert first["title"] == "Atom post one"
    assert first["link"] == "https://example.com/atom/1"
    assert first["published"] == "2024-01-01T12:00:00Z"
    assert first["author"] == "Dave"
    assert first["contentSnippet"] == "First atom entry."
    assert first["feedTitle"] == "Atom Example"

    second = out_items[1].json
    # rel="self" should not replace the rel="alternate" link when both are
    # present; here only rel="self" exists, so it is used as fallback.
    assert second["link"] == "https://example.com/atom/2"
    assert second["author"] == "Eve"


# ── 3. Missing ``url`` parameter → error ──────────────────────────────


@pytest.mark.asyncio
async def test_missing_url_raises() -> None:
    node = _node(params={})
    ctx = _ctx({})
    with pytest.raises(RuntimeError, match="url"):
        await http_node.exec_rss_feed_read(node, [ExecutionItem(json={})], ctx=ctx)


@pytest.mark.asyncio
async def test_empty_url_raises() -> None:
    node = _node(params={"url": ""})
    ctx = _ctx({})
    with pytest.raises(RuntimeError, match="url"):
        await http_node.exec_rss_feed_read(node, [ExecutionItem(json={})], ctx=ctx)


# ── 4. SSRF guard: http://127.0.0.1 → rejected ───────────────────────


@pytest.mark.asyncio
async def test_ssrf_guard_rejects_loopback_without_mocks() -> None:
    node = _node(params={"url": "http://127.0.0.1/feed.xml"})
    ctx = _ctx({})  # no mocks → guard applies
    with pytest.raises(Exception) as excinfo:
        await http_node.exec_rss_feed_read(node, [ExecutionItem(json={})], ctx=ctx)
    # HttpToolSsrfError is the expected error class; allow RuntimeError too
    # since the engine may wrap it.
    assert "127.0.0.1" in str(excinfo.value) or "loopback" in str(excinfo.value).lower() or isinstance(
        excinfo.value, ValueError
    )


@pytest.mark.asyncio
async def test_ssrf_guard_bypassed_when_mock_present() -> None:
    """Loopback URLs are allowed only when a mock supplies the response."""
    node = _node(params={"url": "http://127.0.0.1/feed.rss"})
    ctx = _ctx(
        {
            "rss": {
                "http://127.0.0.1/feed.rss": RSS_2_0_FEED,
            }
        }
    )
    result = await http_node.exec_rss_feed_read(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    assert len(out_items) == 3


# ── 5. Empty feed still emits a single item with the channel title ────


@pytest.mark.asyncio
async def test_empty_rss_feed_emits_one_item() -> None:
    node = _node(params={"url": "https://example.com/empty.rss"})
    empty = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<title>Empty</title></channel></rss>"
    )
    ctx = _ctx({"rss": {"https://example.com/empty.rss": empty}})
    result = await http_node.exec_rss_feed_read(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    assert len(out_items) == 1
    assert out_items[0].json["feedTitle"] == "Empty"


# ── 6. Mock supports dict form with status + body ─────────────────────


@pytest.mark.asyncio
async def test_mock_dict_form_status_body() -> None:
    node = _node(params={"url": "https://example.com/dict.rss"})
    ctx = _ctx(
        {
            "rss": {
                "https://example.com/dict.rss": {
                    "status": 200,
                    "body": RSS_2_0_FEED,
                }
            }
        }
    )
    result = await http_node.exec_rss_feed_read(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    assert len(out_items) == 3
    assert out_items[0].json["title"] == "First post"


# ── 7. End-to-end: Manual Trigger → rssFeedRead (mocked) → Set ───────


@pytest.mark.asyncio
async def test_e2e_manual_rss_set_pipeline() -> None:
    doc = {
        "name": "e2e-rss",
        "nodes": [
            {
                "id": "t1",
                "name": "Start",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
                "parameters": {},
            },
            {
                "id": "r1",
                "name": "FetchFeed",
                "type": "n8n-nodes-base.rssFeedRead",
                "typeVersion": 1,
                "position": [200, 0],
                "parameters": {
                    "url": "https://example.com/feed.rss",
                },
            },
            {
                "id": "s1",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3,
                "position": [400, 0],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "headline",
                                "value": "={{ $json.title }}",
                                "type": "string",
                            },
                            {
                                "name": "href",
                                "value": "={{ $json.link }}",
                                "type": "string",
                            },
                        ]
                    },
                    "includeOtherFields": False,
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "FetchFeed", "type": "main", "index": 0}]]},
            "FetchFeed": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    }
    mocks = {
        "rss": {
            "https://example.com/feed.rss": RSS_2_0_FEED,
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    rss_step = next(s for s in result.steps if s.node_name == "FetchFeed")
    assert rss_step.status == "success"
    assert rss_step.output_count == 3

    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.status == "success"
    # The first item Set saw had the first feed entry's title + link.
    first_sample = set_step.sample_output[0]["json"]
    assert first_sample["headline"] == "First post"
    assert first_sample["href"] == "https://example.com/posts/1"

    # Final items: Set has ``includeOtherFields: False`` so the items
    # carry only the assigned ``headline`` / ``href`` fields. The
    # important assertion is that all three feed entries made it through
    # to the final stage — one per feed item.
    assert len(result.final_items) == 3
    headlines = [it["json"]["headline"] for it in result.final_items]
    assert headlines == ["First post", "Second post", "Third post"]
