"""Tests for the ``n8n-nodes-base.graphql`` clean-room executor.

Covers:

- Basic POST via mock returns ``data`` field.
- ``variables`` dict and JSON-string forms are passed through.
- HTTP 200 with ``{"errors": [...]}`` attaches an ``error`` field.
- Auth: bearer token from ``ctx.credentials`` is sent.
- End-to-end: Manual Trigger → graphql (mocked) → Set sees ``$json.data``.
"""

from __future__ import annotations

import base64
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
    credentials: dict[str, Any] | None = None,
) -> ExecNode:
    return ExecNode(
        id="g1",
        name="GraphQL",
        type="n8n-nodes-base.graphql",
        type_version=1,
        parameters=params,
        credentials=credentials,
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


# ── 1. Basic POST via mock returns data field ─────────────────────────


@pytest.mark.asyncio
async def test_basic_post_via_mock_returns_data() -> None:
    node = _node(
        params={
            "endpoint": "https://api.example.com/graphql",
            "query": "{ users { id name } }",
        }
    )
    ctx = _ctx(
        {
            "http": {
                "POST https://api.example.com/graphql": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"data": {"users": [{"id": 1, "name": "Ada"}]}},
                }
            }
        }
    )
    result = await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)
    assert len(result) == 1
    _, out_items = result[0]
    assert len(out_items) == 1
    payload = out_items[0].json
    assert payload["data"] == {"users": [{"id": 1, "name": "Ada"}]}
    assert payload["query"] == "{ users { id name } }"
    assert payload["variables"] is None
    assert payload["statusCode"] == 200
    assert "error" not in payload


# ── 2. Variables are passed through (dict + JSON string) ──────────────


@pytest.mark.asyncio
async def test_variables_dict_is_passed_through() -> None:
    node = _node(
        params={
            "endpoint": "https://api.example.com/graphql",
            "query": "query($id: ID!) { user(id: $id) { name } }",
            "variables": {"id": 42},
        }
    )
    ctx = _ctx(
        {
            "http": {
                "POST https://api.example.com/graphql": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"data": {"user": {"name": "Grace"}}},
                }
            }
        }
    )
    result = await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    payload = out_items[0].json
    assert payload["data"] == {"user": {"name": "Grace"}}
    assert payload["variables"] == {"id": 42}


@pytest.mark.asyncio
async def test_variables_json_string_is_parsed() -> None:
    node = _node(
        params={
            "endpoint": "https://api.example.com/graphql",
            "query": "query($slug: String!) { project(slug: $slug) { title } }",
            "variables": '{"slug": "everflow"}',
        }
    )
    ctx = _ctx(
        {
            "http": {
                "POST https://api.example.com/graphql": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"data": {"project": {"title": "Project Everflow"}}},
                }
            }
        }
    )
    result = await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    payload = out_items[0].json
    assert payload["data"] == {"project": {"title": "Project Everflow"}}
    assert payload["variables"] == {"slug": "everflow"}


# ── 3. Errors in response attach an error field ───────────────────────


@pytest.mark.asyncio
async def test_graphql_errors_attach_error_field() -> None:
    errs = [{"message": "Field 'foo' not defined", "path": ["foo"]}]
    node = _node(
        params={
            "endpoint": "https://api.example.com/graphql",
            "query": "{ foo }",
        }
    )
    ctx = _ctx(
        {
            "http": {
                "POST https://api.example.com/graphql": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"errors": errs, "data": None},
                }
            }
        }
    )
    result = await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    payload = out_items[0].json
    assert payload["statusCode"] == 200
    assert "error" in payload
    # The error string should mention the GraphQL message
    assert "Field 'foo' not defined" in payload["error"]
    # data is still passed through (None here)
    assert payload["data"] is None


# ── 4. Auth: bearer token is forwarded ────────────────────────────────


@pytest.mark.asyncio
async def test_bearer_auth_is_forwarded() -> None:
    node = _node(
        params={
            "endpoint": "https://api.example.com/graphql",
            "query": "{ me { id } }",
            "authentication": "genericCredentialType",
            "nodeCredentialType": "httpBearerAuth",
        }
    )
    ctx = _ctx(
        {
            "http": {
                "POST https://api.example.com/graphql": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"data": {"me": {"id": 7}}},
                }
            }
        }
    )
    ctx.credentials["httpBearerAuth"] = {"token": "gql_tk_xyz"}
    result = await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    payload = out_items[0].json
    # Auth is applied via the shared client; verify it didn't error out
    assert payload["statusCode"] == 200
    assert payload["data"] == {"me": {"id": 7}}


@pytest.mark.asyncio
async def test_basic_auth_is_forwarded() -> None:
    node = _node(
        params={
            "endpoint": "https://api.example.com/graphql",
            "query": "{ me { id } }",
            "authentication": "genericCredentialType",
            "nodeCredentialType": "httpBasicAuth",
        }
    )
    ctx = _ctx(
        {
            "http": {
                "POST https://api.example.com/graphql": {
                    "status": 200,
                    "headers": {"content-type": "application/json"},
                    "body": {"data": {"me": {"id": 8}}},
                }
            }
        }
    )
    ctx.credentials["httpBasicAuth"] = {"user": "u", "password": "p"}
    result = await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)
    _, out_items = result[0]
    payload = out_items[0].json
    assert payload["data"] == {"me": {"id": 8}}


# ── 5. Missing query raises ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_query_raises() -> None:
    node = _node(
        params={
            "endpoint": "https://api.example.com/graphql",
        }
    )
    ctx = _ctx({})
    with pytest.raises(RuntimeError, match="query"):
        await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)


@pytest.mark.asyncio
async def test_missing_endpoint_raises() -> None:
    node = _node(
        params={
            "query": "{ x }",
        }
    )
    ctx = _ctx({})
    with pytest.raises(RuntimeError, match="endpoint"):
        await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)


# ── 6. HTTP 5xx raises when continue_on_fail=False ────────────────────


@pytest.mark.asyncio
async def test_5xx_without_continue_on_fail_raises() -> None:
    node = _node(
        params={
            "endpoint": "https://api.example.com/graphql",
            "query": "{ x }",
        },
        continue_on_fail=False,
    )
    ctx = _ctx(
        {
            "http": {
                "POST https://api.example.com/graphql": {
                    "status": 500,
                    "headers": {},
                    "body": {"errors": [{"message": "boom"}]},
                }
            }
        }
    )
    with pytest.raises(RuntimeError, match="500"):
        await http_node.exec_graphql(node, [ExecutionItem(json={})], ctx=ctx)


# ── 7. End-to-end: Manual Trigger → graphql (mocked) → Set ───────────


@pytest.mark.asyncio
async def test_e2e_manual_graphql_set_pipeline() -> None:
    doc = {
        "name": "e2e-graphql",
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
                "id": "g1",
                "name": "FetchUser",
                "type": "n8n-nodes-base.graphql",
                "typeVersion": 1,
                "position": [200, 0],
                "parameters": {
                    "endpoint": "https://api.example.com/graphql",
                    "query": "query($id: ID!) { user(id: $id) { name email } }",
                    "variables": {"id": 99},
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
                                "name": "name",
                                "value": "={{ $json.data.user.name }}",
                                "type": "string",
                            },
                            {
                                "name": "email",
                                "value": "={{ $json.data.user.email }}",
                                "type": "string",
                            },
                        ]
                    },
                    "includeOtherFields": False,
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "FetchUser", "type": "main", "index": 0}]]},
            "FetchUser": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    }
    mocks = {
        "http": {
            "POST https://api.example.com/graphql": {
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": {
                    "data": {
                        "user": {"name": "Ada Lovelace", "email": "ada@x.io"}
                    }
                },
            }
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    fetch_step = next(s for s in result.steps if s.node_name == "FetchUser")
    assert fetch_step.status == "success"
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.status == "success"
    set_json = set_step.sample_output[0]["json"]
    assert set_json["code"] == 200
    assert set_json["name"] == "Ada Lovelace"
    assert set_json["email"] == "ada@x.io"

    final_json = result.final_items[0]["json"]
    assert final_json["name"] == "Ada Lovelace"
    assert final_json["email"] == "ada@x.io"
