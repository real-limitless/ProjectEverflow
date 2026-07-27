"""Tests for the binary data node executors (n8n-nodes-base.*).

Covers:

- Mock dict used verbatim for each node
- Mock callable receives correct args
- http_response fallback
- Offline mode produces valid output for each node
- Operation selection works
- Parameter defaults work
- End-to-end: Manual Trigger → node → Set sees output
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem
from app.services.workflows.nodes.binary import (
    ITEM_LISTS_DEFAULT_OPERATION,
    ITEM_LISTS_OPERATIONS,
    MOVE_BINARY_DEFAULT_OPERATION,
    MOVE_BINARY_OPERATIONS,
    READ_PDF_DEFAULT_OPERATION,
    READ_PDF_OPERATIONS,
    SPREADSHEET_DEFAULT_OPERATION,
    SPREADSHEET_OPERATIONS,
    exec_item_lists,
    exec_move_binary_data,
    exec_read_binary_file,
    exec_read_binary_files,
    exec_read_pdf,
    exec_spreadsheet_file,
    exec_write_binary_file,
)


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.itemLists",
    id_: str = "n1",
    name: str = "Item Lists",
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


def _out_items(result: list[tuple[int, list[ExecutionItem]]]) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


def _doc(nodes: list[dict], connections: dict) -> dict:
    return {"name": "binary-test", "nodes": nodes, "connections": connections}


def _n(
    id_: str,
    name: str,
    type_: str,
    params: dict | None = None,
    position: tuple = (0, 0),
) -> dict:
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


# ── 1. Item Lists: mock dict used verbatim ──────────────────────────


@pytest.mark.asyncio
async def test_item_lists_mock_dict_verbatim() -> None:
    node = _node(
        {"operation": "splitOut", "field": "items"},
        type_="n8n-nodes-base.itemLists",
        name="Item Lists",
    )
    ctx = _ctx(
        {
            "itemLists_response": {
                "split": True,
                "count": 3,
            }
        }
    )
    out = _out_items(
        await exec_item_lists(node, [ExecutionItem(json={"orig": 1})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["split"] is True
    assert out[0].json["count"] == 3
    assert out[0].json["orig"] == 1


# ── 2. Item Lists: mock callable receives correct args ──────────────


@pytest.mark.asyncio
async def test_item_lists_mock_callable_receives_args() -> None:
    captured: dict[str, Any] = {}

    def mock(operation: str, params: dict, item: ExecutionItem, ctx: Any) -> dict:
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {"mocked": True}

    node = _node(
        {"operation": "splitOut", "field": "items"},
        type_="n8n-nodes-base.itemLists",
        name="Item Lists",
    )
    ctx = _ctx({"itemLists_response": mock})
    out = _out_items(
        await exec_item_lists(node, [ExecutionItem(json={"x": 1})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["mocked"] is True
    assert captured["operation"] == "splitOut"
    assert captured["params"]["field"] == "items"
    assert captured["item"].json["x"] == 1
    assert captured["ctx"] is ctx


# ── 3. Move Binary Data: mock dict used verbatim ────────────────────


@pytest.mark.asyncio
async def test_move_binary_data_mock_dict_verbatim() -> None:
    node = _node(
        {"operation": "jsonToBinary", "source": "text", "destination": "data"},
        type_="n8n-nodes-base.moveBinaryData",
        id_="mbd1",
        name="Move Binary Data",
    )
    ctx = _ctx(
        {
            "moveBinaryData_response": {
                "converted": True,
                "size": 42,
            }
        }
    )
    out = _out_items(
        await exec_move_binary_data(
            node, [ExecutionItem(json={"text": "hello"})], ctx=ctx
        )
    )
    assert len(out) == 1
    assert out[0].json["converted"] is True
    assert out[0].json["size"] == 42


# ── 4. Move Binary Data: mock callable receives correct args ────────


@pytest.mark.asyncio
async def test_move_binary_data_mock_callable_receives_args() -> None:
    captured: dict[str, Any] = {}

    def mock(operation: str, params: dict, item: ExecutionItem, ctx: Any) -> dict:
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        return {"mocked": True}

    node = _node(
        {"operation": "binaryToJson", "source": "data", "destination": "text"},
        type_="n8n-nodes-base.moveBinaryData",
        id_="mbd1",
        name="Move Binary Data",
    )
    ctx = _ctx({"moveBinaryData_response": mock})
    out = _out_items(
        await exec_move_binary_data(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["mocked"] is True
    assert captured["operation"] == "binaryToJson"
    assert captured["params"]["source"] == "data"


# ── 5. Read Binary File: mock dict used verbatim ────────────────────


@pytest.mark.asyncio
async def test_read_binary_file_mock_dict_verbatim() -> None:
    node = _node(
        {"filePath": "/tmp/test.txt"},
        type_="n8n-nodes-base.readBinaryFile",
        id_="rbf1",
        name="Read Binary File",
    )
    ctx = _ctx(
        {
            "readBinaryFile_response": {
                "data": "aGVsbG8=",
                "fileName": "test.txt",
                "mimeType": "text/plain",
                "fileSize": 5,
            }
        }
    )
    out = _out_items(
        await exec_read_binary_file(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["data"] == "aGVsbG8="
    assert out[0].json["fileName"] == "test.txt"
    assert out[0].json["mimeType"] == "text/plain"
    assert out[0].json["fileSize"] == 5


# ── 6. Read Binary File: mock callable receives correct args ────────


@pytest.mark.asyncio
async def test_read_binary_file_mock_callable_receives_args() -> None:
    captured: dict[str, Any] = {}

    def mock(operation: str, params: dict, item: ExecutionItem, ctx: Any) -> dict:
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        return {"data": "bW9jaw==", "fileName": "mock.bin"}

    node = _node(
        {"filePath": "/tmp/data.bin"},
        type_="n8n-nodes-base.readBinaryFile",
        id_="rbf1",
        name="Read Binary File",
    )
    ctx = _ctx({"readBinaryFile_response": mock})
    out = _out_items(
        await exec_read_binary_file(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["data"] == "bW9jaw=="
    assert captured["operation"] == "read"
    assert captured["params"]["filePath"] == "/tmp/data.bin"


# ── 7. Read Binary Files: mock dict used verbatim ───────────────────


@pytest.mark.asyncio
async def test_read_binary_files_mock_dict_verbatim() -> None:
    node = _node(
        {"fileFolderPath": "/tmp/data", "fileMask": "*.csv"},
        type_="n8n-nodes-base.readBinaryFiles",
        id_="rbfs1",
        name="Read Binary Files",
    )
    ctx = _ctx(
        {
            "readBinaryFiles_response": [
                {"fileName": "a.csv", "data": "YQ==", "fileSize": 1},
                {"fileName": "b.csv", "data": "Yg==", "fileSize": 1},
            ]
        }
    )
    out = _out_items(
        await exec_read_binary_files(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 2
    assert out[0].json["fileName"] == "a.csv"
    assert out[1].json["fileName"] == "b.csv"


# ── 8. Read Binary Files: mock callable receives correct args ───────


@pytest.mark.asyncio
async def test_read_binary_files_mock_callable_receives_args() -> None:
    captured: dict[str, Any] = {}

    def mock(operation: str, params: dict, item: ExecutionItem, ctx: Any) -> list:
        captured["operation"] = operation
        captured["params"] = params
        return [{"fileName": "mock.txt"}]

    node = _node(
        {"fileFolderPath": "/tmp", "fileMask": "*"},
        type_="n8n-nodes-base.readBinaryFiles",
        id_="rbfs1",
        name="Read Binary Files",
    )
    ctx = _ctx({"readBinaryFiles_response": mock})
    out = _out_items(
        await exec_read_binary_files(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["fileName"] == "mock.txt"
    assert captured["operation"] == "read"
    assert captured["params"]["fileMask"] == "*"


# ── 9. Write Binary File: mock dict used verbatim ───────────────────


@pytest.mark.asyncio
async def test_write_binary_file_mock_dict_verbatim() -> None:
    node = _node(
        {"filePath": "/tmp/out.bin", "dataPropertyName": "data"},
        type_="n8n-nodes-base.writeBinaryFile",
        id_="wbf1",
        name="Write Binary File",
    )
    ctx = _ctx(
        {
            "writeBinaryFile_response": {
                "fileName": "out.bin",
                "filePath": "/tmp/out.bin",
                "fileSize": 100,
                "success": True,
            }
        }
    )
    out = _out_items(
        await exec_write_binary_file(
            node, [ExecutionItem(json={})], ctx=ctx
        )
    )
    assert len(out) == 1
    assert out[0].json["fileName"] == "out.bin"
    assert out[0].json["fileSize"] == 100
    assert out[0].json["success"] is True


# ── 10. Write Binary File: mock callable receives correct args ──────


@pytest.mark.asyncio
async def test_write_binary_file_mock_callable_receives_args() -> None:
    captured: dict[str, Any] = {}

    def mock(operation: str, params: dict, item: ExecutionItem, ctx: Any) -> dict:
        captured["operation"] = operation
        captured["params"] = params
        return {"success": True, "fileSize": 42}

    node = _node(
        {"filePath": "/tmp/out.txt"},
        type_="n8n-nodes-base.writeBinaryFile",
        id_="wbf1",
        name="Write Binary File",
    )
    ctx = _ctx({"writeBinaryFile_response": mock})
    out = _out_items(
        await exec_write_binary_file(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["success"] is True
    assert captured["operation"] == "write"
    assert captured["params"]["filePath"] == "/tmp/out.txt"


# ── 11. Spreadsheet File: mock dict used verbatim ───────────────────


@pytest.mark.asyncio
async def test_spreadsheet_file_mock_dict_verbatim() -> None:
    node = _node(
        {"operation": "read", "fileFormat": "csv"},
        type_="n8n-nodes-base.spreadsheetFile",
        id_="sf1",
        name="Spreadsheet File",
    )
    ctx = _ctx(
        {
            "spreadsheetFile_response": {
                "col1": "val1",
                "col2": "val2",
            }
        }
    )
    out = _out_items(
        await exec_spreadsheet_file(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["col1"] == "val1"
    assert out[0].json["col2"] == "val2"


# ── 12. Spreadsheet File: mock callable receives correct args ───────


@pytest.mark.asyncio
async def test_spreadsheet_file_mock_callable_receives_args() -> None:
    captured: dict[str, Any] = {}

    def mock(operation: str, params: dict, item: ExecutionItem, ctx: Any) -> dict:
        captured["operation"] = operation
        captured["params"] = params
        return {"mocked": True}

    node = _node(
        {"operation": "write", "fileFormat": "xlsx"},
        type_="n8n-nodes-base.spreadsheetFile",
        id_="sf1",
        name="Spreadsheet File",
    )
    ctx = _ctx({"spreadsheetFile_response": mock})
    out = _out_items(
        await exec_spreadsheet_file(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["mocked"] is True
    assert captured["operation"] == "write"
    assert captured["params"]["fileFormat"] == "xlsx"


# ── 13. Read PDF: mock dict used verbatim ───────────────────────────


@pytest.mark.asyncio
async def test_read_pdf_mock_dict_verbatim() -> None:
    node = _node(
        {"operation": "pdfExtractText", "file": "data"},
        type_="n8n-nodes-base.readPDF",
        id_="pdf1",
        name="Read PDF",
    )
    ctx = _ctx(
        {
            "readPDF_response": {
                "text": "Extracted text here.",
                "pageCount": 3,
                "fileName": "doc.pdf",
            }
        }
    )
    out = _out_items(
        await exec_read_pdf(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["text"] == "Extracted text here."
    assert out[0].json["pageCount"] == 3
    assert out[0].json["fileName"] == "doc.pdf"


# ── 14. Read PDF: mock callable receives correct args ───────────────


@pytest.mark.asyncio
async def test_read_pdf_mock_callable_receives_args() -> None:
    captured: dict[str, Any] = {}

    def mock(operation: str, params: dict, item: ExecutionItem, ctx: Any) -> dict:
        captured["operation"] = operation
        captured["params"] = params
        return {"text": "mock", "pageCount": 1}

    node = _node(
        {"operation": "pdfExtractText", "file": "data"},
        type_="n8n-nodes-base.readPDF",
        id_="pdf1",
        name="Read PDF",
    )
    ctx = _ctx({"readPDF_response": mock})
    out = _out_items(
        await exec_read_pdf(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["text"] == "mock"
    assert captured["operation"] == "pdfExtractText"
    assert captured["params"]["file"] == "data"


# ── 15. http_response fallback ──────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_read_binary_file() -> None:
    node = _node(
        {"filePath": "/tmp/test.txt"},
        type_="n8n-nodes-base.readBinaryFile",
        id_="rbf1",
        name="Read Binary File",
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "data": "aGk=",
                    "fileName": "from_http.txt",
                    "fileSize": 2,
                },
                "headers": {},
            }
        }
    )
    out = _out_items(
        await exec_read_binary_file(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["data"] == "aGk="
    assert out[0].json["fileName"] == "from_http.txt"


# ── 16. Item Lists: offline splitOut ────────────────────────────────


@pytest.mark.asyncio
async def test_item_lists_offline_splitout() -> None:
    node = _node(
        {"operation": "splitOut", "field": "items"},
        type_="n8n-nodes-base.itemLists",
        name="Item Lists",
    )
    item = ExecutionItem(
        json={
            "items": [
                {"name": "a"},
                {"name": "b"},
                {"name": "c"},
            ]
        }
    )
    out = _out_items(await exec_item_lists(node, [item], ctx=_ctx()))
    assert len(out) == 3
    assert out[0].json["name"] == "a"
    assert out[1].json["name"] == "b"
    assert out[2].json["name"] == "c"


# ── 17. Item Lists: offline aggregate ───────────────────────────────


@pytest.mark.asyncio
async def test_item_lists_offline_aggregate() -> None:
    node = _node(
        {"operation": "aggregate", "field": "value"},
        type_="n8n-nodes-base.itemLists",
        name="Item Lists",
    )
    items = [
        ExecutionItem(json={"value": 1}),
        ExecutionItem(json={"value": 2}),
        ExecutionItem(json={"value": 3}),
    ]
    out = _out_items(await exec_item_lists(node, items, ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["value"] == [1, 2, 3]
    assert out[0].json["count"] == 3


# ── 18. Item Lists: offline flatten ─────────────────────────────────


@pytest.mark.asyncio
async def test_item_lists_offline_flatten() -> None:
    node = _node(
        {"operation": "flatten", "field": "nested"},
        type_="n8n-nodes-base.itemLists",
        name="Item Lists",
    )
    item = ExecutionItem(json={"nested": [[1, 2], [3], [4, 5]]})
    out = _out_items(await exec_item_lists(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["nested"] == [1, 2, 3, 4, 5]


# ── 19. Move Binary Data: offline jsonToBinary ──────────────────────


@pytest.mark.asyncio
async def test_move_binary_data_offline_json_to_binary() -> None:
    node = _node(
        {"operation": "jsonToBinary", "source": "text", "destination": "data"},
        type_="n8n-nodes-base.moveBinaryData",
        id_="mbd1",
        name="Move Binary Data",
    )
    out = _out_items(
        await exec_move_binary_data(
            node, [ExecutionItem(json={"text": "hello"})], ctx=_ctx()
        )
    )
    assert len(out) == 1
    assert "data" in out[0].binary
    bf = out[0].binary["data"]
    assert bf.to_bytes() == b"hello"


# ── 20. Move Binary Data: offline binaryToJson ──────────────────────


@pytest.mark.asyncio
async def test_move_binary_data_offline_binary_to_json() -> None:
    node = _node(
        {"operation": "binaryToJson", "source": "data", "destination": "text"},
        type_="n8n-nodes-base.moveBinaryData",
        id_="mbd1",
        name="Move Binary Data",
    )
    bf = BinaryFile.from_bytes(b"hello world", file_name="test.txt")
    out = _out_items(
        await exec_move_binary_data(
            node, [ExecutionItem(json={}, binary={"data": bf})], ctx=_ctx()
        )
    )
    assert len(out) == 1
    assert out[0].json["text"] == "hello world"


# ── 21. Read Binary File: offline ───────────────────────────────────


@pytest.mark.asyncio
async def test_read_binary_file_offline() -> None:
    node = _node(
        {"filePath": "/tmp/report.txt"},
        type_="n8n-nodes-base.readBinaryFile",
        id_="rbf1",
        name="Read Binary File",
    )
    out = _out_items(
        await exec_read_binary_file(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    assert "data" in out[0].json
    assert out[0].json["fileName"] == "report.txt"
    assert out[0].json["mimeType"] == "text/plain"
    assert out[0].json["fileSize"] == len(b"mock file content")
    assert "data" in out[0].binary
    assert out[0].binary["data"].to_bytes() == b"mock file content"


# ── 22. Read Binary Files: offline ──────────────────────────────────


@pytest.mark.asyncio
async def test_read_binary_files_offline() -> None:
    node = _node(
        {"fileFolderPath": "/tmp/data", "fileMask": "*"},
        type_="n8n-nodes-base.readBinaryFiles",
        id_="rbfs1",
        name="Read Binary Files",
    )
    out = _out_items(
        await exec_read_binary_files(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3
    for i, item in enumerate(out):
        assert item.json["fileName"] == f"mock_file_{i}.txt"
        assert item.json["filePath"] == f"/tmp/data/mock_file_{i}.txt"
        assert "data" in item.binary


# ── 23. Write Binary File: offline ──────────────────────────────────


@pytest.mark.asyncio
async def test_write_binary_file_offline() -> None:
    node = _node(
        {"filePath": "/tmp/out.txt", "dataPropertyName": "data"},
        type_="n8n-nodes-base.writeBinaryFile",
        id_="wbf1",
        name="Write Binary File",
    )
    bf = BinaryFile.from_bytes(b"output data", file_name="out.txt")
    out = _out_items(
        await exec_write_binary_file(
            node, [ExecutionItem(json={}, binary={"data": bf})], ctx=_ctx()
        )
    )
    assert len(out) == 1
    assert out[0].json["fileName"] == "out.txt"
    assert out[0].json["filePath"] == "/tmp/out.txt"
    assert out[0].json["fileSize"] == 11
    assert out[0].json["success"] is True


# ── 24. Spreadsheet File: offline read ──────────────────────────────


@pytest.mark.asyncio
async def test_spreadsheet_file_offline_read() -> None:
    node = _node(
        {"operation": "read", "fileFormat": "csv"},
        type_="n8n-nodes-base.spreadsheetFile",
        id_="sf1",
        name="Spreadsheet File",
    )
    csv_bytes = b"name,age\nAlice,30\nBob,25\n"
    bf = BinaryFile.from_bytes(csv_bytes, file_name="data.csv")
    out = _out_items(
        await exec_spreadsheet_file(
            node, [ExecutionItem(json={}, binary={"data": bf})], ctx=_ctx()
        )
    )
    assert len(out) == 2
    assert out[0].json["name"] == "Alice"
    assert out[0].json["age"] == "30"
    assert out[1].json["name"] == "Bob"
    assert out[1].json["age"] == "25"


# ── 25. Spreadsheet File: offline write ─────────────────────────────


@pytest.mark.asyncio
async def test_spreadsheet_file_offline_write() -> None:
    node = _node(
        {"operation": "write", "fileFormat": "csv"},
        type_="n8n-nodes-base.spreadsheetFile",
        id_="sf1",
        name="Spreadsheet File",
    )
    items = [
        ExecutionItem(json={"name": "Alice", "age": 30}),
        ExecutionItem(json={"name": "Bob", "age": 25}),
    ]
    out = _out_items(await exec_spreadsheet_file(node, items, ctx=_ctx()))
    assert len(out) == 1
    assert "data" in out[0].binary
    csv_text = out[0].binary["data"].to_bytes().decode("utf-8")
    assert "name" in csv_text
    assert "Alice" in csv_text
    assert "Bob" in csv_text
    assert out[0].json["format"] == "csv"


# ── 26. Read PDF: offline ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_pdf_offline() -> None:
    node = _node(
        {"operation": "pdfExtractText", "file": "data"},
        type_="n8n-nodes-base.readPDF",
        id_="pdf1",
        name="Read PDF",
    )
    bf = BinaryFile.from_bytes(b"%PDF-1.4 fake", file_name="doc.pdf")
    out = _out_items(
        await exec_read_pdf(
            node, [ExecutionItem(json={}, binary={"data": bf})], ctx=_ctx()
        )
    )
    assert len(out) == 1
    assert "text" in out[0].json
    assert out[0].json["pageCount"] >= 1
    assert out[0].json["fileName"] == "doc.pdf"


# ── 27. Item Lists: default operation is splitOut ───────────────────


@pytest.mark.asyncio
async def test_item_lists_default_operation() -> None:
    assert ITEM_LISTS_DEFAULT_OPERATION == "splitOut"
    assert "splitOut" in ITEM_LISTS_OPERATIONS
    assert "aggregate" in ITEM_LISTS_OPERATIONS
    assert "flatten" in ITEM_LISTS_OPERATIONS

    node = _node(
        {"field": "items"},
        type_="n8n-nodes-base.itemLists",
        name="Item Lists",
    )
    item = ExecutionItem(json={"items": [{"v": 1}, {"v": 2}]})
    out = _out_items(await exec_item_lists(node, [item], ctx=_ctx()))
    assert len(out) == 2
    assert out[0].json["v"] == 1
    assert out[1].json["v"] == 2


# ── 28. Move Binary Data: default operation is jsonToBinary ────────


@pytest.mark.asyncio
async def test_move_binary_data_default_operation() -> None:
    assert MOVE_BINARY_DEFAULT_OPERATION == "jsonToBinary"
    assert "jsonToBinary" in MOVE_BINARY_OPERATIONS
    assert "binaryToJson" in MOVE_BINARY_OPERATIONS


# ── 29. Spreadsheet File: default operation is read ────────────────


@pytest.mark.asyncio
async def test_spreadsheet_file_default_operation() -> None:
    assert SPREADSHEET_DEFAULT_OPERATION == "read"
    assert "read" in SPREADSHEET_OPERATIONS
    assert "write" in SPREADSHEET_OPERATIONS


# ── 30. Read PDF: default operation is pdfExtractText ──────────────


@pytest.mark.asyncio
async def test_read_pdf_default_operation() -> None:
    assert READ_PDF_DEFAULT_OPERATION == "pdfExtractText"
    assert "pdfExtractText" in READ_PDF_OPERATIONS


# ── 31. End-to-end: Manual Trigger → Read PDF → Set sees output ────


@pytest.mark.asyncio
async def test_end_to_end_manual_read_pdf_set_sees_output() -> None:
    mocks = {
        "readPDF_response": {
            "text": "Hello from PDF.",
            "pageCount": 2,
            "fileName": "report.pdf",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "p1",
                "ReadPDF",
                "n8n-nodes-base.readPDF",
                {"operation": "pdfExtractText", "file": "data"},
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "pdf_text",
                                "value": "={{ $json.text }}",
                                "type": "string",
                            },
                            {
                                "name": "pdf_pages",
                                "value": "={{ $json.pageCount }}",
                                "type": "number",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "ReadPDF", "type": "main", "index": 0}]]},
            "ReadPDF": {
                "main": [[{"node": "Downstream", "type": "main", "index": 0}]]
            },
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    pdf_step = next(s for s in result.steps if s.node_name == "ReadPDF")
    assert pdf_step.status == "success", pdf_step.error
    assert pdf_step.output_count == 1

    final = result.final_items
    assert final
    assert final[0]["json"]["pdf_text"] == "Hello from PDF."
    assert final[0]["json"]["pdf_pages"] == 2


# ── 32. Descriptor registration (CI invariant) ─────────────────────


def test_descriptor_registration_all_binary_nodes() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    expected = {
        "n8n-nodes-base.itemLists": "transform",
        "n8n-nodes-base.moveBinaryData": "transform",
        "n8n-nodes-base.readBinaryFile": "transform",
        "n8n-nodes-base.readBinaryFiles": "transform",
        "n8n-nodes-base.writeBinaryFile": "transform",
        "n8n-nodes-base.spreadsheetFile": "transform",
        "n8n-nodes-base.readPDF": "transform",
    }
    for n8n_type, category in expected.items():
        assert n8n_type in REGISTRY, f"{n8n_type} missing from REGISTRY"
        assert n8n_type in SUPPORTED_NODE_TYPES, (
            f"{n8n_type} missing from SUPPORTED_NODE_TYPES"
        )
        assert SUPPORTED_NODE_TYPES[n8n_type] == category, (
            f"{n8n_type} category mismatch: "
            f"expected {category}, got {SUPPORTED_NODE_TYPES[n8n_type]}"
        )
        desc = REGISTRY[n8n_type]
        assert desc.executor.startswith("app.services.workflows.nodes.binary:"), (
            f"{n8n_type} executor not in binary module: {desc.executor}"
        )