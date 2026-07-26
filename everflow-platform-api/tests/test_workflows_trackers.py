"""Tests for project tracker node executors.

Covers the six tracker nodes (``n8n-nodes-base.clickUp``, ``trello``,
``asana``, ``mondayCom``, ``todoist``, ``linear``):

- ``<node>_response`` dict mock → response used verbatim
- ``<node>_response`` callable mock receives ``(operation, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline ``create`` produces valid output (all fields present)
- Offline ``get`` echoes the resolved id
- Offline ``update`` / ``list`` / ``delete`` produce valid output
- Default operation is ``create``
- One output item per input
- ``$json`` fallback for the id field
- Unsupported operation raises ``ValueError``
- All operations reflected in emitted item
- End-to-end: Manual → ClickUp → Set sees ``source``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.trackers import (
    ASANA_OPERATIONS,
    CLICKUP_DEFAULT_OPERATION,
    CLICKUP_OPERATIONS,
    LINEAR_OPERATIONS,
    MONDAY_OPERATIONS,
    TODOIST_OPERATIONS,
    TRELLO_OPERATIONS,
    exec_asana,
    exec_clickup,
    exec_linear,
    exec_monday,
    exec_todoist,
    exec_trello,
)


NODE_SPECS = [
    (
        "n8n-nodes-base.clickUp",
        exec_clickup,
        "clickup_response",
        "clickup",
        "taskId",
        "name",
        "status",
        "open",
    ),
    (
        "n8n-nodes-base.trello",
        exec_trello,
        "trello_response",
        "trello",
        "cardId",
        "name",
        "listId",
        "L1",
    ),
    (
        "n8n-nodes-base.asana",
        exec_asana,
        "asana_response",
        "asana",
        "taskId",
        "name",
        "projectId",
        "P1",
    ),
    (
        "n8n-nodes-base.mondayCom",
        exec_monday,
        "monday_response",
        "monday",
        "itemId",
        "itemName",
        "boardId",
        "B1",
    ),
    (
        "n8n-nodes-base.todoist",
        exec_todoist,
        "todoist_response",
        "todoist",
        "taskId",
        "content",
        "projectId",
        "P1",
    ),
    (
        "n8n-nodes-base.linear",
        exec_linear,
        "linear_response",
        "linear",
        "issueId",
        "title",
        "status",
        "open",
    ),
]


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.clickUp",
    id_: str = "n1",
    name: str = "ClickUp",
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


def _out_items(result) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,id_field,name_field,extra_field,extra_value",
    NODE_SPECS,
)
@pytest.mark.asyncio
async def test_mock_dict_used_verbatim(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    id_field: str,
    name_field: str,
    extra_field: str,
    extra_value: str,
) -> None:
    mock = {id_field: "X1", name_field: "N", extra_field: extra_value}
    node = _node({"operation": "get"}, type_=type_, name=source.title())
    ctx = _ctx({mock_key: mock})
    out = _out_items(await fn(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p[id_field] == "X1"
    assert p[name_field] == "N"
    assert p[extra_field] == extra_value
    assert p["operation"] == "get"
    assert p["source"] == source
    assert "mockSource" not in p


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,id_field,name_field,extra_field,extra_value",
    NODE_SPECS,
)
@pytest.mark.asyncio
async def test_mock_callable_receives_args(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    id_field: str,
    name_field: str,
    extra_field: str,
    extra_value: str,
) -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {id_field: "C1", name_field: "from callable", extra_field: extra_value}

    node = _node({"operation": "get", "hint": 1}, type_=type_, name=source.title())
    ctx = _ctx({mock_key: _mock})
    item = ExecutionItem(json={"k": 1})
    out = _out_items(await fn(node, [item], ctx=ctx))

    assert captured["operation"] == "get"
    assert captured["params"]["hint"] == 1
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    p = out[0].json
    assert p[id_field] == "C1"
    assert p[name_field] == "from callable"
    assert p[extra_field] == extra_value
    assert p["source"] == source
    assert "mockSource" not in p


@pytest.mark.asyncio
async def test_http_response_fallback_clickup() -> None:
    node = _node({"operation": "get", "taskId": "T9"})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {"taskId": "T9", "name": "via http", "status": "open"},
            }
        }
    )
    out = _out_items(await exec_clickup(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["taskId"] == "T9"
    assert p["name"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "clickup"


@pytest.mark.asyncio
async def test_http_response_fallback_linear() -> None:
    node = _node(
        {"operation": "get", "issueId": "I9"},
        type_="n8n-nodes-base.linear",
        name="Linear",
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {"issueId": "I9", "title": "via http", "status": "in progress"},
            }
        }
    )
    out = _out_items(await exec_linear(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["issueId"] == "I9"
    assert p["title"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "linear"


@pytest.mark.parametrize(
    "type_,fn,mock_key,source,id_field,name_field,extra_field,extra_value",
    NODE_SPECS,
)
@pytest.mark.asyncio
async def test_offline_create_valid_output(
    type_: str,
    fn: Any,
    mock_key: str,
    source: str,
    id_field: str,
    name_field: str,
    extra_field: str,
    extra_value: str,
) -> None:
    params: dict[str, Any] = {"operation": "create", name_field: "My Item"}
    node = _node(params, type_=type_, name=source.title())
    out = _out_items(await fn(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p[id_field].startswith(f"mock_{source}_")
    assert p[name_field] == "My Item"
    assert p["operation"] == "create"
    assert p["source"] == source
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_get_echoes_id_clickup() -> None:
    node = _node({"operation": "get", "taskId": "T55"})
    out = _out_items(await exec_clickup(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["taskId"] == "T55"
    assert p["operation"] == "get"
    assert p["source"] == "clickup"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_update_linear() -> None:
    node = _node(
        {"operation": "update", "issueId": "I33", "title": "Updated", "status": "In Progress"},
        type_="n8n-nodes-base.linear",
        name="Linear",
    )
    out = _out_items(await exec_linear(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["issueId"] == "I33"
    assert p["title"] == "Updated"
    assert p["status"] == "In Progress"
    assert p["operation"] == "update"
    assert p["source"] == "linear"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_list_trello() -> None:
    node = _node(
        {"operation": "list"},
        type_="n8n-nodes-base.trello",
        name="Trello",
    )
    out = _out_items(await exec_trello(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["operation"] == "list"
    assert p["source"] == "trello"
    assert p["mockSource"] == "offline"
    assert "cardId" in p
    assert "name" in p
    assert "listId" in p


@pytest.mark.asyncio
async def test_offline_delete_asana() -> None:
    node = _node(
        {"operation": "delete", "taskId": "A77"},
        type_="n8n-nodes-base.asana",
        name="Asana",
    )
    out = _out_items(await exec_asana(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["taskId"] == "A77"
    assert p["operation"] == "delete"
    assert p["source"] == "asana"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_default_operation_is_create_clickup() -> None:
    node = _node({})
    out = _out_items(await exec_clickup(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["operation"] == "create"
    assert CLICKUP_DEFAULT_OPERATION == "create"


@pytest.mark.asyncio
async def test_one_item_per_input_monday() -> None:
    node = _node(
        {"operation": "get"},
        type_="n8n-nodes-base.mondayCom",
        name="Monday",
    )
    items = [
        ExecutionItem(json={"itemId": "I1"}),
        ExecutionItem(json={"itemId": "I2"}),
        ExecutionItem(json={"itemId": "I3"}),
    ]
    out = _out_items(await exec_monday(node, items, ctx=_ctx()))
    assert len(out) == 3
    ids = [o.json["itemId"] for o in out]
    assert ids == ["I1", "I2", "I3"]
    assert all(o.json["source"] == "monday" for o in out)


@pytest.mark.asyncio
async def test_json_fallback_todoist() -> None:
    node = _node(
        {"operation": "get"},
        type_="n8n-nodes-base.todoist",
        name="Todoist",
    )
    item = ExecutionItem(json={"taskId": "TD123"})
    out = _out_items(await exec_todoist(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["taskId"] == "TD123"


@pytest.mark.asyncio
async def test_unsupported_operation_raises_trello() -> None:
    node = _node(
        {"operation": "bogus"},
        type_="n8n-nodes-base.trello",
        name="Trello",
    )
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_trello(node, [ExecutionItem(json={})], ctx=_ctx())


@pytest.mark.asyncio
async def test_all_clickup_operations_reflected() -> None:
    for op in CLICKUP_OPERATIONS:
        node = _node({"operation": op, "taskId": "T1", "name": "N"})
        out = _out_items(await exec_clickup(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) == 1, f"no output for {op}"
        assert out[0].json["operation"] == op
        assert out[0].json["source"] == "clickup"


@pytest.mark.asyncio
async def test_all_trello_operations_reflected() -> None:
    for op in TRELLO_OPERATIONS:
        node = _node(
            {"operation": op, "cardId": "C1", "name": "N"},
            type_="n8n-nodes-base.trello",
            name="Trello",
        )
        out = _out_items(await exec_trello(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) == 1, f"no output for {op}"
        assert out[0].json["operation"] == op


@pytest.mark.asyncio
async def test_end_to_end_manual_clickup_set() -> None:
    mocks = {"clickup_response": {"taskId": "T1", "name": "E2E Task", "status": "open"}}
    doc = {
        "name": "tracker-test",
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
                "id": "c1",
                "name": "ClickUp",
                "type": "n8n-nodes-base.clickUp",
                "typeVersion": 1,
                "position": [240, 0],
                "parameters": {"operation": "create", "name": "E2E Task"},
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
            "Start": {"main": [[{"node": "ClickUp", "type": "main", "index": 0}]]},
            "ClickUp": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    clickup_step = next(s for s in result.steps if s.node_name == "ClickUp")
    assert clickup_step.status == "success", clickup_step.error
    assert clickup_step.output_count == 1
    sample = clickup_step.sample_output[0]
    assert sample["json"]["source"] == "clickup"
    assert sample["json"]["operation"] == "create"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result") == "clickup"


def test_tracker_descriptors_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    expected = {
        "n8n-nodes-base.clickUp": "exec_clickup",
        "n8n-nodes-base.trello": "exec_trello",
        "n8n-nodes-base.asana": "exec_asana",
        "n8n-nodes-base.mondayCom": "exec_monday",
        "n8n-nodes-base.todoist": "exec_todoist",
        "n8n-nodes-base.linear": "exec_linear",
    }
    for ntype, fn_name in expected.items():
        assert ntype in REGISTRY, f"{ntype} not registered"
        assert ntype in SUPPORTED_NODE_TYPES, f"{ntype} not in SUPPORTED_NODE_TYPES"
        assert SUPPORTED_NODE_TYPES[ntype] == "action"
        desc = REGISTRY[ntype]
        assert desc.category == "action"
        assert desc.executor.endswith(f":{fn_name}")


def test_tracker_operations_constants() -> None:
    assert CLICKUP_OPERATIONS == (
        "create",
        "get",
        "update",
        "delete",
        "list",
        "createList",
    )
    assert TRELLO_OPERATIONS == (
        "create",
        "get",
        "update",
        "delete",
        "list",
        "createBoard",
        "createList",
    )
    assert ASANA_OPERATIONS == (
        "create",
        "get",
        "update",
        "delete",
        "list",
        "createProject",
    )
    assert MONDAY_OPERATIONS == (
        "create",
        "get",
        "update",
        "delete",
        "list",
        "createBoard",
    )
    assert TODOIST_OPERATIONS == (
        "create",
        "get",
        "update",
        "delete",
        "list",
        "createProject",
    )
    assert LINEAR_OPERATIONS == (
        "create",
        "get",
        "update",
        "delete",
        "list",
        "createProject",
    )
