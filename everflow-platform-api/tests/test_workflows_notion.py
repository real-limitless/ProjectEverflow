"""Tests for the Notion node executor (``n8n-nodes-base.notion``).

Covers:

- ``notion_response`` dict mock → envelope used verbatim (per operation)
- ``notion_response`` callable mock receives
  ``(operation, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline synthetic responses for search (up to 3 results), createPage
  (pageId present, parentId echoed), getPage (pageId echoed, title
  present), updatePage (properties echoed), queryDatabase (up to 3
  results)
- ``operation='search'`` reflected in payload
- ``query``/``pageId`` defaults from ``$json``
- ``pageSize`` honored
- Empty ``pageId`` for getPage → no item emitted
- End-to-end: Manual Trigger → notion (search mock) → Set sees
  ``pageId`` and ``title``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.notion import (
    NOTION_OPERATIONS,
    exec_notion,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.notion",
    id_: str = "n1",
    name: str = "Notion",
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


# ── 1. notion_response dict mock (search) ────────────────────────────


@pytest.mark.asyncio
async def test_notion_response_dict_mock_is_used_verbatim_for_search() -> None:
    node = _node(
        {
            "operation": "search",
            "query": "hello",
        }
    )
    ctx = _ctx(
        {
            "notion_response": {
                "results": [
                    {
                        "id": "fixed-page-1",
                        "object": "page",
                        "url": "https://notion.so/fixed-page-1",
                        "properties": {
                            "title": {
                                "title": [
                                    {"text": {"content": "Fixed Page"}}
                                ]
                            }
                        },
                        "created_time": "2024-01-01T00:00:00Z",
                        "last_edited_time": "2024-01-02T00:00:00Z",
                    }
                ],
                "has_more": False,
                "next_cursor": None,
            }
        }
    )
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    p = out[0].json
    assert p["pageId"] == "fixed-page-1"
    assert p["title"] == "Fixed Page"
    assert p["url"] == "https://notion.so/fixed-page-1"
    assert p["object"] == "page"
    assert p["createdTime"] == "2024-01-01T00:00:00Z"
    assert p["source"] == "notion"
    assert "mockSource" not in p


# ── 2. notion_response callable mock signature ───────────────────────


@pytest.mark.asyncio
async def test_notion_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "results": [
                {
                    "id": "cb-page-1",
                    "object": "page",
                    "url": "https://notion.so/cb-page-1",
                    "properties": {
                        "title": {
                            "title": [
                                {"text": {"content": params.get("query", "")}}
                            ]
                        }
                    },
                    "created_time": "2024-01-01T00:00:00Z",
                    "last_edited_time": "2024-01-01T00:00:00Z",
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }

    node = _node(
        {
            "operation": "search",
            "query": "From Param",
            "extra": "keep",
        }
    )
    ctx = _ctx({"notion_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_notion(node, [item], ctx=ctx))

    assert captured["operation"] == "search"
    assert captured["params"]["query"] == "From Param"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["pageId"] == "cb-page-1"
    assert out[0].json["title"] == "From Param"


# ── 3. http_response fallback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "getPage",
            "pageId": "page-http",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "id": "page-http",
                    "object": "page",
                    "url": "https://notion.so/page-http",
                    "properties": {
                        "title": {
                            "title": [
                                {"text": {"content": "From HTTP"}}
                            ]
                        }
                    },
                    "created_time": "2024-01-01T00:00:00Z",
                    "last_edited_time": "2024-01-01T00:00:00Z",
                },
            }
        }
    )
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    p = out[0].json
    assert p["pageId"] == "page-http"
    assert p["title"] == "From HTTP"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "notion"


# ── 4. Offline synthetic response — search ───────────────────────────


@pytest.mark.asyncio
async def test_offline_search_returns_up_to_three_results() -> None:
    node = _node({"operation": "search", "query": "test"})
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3
    for i, item in enumerate(out, start=1):
        p = item.json
        assert p["pageId"] == f"mock_page_{i}"
        assert p["title"] == f"Mock Page {i}"
        assert p["url"] == f"https://notion.so/mock_page_{i}"
        assert p["object"] == "page"
        assert p["source"] == "notion"
        assert p["mockSource"] == "offline"
        assert "createdTime" in p


# ── 5. Offline synthetic response — createPage ───────────────────────


@pytest.mark.asyncio
async def test_offline_create_page_has_page_id_and_parent_id() -> None:
    node = _node(
        {
            "operation": "createPage",
            "parentId": "db-123",
            "properties": {
                "title": {"title": [{"text": {"content": "New Page"}}]}
            },
        }
    )
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["pageId"].startswith("mock_page_")
    assert p["parentId"] == "db-123"
    assert p["url"] == "https://notion.so/mock_page"
    assert p["source"] == "notion"
    assert p["mockSource"] == "offline"
    assert "createdTime" in p
    assert "properties" in p


# ── 6. Offline synthetic response — getPage ──────────────────────────


@pytest.mark.asyncio
async def test_offline_get_page_echoes_page_id_and_title() -> None:
    node = _node({"operation": "getPage", "pageId": "page-abc"})
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["pageId"] == "page-abc"
    assert p["title"] == "Mock Page"
    assert p["url"] == "https://notion.so/page-abc"
    assert p["source"] == "notion"
    assert p["mockSource"] == "offline"
    assert "createdTime" in p
    assert "properties" in p


# ── 7. Offline synthetic response — updatePage ───────────────────────


@pytest.mark.asyncio
async def test_offline_update_page_echoes_properties() -> None:
    props = {
        "title": {"title": [{"text": {"content": "Updated Title"}}]}
    }
    node = _node(
        {
            "operation": "updatePage",
            "pageId": "page-upd",
            "properties": props,
        }
    )
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["pageId"] == "page-upd"
    assert p["url"] == "https://notion.so/page-upd"
    assert p["properties"] == props
    assert p["source"] == "notion"
    assert p["mockSource"] == "offline"
    assert "lastEditedTime" in p
    assert p["archived"] is False


# ── 8. Offline synthetic response — queryDatabase ────────────────────


@pytest.mark.asyncio
async def test_offline_query_database_returns_up_to_three_results() -> None:
    node = _node(
        {
            "operation": "queryDatabase",
            "databaseId": "db-query",
        }
    )
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3
    for i, item in enumerate(out, start=1):
        p = item.json
        assert p["pageId"] == f"mock_record_{i}"
        assert p["title"] == f"Record {i}"
        assert p["source"] == "notion"
        assert p["mockSource"] == "offline"
        assert "createdTime" in p
        assert p["databaseId"] == "db-query"


# ── 9. operation='search' reflected ──────────────────────────────────


@pytest.mark.asyncio
async def test_search_operation_reflected_in_payload() -> None:
    node = _node({"operation": "search", "query": "reflected"})
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    p = out[0].json
    assert p["operation"] == "search"
    assert p["source"] == "notion"
    assert "pageId" in p
    assert "title" in p
    assert "url" in p


# ── 10. query default from $json ─────────────────────────────────────


@pytest.mark.asyncio
async def test_query_defaults_from_json_query() -> None:
    node = _node({"operation": "search"})
    item = ExecutionItem(json={"query": "json-query"})
    out = _out_items(await exec_notion(node, [item], ctx=_ctx()))
    # Offline search still returns 3 results; query is echoed in object mode
    assert len(out) == 3


@pytest.mark.asyncio
async def test_query_defaults_from_json_search() -> None:
    node = _node({"operation": "search"})
    item = ExecutionItem(json={"search": "json-search"})
    out = _out_items(await exec_notion(node, [item], ctx=_ctx()))
    assert len(out) == 3


# ── 11. pageId default from $json ────────────────────────────────────


@pytest.mark.asyncio
async def test_page_id_defaults_from_json_page_id() -> None:
    node = _node({"operation": "getPage"})
    item = ExecutionItem(json={"pageId": "json-page-1"})
    out = _out_items(await exec_notion(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["pageId"] == "json-page-1"


@pytest.mark.asyncio
async def test_page_id_falls_back_to_id_key() -> None:
    node = _node({"operation": "getPage"})
    item = ExecutionItem(json={"id": "json-id-1"})
    out = _out_items(await exec_notion(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["pageId"] == "json-id-1"


# ── 12. pageSize honored ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_page_size_honored_for_search() -> None:
    node = _node({"operation": "search", "pageSize": 2})
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 2


@pytest.mark.asyncio
async def test_page_size_honored_for_query_database() -> None:
    node = _node(
        {"operation": "queryDatabase", "databaseId": "db", "pageSize": 1}
    )
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1


@pytest.mark.asyncio
async def test_page_size_capped_at_three_offline() -> None:
    node = _node({"operation": "search", "pageSize": 10})
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3


# ── 13. Empty pageId for getPage → no item ───────────────────────────


@pytest.mark.asyncio
async def test_empty_page_id_for_get_page_skips_item() -> None:
    node = _node({"operation": "getPage", "pageId": ""})
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_page_id_for_update_page_skips_item() -> None:
    node = _node(
        {"operation": "updatePage", "pageId": "", "properties": {}}
    )
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_page_id_when_only_in_json_skips_item() -> None:
    node = _node({"operation": "getPage"})
    item = ExecutionItem(json={"pageId": "", "id": ""})
    out = _out_items(await exec_notion(node, [item], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_database_id_for_query_database_skips_item() -> None:
    node = _node({"operation": "queryDatabase", "databaseId": ""})
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


# ── 14. Unsupported operation raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "deletePage", "pageId": "x"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 15. Default operation is search ──────────────────────────────────


@pytest.mark.asyncio
async def test_default_operation_is_search() -> None:
    node = _node({"query": "default"})
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    p = out[0].json
    assert p["operation"] == "search"
    assert "pageId" in p
    assert "title" in p


# ── 16. dataMode='object' for search ─────────────────────────────────


@pytest.mark.asyncio
async def test_search_data_mode_object_emits_single_item_with_results() -> None:
    node = _node(
        {"operation": "search", "query": "test", "dataMode": "object"}
    )
    out = _out_items(
        await exec_notion(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert "results" in p
    assert isinstance(p["results"], list)
    assert len(p["results"]) == 3
    assert p["source"] == "notion"


# ── 17. Descriptor registration ──────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.notion" in REGISTRY
    assert "n8n-nodes-base.notion" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.notion"] == "output"
    desc = REGISTRY["n8n-nodes-base.notion"]
    assert desc.executor.endswith(":exec_notion")
    assert desc.category == "output"
    assert set(NOTION_OPERATIONS) == {
        "search",
        "createPage",
        "getPage",
        "updatePage",
        "queryDatabase",
    }


# ── 18. End-to-end: Manual Trigger → notion (search mock) → Set ─────


def _doc(nodes, connections):
    return {"name": "notion-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_notion_search_set_sees_page_id_and_title() -> None:
    """Manual Trigger → notion (search with notion_response mock) → Set."""
    mocks = {
        "notion_response": {
            "results": [
                {
                    "id": "e2e-page-1",
                    "object": "page",
                    "url": "https://notion.so/e2e-page-1",
                    "properties": {
                        "title": {
                            "title": [
                                {"text": {"content": "E2E Title"}}
                            ]
                        }
                    },
                    "created_time": "2024-01-01T00:00:00Z",
                    "last_edited_time": "2024-01-01T00:00:00Z",
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "n1",
                "Notion",
                "n8n-nodes-base.notion",
                {
                    "operation": "search",
                    "query": "E2E",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_page_id", "value": "={{ $json.pageId }}", "type": "string"},
                            {"name": "result_title", "value": "={{ $json.title }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Notion", "type": "main", "index": 0}]]},
            "Notion": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    notion_step = next(s for s in result.steps if s.node_name == "Notion")
    assert notion_step.status == "success", notion_step.error
    assert notion_step.output_count == 1
    first = notion_step.sample_output[0]
    assert first["json"]["pageId"] == "e2e-page-1"
    assert first["json"]["title"] == "E2E Title"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_page_id") == "e2e-page-1"
    assert fjson.get("result_title") == "E2E Title"
    assert fjson.get("result_source") == "notion"