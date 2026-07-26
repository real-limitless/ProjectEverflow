"""Tests for Microsoft extra nodes (``n8n-nodes-base.*``).

Covers Microsoft Excel, OneDrive, SharePoint, SQL, Entra, To Do.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.microsoft_extra import (
    exec_microsoft_entra,
    exec_microsoft_excel,
    exec_microsoft_onedrive,
    exec_microsoft_sharepoint,
    exec_microsoft_sql,
    exec_microsoft_todo,
)
from app.services.workflows.registry import REGISTRY


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.microsoftExcel",
    id_: str = "n1",
    name: str = "Excel",
) -> ExecNode:
    return ExecNode(
        id=id_, name=name, type=type_, type_version=1,
        parameters=params, credentials=None, position={"x": 0, "y": 0},
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


def _input_item(**kw) -> ExecutionItem:
    return ExecutionItem(json=kw)


# ── Excel ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_excel_dict_mock() -> None:
    node = _node({"operation": "read"})
    ctx = _ctx({"microsoft_excel_response": {"rows": [{"a": 1}], "custom": True}})
    items = _out_items(await exec_microsoft_excel(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_excel_callable_mock() -> None:
    calls: list[tuple] = []
    def mock(op, params, item, c):
        calls.append(op)
        return {"rows": [], "op": op}
    node = _node({"operation": "read"})
    items = _out_items(await exec_microsoft_excel(node, [_input_item()], ctx=_ctx({"microsoft_excel_response": mock})))
    assert items[0].json["op"] == "read"
    assert calls == ["read"]


@pytest.mark.asyncio
async def test_excel_http_fallback() -> None:
    node = _node({"operation": "read"})
    ctx = _ctx({"http_response": {"status_code": 200, "body": {"rows": [{"x": 1}]}}})
    items = _out_items(await exec_microsoft_excel(node, [_input_item()], ctx=ctx))
    assert items[0].json["rows"] == [{"x": 1}]


@pytest.mark.asyncio
async def test_excel_offline_read() -> None:
    node = _node({"operation": "read", "fileId": "f1"})
    items = _out_items(await exec_microsoft_excel(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "microsoft_excel"
    assert items[0].json["fileId"] == "f1"
    assert "rows" in items[0].json


@pytest.mark.asyncio
async def test_excel_offline_append() -> None:
    node = _node({"operation": "append", "fileId": "f1"})
    items = _out_items(await exec_microsoft_excel(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["operation"] == "append"
    assert items[0].json["affectedRows"] == 1


# ── OneDrive ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_onedrive_dict_mock() -> None:
    node = _node({"operation": "upload"}, type_="n8n-nodes-base.microsoftOneDrive", name="OneDrive")
    ctx = _ctx({"microsoft_onedrive_response": {"fileName": "test.txt", "custom": True}})
    items = _out_items(await exec_microsoft_onedrive(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_onedrive_offline() -> None:
    node = _node({"operation": "download", "fileName": "doc.pdf"}, type_="n8n-nodes-base.microsoftOneDrive")
    items = _out_items(await exec_microsoft_onedrive(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "microsoft_onedrive"
    assert items[0].json["fileName"] == "doc.pdf"


# ── SharePoint ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sharepoint_dict_mock() -> None:
    node = _node({"operation": "list"}, type_="n8n-nodes-base.microsoftSharePoint", name="SharePoint")
    ctx = _ctx({"microsoft_sharepoint_response": {"siteId": "s1", "custom": True}})
    items = _out_items(await exec_microsoft_sharepoint(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_sharepoint_offline() -> None:
    node = _node({"operation": "download", "siteId": "s1", "listId": "l1"}, type_="n8n-nodes-base.microsoftSharePoint")
    items = _out_items(await exec_microsoft_sharepoint(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "microsoft_sharepoint"
    assert items[0].json["siteId"] == "s1"


# ── MS SQL ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mssql_dict_mock() -> None:
    node = _node({"operation": "executeQuery"}, type_="n8n-nodes-base.microsoftSql", name="MS SQL")
    ctx = _ctx({"microsoft_sql_response": {"rows": [{"id": 1}], "custom": True}})
    items = _out_items(await exec_microsoft_sql(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_mssql_offline_query() -> None:
    node = _node({"operation": "executeQuery"}, type_="n8n-nodes-base.microsoftSql")
    items = _out_items(await exec_microsoft_sql(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "microsoft_sql"
    assert "rows" in items[0].json


@pytest.mark.asyncio
async def test_mssql_offline_insert() -> None:
    node = _node({"operation": "insert"}, type_="n8n-nodes-base.microsoftSql")
    items = _out_items(await exec_microsoft_sql(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["operation"] == "insert"
    assert items[0].json["affectedRows"] == 1


# ── Entra ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_entra_dict_mock() -> None:
    node = _node({"operation": "getUser"}, type_="n8n-nodes-base.microsoftEntra", name="Entra")
    ctx = _ctx({"microsoft_entra_response": {"id": "u1", "custom": True}})
    items = _out_items(await exec_microsoft_entra(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_entra_offline_get_user() -> None:
    node = _node({"operation": "getUser", "userId": "u1"}, type_="n8n-nodes-base.microsoftEntra")
    items = _out_items(await exec_microsoft_entra(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "microsoft_entra"
    assert items[0].json["id"] == "u1"


@pytest.mark.asyncio
async def test_entra_offline_list_users() -> None:
    node = _node({"operation": "listUsers"}, type_="n8n-nodes-base.microsoftEntra")
    items = _out_items(await exec_microsoft_entra(node, [_input_item()], ctx=_ctx()))
    assert "users" in items[0].json
    assert len(items[0].json["users"]) == 3


# ── To Do ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_todo_dict_mock() -> None:
    node = _node({"operation": "createTask"}, type_="n8n-nodes-base.microsoftToDo", name="ToDo")
    ctx = _ctx({"microsoft_todo_response": {"taskId": "t1", "custom": True}})
    items = _out_items(await exec_microsoft_todo(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True


@pytest.mark.asyncio
async def test_todo_offline() -> None:
    node = _node({"operation": "createTask", "taskTitle": "Buy milk"}, type_="n8n-nodes-base.microsoftToDo")
    items = _out_items(await exec_microsoft_todo(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "microsoft_todo"
    assert items[0].json["taskTitle"] == "Buy milk"


# ── E2E ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_excel_to_set() -> None:
    doc = {
        "nodes": [
            {"id": "t", "name": "Manual", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "parameters": {}, "position": [0, 0]},
            {"id": "e", "name": "Excel", "type": "n8n-nodes-base.microsoftExcel", "typeVersion": 1, "parameters": {"operation": "read", "fileId": "f1"}, "position": [200, 0]},
            {"id": "s", "name": "Set", "type": "n8n-nodes-base.set", "typeVersion": 1, "parameters": {"assignments": {"assignments": [{"name": "result", "value": "={{ $json.source }}", "type": "string"}]}}, "position": [400, 0]},
        ],
        "connections": {
            "t": {"main": [[{"node": "e", "index": 0}]]},
            "e": {"main": [[{"node": "s", "index": 0}]]},
        },
    }
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run()
    assert result.status == "success"
    assert len(result.final_items) == 1
    assert result.final_items[0]["json"]["result"] == "microsoft_excel"


# ── Descriptor registration ─────────────────────────────────────────


def test_descriptors_registered() -> None:
    types = [
        "n8n-nodes-base.microsoftExcel",
        "n8n-nodes-base.microsoftOneDrive",
        "n8n-nodes-base.microsoftSharePoint",
        "n8n-nodes-base.microsoftSql",
        "n8n-nodes-base.microsoftEntra",
        "n8n-nodes-base.microsoftToDo",
    ]
    for t in types:
        assert t in REGISTRY, f"{t} not registered"