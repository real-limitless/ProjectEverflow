"""Tests for DevOps integration node executors.

Covers six DevOps nodes (``n8n-nodes-base.gitlab``, ``gitlabTrigger``,
``githubTrigger``, ``bitbucketTrigger``, ``jenkins``, ``circleCi``):

- ``<node>_response`` dict mock → response used verbatim
- ``<node>_response`` callable mock receives ``(operation, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline default operation produces valid output (all fields present)
- Offline get/trigger echoes the resolved id
- Default operation is applied when ``operation`` is omitted
- One output item per input
- ``$json`` fallback for the id field
- Unsupported operation raises ``ValueError``
- All operations reflected in emitted item
- Trigger ``<node>_trigger_payload`` dict mock → payload used verbatim
- Trigger ``trigger_payload`` generic fallback
- Trigger offline produces valid output
- Trigger emits exactly one item when no upstream items
- End-to-end: Manual → GitLab → Set sees ``source``
- End-to-end: Manual → Jenkins → Set sees ``source``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.devops import (
    CIRCLECI_DEFAULT_OPERATION,
    CIRCLECI_OPERATIONS,
    GITLAB_DEFAULT_OPERATION,
    GITLAB_OPERATIONS,
    JENKINS_DEFAULT_OPERATION,
    JENKINS_OPERATIONS,
    exec_bitbucket_trigger,
    exec_circleci,
    exec_gitlab,
    exec_gitlab_trigger,
    exec_github_trigger,
    exec_jenkins,
)


ACTION_SPECS = [
    (
        "n8n-nodes-base.gitlab",
        exec_gitlab,
        "gitlab_response",
        "gitlab",
        "issueIid",
        "title",
        "create",
    ),
    (
        "n8n-nodes-base.jenkins",
        exec_jenkins,
        "jenkins_response",
        "jenkins",
        "buildId",
        "jobName",
        "trigger",
    ),
    (
        "n8n-nodes-base.circleCi",
        exec_circleci,
        "circleci_response",
        "circleci",
        "pipelineId",
        "status",
        "trigger",
    ),
]

TRIGGER_SPECS = [
    (
        "n8n-nodes-base.gitlabTrigger",
        exec_gitlab_trigger,
        "gitlab_trigger_payload",
        "gitlab",
        ("event", "projectId", "objectKind"),
    ),
    (
        "n8n-nodes-base.githubTrigger",
        exec_github_trigger,
        "github_trigger_payload",
        "github",
        ("event", "action", "repository", "sender"),
    ),
    (
        "n8n-nodes-base.bitbucketTrigger",
        exec_bitbucket_trigger,
        "bitbucket_trigger_payload",
        "bitbucket",
        ("event", "repository", "actor"),
    ),
]


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.gitlab",
    id_: str = "n1",
    name: str = "GitLab",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params,
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
    return EngineContext(graph=g, mocks=mocks or {})  # type: ignore[arg-type]


def _out_items(result: list) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── Action: mock dict used verbatim ───────────────────────────────────


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,id_field,name_field,default_op",
    ACTION_SPECS,
)
@pytest.mark.asyncio
async def test_mock_dict_used_verbatim(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    id_field: str,
    name_field: str,
    default_op: str,
) -> None:
    mock = {id_field: "X1", name_field: "N"}
    node = _node({"operation": default_op}, type_=type_, name=source.title())
    ctx = _ctx({mock_key: mock})
    out = _out_items(await fn(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p[id_field] == "X1"
    assert p[name_field] == "N"
    assert p["operation"] == default_op
    assert p["source"] == source
    assert "mockSource" not in p


# ── Action: mock callable receives correct args ──────────────────────


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,id_field,name_field,default_op",
    ACTION_SPECS,
)
@pytest.mark.asyncio
async def test_mock_callable_receives_args(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    id_field: str,
    name_field: str,
    default_op: str,
) -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {id_field: "C1", name_field: "from callable"}

    node = _node(
        {"operation": default_op, "hint": 1}, type_=type_, name=source.title()
    )
    ctx = _ctx({mock_key: _mock})
    item = ExecutionItem(json={"k": 1})
    out = _out_items(await fn(node, [item], ctx=ctx))

    assert captured["operation"] == default_op
    assert captured["params"]["hint"] == 1
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    p = out[0].json
    assert p[id_field] == "C1"
    assert p[name_field] == "from callable"
    assert p["source"] == source
    assert "mockSource" not in p


# ── Action: http_response fallback ───────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_gitlab() -> None:
    node = _node({"operation": "get", "issueIid": "I9"})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {"issueIid": "I9", "title": "via http"},
            }
        }
    )
    out = _out_items(await exec_gitlab(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["issueIid"] == "I9"
    assert p["title"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "gitlab"


@pytest.mark.asyncio
async def test_http_response_fallback_jenkins() -> None:
    node = _node(
        {"operation": "getBuild", "buildId": "B9"},
        type_="n8n-nodes-base.jenkins",
        name="Jenkins",
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {"jobName": "via http", "buildId": "B9"},
            }
        }
    )
    out = _out_items(await exec_jenkins(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["buildId"] == "B9"
    assert p["jobName"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "jenkins"


@pytest.mark.asyncio
async def test_http_response_fallback_circleci() -> None:
    node = _node(
        {"operation": "getPipeline", "pipelineId": "P9"},
        type_="n8n-nodes-base.circleCi",
        name="CircleCI",
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {"pipelineId": "P9", "status": "running"},
            }
        }
    )
    out = _out_items(await exec_circleci(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["pipelineId"] == "P9"
    assert p["status"] == "running"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "circleci"


# ── Action: offline default operation valid output ───────────────────


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,id_field,name_field,default_op",
    ACTION_SPECS,
)
@pytest.mark.asyncio
async def test_offline_default_operation_valid_output(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    id_field: str,
    name_field: str,
    default_op: str,
) -> None:
    node = _node({}, type_=type_, name=source.title())
    out = _out_items(await fn(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p[id_field].startswith(f"mock_{source}_")
    assert p["operation"] == default_op
    assert p["source"] == source
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_get_echoes_id_gitlab() -> None:
    node = _node({"operation": "get", "issueIid": "I55"})
    out = _out_items(await exec_gitlab(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["issueIid"] == "I55"
    assert p["operation"] == "get"
    assert p["source"] == "gitlab"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_getbuild_echoes_buildid_jenkins() -> None:
    node = _node(
        {"operation": "getBuild", "buildId": "B42"},
        type_="n8n-nodes-base.jenkins",
        name="Jenkins",
    )
    out = _out_items(await exec_jenkins(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["buildId"] == "B42"
    assert p["operation"] == "getBuild"
    assert p["source"] == "jenkins"
    assert p["status"] == "queued"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_getpipeline_echoes_pipelineid_circleci() -> None:
    node = _node(
        {"operation": "getPipeline", "pipelineId": "PL9"},
        type_="n8n-nodes-base.circleCi",
        name="CircleCI",
    )
    out = _out_items(await exec_circleci(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["pipelineId"] == "PL9"
    assert p["operation"] == "getPipeline"
    assert p["source"] == "circleci"
    assert p["status"] == "queued"
    assert p["mockSource"] == "offline"


# ── Action: default operation constant ───────────────────────────────


def test_default_operation_constants() -> None:
    assert GITLAB_DEFAULT_OPERATION == "create"
    assert JENKINS_DEFAULT_OPERATION == "trigger"
    assert CIRCLECI_DEFAULT_OPERATION == "trigger"


# ── Action: one item per input ───────────────────────────────────────


@pytest.mark.asyncio
async def test_one_item_per_input_gitlab() -> None:
    node = _node({"operation": "get"})
    items = [
        ExecutionItem(json={"issueIid": "I1"}),
        ExecutionItem(json={"issueIid": "I2"}),
        ExecutionItem(json={"issueIid": "I3"}),
    ]
    out = _out_items(await exec_gitlab(node, items, ctx=_ctx()))
    assert len(out) == 3
    ids = [o.json["issueIid"] for o in out]
    assert ids == ["I1", "I2", "I3"]
    assert all(o.json["source"] == "gitlab" for o in out)


# ── Action: $json fallback ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_fallback_jenkins() -> None:
    node = _node(
        {"operation": "getBuild"},
        type_="n8n-nodes-base.jenkins",
        name="Jenkins",
    )
    item = ExecutionItem(json={"buildId": "BJ123"})
    out = _out_items(await exec_jenkins(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["buildId"] == "BJ123"


# ── Action: unsupported operation raises ─────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises_gitlab() -> None:
    node = _node({"operation": "bogus"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_gitlab(node, [ExecutionItem(json={})], ctx=_ctx())


@pytest.mark.asyncio
async def test_unsupported_operation_raises_jenkins() -> None:
    node = _node(
        {"operation": "bogus"},
        type_="n8n-nodes-base.jenkins",
        name="Jenkins",
    )
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_jenkins(node, [ExecutionItem(json={})], ctx=_ctx())


# ── Action: all operations reflected ─────────────────────────────────


@pytest.mark.asyncio
async def test_all_gitlab_operations_reflected() -> None:
    for op in GITLAB_OPERATIONS:
        node = _node({"operation": op, "issueIid": "I1", "title": "T"})
        out = _out_items(await exec_gitlab(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) == 1, f"no output for {op}"
        assert out[0].json["operation"] == op
        assert out[0].json["source"] == "gitlab"


@pytest.mark.asyncio
async def test_all_jenkins_operations_reflected() -> None:
    for op in JENKINS_OPERATIONS:
        node = _node(
            {"operation": op, "jobName": "J", "buildId": "B1"},
            type_="n8n-nodes-base.jenkins",
            name="Jenkins",
        )
        out = _out_items(await exec_jenkins(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) == 1, f"no output for {op}"
        assert out[0].json["operation"] == op
        assert out[0].json["source"] == "jenkins"


@pytest.mark.asyncio
async def test_all_circleci_operations_reflected() -> None:
    for op in CIRCLECI_OPERATIONS:
        node = _node(
            {"operation": op, "pipelineId": "P1"},
            type_="n8n-nodes-base.circleCi",
            name="CircleCI",
        )
        out = _out_items(await exec_circleci(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) == 1, f"no output for {op}"
        assert out[0].json["operation"] == op
        assert out[0].json["source"] == "circleci"


# ── Action: operations constants ─────────────────────────────────────


def test_action_operations_constants() -> None:
    assert GITLAB_OPERATIONS == (
        "create",
        "get",
        "update",
        "delete",
        "list",
        "createMergeRequest",
        "getMergeRequest",
    )
    assert JENKINS_OPERATIONS == (
        "trigger",
        "getJob",
        "getBuild",
        "listJobs",
    )
    assert CIRCLECI_OPERATIONS == (
        "trigger",
        "getPipeline",
        "getWorkflow",
        "getJob",
    )


# ── Trigger: mock dict used verbatim ─────────────────────────────────


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,fields",
    TRIGGER_SPECS,
)
@pytest.mark.asyncio
async def test_trigger_mock_dict_used_verbatim(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    fields: tuple[str, ...],
) -> None:
    mock = {f: f"val_{f}" for f in fields}
    node = _node({}, type_=type_, name=source.title())
    ctx = _ctx({mock_key: mock})
    out = _out_items(await fn(node, [], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    for f in fields:
        assert p[f] == f"val_{f}"
    assert p["source"] == source
    assert "mockSource" not in p


# ── Trigger: mock callable receives (node, ctx) ──────────────────────


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,fields",
    TRIGGER_SPECS,
)
@pytest.mark.asyncio
async def test_trigger_mock_callable_receives_args(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    fields: tuple[str, ...],
) -> None:
    captured: dict[str, Any] = {}

    def _mock(node, ctx):
        captured["node"] = node
        captured["ctx"] = ctx
        return {f: f"cb_{f}" for f in fields}

    node = _node({}, type_=type_, name=source.title())
    ctx = _ctx({mock_key: _mock})
    out = _out_items(await fn(node, [], ctx=ctx))

    assert captured["node"] is node
    assert captured["ctx"] is ctx

    assert len(out) == 1
    p = out[0].json
    for f in fields:
        assert p[f] == f"cb_{f}"
    assert p["source"] == source


# ── Trigger: trigger_payload fallback ────────────────────────────────


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,fields",
    TRIGGER_SPECS,
)
@pytest.mark.asyncio
async def test_trigger_trigger_payload_fallback(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    fields: tuple[str, ...],
) -> None:
    mock = {f: f"tp_{f}" for f in fields}
    node = _node({}, type_=type_, name=source.title())
    ctx = _ctx({"trigger_payload": mock})
    out = _out_items(await fn(node, [], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    for f in fields:
        assert p[f] == f"tp_{f}"
    assert p["source"] == source
    assert p["mockSource"] == "trigger_payload"


# ── Trigger: offline valid output ────────────────────────────────────


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,fields",
    TRIGGER_SPECS,
)
@pytest.mark.asyncio
async def test_trigger_offline_valid_output(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    fields: tuple[str, ...],
) -> None:
    node = _node({}, type_=type_, name=source.title())
    out = _out_items(await fn(node, [], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    for f in fields:
        assert f in p
        assert p[f] is not None
    assert p["source"] == source
    assert "mockSource" not in p


# ── Trigger: emits exactly one item ──────────────────────────────────


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,fields",
    TRIGGER_SPECS,
)
@pytest.mark.asyncio
async def test_trigger_emits_one_item(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    fields: tuple[str, ...],
) -> None:
    node = _node({}, type_=type_, name=source.title())
    out = _out_items(await fn(node, [], ctx=_ctx()))
    assert len(out) == 1


# ── Trigger: specific offline field checks ───────────────────────────


@pytest.mark.asyncio
async def test_gitlab_trigger_offline_fields() -> None:
    node = _node(
        {},
        type_="n8n-nodes-base.gitlabTrigger",
        name="GitLab Trigger",
    )
    out = _out_items(await exec_gitlab_trigger(node, [], ctx=_ctx()))
    p = out[0].json
    assert p["event"] == "push"
    assert p["objectKind"] == "push"
    assert isinstance(p["projectId"], int)
    assert p["source"] == "gitlab"


@pytest.mark.asyncio
async def test_github_trigger_offline_fields() -> None:
    node = _node(
        {},
        type_="n8n-nodes-base.githubTrigger",
        name="GitHub Trigger",
    )
    out = _out_items(await exec_github_trigger(node, [], ctx=_ctx()))
    p = out[0].json
    assert p["event"] == "push"
    assert p["action"] == "opened"
    assert isinstance(p["repository"], dict)
    assert isinstance(p["sender"], dict)
    assert p["source"] == "github"


@pytest.mark.asyncio
async def test_bitbucket_trigger_offline_fields() -> None:
    node = _node(
        {},
        type_="n8n-nodes-base.bitbucketTrigger",
        name="Bitbucket Trigger",
    )
    out = _out_items(await exec_bitbucket_trigger(node, [], ctx=_ctx()))
    p = out[0].json
    assert p["event"] == "repo:push"
    assert isinstance(p["repository"], dict)
    assert isinstance(p["actor"], dict)
    assert p["source"] == "bitbucket"


# ── Trigger: snake_case fallback keys ────────────────────────────────


@pytest.mark.asyncio
async def test_gitlab_trigger_snake_case_fallback() -> None:
    payload = {
        "object_kind": "merge_request",
        "project_id": 99,
    }
    node = _node(
        {},
        type_="n8n-nodes-base.gitlabTrigger",
        name="GitLab Trigger",
    )
    ctx = _ctx({"gitlab_trigger_payload": payload})
    out = _out_items(await exec_gitlab_trigger(node, [], ctx=ctx))
    p = out[0].json
    assert p["event"] == "merge_request"
    assert p["objectKind"] == "merge_request"
    assert p["projectId"] == 99
    assert p["source"] == "gitlab"


# ── End-to-end: Manual → GitLab → Set ────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_manual_gitlab_set() -> None:
    mocks = {
        "gitlab_response": {"issueIid": "I1", "title": "E2E Issue", "projectId": "P1"}
    }
    doc = {
        "name": "devops-gitlab-test",
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
                "name": "GitLab",
                "type": "n8n-nodes-base.gitlab",
                "typeVersion": 1,
                "position": [240, 0],
                "parameters": {"operation": "create", "title": "E2E Issue"},
            },
            {
                "id": "s1",
                "name": "Downstream",
                "type": "n8n-nodes-base.set",
                "typeVersion": 1,
                "position": [480, 0],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "result",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "GitLab", "type": "main", "index": 0}]]},
            "GitLab": {
                "main": [[{"node": "Downstream", "type": "main", "index": 0}]]
            },
        },
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    gitlab_step = next(s for s in result.steps if s.node_name == "GitLab")
    assert gitlab_step.status == "success", gitlab_step.error
    assert gitlab_step.output_count == 1
    sample = gitlab_step.sample_output[0]
    assert sample["json"]["source"] == "gitlab"
    assert sample["json"]["operation"] == "create"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result") == "gitlab"


# ── End-to-end: Manual → Jenkins → Set ───────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_manual_jenkins_set() -> None:
    mocks = {
        "jenkins_response": {"jobName": "build", "buildId": "B1", "status": "queued"}
    }
    doc = {
        "name": "devops-jenkins-test",
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
                "id": "j1",
                "name": "Jenkins",
                "type": "n8n-nodes-base.jenkins",
                "typeVersion": 1,
                "position": [240, 0],
                "parameters": {"operation": "trigger", "jobName": "build"},
            },
            {
                "id": "s1",
                "name": "Downstream",
                "type": "n8n-nodes-base.set",
                "typeVersion": 1,
                "position": [480, 0],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "result",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Jenkins", "type": "main", "index": 0}]]},
            "Jenkins": {
                "main": [[{"node": "Downstream", "type": "main", "index": 0}]]
            },
        },
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    jenkins_step = next(s for s in result.steps if s.node_name == "Jenkins")
    assert jenkins_step.status == "success", jenkins_step.error
    assert jenkins_step.output_count == 1
    sample = jenkins_step.sample_output[0]
    assert sample["json"]["source"] == "jenkins"
    assert sample["json"]["operation"] == "trigger"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result") == "jenkins"


# ── Descriptor registration (CI invariant) ───────────────────────────


def test_devops_descriptors_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    expected = {
        "n8n-nodes-base.gitlab": ("exec_gitlab", "action"),
        "n8n-nodes-base.gitlabTrigger": ("exec_gitlab_trigger", "trigger"),
        "n8n-nodes-base.githubTrigger": ("exec_github_trigger", "trigger"),
        "n8n-nodes-base.bitbucketTrigger": (
            "exec_bitbucket_trigger",
            "trigger",
        ),
        "n8n-nodes-base.jenkins": ("exec_jenkins", "action"),
        "n8n-nodes-base.circleCi": ("exec_circleci", "action"),
    }
    for ntype, (fn_name, category) in expected.items():
        assert ntype in REGISTRY, f"{ntype} not registered"
        assert ntype in SUPPORTED_NODE_TYPES, f"{ntype} not in SUPPORTED_NODE_TYPES"
        assert SUPPORTED_NODE_TYPES[ntype] == category
        desc = REGISTRY[ntype]
        assert desc.category == category
        assert desc.executor.endswith(f":{fn_name}")