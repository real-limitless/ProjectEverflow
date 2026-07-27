"""Tests for the WordPress node executor (``n8n-nodes-base.wordpress``).

Covers:

- ``wordpress_response`` dict mock → envelope used verbatim
- ``wordpress_response`` callable mock receives ``(operation, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline create: postId present, title echoed
- Offline get: postId echoed, title present
- Offline update: status echoed
- Offline list: returns up to 3 posts
- Offline delete: deleted=True
- ``operation='create'`` reflected
- ``postId`` default from ``$json``
- ``title`` default from ``$json``
- ``perPage`` honored
- Empty ``postId`` for get → no item
- End-to-end: Manual Trigger → wordpress (list mock) → Set sees posts
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.wordpress import (
    WORDPRESS_DEFAULT_OPERATION,
    WORDPRESS_OFFLINE_MAX_POSTS,
    WORDPRESS_OPERATIONS,
    exec_wordpress,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.wordpress",
    id_: str = "wp1",
    name: str = "WordPress",
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


# ── 1. wordpress_response dict mock ────────────────────────────────────


@pytest.mark.asyncio
async def test_wordpress_response_dict_mock_used_verbatim() -> None:
    node = _node(
        {
            "operation": "create",
            "title": "Hello World",
            "content": "First post",
            "status": "publish",
        }
    )
    ctx = _ctx(
        {
            "wordpress_response": {
                "id": 42,
                "title": {"rendered": "Hello World"},
                "content": {"rendered": "First post"},
                "status": "publish",
                "author": 2,
                "date": "2025-01-15T10:00:00Z",
                "link": "https://example.com/?p=42",
                "type": "post",
            }
        }
    )
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p["postId"] == 42
    assert p["title"] == "Hello World"
    assert p["content"] == "First post"
    assert p["status"] == "publish"
    assert p["author"] == 2
    assert p["link"] == "https://example.com/?p=42"
    assert p["source"] == "wordpress"
    assert p["operation"] == "create"
    assert "mockSource" not in p


# ── 2. wordpress_response callable mock signature ─────────────────────


@pytest.mark.asyncio
async def test_wordpress_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": 99,
            "title": {"rendered": "Mocked"},
            "content": {"rendered": "Mocked content"},
            "status": "draft",
            "author": 1,
            "date": "2025-01-15T10:00:00Z",
            "link": "https://example.com/?p=99",
        }

    node = _node(
        {
            "operation": "create",
            "title": "T",
            "content": "C",
            "extra": "keep",
        }
    )
    ctx = _ctx({"wordpress_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_wordpress(node, [item], ctx=ctx))

    assert captured["operation"] == "create"
    assert captured["params"]["title"] == "T"
    assert captured["params"]["content"] == "C"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["postId"] == 99
    assert out[0].json["title"] == "Mocked"


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node({"operation": "get", "postId": 7})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "id": 7,
                    "title": {"rendered": "From HTTP"},
                    "content": {"rendered": "HTTP body"},
                    "status": "publish",
                    "author": 3,
                    "date": "2025-02-01T00:00:00Z",
                    "link": "https://example.com/?p=7",
                },
            }
        }
    )
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p["postId"] == 7
    assert p["title"] == "From HTTP"
    assert p["content"] == "HTTP body"
    assert p["author"] == 3
    assert p["mockSource"] == "http_response"
    assert p["source"] == "wordpress"


# ── 4. Offline create ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_create_returns_post_id_and_title() -> None:
    node = _node(
        {
            "operation": "create",
            "title": "My First Post",
            "content": "Hello WordPress",
        }
    )
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["postId"] is not None
    assert isinstance(p["postId"], int)
    assert p["title"] == "My First Post"
    assert p["content"] == "Hello WordPress"
    assert p["status"] == "draft"
    assert p["author"] == 1
    assert p["link"].startswith("https://example.com/?p=")
    assert p["source"] == "wordpress"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "create"


# ── 5. Offline get ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_get_returns_post_with_id() -> None:
    node = _node({"operation": "get", "postId": 55})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["postId"] == 55
    assert p["title"] == "Mock Post"
    assert p["content"] == "Mock post content here."
    assert p["status"] == "publish"
    assert p["author"] == 1
    assert p["link"] == "https://example.com/?p=55"
    assert p["source"] == "wordpress"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "get"


# ── 6. Offline update ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_update_echoes_status() -> None:
    node = _node(
        {
            "operation": "update",
            "postId": 33,
            "title": "Updated Title",
            "content": "Updated content",
            "status": "pending",
        }
    )
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["postId"] == 33
    assert p["title"] == "Updated Title"
    assert p["content"] == "Updated content"
    assert p["status"] == "pending"
    assert p["link"] == "https://example.com/?p=33"
    assert p["source"] == "wordpress"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "update"


# ── 7. Offline list ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_list_returns_up_to_three_posts() -> None:
    node = _node({"operation": "list"})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == WORDPRESS_OFFLINE_MAX_POSTS
    for i, o in enumerate(out, start=1):
        assert o.json["source"] == "wordpress"
        assert o.json["postId"] == i
        assert o.json["title"] == f"Mock Post {i}"
        assert o.json["content"] == f"Content {i}"
        assert o.json["status"] == "publish"
        assert o.json["link"] == f"https://example.com/?p={i}"
        assert o.json["mockSource"] == "offline"
        assert o.json["operation"] == "list"


# ── 8. Offline delete ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_delete_returns_deleted_true() -> None:
    node = _node({"operation": "delete", "postId": 77})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["postId"] == 77
    assert p["deleted"] is True
    assert p["source"] == "wordpress"
    assert p["mockSource"] == "offline"
    assert p["operation"] == "delete"


# ── 9. operation='create' reflected ───────────────────────────────────


@pytest.mark.asyncio
async def test_create_operation_reflected_in_payload() -> None:
    node = _node(
        {
            "operation": "create",
            "title": "Reflected",
            "content": "Hello",
        }
    )
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["operation"] == "create"
    assert p["source"] == "wordpress"
    assert "postId" in p
    assert "title" in p
    assert "content" in p


# ── 10. postId default from $json ─────────────────────────────────────


@pytest.mark.asyncio
async def test_post_id_default_from_json_post_id() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"postId": 123})
    out = _out_items(await exec_wordpress(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["postId"] == 123


@pytest.mark.asyncio
async def test_post_id_default_from_json_id() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"id": 456})
    out = _out_items(await exec_wordpress(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["postId"] == 456


# ── 11. title default from $json ──────────────────────────────────────


@pytest.mark.asyncio
async def test_title_default_from_json() -> None:
    node = _node({"operation": "create", "content": "x"})
    item = ExecutionItem(json={"title": "Json Title"})
    out = _out_items(await exec_wordpress(node, [item], ctx=_ctx()))
    assert out[0].json["title"] == "Json Title"


# ── 12. perPage honored ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_per_page_honored() -> None:
    node = _node({"operation": "list", "perPage": 2})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 2


@pytest.mark.asyncio
async def test_per_page_capped_at_offline_max() -> None:
    node = _node({"operation": "list", "perPage": 100})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == WORDPRESS_OFFLINE_MAX_POSTS


# ── 13. Empty postId for get → no item ────────────────────────────────


@pytest.mark.asyncio
async def test_empty_post_id_for_get_skips_item() -> None:
    node = _node({"operation": "get", "postId": ""})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_post_id_for_get_when_only_in_json_skips_item() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"postId": "", "id": ""})
    out = _out_items(await exec_wordpress(node, [item], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_post_id_for_update_skips_item() -> None:
    node = _node({"operation": "update", "postId": ""})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_post_id_for_delete_skips_item() -> None:
    node = _node({"operation": "delete", "postId": ""})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


# ── 14. Default operation is 'get' ────────────────────────────────────


@pytest.mark.asyncio
async def test_default_operation_is_get() -> None:
    assert WORDPRESS_DEFAULT_OPERATION == "get"
    node = _node({"postId": 1})
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["operation"] == "get"
    assert "title" in out[0].json


# ── 15. dataMode='object' emits single item with posts[] ──────────────


@pytest.mark.asyncio
async def test_list_data_mode_object_emits_single_item() -> None:
    node = _node(
        {
            "operation": "list",
            "dataMode": "object",
        }
    )
    out = _out_items(await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["posts"], list)
    assert len(p["posts"]) == WORDPRESS_OFFLINE_MAX_POSTS
    assert p["totalPosts"] == WORDPRESS_OFFLINE_MAX_POSTS
    assert p["source"] == "wordpress"


# ── 16. content default from $json ────────────────────────────────────


@pytest.mark.asyncio
async def test_content_default_from_json_content() -> None:
    node = _node({"operation": "create", "title": "T"})
    item = ExecutionItem(json={"content": "Json Content"})
    out = _out_items(await exec_wordpress(node, [item], ctx=_ctx()))
    assert out[0].json["content"] == "Json Content"


@pytest.mark.asyncio
async def test_content_default_from_json_body() -> None:
    node = _node({"operation": "create", "title": "T"})
    item = ExecutionItem(json={"body": "Json Body"})
    out = _out_items(await exec_wordpress(node, [item], ctx=_ctx()))
    assert out[0].json["content"] == "Json Body"


# ── 17. Unsupported operation raises ──────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "publish", "postId": 1})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_wordpress(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 18. Descriptor registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.wordpress" in REGISTRY
    assert "n8n-nodes-base.wordpress" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.wordpress"] == "output"
    desc = REGISTRY["n8n-nodes-base.wordpress"]
    assert desc.executor.endswith(":exec_wordpress")
    assert desc.category == "output"
    assert set(WORDPRESS_OPERATIONS) == {"create", "get", "update", "list", "delete"}


# ── 19. End-to-end: Manual Trigger → wordpress (list mock) → Set ──────


def _doc(nodes, connections):
    return {"name": "wp-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_wordpress_set_sees_posts() -> None:
    """Manual Trigger → wordpress (wordpress_response list mock) → Set pulls posts."""
    mocks = {
        "wordpress_response": {
            "posts": [
                {
                    "id": 101,
                    "title": {"rendered": "E2E Post 1"},
                    "content": {"rendered": "E2E content 1"},
                    "status": "publish",
                    "date": "2025-04-01T10:00:00Z",
                    "link": "https://example.com/?p=101",
                    "author": 1,
                },
                {
                    "id": 102,
                    "title": {"rendered": "E2E Post 2"},
                    "content": {"rendered": "E2E content 2"},
                    "status": "publish",
                    "date": "2025-04-02T10:00:00Z",
                    "link": "https://example.com/?p=102",
                    "author": 1,
                },
            ],
            "totalPosts": 2,
            "totalPages": 1,
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "wp1",
                "WP",
                "n8n-nodes-base.wordpress",
                {
                    "operation": "list",
                    "perPage": 10,
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_post_id", "value": "={{ $json.postId }}", "type": "string"},
                            {"name": "result_title", "value": "={{ $json.title }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "WP", "type": "main", "index": 0}]]},
            "WP": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    wp_step = next(s for s in result.steps if s.node_name == "WP")
    assert wp_step.status == "success", wp_step.error
    assert wp_step.output_count == 2
    post_ids = {o["json"]["postId"] for o in wp_step.sample_output}
    assert 101 in post_ids
    assert 102 in post_ids
    for o in wp_step.sample_output:
        assert o["json"]["source"] == "wordpress"

    final = result.final_items
    assert final, "expected at least one final item"
    final_ids = {
        f.get("json", {}).get("result_post_id")
        for f in final
        if isinstance(f, dict)
    }
    assert 101 in final_ids
    assert 102 in final_ids
    for f in final:
        if isinstance(f, dict):
            assert f.get("json", {}).get("result_source") == "wordpress"