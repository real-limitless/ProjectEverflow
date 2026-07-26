"""Tests for social media executors: Twitter, LinkedIn, Reddit."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list


def _node(type_: str, params: dict[str, Any] | None = None, id_: str = "n1", name: str = "Soc") -> ExecNode:
    return ExecNode(
        id=id_, name=name, type=type_, type_version=1,
        parameters=params or {}, credentials=None, position={"x": 0, "y": 0},
    )


def _ctx(mocks: dict[str, Any] | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {}, run_id="test")  # type: ignore[arg-type]


def _items(rows: list[dict] | None = None):
    return items_from_json_list(rows or [])


# ── Twitter ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_twitter_mock_returns_dict() -> None:
    node = _node("n8n-nodes-base.twitter", {"text": "hello"})
    ctx = _ctx({"twitter_response": {"data": {"id": "123", "text": "mocked", "author_id": "u1", "created_at": "2026-01-01T00:00:00Z"}}})
    result = await __import__("app.services.workflows.nodes.social", fromlist=["exec_twitter"]).exec_twitter(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["tweetId"] == "123"
    assert out[0].json["text"] == "mocked"
    assert out[0].json["source"] == "twitter"


@pytest.mark.asyncio
async def test_twitter_callable_mock() -> None:
    seen = []
    def mock(op, text, params, item, ctx):
        seen.append((op, text))
        return {"data": {"id": "999", "text": text, "author_id": "a", "created_at": "t"}}
    node = _node("n8n-nodes-base.twitter", {"text": "hi", "operation": "tweet"})
    ctx = _ctx({"twitter_response": mock})
    result = await __import__("app.services.workflows.nodes.social", fromlist=["exec_twitter"]).exec_twitter(node, _items([{}]), ctx=ctx)
    assert seen == [("tweet", "hi")]
    assert result[0][1][0].json["tweetId"] == "999"


@pytest.mark.asyncio
async def test_twitter_offline_tweet() -> None:
    from app.services.workflows.nodes.social import exec_twitter
    node = _node("n8n-nodes-base.twitter", {"text": "hello world"})
    ctx = _ctx()
    result = await exec_twitter(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["tweetId"]
    assert out[0].json["text"] == "hello world"
    assert out[0].json["operation"] == "tweet"
    assert out[0].json["source"] == "twitter"


@pytest.mark.asyncio
async def test_twitter_offline_retweet() -> None:
    from app.services.workflows.nodes.social import exec_twitter
    node = _node("n8n-nodes-base.twitter", {"operation": "retweet", "tweetId": "42", "text": "ignored"})
    ctx = _ctx()
    result = await exec_twitter(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["operation"] == "retweet"


@pytest.mark.asyncio
async def test_twitter_offline_reply() -> None:
    from app.services.workflows.nodes.social import exec_twitter
    node = _node("n8n-nodes-base.twitter", {"operation": "reply", "tweetId": "42", "text": "reply text"})
    ctx = _ctx()
    result = await exec_twitter(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["text"] == "reply text"
    assert out[0].json["operation"] == "reply"


@pytest.mark.asyncio
async def test_twitter_text_default_from_json() -> None:
    from app.services.workflows.nodes.social import exec_twitter
    node = _node("n8n-nodes-base.twitter")
    ctx = _ctx()
    result = await exec_twitter(node, _items([{"text": "from json"}]), ctx=ctx)
    out = result[0][1]
    assert out[0].json["text"] == "from json"


@pytest.mark.asyncio
async def test_twitter_empty_text_skips() -> None:
    from app.services.workflows.nodes.social import exec_twitter
    node = _node("n8n-nodes-base.twitter", {"operation": "tweet"})
    ctx = _ctx()
    result = await exec_twitter(node, _items([{}]), ctx=ctx)
    assert result[0][1] == []


@pytest.mark.asyncio
async def test_twitter_http_fallback() -> None:
    from app.services.workflows.nodes.social import exec_twitter
    node = _node("n8n-nodes-base.twitter", {"text": "hi"})
    ctx = _ctx({"http_response": {"body": {"data": {"id": "fb1", "text": "fallback", "author_id": "x", "created_at": "t"}}}})
    result = await exec_twitter(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert out[0].json["tweetId"] == "fb1"


# ── LinkedIn ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_linkedin_mock_returns_dict() -> None:
    from app.services.workflows.nodes.social import exec_linkedin
    node = _node("n8n-nodes-base.linkedIn", {"text": "hello"})
    ctx = _ctx({"linkedin_response": {"id": "urn:li:share:123", "text": "mocked", "visibility": "PUBLIC", "author": "urn:li:person:x", "created_at": "2026-01-01T00:00:00Z"}})
    result = await exec_linkedin(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert out[0].json["shareId"] == "urn:li:share:123"
    assert out[0].json["source"] == "linkedIn"


@pytest.mark.asyncio
async def test_linkedin_callable_mock() -> None:
    from app.services.workflows.nodes.social import exec_linkedin
    seen = []
    def mock(text, params, item, ctx):
        seen.append(text)
        return {"id": "s1", "text": text, "visibility": "CONNECTIONS", "author": "a", "created_at": "t"}
    node = _node("n8n-nodes-base.linkedIn", {"text": "hi"})
    ctx = _ctx({"linkedin_response": mock})
    result = await exec_linkedin(node, _items([{}]), ctx=ctx)
    assert seen == ["hi"]
    assert result[0][1][0].json["visibility"] == "CONNECTIONS"


@pytest.mark.asyncio
async def test_linkedin_offline_share() -> None:
    from app.services.workflows.nodes.social import exec_linkedin
    node = _node("n8n-nodes-base.linkedIn", {"text": "my post", "visibility": "PUBLIC", "author": "urn:li:person:me"})
    ctx = _ctx()
    result = await exec_linkedin(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["shareId"].startswith("urn:li:share:")
    assert out[0].json["text"] == "my post"
    assert out[0].json["visibility"] == "PUBLIC"
    assert out[0].json["source"] == "linkedIn"


@pytest.mark.asyncio
async def test_linkedin_visibility_default_public() -> None:
    from app.services.workflows.nodes.social import exec_linkedin
    node = _node("n8n-nodes-base.linkedIn", {"text": "hi"})
    ctx = _ctx()
    result = await exec_linkedin(node, _items([{}]), ctx=ctx)
    assert result[0][1][0].json["visibility"] == "PUBLIC"


@pytest.mark.asyncio
async def test_linkedin_text_default_from_json() -> None:
    from app.services.workflows.nodes.social import exec_linkedin
    node = _node("n8n-nodes-base.linkedIn")
    ctx = _ctx()
    result = await exec_linkedin(node, _items([{"text": "from json"}]), ctx=ctx)
    assert result[0][1][0].json["text"] == "from json"


@pytest.mark.asyncio
async def test_linkedin_empty_text_skips() -> None:
    from app.services.workflows.nodes.social import exec_linkedin
    node = _node("n8n-nodes-base.linkedIn")
    ctx = _ctx()
    result = await exec_linkedin(node, _items([{}]), ctx=ctx)
    assert result[0][1] == []


# ── Reddit ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reddit_mock_returns_dict() -> None:
    from app.services.workflows.nodes.social import exec_reddit
    node = _node("n8n-nodes-base.reddit", {"title": "hello", "subreddit": "test"})
    ctx = _ctx({"reddit_response": {"id": "t3_abc", "title": "mocked", "selftext": "body", "subreddit": "test"}})
    result = await exec_reddit(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert out[0].json["postId"] == "t3_abc"
    assert out[0].json["source"] == "reddit"


@pytest.mark.asyncio
async def test_reddit_callable_mock() -> None:
    from app.services.workflows.nodes.social import exec_reddit
    seen = []
    def mock(title, text, subreddit, params, item, ctx):
        seen.append((title, subreddit))
        return {"id": "t3_x", "title": title, "selftext": text, "subreddit": subreddit}
    node = _node("n8n-nodes-base.reddit", {"title": "hi", "subreddit": "r"})
    ctx = _ctx({"reddit_response": mock})
    result = await exec_reddit(node, _items([{}]), ctx=ctx)
    assert seen == [("hi", "r")]
    assert result[0][1][0].json["postId"] == "t3_x"


@pytest.mark.asyncio
async def test_reddit_offline_post() -> None:
    from app.services.workflows.nodes.social import exec_reddit
    node = _node("n8n-nodes-base.reddit", {"title": "my title", "text": "my body", "subreddit": "python"})
    ctx = _ctx()
    result = await exec_reddit(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert len(out) == 1
    assert out[0].json["postId"].startswith("t3_")
    assert out[0].json["title"] == "my title"
    assert out[0].json["subreddit"] == "python"
    assert out[0].json["source"] == "reddit"


@pytest.mark.asyncio
async def test_reddit_kind_link_with_url() -> None:
    from app.services.workflows.nodes.social import exec_reddit
    node = _node("n8n-nodes-base.reddit", {"title": "link post", "subreddit": "r", "kind": "link", "url": "https://example.com"})
    ctx = _ctx()
    result = await exec_reddit(node, _items([{}]), ctx=ctx)
    out = result[0][1]
    assert out[0].json["kind"] == "link"


@pytest.mark.asyncio
async def test_reddit_subreddit_default_from_json() -> None:
    from app.services.workflows.nodes.social import exec_reddit
    node = _node("n8n-nodes-base.reddit", {"title": "t"})
    ctx = _ctx()
    result = await exec_reddit(node, _items([{"subreddit": "fromjson"}]), ctx=ctx)
    assert result[0][1][0].json["subreddit"] == "fromjson"


@pytest.mark.asyncio
async def test_reddit_empty_title_skips() -> None:
    from app.services.workflows.nodes.social import exec_reddit
    node = _node("n8n-nodes-base.reddit", {"subreddit": "r"})
    ctx = _ctx()
    result = await exec_reddit(node, _items([{}]), ctx=ctx)
    assert result[0][1] == []


@pytest.mark.asyncio
async def test_reddit_empty_subreddit_skips() -> None:
    from app.services.workflows.nodes.social import exec_reddit
    node = _node("n8n-nodes-base.reddit", {"title": "t"})
    ctx = _ctx()
    result = await exec_reddit(node, _items([{}]), ctx=ctx)
    assert result[0][1] == []


# ── Descriptor registration ───────────────────────────────────────────


def test_descriptors_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    for ntype in ("n8n-nodes-base.twitter", "n8n-nodes-base.linkedIn", "n8n-nodes-base.reddit"):
        assert ntype in REGISTRY, f"{ntype} not in REGISTRY"
        assert ntype in SUPPORTED_NODE_TYPES, f"{ntype} not in SUPPORTED_NODE_TYPES"
        assert SUPPORTED_NODE_TYPES[ntype] == "output"
        assert REGISTRY[ntype].category == "output"


# ── End-to-end ────────────────────────────────────────────────────────


def _doc(nodes, connections):
    return {"name": "social-e2e", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None):
    return {"id": id_, "name": name, "type": type_, "typeVersion": 1, "position": [0, 0], "parameters": params or {}}


@pytest.mark.asyncio
async def test_e2e_twitter_to_set() -> None:
    from app.services.workflows.nodes.social import exec_twitter
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("tw1", "Tweet", "n8n-nodes-base.twitter", {"text": "hello"}),
            _n("s1", "Set", "n8n-nodes-base.set", {"assignments": {"assignments": [{"name": "tid", "value": "={{ $json.tweetId }}", "type": "string"}]}}),
        ],
        {"Start": {"main": [[{"node": "Tweet", "type": "main", "index": 0}]]}, "Tweet": {"main": [[{"node": "Set", "type": "main", "index": 0}]]}},
    )
    engine = WorkflowEngine(doc, mocks={"twitter_response": {"data": {"id": "42", "text": "hello", "author_id": "u", "created_at": "t"}}})
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["tid"] == "42"


@pytest.mark.asyncio
async def test_e2e_linkedin_to_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("li1", "Share", "n8n-nodes-base.linkedIn", {"text": "hello"}),
            _n("s1", "Set", "n8n-nodes-base.set", {"assignments": {"assignments": [{"name": "sid", "value": "={{ $json.shareId }}", "type": "string"}]}}),
        ],
        {"Start": {"main": [[{"node": "Share", "type": "main", "index": 0}]]}, "Share": {"main": [[{"node": "Set", "type": "main", "index": 0}]]}},
    )
    engine = WorkflowEngine(doc, mocks={"linkedin_response": {"id": "urn:li:share:99", "text": "hello", "visibility": "PUBLIC", "author": "a", "created_at": "t"}})
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["sid"] == "urn:li:share:99"


@pytest.mark.asyncio
async def test_e2e_reddit_to_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("rd1", "Post", "n8n-nodes-base.reddit", {"title": "hi", "subreddit": "test"}),
            _n("s1", "Set", "n8n-nodes-base.set", {"assignments": {"assignments": [{"name": "pid", "value": "={{ $json.postId }}", "type": "string"}]}}),
        ],
        {"Start": {"main": [[{"node": "Post", "type": "main", "index": 0}]]}, "Post": {"main": [[{"node": "Set", "type": "main", "index": 0}]]}},
    )
    engine = WorkflowEngine(doc, mocks={"reddit_response": {"id": "t3_xyz", "title": "hi", "selftext": "", "subreddit": "test"}})
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["pid"] == "t3_xyz"