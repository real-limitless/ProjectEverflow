"""Tests for utility extra executors."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem, items_from_json_list
from app.services.workflows.nodes.utility_extra import (
    exec_activation_trigger,
    exec_debug_helper,
    exec_evaluation,
    exec_evaluation_trigger,
    exec_execute_command,
    exec_form,
    exec_hacker_news,
    exec_icalendar,
    exec_n8n,
    exec_n8n_trigger,
    exec_quick_chart,
    exec_ldap,
    exec_totp,
)


def _node(
    type_: str,
    params: dict[str, Any] | None = None,
    id_: str = "n1",
    name: str = "Node",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
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


def _out_items(result):
    out = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── Debug Helper ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_debug_helper_mock_dict_logged() -> None:
    node = _node("n8n-nodes-base.debugHelper", {"options": {"prefix": "T:"}})
    ctx = _ctx({"debug_helper_response": {"custom": "log"}})
    ctx.debug_log = []  # type: ignore[attr-defined]
    result = await exec_debug_helper(node, _items([{"a": 1}]), ctx=ctx)
    assert ctx.debug_log[-1]["data"] == {"custom": "log"}  # type: ignore[attr-defined]
    assert ctx.debug_log[-1]["prefix"] == "T:"  # type: ignore[attr-defined]
    assert result[0][1][0].json == {"a": 1}


@pytest.mark.asyncio
async def test_debug_helper_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append((operation, params, item, ctx))
        return {"mocked": True}

    node = _node("n8n-nodes-base.debugHelper", {"options": {"logLevel": "debug"}})
    ctx = _ctx({"debug_helper_response": mock})
    ctx.debug_log = []  # type: ignore[attr-defined]
    await exec_debug_helper(node, _items([{"x": 1}]), ctx=ctx)
    assert seen[0][0] == ""
    assert seen[0][1] == {"options": {"logLevel": "debug"}}
    assert seen[0][2].json == {"x": 1}
    assert seen[0][3] is ctx


@pytest.mark.asyncio
async def test_debug_helper_offline_logs_item_json() -> None:
    node = _node("n8n-nodes-base.debugHelper")
    ctx = _ctx()
    ctx.debug_log = []  # type: ignore[attr-defined]
    await exec_debug_helper(node, _items([{"val": 42}]), ctx=ctx)
    assert ctx.debug_log[-1]["data"] == {"val": 42}  # type: ignore[attr-defined]
    assert ctx.debug_log[-1]["level"] == "info"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_debug_helper_http_fallback() -> None:
    node = _node("n8n-nodes-base.debugHelper")
    ctx = _ctx({"http_response": {"body": {"fb": True}}})
    ctx.debug_log = []  # type: ignore[attr-defined]
    await exec_debug_helper(node, _items([{}]), ctx=ctx)
    assert ctx.debug_log[-1]["data"] == {"fb": True}  # type: ignore[attr-defined]
    assert ctx.debug_log[-1]["mockSource"] == "http_response"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_debug_helper_passes_items_unchanged() -> None:
    node = _node("n8n-nodes-base.debugHelper")
    ctx = _ctx()
    result = await exec_debug_helper(node, _items([{"a": 1}, {"b": 2}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 2
    assert out[0].json == {"a": 1}
    assert out[1].json == {"b": 2}


# ── Execute Command ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_command_mock_dict() -> None:
    node = _node("n8n-nodes-base.executeCommand", {"command": "echo hi"})
    ctx = _ctx({"execute_command_response": {"stdout": "hi", "stderr": "", "exitCode": 0}})
    result = await exec_execute_command(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["stdout"] == "hi"
    assert out[0].json["exitCode"] == 0
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_execute_command_callable() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append((operation, params))
        return {"stdout": "ok", "stderr": "", "exitCode": 0}

    node = _node("n8n-nodes-base.executeCommand", {"command": "ls"})
    ctx = _ctx({"execute_command_response": mock})
    result = await exec_execute_command(node, _items([{}]), ctx=ctx)
    assert seen[0] == ("", {"command": "ls"})
    assert _out_items(result)[0].json["stdout"] == "ok"


@pytest.mark.asyncio
async def test_execute_command_offline() -> None:
    node = _node("n8n-nodes-base.executeCommand", {"command": "echo test"})
    ctx = _ctx()
    result = await exec_execute_command(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["stdout"] == ""
    assert out[0].json["exitCode"] == 0
    assert out[0].json["command"] == "echo test"


@pytest.mark.asyncio
async def test_execute_command_http_fallback() -> None:
    node = _node("n8n-nodes-base.executeCommand", {"command": "ls"})
    ctx = _ctx({"http_response": {"body": {"stdout": "fb", "stderr": "", "exitCode": 1}}})
    result = await exec_execute_command(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["stdout"] == "fb"
    assert out[0].json["mockSource"] == "http_response"


@pytest.mark.asyncio
async def test_execute_command_execute_once_caches() -> None:
    call_count = 0

    def mock(operation, params, item, ctx):
        nonlocal call_count
        call_count += 1
        return {"stdout": str(call_count), "stderr": "", "exitCode": 0}

    node = _node("n8n-nodes-base.executeCommand", {"command": "x", "executeOnce": True})
    ctx = _ctx({"execute_command_response": mock})
    result = await exec_execute_command(node, _items([{}, {}, {}]), ctx=ctx)
    out = _out_items(result)
    assert call_count == 1
    assert all(o.json["stdout"] == "1" for o in out)


# ── n8n (meta API) ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n8n_meta_mock_dict() -> None:
    node = _node("n8n-nodes-base.n8n", {"operation": "getWorkflow"})
    ctx = _ctx({"n8n_meta_response": {"id": "wf-99", "name": "Mocked"}})
    result = await exec_n8n(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["id"] == "wf-99"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_n8n_meta_callable() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append(operation)
        return {"id": "wf-x", "op": operation}

    node = _node("n8n-nodes-base.n8n", {"operation": "getExecutions"})
    ctx = _ctx({"n8n_meta_response": mock})
    result = await exec_n8n(node, _items([{}]), ctx=ctx)
    assert seen == ["getExecutions"]
    assert _out_items(result)[0].json["op"] == "getExecutions"


@pytest.mark.asyncio
async def test_n8n_meta_offline_get_workflow() -> None:
    node = _node("n8n-nodes-base.n8n", {"operation": "getWorkflow"})
    ctx = _ctx()
    result = await exec_n8n(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["id"] == "wf-mock-1"
    assert out[0].json["name"] == "Mock Workflow"
    assert out[0].json["active"] is True


@pytest.mark.asyncio
async def test_n8n_meta_offline_get_executions() -> None:
    node = _node("n8n-nodes-base.n8n", {"operation": "getExecutions"})
    ctx = _ctx()
    result = await exec_n8n(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out[0].json["data"]) == 2
    assert out[0].json["nextCursor"] == ""


@pytest.mark.asyncio
async def test_n8n_meta_operation_default() -> None:
    node = _node("n8n-nodes-base.n8n")
    ctx = _ctx()
    result = await exec_n8n(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["id"] == "wf-mock-1"


# ── Evaluation ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluation_exact_match_pass() -> None:
    node = _node(
        "n8n-nodes-base.evaluation",
        {"expectedOutput": "hello", "actualOutput": "hello"},
    )
    ctx = _ctx()
    result = await exec_evaluation(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["score"] == 1.0
    assert out[0].json["passed"] is True
    assert out[0].json["metric"] == "exact_match"


@pytest.mark.asyncio
async def test_evaluation_exact_match_fail() -> None:
    node = _node(
        "n8n-nodes-base.evaluation",
        {"expectedOutput": "hello", "actualOutput": "world"},
    )
    ctx = _ctx()
    result = await exec_evaluation(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["score"] == 0.0
    assert out[0].json["passed"] is False


@pytest.mark.asyncio
async def test_evaluation_mock_dict() -> None:
    node = _node("n8n-nodes-base.evaluation", {"expectedOutput": "a", "actualOutput": "b"})
    ctx = _ctx({"evaluation_response": {"score": 0.5, "metric": "custom", "expected": "a", "actual": "b", "passed": True}})
    result = await exec_evaluation(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["score"] == 0.5
    assert out[0].json["metric"] == "custom"
    assert out[0].json["passed"] is True


@pytest.mark.asyncio
async def test_evaluation_metric_default() -> None:
    node = _node(
        "n8n-nodes-base.evaluation",
        {"expectedOutput": "x", "actualOutput": "x"},
    )
    ctx = _ctx()
    result = await exec_evaluation(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["metric"] == "exact_match"


# ── Evaluation Trigger ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluation_trigger_offline() -> None:
    node = _node("n8n-nodes-base.evaluationTrigger")
    ctx = _ctx()
    result = await exec_evaluation_trigger(node, _items([]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 1
    assert "testId" in out[0].json
    assert "input" in out[0].json
    assert "expectedOutput" in out[0].json


@pytest.mark.asyncio
async def test_evaluation_trigger_mock() -> None:
    node = _node("n8n-nodes-base.evaluationTrigger")
    ctx = _ctx({"evaluation_trigger_payload": {"testId": "t9", "input": "q", "expectedOutput": "a"}})
    result = await exec_evaluation_trigger(node, _items([]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["testId"] == "t9"
    assert "mockSource" not in out[0].json


# ── Activation Trigger ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_activation_trigger_offline() -> None:
    node = _node("n8n-nodes-base.activationTrigger")
    ctx = _ctx()
    result = await exec_activation_trigger(node, _items([]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 1
    assert "activatedAt" in out[0].json
    assert out[0].json["workflowId"] == "wf-mock-1"


@pytest.mark.asyncio
async def test_activation_trigger_mock() -> None:
    node = _node("n8n-nodes-base.activationTrigger")
    ctx = _ctx({"activation_payload": {"activatedAt": "2026-01-01T00:00:00Z", "workflowId": "wf-x"}})
    result = await exec_activation_trigger(node, _items([]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["workflowId"] == "wf-x"


# ── n8n Trigger ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_n8n_trigger_offline() -> None:
    node = _node("n8n-nodes-base.n8nTrigger")
    ctx = _ctx()
    result = await exec_n8n_trigger(node, _items([]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 1
    assert "event" in out[0].json
    assert "timestamp" in out[0].json
    assert out[0].json["workflowId"] == "wf-mock-1"


@pytest.mark.asyncio
async def test_n8n_trigger_mock() -> None:
    node = _node("n8n-nodes-base.n8nTrigger")
    ctx = _ctx({"n8n_trigger_payload": {"event": "publish", "timestamp": "t", "workflowId": "wf-y"}})
    result = await exec_n8n_trigger(node, _items([]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["event"] == "publish"


# ── n8n Form ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_form_offline() -> None:
    node = _node(
        "n8n-nodes-base.form",
        {"formTitle": "Survey", "formFields": [{"fieldName": "name"}, {"fieldName": "email"}]},
    )
    ctx = _ctx()
    result = await exec_form(node, _items([]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["formTitle"] == "Survey"
    assert "name" in out[0].json["fields"]
    assert "email" in out[0].json["fields"]


@pytest.mark.asyncio
async def test_form_mock() -> None:
    node = _node("n8n-nodes-base.form", {"formTitle": "F"})
    ctx = _ctx({"form_submission": {"formTitle": "F", "submittedAt": "t", "fields": {"x": "1"}}})
    result = await exec_form(node, _items([]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["fields"] == {"x": "1"}


# ── TOTP ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_totp_generate() -> None:
    node = _node("n8n-nodes-base.totp", {"operation": "generate", "secret": "KQXG"})
    ctx = _ctx()
    result = await exec_totp(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["token"] == "123456"
    assert out[0].json["secret"] == "KQXG"
    assert out[0].json["algorithm"] == "SHA1"
    assert out[0].json["digits"] == 6
    assert out[0].json["period"] == 30


@pytest.mark.asyncio
async def test_totp_validate() -> None:
    node = _node("n8n-nodes-base.totp", {"operation": "validate", "secret": "KQXG", "token": "999999"})
    ctx = _ctx()
    result = await exec_totp(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["valid"] is True
    assert out[0].json["token"] == "999999"


@pytest.mark.asyncio
async def test_totp_default_operation_is_generate() -> None:
    node = _node("n8n-nodes-base.totp", {"secret": "S"})
    ctx = _ctx()
    result = await exec_totp(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert "token" in out[0].json
    assert "algorithm" in out[0].json


@pytest.mark.asyncio
async def test_totp_mock_dict() -> None:
    node = _node("n8n-nodes-base.totp", {"operation": "generate", "secret": "S"})
    ctx = _ctx({"totp_response": {"token": "654321", "secret": "S", "algorithm": "SHA256", "digits": 8, "period": 60}})
    result = await exec_totp(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["token"] == "654321"
    assert out[0].json["algorithm"] == "SHA256"


# ── LDAP ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ldap_search_emits_multiple() -> None:
    node = _node("n8n-nodes-base.ldap", {"operation": "search", "baseDn": "dc=example,dc=com"})
    ctx = _ctx()
    result = await exec_ldap(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 3
    assert "dn" in out[0].json
    assert "attributes" in out[0].json


@pytest.mark.asyncio
async def test_ldap_add_emits_one() -> None:
    node = _node("n8n-nodes-base.ldap", {"operation": "add", "baseDn": "cn=test,dc=example,dc=com"})
    ctx = _ctx()
    result = await exec_ldap(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["success"] is True
    assert out[0].json["operation"] == "add"


@pytest.mark.asyncio
async def test_ldap_mock_dict() -> None:
    node = _node("n8n-nodes-base.ldap", {"operation": "search", "baseDn": "dc=x"})
    ctx = _ctx({"ldap_response": [{"dn": "cn=a,dc=x", "attributes": {"cn": "a"}}]})
    result = await exec_ldap(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["dn"] == "cn=a,dc=x"


# ── iCalendar ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_icalendar_parse_vevents() -> None:
    ics = (
        "BEGIN:VCALENDAR\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:evt-1\r\n"
        "SUMMARY:Meeting\r\n"
        "DTSTART:20260101T100000Z\r\n"
        "DTEND:20260101T110000Z\r\n"
        "LOCATION:Room A\r\n"
        "DESCRIPTION:Team sync\r\n"
        "END:VEVENT\r\n"
        "BEGIN:VEVENT\r\n"
        "UID:evt-2\r\n"
        "SUMMARY:Lunch\r\n"
        "DTSTART:20260101T120000Z\r\n"
        "DTEND:20260101T130000Z\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    node = _node("n8n-nodes-base.iCalendar", {"icsData": ics})
    ctx = _ctx()
    result = await exec_icalendar(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 2
    assert out[0].json["summary"] == "Meeting"
    assert out[0].json["uid"] == "evt-1"
    assert out[0].json["location"] == "Room A"
    assert out[1].json["summary"] == "Lunch"


@pytest.mark.asyncio
async def test_icalendar_mock_dict() -> None:
    node = _node("n8n-nodes-base.iCalendar", {"icsData": "BEGIN:VCALENDAR\nEND:VCALENDAR"})
    ctx = _ctx({"icalendar_response": [{"summary": "Mocked", "start": "s", "end": "e", "location": "", "description": "", "uid": "u"}]})
    result = await exec_icalendar(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["summary"] == "Mocked"


# ── Quick Chart ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quick_chart_offline() -> None:
    node = _node(
        "n8n-nodes-base.quickChart",
        {"type": "bar", "datasets": [{"data": [1, 2, 3]}], "labels": ["a", "b", "c"]},
    )
    ctx = _ctx()
    result = await exec_quick_chart(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["type"] == "bar"
    assert out[0].json["chartUrl"].startswith("https://quickchart.io/chart?c=")
    assert out[0].json["config"]["type"] == "bar"
    assert out[0].json["config"]["data"]["labels"] == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_quick_chart_mock_dict() -> None:
    node = _node("n8n-nodes-base.quickChart", {"type": "pie"})
    ctx = _ctx({"quick_chart_response": {"chartUrl": "https://example.com/c", "type": "pie", "config": {}}})
    result = await exec_quick_chart(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["chartUrl"] == "https://example.com/c"


# ── Hacker News ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hacker_news_get() -> None:
    node = _node("n8n-nodes-base.hackerNews", {"operation": "get", "storyId": "42"})
    ctx = _ctx()
    result = await exec_hacker_news(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 1
    assert out[0].json["id"] == 42
    assert out[0].json["title"] == "Mock Story 42"
    assert out[0].json["type"] == "story"


@pytest.mark.asyncio
async def test_hacker_news_getall_capped_at_3() -> None:
    node = _node("n8n-nodes-base.hackerNews", {"operation": "getAll", "limit": 10})
    ctx = _ctx()
    result = await exec_hacker_news(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert len(out) == 3


@pytest.mark.asyncio
async def test_hacker_news_mock_dict() -> None:
    node = _node("n8n-nodes-base.hackerNews", {"operation": "get", "storyId": "1"})
    ctx = _ctx({"hacker_news_response": {"id": 99, "title": "Mocked", "url": "u", "score": 1, "by": "b", "time": 0, "type": "story"}})
    result = await exec_hacker_news(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["id"] == 99
    assert out[0].json["title"] == "Mocked"


# ── Descriptor registration ───────────────────────────────────────────


def test_descriptors_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    expected = {
        "n8n-nodes-base.debugHelper": "transform",
        "n8n-nodes-base.executeCommand": "transform",
        "n8n-nodes-base.n8n": "transform",
        "n8n-nodes-base.evaluation": "transform",
        "n8n-nodes-base.evaluationTrigger": "trigger",
        "n8n-nodes-base.activationTrigger": "trigger",
        "n8n-nodes-base.n8nTrigger": "trigger",
        "n8n-nodes-base.form": "trigger",
        "n8n-nodes-base.totp": "transform",
        "n8n-nodes-base.ldap": "transform",
        "n8n-nodes-base.iCalendar": "transform",
        "n8n-nodes-base.quickChart": "transform",
        "n8n-nodes-base.hackerNews": "transform",
    }
    for ntype, category in expected.items():
        assert ntype in REGISTRY, f"{ntype} not in REGISTRY"
        assert ntype in SUPPORTED_NODE_TYPES, f"{ntype} not in SUPPORTED_NODE_TYPES"
        assert REGISTRY[ntype].category == category, (
            f"{ntype} category mismatch: expected {category}, got {REGISTRY[ntype].category}"
        )


# ── End-to-end ────────────────────────────────────────────────────────


def _doc(nodes, connections):
    return {"name": "util-e2e", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": [0, 0],
        "parameters": params or {},
    }


@pytest.mark.asyncio
async def test_e2e_debug_helper_to_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("d1", "Debug", "n8n-nodes-base.debugHelper", {"options": {"prefix": "T: "}}),
            _n("s1", "Set", "n8n-nodes-base.set", {"assignments": {"assignments": [{"name": "seen", "value": "yes", "type": "string"}]}}),
        ],
        {
            "Start": {"main": [[{"node": "Debug", "type": "main", "index": 0}]]},
            "Debug": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["seen"] == "yes"


@pytest.mark.asyncio
async def test_e2e_execute_command_to_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("e1", "Exec", "n8n-nodes-base.executeCommand", {"command": "echo hi"}),
            _n("s1", "Set", "n8n-nodes-base.set", {"assignments": {"assignments": [{"name": "exit", "value": "={{ $json.exitCode }}", "type": "number"}]}}),
        ],
        {
            "Start": {"main": [[{"node": "Exec", "type": "main", "index": 0}]]},
            "Exec": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(
        doc,
        mocks={"execute_command_response": {"stdout": "hi", "stderr": "", "exitCode": 0}},
    )
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["exit"] == 0