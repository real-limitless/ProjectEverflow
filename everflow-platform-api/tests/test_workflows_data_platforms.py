"""Tests for data platform nodes (Baserow, NocoDB, Dropbox, Nextcloud)."""
from __future__ import annotations
from typing import Any
import pytest
from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.data_platforms import exec_baserow, exec_dropbox, exec_nextcloud, exec_nocodb
from app.services.workflows.registry import REGISTRY

def _node(params, *, type_="n8n-nodes-base.baserow", id_="n1", name="Baserow"):
    return ExecNode(id=id_, name=name, type=type_, type_version=1, parameters=params, credentials=None, position={"x": 0, "y": 0})
def _ctx(mocks=None):
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {})
def _out_items(result):
    out = []
    for _idx, items in result: out.extend(items)
    return out
def _input_item(**kw): return ExecutionItem(json=kw)

@pytest.mark.asyncio
async def test_baserow_dict_mock():
    node = _node({"operation": "create"})
    ctx = _ctx({"baserow_response": {"rowId": "r1", "custom": True}})
    items = _out_items(await exec_baserow(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_baserow_offline():
    node = _node({"operation": "create", "name": "Test"})
    items = _out_items(await exec_baserow(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "baserow"

@pytest.mark.asyncio
async def test_nocodb_dict_mock():
    node = _node({"operation": "create"}, type_="n8n-nodes-base.nocoDb", name="NocoDB")
    ctx = _ctx({"nocodb_response": {"rowId": "r1", "custom": True}})
    items = _out_items(await exec_nocodb(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_nocodb_offline():
    node = _node({"operation": "create", "name": "Test"}, type_="n8n-nodes-base.nocoDb")
    items = _out_items(await exec_nocodb(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "nocodb"

@pytest.mark.asyncio
async def test_dropbox_dict_mock():
    node = _node({"operation": "upload"}, type_="n8n-nodes-base.dropbox", name="Dropbox")
    ctx = _ctx({"dropbox_response": {"path": "/test", "custom": True}})
    items = _out_items(await exec_dropbox(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_dropbox_offline():
    node = _node({"operation": "download", "path": "/file.txt"}, type_="n8n-nodes-base.dropbox")
    items = _out_items(await exec_dropbox(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "dropbox"

@pytest.mark.asyncio
async def test_nextcloud_dict_mock():
    node = _node({"operation": "upload"}, type_="n8n-nodes-base.nextCloud", name="Nextcloud")
    ctx = _ctx({"nextcloud_response": {"path": "/test", "custom": True}})
    items = _out_items(await exec_nextcloud(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_nextcloud_offline():
    node = _node({"operation": "download", "path": "/file.txt"}, type_="n8n-nodes-base.nextCloud")
    items = _out_items(await exec_nextcloud(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "nextcloud"

@pytest.mark.asyncio
async def test_e2e_baserow_to_set():
    doc = {
        "nodes": [
            {"id": "t", "name": "Manual", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "parameters": {}, "position": [0, 0]},
            {"id": "b", "name": "Baserow", "type": "n8n-nodes-base.baserow", "typeVersion": 1, "parameters": {"operation": "create", "name": "Test"}, "position": [200, 0]},
            {"id": "s", "name": "Set", "type": "n8n-nodes-base.set", "typeVersion": 1, "parameters": {"assignments": {"assignments": [{"name": "result", "value": "={{ $json.source }}", "type": "string"}]}}, "position": [400, 0]},
        ],
        "connections": {"t": {"main": [[{"node": "b", "index": 0}]]}, "b": {"main": [[{"node": "s", "index": 0}]]}},
    }
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run()
    assert result.status == "success"
    assert result.final_items[0]["json"]["result"] == "baserow"

def test_descriptors_registered():
    for t in ["n8n-nodes-base.baserow", "n8n-nodes-base.nocoDb", "n8n-nodes-base.dropbox", "n8n-nodes-base.nextCloud"]:
        assert t in REGISTRY, f"{t} not registered"