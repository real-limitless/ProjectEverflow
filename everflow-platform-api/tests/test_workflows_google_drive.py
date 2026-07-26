"""Tests for the Google Drive node executor (``n8n-nodes-base.googleDrive``).

Covers:

- ``drive_response`` dict mock → envelope is used per operation
- ``drive_response`` callable mock receives ``(operation, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline upload: id present, name echoed, size=1024
- Offline download: content base64-decodes to ``b'mock file content'``
- Offline list: returns 3 files by default
- Offline delete: success=True
- ``operation='upload'`` reflected on the payload
- ``fileId``/``folderId`` defaults from ``$json``
- ``pageSize`` honored (offline caps at 3)
- End-to-end: Manual Trigger → googleDrive (list mock) → Set sees files
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.google_drive import (
    DRIVE_DEFAULT_OPERATION,
    DRIVE_OPERATIONS,
    exec_google_drive,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.googleDrive",
    id_: str = "gd1",
    name: str = "Drive",
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


# ── 1. drive_response dict mock (upload) ──────────────────────────────


@pytest.mark.asyncio
async def test_drive_response_dict_mock_upload_used_verbatim() -> None:
    node = _node(
        {
            "operation": "upload",
            "name": "report.txt",
            "mimeType": "text/plain",
        }
    )
    ctx = _ctx(
        {
            "drive_response": {
                "id": "drive-file-001",
                "name": "report.txt",
                "mimeType": "text/plain",
                "size": 4096,
                "webViewLink": "https://drive.google.com/file/d/drive-file-001/view",
            }
        }
    )
    out = _out_items(
        await exec_google_drive(
            node, [ExecutionItem(json={"content": "aGk="})], ctx=ctx
        )
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["id"] == "drive-file-001"
    assert payload["name"] == "report.txt"
    assert payload["mimeType"] == "text/plain"
    assert payload["size"] == 4096
    assert payload["webViewLink"].endswith("/view")
    assert payload["source"] == "googleDrive"
    assert payload["operation"] == "upload"


# ── 2. drive_response callable mock signature ─────────────────────────


@pytest.mark.asyncio
async def test_drive_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "captured-001",
            "name": params.get("name"),
            "mimeType": "text/plain",
            "size": 2048,
            "webViewLink": "https://drive.google.com/file/d/captured-001/view",
        }

    node = _node(
        {
            "operation": "upload",
            "name": "from-mock.txt",
            "mimeType": "text/plain",
            "extra": "keep",
        }
    )
    ctx = _ctx({"drive_response": _mock})
    item = ExecutionItem(json={"hint": 1, "content": "aGk="})
    out = _out_items(await exec_google_drive(node, [item], ctx=ctx))

    assert captured["operation"] == "upload"
    assert captured["params"]["name"] == "from-mock.txt"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx
    assert out[0].json["id"] == "captured-001"


@pytest.mark.asyncio
async def test_drive_response_callable_for_list() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        return {
            "files": [
                {"id": "a", "name": "alpha.txt", "mimeType": "text/plain", "size": 10},
                {"id": "b", "name": "beta.txt", "mimeType": "text/plain", "size": 20},
            ],
            "nextPageToken": None,
        }

    node = _node({"operation": "list", "folderId": "folderX", "pageSize": 5})
    out = _out_items(
        await exec_google_drive(
            node, [ExecutionItem(json={})], ctx=_ctx({"drive_response": _mock})
        )
    )
    assert captured["operation"] == "list"
    assert captured["params"]["folderId"] == "folderX"
    assert len(out) == 2
    assert out[0].json["name"] == "alpha.txt"
    assert out[1].json["name"] == "beta.txt"


# ── 3. http_response fallback (list) ──────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_list_body() -> None:
    node = _node({"operation": "list", "pageSize": 2})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "files": [
                        {"id": "x", "name": "x.txt", "mimeType": "text/plain", "size": 1},
                    ],
                    "nextPageToken": None,
                },
            }
        }
    )
    out = _out_items(await exec_google_drive(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    assert out[0].json["name"] == "x.txt"
    assert out[0].json["mockSource"] == "http_response"


# ── 4. Offline upload ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_upload_id_present_name_echoed_size_1024() -> None:
    node = _node(
        {
            "operation": "upload",
            "name": "offline.txt",
            "mimeType": "text/plain",
        }
    )
    out = _out_items(
        await exec_google_drive(
            node, [ExecutionItem(json={"content": ""})], ctx=_ctx()
        )
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["id"].startswith("mock_file_")
    assert payload["name"] == "offline.txt"
    assert payload["mimeType"] == "text/plain"
    assert payload["size"] == 1024
    assert payload["webViewLink"].startswith("https://drive.google.com/file/d/")
    assert payload["source"] == "googleDrive"
    assert payload["operation"] == "upload"
    assert payload["mockSource"] == "offline"


# ── 5. Offline download ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_download_content_base64_decodes() -> None:
    node = _node({"operation": "download", "fileId": "file-007"})
    out = _out_items(
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["id"] == "file-007"
    assert payload["name"] == "mock_file.txt"
    assert payload["mimeType"] == "text/plain"
    assert base64.b64decode(payload["content"]) == b"mock file content"
    assert payload["size"] == 17
    assert payload["source"] == "googleDrive"
    assert payload["operation"] == "download"


# ── 6. Offline list returns 3 files by default ────────────────────────


@pytest.mark.asyncio
async def test_offline_list_returns_three_files_by_default() -> None:
    node = _node({"operation": "list"})
    out = _out_items(
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3
    names = [o.json["name"] for o in out]
    assert names == ["mock_file_0.txt", "mock_file_1.txt", "mock_file_2.txt"]
    for o in out:
        assert o.json["id"].startswith("mock_")
        assert o.json["mimeType"] == "text/plain"
        assert o.json["size"] == 1024
        assert o.json["source"] == "googleDrive"
        assert o.json["operation"] == "list"
        assert o.json["folderId"] == "root"


@pytest.mark.asyncio
async def test_offline_list_data_mode_object() -> None:
    node = _node({"operation": "list", "dataMode": "object"})
    out = _out_items(
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    payload = out[0].json
    assert isinstance(payload["files"], list)
    assert len(payload["files"]) == 3
    assert payload["folderId"] == "root"
    assert payload["source"] == "googleDrive"


# ── 7. Offline delete: success=True ──────────────────────────────────


@pytest.mark.asyncio
async def test_offline_delete_success_true() -> None:
    node = _node({"operation": "delete", "fileId": "file-xyz"})
    out = _out_items(
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["fileId"] == "file-xyz"
    assert payload["success"] is True
    assert payload["ok"] is True
    assert payload["deletedAt"].endswith("Z")
    assert payload["source"] == "googleDrive"
    assert payload["operation"] == "delete"


# ── 8. operation='upload' reflected on output ────────────────────────


@pytest.mark.asyncio
async def test_operation_upload_reflected_on_output() -> None:
    node = _node(
        {
            "operation": "upload",
            "name": "x.txt",
            "mimeType": "text/plain",
        }
    )
    out = _out_items(
        await exec_google_drive(
            node, [ExecutionItem(json={"content": "aGk="})], ctx=_ctx()
        )
    )
    assert out[0].json["operation"] == "upload"


# ── 9. fileId / folderId defaults from $json ─────────────────────────


@pytest.mark.asyncio
async def test_file_id_default_from_json() -> None:
    node = _node({"operation": "download"})
    out = _out_items(
        await exec_google_drive(
            node, [ExecutionItem(json={"id": "from-json"})], ctx=_ctx()
        )
    )
    assert out[0].json["id"] == "from-json"


@pytest.mark.asyncio
async def test_file_id_default_from_json_fieldId() -> None:
    node = _node({"operation": "delete"})
    out = _out_items(
        await exec_google_drive(
            node, [ExecutionItem(json={"fileId": "fid-1"})], ctx=_ctx()
        )
    )
    assert out[0].json["fileId"] == "fid-1"


@pytest.mark.asyncio
async def test_folder_id_default_from_json() -> None:
    node = _node({"operation": "list"})
    out = _out_items(
        await exec_google_drive(
            node, [ExecutionItem(json={"folderId": "custom-folder"})], ctx=_ctx()
        )
    )
    assert out[0].json["folderId"] == "custom-folder"


@pytest.mark.asyncio
async def test_name_default_from_json_fileName() -> None:
    node = _node(
        {"operation": "upload", "mimeType": "text/plain"}
    )
    out = _out_items(
        await exec_google_drive(
            node,
            [ExecutionItem(json={"fileName": "fallback.txt", "content": "aGk="})],
            ctx=_ctx(),
        )
    )
    assert out[0].json["name"] == "fallback.txt"


# ── 10. pageSize honored ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_page_size_honored_capped_at_three() -> None:
    node = _node({"operation": "list", "pageSize": 100})
    out = _out_items(
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    # offline caps at 3
    assert len(out) == 3


@pytest.mark.asyncio
async def test_page_size_one_returns_one_file() -> None:
    node = _node({"operation": "list", "pageSize": 1})
    out = _out_items(
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1


# ── 11. Skip behavior ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_download_skipped_when_no_file_id() -> None:
    node = _node({"operation": "download"})
    out = _out_items(
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_delete_skipped_when_no_file_id() -> None:
    node = _node({"operation": "delete"})
    out = _out_items(
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "share"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_google_drive(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 12. Default operation is 'list' ──────────────────────────────────


def test_default_operation_is_list() -> None:
    assert DRIVE_DEFAULT_OPERATION == "list"
    assert set(DRIVE_OPERATIONS) == {"upload", "download", "list", "delete"}


# ── 13. Multiple input items produce one envelope each ────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input_for_download() -> None:
    node = _node({"operation": "download"})
    items = [
        ExecutionItem(json={"fileId": "a"}),
        ExecutionItem(json={"fileId": "b"}),
        ExecutionItem(json={"fileId": "c"}),
    ]
    out = _out_items(await exec_google_drive(node, items, ctx=_ctx()))
    assert len(out) == 3
    assert [o.json["id"] for o in out] == ["a", "b", "c"]


# ── 14. Descriptor registration ──────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.googleDrive" in REGISTRY
    assert "n8n-nodes-base.googleDrive" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.googleDrive"] == "output"
    desc = REGISTRY["n8n-nodes-base.googleDrive"]
    assert desc.executor.endswith(":exec_google_drive")
    assert desc.category == "output"


# ── 15. End-to-end: Manual Trigger → googleDrive (list mock) → Set sees files


def _doc(nodes, connections):
    return {"name": "drive-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_drive_list_set_sees_files() -> None:
    """Manual Trigger → googleDrive (list, drive_response mock) → Set sees file info."""
    mocks = {
        "drive_response": {
            "files": [
                {"id": "f1", "name": "first.txt", "mimeType": "text/plain", "size": 11},
                {"id": "f2", "name": "second.txt", "mimeType": "text/plain", "size": 22},
            ],
            "nextPageToken": None,
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "d1",
                "Drive",
                "n8n-nodes-base.googleDrive",
                {"operation": "list", "folderId": "root", "pageSize": 5},
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
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Drive", "type": "main", "index": 0}]]},
            "Drive": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    drive_step = next(s for s in result.steps if s.node_name == "Drive")
    assert drive_step.status == "success", drive_step.error
    assert drive_step.output_count == 2

    final = result.final_items
    assert final, "expected at least one final item"
    names = [f.get("json", {}).get("result_name") for f in final]
    ids = [f.get("json", {}).get("result_id") for f in final]
    sources = [f.get("json", {}).get("result_source") for f in final]
    assert names == ["first.txt", "second.txt"]
    assert ids == ["f1", "f2"]
    assert sources == ["googleDrive", "googleDrive"]
