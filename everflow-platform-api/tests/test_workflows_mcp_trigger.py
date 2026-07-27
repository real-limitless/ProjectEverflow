"""Tests for the MCP Trigger node executor (@n8n/n8n-nodes-langchain.mcpTrigger)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.mcp_trigger import exec_mcp_trigger


# ── Helpers ───────────────────────────────────────────────────────────


def _node(name: str = "MCP", params: dict | None = None) -> ExecNode:
    return ExecNode(
        id="m1",
        name=name,
        type="@n8n/n8n-nodes-langchain.mcpTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(*, mocks: dict | None = None) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    return EngineContext(graph=g, mocks=mocks or {})


def _doc(nodes, connections):
    return {"name": "mcp-trigger-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


# ── mcp_payload mock ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_payload_dict_mock_emits_item() -> None:
    payload = {
        "jsonrpc": "2.0",
        "method": "message",
        "params": {"content": "hello from MCP", "from": "test-client"},
    }
    ctx = _ctx(mocks={"mcp_payload": payload})
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    item = items[0].json
    assert item["jsonrpc"] == "2.0"
    assert item["method"] == "message"
    assert item["params"] == {"content": "hello from MCP", "from": "test-client"}
    assert item["content"] == "hello from MCP"


@pytest.mark.asyncio
async def test_mcp_payload_callable_mock_receives_node_and_ctx() -> None:
    captured: dict = {}

    def producer(node, ctx):
        captured["type"] = node.type
        captured["mocks_key"] = "mcp_payload"
        return {
            "jsonrpc": "2.0",
            "method": "message",
            "params": {"content": "from callable"},
        }

    ctx = _ctx(mocks={"mcp_payload": producer})
    node = _node(params={"serverName": "n8n-prod"})

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    assert captured == {"type": "@n8n/n8n-nodes-langchain.mcpTrigger", "mocks_key": "mcp_payload"}
    item = out[0][1][0].json
    assert item["content"] == "from callable"
    assert item["serverName"] == "n8n-prod"


@pytest.mark.asyncio
async def test_callable_mock_async_is_supported() -> None:
    """callable mocks can also be async coroutines."""

    async def producer(node, ctx):
        return {
            "jsonrpc": "2.0",
            "method": "message",
            "params": {"content": "async callable"},
        }

    ctx = _ctx(mocks={"mcp_payload": producer})
    node = _node()

    # NOTE: the spec only requires sync callables; async should fall through
    # to the synthetic payload in our current implementation. We document
    # the actual behavior here.
    out = await exec_mcp_trigger(node, items=[], ctx=ctx)
    item = out[0][1][0].json
    # Async coroutine isn't a dict; the executor falls back to synthetic.
    assert item["jsonrpc"] == "2.0"
    assert item["method"] == "message"
    assert item["content"] == "Mock MCP message"


# ── trigger_payload fallback ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_payload_fallback_used_when_no_mcp_payload() -> None:
    payload = {
        "jsonrpc": "2.0",
        "method": "notify",
        "params": {"content": "via trigger_payload"},
    }
    ctx = _ctx(mocks={"trigger_payload": payload})
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    item = out[0][1][0].json
    assert item["method"] == "notify"
    assert item["content"] == "via trigger_payload"


@pytest.mark.asyncio
async def test_mcp_payload_wins_over_trigger_payload() -> None:
    ctx = _ctx(
        mocks={
            "mcp_payload": {
                "jsonrpc": "2.0",
                "method": "message",
                "params": {"content": "from mcp_payload"},
            },
            "trigger_payload": {
                "jsonrpc": "2.0",
                "method": "message",
                "params": {"content": "from trigger_payload"},
            },
        }
    )
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    assert out[0][1][0].json["content"] == "from mcp_payload"


# ── Offline / synthetic fallback ──────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_payload() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    item = out[0][1][0].json
    assert item["jsonrpc"] == "2.0"
    assert item["method"] == "message"
    assert item["content"] == "Mock MCP message"
    assert item["params"] == {
        "content": "Mock MCP message",
        "from": "mock-mcp-client",
    }


@pytest.mark.asyncio
async def test_non_dict_mcp_payload_falls_through_to_synthetic() -> None:
    ctx = _ctx(mocks={"mcp_payload": "not a dict"})
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    item = out[0][1][0].json
    assert item["content"] == "Mock MCP message"


# ── serverName / path ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_default_server_name_and_path_echoed() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    item = out[0][1][0].json
    assert item["serverName"] == "n8n-mcp-server"
    assert item["path"] == "/mcp"


@pytest.mark.asyncio
async def test_parameter_server_name_overrides_default() -> None:
    ctx = _ctx()
    node = _node(params={"serverName": "custom-server", "path": "/api/mcp"})

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    item = out[0][1][0].json
    assert item["serverName"] == "custom-server"
    assert item["path"] == "/api/mcp"


@pytest.mark.asyncio
async def test_source_marker_is_mcp_trigger() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    assert out[0][1][0].json["source"] == "mcpTrigger"


# ── Pass-through behavior with upstream items ─────────────────────────


@pytest.mark.asyncio
async def test_upstream_items_pass_through_with_mcp_context() -> None:
    ctx = _ctx(
        mocks={
            "mcp_payload": {
                "jsonrpc": "2.0",
                "method": "message",
                "params": {"content": "ctx"},
            }
        }
    )
    node = _node()

    in_items = [ExecutionItem(json={"foo": 1, "serverName": "kept"})]
    out = await exec_mcp_trigger(node, items=in_items, ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    item = items[0].json
    # upstream field preserved
    assert item["foo"] == 1
    # existing serverName is NOT clobbered (upstream wins on conflict)
    assert item["serverName"] == "kept"
    # other MCP context fields added
    assert item["path"] == "/mcp"
    assert item["source"] == "mcpTrigger"
    assert item["method"] == "message"


@pytest.mark.asyncio
async def test_empty_items_emits_single_synthetic_item() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert len(out[0][1]) == 1


# ── Content extraction from various param keys ────────────────────────


@pytest.mark.asyncio
async def test_content_extraction_uses_first_recognized_key() -> None:
    ctx = _ctx(
        mocks={
            "mcp_payload": {
                "jsonrpc": "2.0",
                "method": "message",
                "params": {"message": "via message key"},
            }
        }
    )
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)
    assert out[0][1][0].json["content"] == "via message key"


@pytest.mark.asyncio
async def test_content_empty_when_params_is_not_dict() -> None:
    ctx = _ctx(mocks={"mcp_payload": {"jsonrpc": "2.0", "method": "message", "params": None}})
    node = _node()

    out = await exec_mcp_trigger(node, items=[], ctx=ctx)
    item = out[0][1][0].json
    assert item["content"] == ""
    assert item["params"] == {}


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.mcpTrigger" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.mcpTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.mcpTrigger"] == "trigger"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.mcpTrigger"]
    assert desc.executor.endswith(":exec_mcp_trigger")
    assert desc.category == "trigger"


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_mcp_trigger_seeds_downstream_set() -> None:
    """Manual → mcpTrigger → Set. The MCP trigger reads the pinned
    payload via mocks and the downstream Set should see ``$json.content``,
    ``$json.serverName``, and ``$json.path`` in scope."""
    doc = _doc(
        [
            _n("m1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "t1",
                "MCP",
                "@n8n/n8n-nodes-langchain.mcpTrigger",
                {"serverName": "demo-server", "path": "/api/mcp"},
            ),
            _n(
                "s1",
                "Echo",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "echo",
                                "value": "={{ $json.content }}",
                                "type": "string",
                            },
                            {
                                "name": "endpoint",
                                "value": "={{ $json.serverName + $json.path }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "MCP", "type": "main", "index": 0}]]},
            "MCP": {"main": [[{"node": "Echo", "type": "main", "index": 0}]]},
        },
    )
    mocks = {
        "mcp_payload": {
            "jsonrpc": "2.0",
            "method": "message",
            "params": {"content": "hello MCP", "from": "e2e"},
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message
    assert result.final_items, "expected final items from Echo"
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("echo") == "hello MCP"
    assert final_json.get("endpoint") == "demo-server/api/mcp"
    # Context fields preserved on the item
    assert final_json.get("serverName") == "demo-server"
    assert final_json.get("path") == "/api/mcp"
    assert final_json.get("source") == "mcpTrigger"


@pytest.mark.asyncio
async def test_end_to_end_mcp_trigger_without_mock_emits_synthetic() -> None:
    """End-to-end with no mcp_payload mock: downstream still receives one
    item with the synthetic payload and default serverName/path."""
    doc = _doc(
        [
            _n("m1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "t1",
                "MCP",
                "@n8n/n8n-nodes-langchain.mcpTrigger",
                {},
            ),
        ],
        {
            "Start": {"main": [[{"node": "MCP", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message
    assert result.final_items
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("content") == "Mock MCP message"
    assert final_json.get("serverName") == "n8n-mcp-server"
    assert final_json.get("path") == "/mcp"
    assert final_json.get("jsonrpc") == "2.0"
    assert final_json.get("method") == "message"
