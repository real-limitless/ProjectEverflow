"""Tests for the Facebook Graph API node executor
(``n8n-nodes-base.facebookGraphApi``).

Covers:

- ``facebook_response`` dict mock → response used verbatim
- ``facebook_response`` callable mock receives ``(operation, node, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline ``get`` (id and name present)
- Offline ``post`` (id present, success=True)
- Offline ``delete`` (success=True)
- ``operation='get'`` reflected in emitted item
- ``node`` default from ``$json``
- ``version`` echoed
- ``fields`` honored
- Empty ``node`` → no item
- End-to-end: Manual → facebookGraphApi (get mock) → Set sees ``id`` and ``name``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.facebook import (
    FACEBOOK_DEFAULT_OPERATION,
    FACEBOOK_DEFAULT_VERSION,
    FACEBOOK_OPERATIONS,
    exec_facebook_graph_api,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.facebookGraphApi",
    id_: str = "fb1",
    name: str = "Facebook",
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


# ══════════════════════════════════════════════════════════════════════
#  facebook_response dict mock
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_facebook_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "operation": "get",
            "node": "me",
            "version": "v18.0",
        }
    )
    ctx = _ctx(
        {
            "facebook_response": {
                "id": "123456789",
                "name": "Real User",
                "email": "user@example.com",
            }
        }
    )
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p["id"] == "123456789"
    assert p["name"] == "Real User"
    assert p["email"] == "user@example.com"
    assert p["operation"] == "get"
    assert p["node"] == "me"
    assert p["version"] == "v18.0"
    assert p["source"] == "facebookGraphApi"
    assert "mockSource" not in p


# ══════════════════════════════════════════════════════════════════════
#  facebook_response callable mock signature
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_facebook_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, node, params, item, ctx):
        captured["operation"] = operation
        captured["node"] = node
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "from_callable",
            "name": "Callable Object",
        }

    node = _node(
        {
            "operation": "get",
            "node": "me/feed",
            "version": "v19.0",
            "parameters": {"limit": 5},
        }
    )
    ctx = _ctx({"facebook_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_facebook_graph_api(node, [item], ctx=ctx))

    assert captured["operation"] == "get"
    assert captured["node"] == "me/feed"
    assert captured["params"] == {"limit": 5}
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["id"] == "from_callable"
    assert out[0].json["name"] == "Callable Object"


# ══════════════════════════════════════════════════════════════════════
#  http_response fallback
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "get",
            "node": "me",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "id": "via_http",
                    "name": "Via HTTP",
                },
            }
        }
    )
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["id"] == "via_http"
    assert p["name"] == "Via HTTP"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "facebookGraphApi"


# ══════════════════════════════════════════════════════════════════════
#  Offline get
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_get_has_id_and_name() -> None:
    node = _node({"operation": "get", "node": "me", "version": "v18.0"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["id"] == "mock_fb_id"
    assert p["name"] == "Mock Facebook Object"
    assert p["data"] == []
    assert p["paging"]["cursors"]["before"] == "mock_before"
    assert p["paging"]["cursors"]["after"] == "mock_after"
    assert p["version"] == "v18.0"
    assert p["node"] == "me"
    assert p["operation"] == "get"
    assert p["source"] == "facebookGraphApi"
    assert p["mockSource"] == "offline"


# ══════════════════════════════════════════════════════════════════════
#  Offline post
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_post_has_id_and_success() -> None:
    node = _node({"operation": "post", "node": "me/feed", "version": "v18.0"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["id"], str)
    assert p["id"].startswith("mock_post_")
    assert p["success"] is True
    assert p["node"] == "me/feed"
    assert p["version"] == "v18.0"
    assert p["operation"] == "post"
    assert p["source"] == "facebookGraphApi"
    assert p["mockSource"] == "offline"


# ══════════════════════════════════════════════════════════════════════
#  Offline delete
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_delete_has_success() -> None:
    node = _node({"operation": "delete", "node": "123_456", "version": "v18.0"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["success"] is True
    assert p["node"] == "123_456"
    assert p["version"] == "v18.0"
    assert p["operation"] == "delete"
    assert p["source"] == "facebookGraphApi"
    assert p["mockSource"] == "offline"


# ══════════════════════════════════════════════════════════════════════
#  operation='get' reflected
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_operation_reflected_in_emitted_item() -> None:
    for op in FACEBOOK_OPERATIONS:
        node = _node({"operation": op, "node": "me", "version": "v18.0"})
        out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) == 1, f"no output for {op}"
        assert out[0].json["operation"] == op, f"operation not reflected for {op}"


@pytest.mark.asyncio
async def test_default_operation_is_get() -> None:
    node = _node({"node": "me"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["operation"] == "get"
    assert FACEBOOK_DEFAULT_OPERATION == "get"


# ══════════════════════════════════════════════════════════════════════
#  node default from $json
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_node_default_from_json() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"node": "me/posts"})
    out = _out_items(await exec_facebook_graph_api(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["node"] == "me/posts"


@pytest.mark.asyncio
async def test_node_path_alias_from_json() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"path": "me/accounts"})
    out = _out_items(await exec_facebook_graph_api(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["node"] == "me/accounts"


# ══════════════════════════════════════════════════════════════════════
#  version echoed
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_version_echoed() -> None:
    node = _node({"operation": "get", "node": "me", "version": "v19.0"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["version"] == "v19.0"


@pytest.mark.asyncio
async def test_default_version_is_v18() -> None:
    node = _node({"operation": "get", "node": "me"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["version"] == "v18.0"
    assert FACEBOOK_DEFAULT_VERSION == "v18.0"


# ══════════════════════════════════════════════════════════════════════
#  fields honored
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_fields_honored_for_get() -> None:
    node = _node(
        {
            "operation": "get",
            "node": "me",
            "fields": ["id", "name", "email"],
        }
    )
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["fields"] == ["id", "name", "email"]


@pytest.mark.asyncio
async def test_fields_not_echoed_when_empty() -> None:
    node = _node({"operation": "get", "node": "me"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert "fields" not in out[0].json


@pytest.mark.asyncio
async def test_fields_from_json_fallback() -> None:
    node = _node({"operation": "get", "node": "me"})
    item = ExecutionItem(json={"fields": ["name", "picture"]})
    out = _out_items(await exec_facebook_graph_api(node, [item], ctx=_ctx()))
    assert out[0].json["fields"] == ["name", "picture"]


# ══════════════════════════════════════════════════════════════════════
#  Empty node → no item
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_empty_node_skips_item() -> None:
    node = _node({"operation": "get", "node": "", "version": "v18.0"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_node_from_json_skips_item() -> None:
    node = _node({"operation": "get"})
    out = _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


# ══════════════════════════════════════════════════════════════════════
#  One output item per input
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({"operation": "get", "node": "me"})
    items = [
        ExecutionItem(json={"seq": 1}),
        ExecutionItem(json={"seq": 2}),
        ExecutionItem(json={"seq": 3}),
    ]
    out = _out_items(await exec_facebook_graph_api(node, items, ctx=_ctx()))
    assert len(out) == 3
    assert all(o.json["source"] == "facebookGraphApi" for o in out)
    assert [o.json["seq"] for o in out] == [1, 2, 3]


# ══════════════════════════════════════════════════════════════════════
#  parameters (dict) honored
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_parameters_dict_passed_to_callable_mock() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, node, params, item, ctx):
        captured["params"] = params
        return {"id": "ok"}

    node = _node(
        {
            "operation": "get",
            "node": "me",
            "parameters": {"limit": 10, "since": "2024-01-01"},
        }
    )
    ctx = _ctx({"facebook_response": _mock})
    _out_items(await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=ctx))
    assert captured["params"] == {"limit": 10, "since": "2024-01-01"}


@pytest.mark.asyncio
async def test_parameters_default_from_json() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, node, params, item, ctx):
        captured["params"] = params
        return {"id": "ok"}

    node = _node({"operation": "get", "node": "me"})
    item = ExecutionItem(json={"parameters": {"q": "test"}})
    ctx = _ctx({"facebook_response": _mock})
    _out_items(await exec_facebook_graph_api(node, [item], ctx=ctx))
    assert captured["params"] == {"q": "test"}


# ══════════════════════════════════════════════════════════════════════
#  Unsupported operation raises
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "patch", "node": "me"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_facebook_graph_api(node, [ExecutionItem(json={})], ctx=_ctx())


# ══════════════════════════════════════════════════════════════════════
#  Descriptor registration (CI invariant)
# ══════════════════════════════════════════════════════════════════════


def test_facebook_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.facebookGraphApi" in REGISTRY
    assert "n8n-nodes-base.facebookGraphApi" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.facebookGraphApi"] == "output"
    desc = REGISTRY["n8n-nodes-base.facebookGraphApi"]
    assert desc.executor.endswith(":exec_facebook_graph_api")
    assert desc.category == "output"


# ══════════════════════════════════════════════════════════════════════
#  End-to-end: Manual → facebookGraphApi (get mock) → Set sees id and name
# ══════════════════════════════════════════════════════════════════════


def _doc(nodes, connections):
    return {"name": "facebook-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_facebook_set_sees_id_and_name() -> None:
    mocks = {
        "facebook_response": {
            "id": "e2e_fb_id",
            "name": "E2E User",
            "email": "e2e@example.com",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "fb1",
                "Facebook",
                "n8n-nodes-base.facebookGraphApi",
                {
                    "operation": "get",
                    "node": "me",
                    "version": "v18.0",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_id", "value": "={{ $json.id }}", "type": "string"},
                            {"name": "result_name", "value": "={{ $json.name }}", "type": "string"},
                            {"name": "result_node", "value": "={{ $json.node }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Facebook", "type": "main", "index": 0}]]},
            "Facebook": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    fb_step = next(s for s in result.steps if s.node_name == "Facebook")
    assert fb_step.status == "success", fb_step.error
    assert fb_step.output_count == 1
    sample = fb_step.sample_output[0]
    assert sample["json"]["id"] == "e2e_fb_id"
    assert sample["json"]["name"] == "E2E User"
    assert sample["json"]["node"] == "me"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_id") == "e2e_fb_id"
    assert fjson.get("result_name") == "E2E User"
    assert fjson.get("result_node") == "me"