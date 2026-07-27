"""Tests for the ``n8n-nodes-base.httpRequest`` clean-room executor.

Covers:

- GET via ``ctx.mocks['http']`` returns a parsed JSON body.
- POST with JSON body via mocks.
- 5xx response sets ``error`` field when ``continue_on_fail=True``.
- 5xx response raises when ``continue_on_fail=False``.
- Auth resolution: header / bearer / basic via ``ctx.credentials``.
- End-to-end engine: Manual Trigger → httpRequest (mock) → Set.
"""

from __future__ import annotations

import base64
import json
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
    retry_on_fail: bool = False,
    max_tries: int | None = None,
    credentials: dict[str, Any] | None = None,
) -> ExecNode:
    return ExecNode(
        id="http1",
        name="HTTP",
        type="n8n-nodes-base.httpRequest",
        type_version=4.1,
        parameters=params,
        credentials=credentials,
        position={"x": 0, "y": 0},
        retry_on_fail=retry_on_fail,
        max_tries=max_tries,
        continue_on_fail=continue_on_fail,
        disabled=False,
    )


def _ctx(mocks: dict[str, Any] | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.nodes_by_id = {}
    g.out_edges = {}
    return EngineContext(graph=g, mocks=mocks or {})


# ── 1. GET via mock returns JSON body ────────────────────────────────


@pytest.mark.asyncio
async def test_get_via_mock_returns_parsed_json() -> None:
    node = _node(
        params={
            "method": "GET",
            "url": "https://api.example.com/v1/items",
        }
    )
    ctx = _ctx(
        {
            "http": {
                "GET https://api.example.com/v1/items": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"items": [1, 2, 3], "count": 3},
                }
            }
        }
    )
    result = await http_node.exec_http_request(node, [ExecutionItem(json={})], ctx=ctx)
    assert len(result) == 1
    out_idx, out_items = result[0]
    assert out_idx == 0
    assert len(out_items) == 1
    payload = out_items[0].json
    assert payload["statusCode"] == 200
    assert payload["body"] == {"items": [1, 2, 3], "count": 3}
    assert payload["url"] == "https://api.example.com/v1/items"
    assert payload["elapsedMs"] == 0
    assert payload["request"]["method"] == "GET"
    assert payload["request"]["url"] == "https://api.example.com/v1/items"


# ── 2. POST with JSON body via mock ──────────────────────────────────


@pytest.mark.asyncio
async def test_post_with_json_body_via_mock() -> None:
    node = _node(
        params={
            "method": "POST",
            "url": "https://api.example.com/v1/echo",
            "sendBody": True,
            "bodyContentType": "json",
            "jsonBody": {"hello": "world", "n": 7},
            "headers": {
                "parameters": [{"name": "X-Test", "value": "yes"}],
            },
        }
    )
    ctx = _ctx(
        {
            "http": {
                "POST https://api.example.com/v1/echo": {
                    "status": 201,
                    "headers": {"content-type": "application/json"},
                    "body": {"ok": True, "echoed": True},
                }
            }
        }
    )
    result = await http_node.exec_http_request(node, [ExecutionItem(json={"x": 1})], ctx=ctx)
    assert len(result) == 1
    _, out_items = result[0]
    payload = out_items[0].json
    # upstream item fields are preserved
    assert payload["x"] == 1
    assert payload["statusCode"] == 201
    assert payload["body"] == {"ok": True, "echoed": True}
    # request echo
    assert payload["request"]["method"] == "POST"
    assert payload["request"]["body"] == {"hello": "world", "n": 7}
    # user-set header
    assert payload["request"]["headers"]["X-Test"] == "yes"


# ── 3. 5xx with continue_on_fail=True attaches error field ───────────


@pytest.mark.asyncio
async def test_5xx_with_continue_on_fail_attaches_error() -> None:
    node = _node(
        params={
            "method": "GET",
            "url": "https://api.example.com/v1/down",
        },
        continue_on_fail=True,
    )
    ctx = _ctx(
        {
            "http": {
                "GET https://api.example.com/v1/down": {
                    "status": 503,
                    "headers": {},
                    "body": "service unavailable",
                }
            }
        }
    )
    result = await http_node.exec_http_request(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    payload = out_items[0].json
    assert payload["statusCode"] == 503
    assert "error" in payload
    assert "503" in payload["error"]
    assert "https://api.example.com/v1/down" in payload["error"]


# ── 4. 5xx with continue_on_fail=False raises ────────────────────────


@pytest.mark.asyncio
async def test_5xx_without_continue_on_fail_raises() -> None:
    node = _node(
        params={
            "method": "GET",
            "url": "https://api.example.com/v1/bad",
        },
        continue_on_fail=False,
    )
    ctx = _ctx(
        {
            "http": {
                "GET https://api.example.com/v1/bad": {
                    "status": 500,
                    "headers": {},
                    "body": "boom",
                }
            }
        }
    )
    with pytest.raises(RuntimeError, match="500"):
        await http_node.exec_http_request(node, [ExecutionItem(json={})], ctx=ctx)


# ── 5. Auth resolution: header / bearer / basic ─────────────────────


@pytest.mark.asyncio
async def test_auth_header_resolution_via_credentials() -> None:
    node = _node(
        params={
            "method": "GET",
            "url": "https://api.example.com/v1/secret",
            "authentication": "genericCredentialType",
            "nodeCredentialType": "httpHeaderAuth",
        },
    )
    ctx = _ctx(
        {
            "http": {
                "GET https://api.example.com/v1/secret": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"ok": True},
                }
            }
        }
    )
    ctx.credentials["httpHeaderAuth"] = {"name": "X-Api-Key", "value": "shhh"}
    result = await http_node.exec_http_request(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    payload = out_items[0].json
    assert payload["statusCode"] == 200
    assert payload["request"]["headers"].get("X-Api-Key") == "shhh"


@pytest.mark.asyncio
async def test_auth_bearer_resolution_via_credentials() -> None:
    node = _node(
        params={
            "method": "GET",
            "url": "https://api.example.com/v1/bearer",
            "authentication": "genericCredentialType",
            "nodeCredentialType": "httpBearerAuth",
        },
    )
    ctx = _ctx(
        {
            "http": {
                "GET https://api.example.com/v1/bearer": {
                    "status": 200,
                    "headers": {},
                    "body": {"who": "user"},
                }
            }
        }
    )
    ctx.credentials["httpBearerAuth"] = {"token": "tk_abc"}
    result = await http_node.exec_http_request(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    headers = out_items[0].json["request"]["headers"]
    assert headers.get("Authorization") == "Bearer tk_abc"


@pytest.mark.asyncio
async def test_auth_basic_resolution_via_credentials() -> None:
    node = _node(
        params={
            "method": "GET",
            "url": "https://api.example.com/v1/basic",
            "authentication": "genericCredentialType",
            "nodeCredentialType": "httpBasicAuth",
        },
    )
    ctx = _ctx(
        {
            "http": {
                "GET https://api.example.com/v1/basic": {
                    "status": 200,
                    "headers": {},
                    "body": {"who": "user"},
                }
            }
        }
    )
    ctx.credentials["httpBasicAuth"] = {"user": "alice", "password": "wonderland"}
    result = await http_node.exec_http_request(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    auth = out_items[0].json["request"]["headers"].get("Authorization", "")
    assert auth.startswith("Basic ")
    decoded = base64.b64decode(auth.split(" ", 1)[1]).decode("ascii")
    assert decoded == "alice:wonderland"


# ── 6. End-to-end: Manual Trigger → httpRequest (mock) → Set ─────────


@pytest.mark.asyncio
async def test_e2e_manual_http_set_pipeline() -> None:
    doc = {
        "name": "e2e-http",
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
                "id": "h1",
                "name": "Fetch",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.1,
                "position": [200, 0],
                "parameters": {
                    "method": "GET",
                    "url": "https://api.example.com/v1/data",
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
                                "name": "code",
                                "value": "={{ $json.statusCode }}",
                                "type": "number",
                            },
                            {
                                "name": "firstName",
                                "value": "={{ $json.body.name }}",
                                "type": "string",
                            },
                        ]
                    },
                    "includeOtherFields": False,
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Fetch", "type": "main", "index": 0}]]},
            "Fetch": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    }
    mocks = {
        "http": {
            "GET https://api.example.com/v1/data": {
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": {"name": "alpha", "id": 42},
            }
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    fetch_step = next(s for s in result.steps if s.node_name == "Fetch")
    assert fetch_step.status == "success"
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.status == "success"
    # Set saw the http response fields
    assert set_step.sample_output
    set_json = set_step.sample_output[0]["json"]
    assert set_json["code"] == 200
    assert set_json["firstName"] == "alpha"
    # and downstream final items also carry them
    final_json = result.final_items[0]["json"]
    assert final_json["code"] == 200
    assert final_json["firstName"] == "alpha"
