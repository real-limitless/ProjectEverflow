"""Tests for the Jira node executor (``n8n-nodes-base.jira``).

Covers:

- ``jira_response`` dict mock → response used verbatim
- ``jira_response`` callable mock receives ``(operation, issue_or_jql, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline ``create`` (issueId and issueKey present, key starts with projectKey)
- Offline ``get`` (issueKey echoed, status present)
- Offline ``update`` (summary echoed)
- Offline ``search`` (returns up to 3 issues)
- Offline ``delete`` (success=True)
- Operation reflected in emitted item
- ``issueKey`` default from ``$json``
- ``projectKey`` default from ``$json``
- ``maxResults`` honored
- Empty ``issueKey`` for get → no item
- End-to-end: Manual → jira (search mock) → Set sees issues
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.jira import (
    JIRA_DEFAULT_OPERATION,
    JIRA_OPERATIONS,
    exec_jira,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.jira",
    id_: str = "jira1",
    name: str = "Jira",
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
#  1. jira_response dict mock
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_jira_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "operation": "get",
            "issueKey": "DEMO-42",
        }
    )
    ctx = _ctx(
        {
            "jira_response": {
                "id": "10042",
                "key": "DEMO-42",
                "self": "https://mock-jira.atlassian.net/rest/api/3/issue/10042",
                "fields": {
                    "summary": "Found a bug",
                    "description": "Something is broken",
                    "status": {"name": "In Progress"},
                    "issuetype": {"name": "Bug"},
                    "project": {"key": "DEMO"},
                    "created": "2024-01-01T00:00:00.000Z",
                },
            }
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p["issueId"] == "10042"
    assert p["issueKey"] == "DEMO-42"
    assert p["summary"] == "Found a bug"
    assert p["description"] == "Something is broken"
    assert p["status"] == "In Progress"
    assert p["issueType"] == "Bug"
    assert p["projectKey"] == "DEMO"
    assert p["source"] == "jira"


# ══════════════════════════════════════════════════════════════════════
#  2. jira_response callable mock signature
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_jira_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, issue_or_jql, params, item, ctx):
        captured["operation"] = operation
        captured["issue_or_jql"] = issue_or_jql
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "7",
            "key": "DEMO-7",
            "self": "https://mock-jira.atlassian.net/rest/api/3/issue/7",
            "fields": {
                "summary": "from callable",
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "project": {"key": "DEMO"},
            },
        }

    node = _node(
        {
            "operation": "get",
            "issueKey": "DEMO-7",
            "extra": "keep",
        }
    )
    ctx = _ctx({"jira_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_jira(node, [item], ctx=ctx))

    assert captured["operation"] == "get"
    assert captured["issue_or_jql"] == "DEMO-7"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["issueId"] == "7"
    assert out[0].json["issueKey"] == "DEMO-7"
    assert out[0].json["summary"] == "from callable"


# ══════════════════════════════════════════════════════════════════════
#  3. http_response fallback
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "get",
            "issueKey": "DEMO-99",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "id": "99",
                    "key": "DEMO-99",
                    "self": "https://mock-jira.atlassian.net/rest/api/3/issue/99",
                    "fields": {
                        "summary": "via http",
                        "status": {"name": "Open"},
                        "issuetype": {"name": "Task"},
                        "project": {"key": "DEMO"},
                    },
                },
            }
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["issueId"] == "99"
    assert p["summary"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "jira"


# ══════════════════════════════════════════════════════════════════════
#  4. Offline create
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_create_issue_id_and_key_present() -> None:
    node = _node(
        {
            "operation": "create",
            "projectKey": "DEMO",
            "summary": "New bug",
            "description": "Steps to reproduce",
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["issueId"]
    assert p["issueKey"]
    assert p["issueKey"].startswith("DEMO-")
    assert p["summary"] == "New bug"
    assert p["description"] == "Steps to reproduce"
    assert p["status"] == "Open"
    assert p["issueType"] == "Task"
    assert p["projectKey"] == "DEMO"
    assert p["source"] == "jira"
    assert p["mockSource"] == "offline"


# ══════════════════════════════════════════════════════════════════════
#  5. Offline get
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_get_issue_key_echoed_and_status_present() -> None:
    node = _node(
        {
            "operation": "get",
            "issueKey": "DEMO-55",
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["issueKey"] == "DEMO-55"
    assert p["status"] == "Open"
    assert p["summary"] == "Mock Issue"
    assert p["source"] == "jira"
    assert p["mockSource"] == "offline"


# ══════════════════════════════════════════════════════════════════════
#  6. Offline update
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_update_summary_echoed() -> None:
    node = _node(
        {
            "operation": "update",
            "issueKey": "DEMO-33",
            "summary": "Updated title",
            "status": "In Progress",
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["issueKey"] == "DEMO-33"
    assert p["summary"] == "Updated title"
    assert p["status"] == "In Progress"
    assert p["source"] == "jira"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_update_defaults_summary() -> None:
    node = _node(
        {
            "operation": "update",
            "issueKey": "DEMO-10",
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["summary"] == "Updated"
    assert p["status"] == "Open"


# ══════════════════════════════════════════════════════════════════════
#  7. Offline search
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_search_returns_up_to_3_issues() -> None:
    node = _node(
        {
            "operation": "search",
            "jql": "project = DEMO ORDER BY created DESC",
            "maxResults": 10,
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 3
    for i, item in enumerate(out, start=1):
        p = item.json
        assert p["issueKey"] == f"DEMO-{i}"
        assert p["summary"] == f"Mock Issue {i}"
        assert p["status"] == "Open"
        assert p["assignee"] == "Mock User"
        assert p["source"] == "jira"
        assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_search_data_mode_object() -> None:
    node = _node(
        {
            "operation": "search",
            "dataMode": "object",
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert "issues" in p
    assert isinstance(p["issues"], list)
    assert len(p["issues"]) == 3
    assert p["total"] == 3
    assert p["source"] == "jira"


# ══════════════════════════════════════════════════════════════════════
#  8. Offline delete
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_delete_success_true() -> None:
    node = _node(
        {
            "operation": "delete",
            "issueKey": "DEMO-77",
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["issueKey"] == "DEMO-77"
    assert p["success"] is True
    assert "deletedAt" in p
    assert p["source"] == "jira"
    assert p["mockSource"] == "offline"


# ══════════════════════════════════════════════════════════════════════
#  9. Operation reflected
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_operation_reflected_in_emitted_item() -> None:
    for op in JIRA_OPERATIONS:
        params: dict[str, Any] = {
            "operation": op,
            "issueKey": "DEMO-1",
            "projectKey": "DEMO",
            "summary": "T",
            "jql": "project = DEMO",
            "maxResults": 5,
        }
        node = _node(params)
        out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) >= 1, f"no output for {op}"
        assert out[0].json["source"] == "jira"


# ══════════════════════════════════════════════════════════════════════
#  10. issueKey default from $json
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_issue_key_default_from_json() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"issueKey": "PROJ-123"})
    out = _out_items(await exec_jira(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["issueKey"] == "PROJ-123"


@pytest.mark.asyncio
async def test_issue_key_default_from_json_key_alias() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"key": "PROJ-456"})
    out = _out_items(await exec_jira(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["issueKey"] == "PROJ-456"


@pytest.mark.asyncio
async def test_issue_key_default_from_json_id_alias() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"id": "PROJ-789"})
    out = _out_items(await exec_jira(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["issueKey"] == "PROJ-789"


# ══════════════════════════════════════════════════════════════════════
#  11. projectKey default from $json
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_project_key_default_from_json() -> None:
    node = _node({"operation": "create", "summary": "T"})
    item = ExecutionItem(json={"projectKey": "PROJ"})
    out = _out_items(await exec_jira(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["issueKey"].startswith("PROJ-")
    assert out[0].json["projectKey"] == "PROJ"


# ══════════════════════════════════════════════════════════════════════
#  12. maxResults honored
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_max_results_honored() -> None:
    node = _node(
        {
            "operation": "search",
            "maxResults": 2,
        }
    )
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 2


@pytest.mark.asyncio
async def test_max_results_honored_from_json() -> None:
    node = _node({"operation": "search"})
    item = ExecutionItem(json={"maxResults": 1})
    out = _out_items(await exec_jira(node, [item], ctx=_ctx()))
    assert len(out) == 1


# ══════════════════════════════════════════════════════════════════════
#  13. Empty issueKey for get → no item
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_empty_issue_key_for_get_skips_item() -> None:
    node = _node({"operation": "get", "issueKey": ""})
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_issue_key_for_update_skips_item() -> None:
    node = _node({"operation": "update", "issueKey": ""})
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_issue_key_for_delete_skips_item() -> None:
    node = _node({"operation": "delete", "issueKey": ""})
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_project_key_for_create_skips_item() -> None:
    node = _node({"operation": "create", "projectKey": ""})
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


# ══════════════════════════════════════════════════════════════════════
#  14. Default operation is get
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_default_operation_is_get() -> None:
    node = _node({"issueKey": "DEMO-1"})
    out = _out_items(await exec_jira(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["issueKey"] == "DEMO-1"
    assert JIRA_DEFAULT_OPERATION == "get"


# ══════════════════════════════════════════════════════════════════════
#  15. One output item per input (for get)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({"operation": "get"})
    items = [
        ExecutionItem(json={"issueKey": "DEMO-10"}),
        ExecutionItem(json={"issueKey": "DEMO-20"}),
        ExecutionItem(json={"issueKey": "DEMO-30"}),
    ]
    out = _out_items(await exec_jira(node, items, ctx=_ctx()))
    assert len(out) == 3
    keys = [o.json["issueKey"] for o in out]
    assert keys == ["DEMO-10", "DEMO-20", "DEMO-30"]
    assert all(o.json["source"] == "jira" for o in out)


# ══════════════════════════════════════════════════════════════════════
#  16. Descriptor registration
# ══════════════════════════════════════════════════════════════════════


def test_jira_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.jira" in REGISTRY
    assert "n8n-nodes-base.jira" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.jira"] == "output"
    desc = REGISTRY["n8n-nodes-base.jira"]
    assert desc.executor.endswith(":exec_jira")
    assert desc.category == "output"


# ══════════════════════════════════════════════════════════════════════
#  17. End-to-end: Manual → jira (search mock) → Set sees issues
# ══════════════════════════════════════════════════════════════════════


def _doc(nodes, connections):
    return {"name": "jira-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_jira_search_set_sees_issues() -> None:
    mocks = {
        "jira_response": {
            "startAt": 0,
            "maxResults": 10,
            "total": 2,
            "issues": [
                {
                    "id": "1",
                    "key": "DEMO-1",
                    "fields": {
                        "summary": "E2E Issue 1",
                        "status": {"name": "Open"},
                        "assignee": {"displayName": "Alice"},
                    },
                },
                {
                    "id": "2",
                    "key": "DEMO-2",
                    "fields": {
                        "summary": "E2E Issue 2",
                        "status": {"name": "Done"},
                        "assignee": {"displayName": "Bob"},
                    },
                },
            ],
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "j1",
                "Jira",
                "n8n-nodes-base.jira",
                {
                    "operation": "search",
                    "jql": "project = DEMO",
                    "maxResults": 10,
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_key", "value": "={{ $json.issueKey }}", "type": "string"},
                            {"name": "result_summary", "value": "={{ $json.summary }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Jira", "type": "main", "index": 0}]]},
            "Jira": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    jira_step = next(s for s in result.steps if s.node_name == "Jira")
    assert jira_step.status == "success", jira_step.error
    assert jira_step.output_count == 2
    sample = jira_step.sample_output[0]
    assert sample["json"]["issueKey"] == "DEMO-1"
    assert sample["json"]["summary"] == "E2E Issue 1"
    assert sample["json"]["source"] == "jira"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_key") == "DEMO-1"
    assert fjson.get("result_summary") == "E2E Issue 1"
    assert fjson.get("result_source") == "jira"