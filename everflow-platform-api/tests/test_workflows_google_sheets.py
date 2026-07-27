"""Tests for the Google Sheets node executor (``n8n-nodes-base.googleSheets``).

Covers:

- ``sheets_response`` dict mock → envelope used verbatim (read/append/update)
- ``sheets_response`` callable mock receives
  ``(operation, sheetId, range, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline synthetic responses for read (values list), append (updatedRows/Cols),
  and update (updatedCells)
- ``sheetId``/``range`` defaults from ``$json``
- ``data`` defaults from ``$json.data`` / ``$json.values``
- ``operation='append'`` reflected
- Empty ``sheetId`` → no item emitted
- End-to-end: Manual Trigger → googleSheets (read mock) → Set sees range/values
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.google_sheets import (
    SHEETS_OPERATIONS,
    exec_google_sheets,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.googleSheets",
    id_: str = "gs1",
    name: str = "Google Sheets",
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


# ── 1. sheets_response dict mock (read) ───────────────────────────────


@pytest.mark.asyncio
async def test_sheets_response_dict_mock_is_used_verbatim_for_read() -> None:
    node = _node(
        {
            "operation": "read",
            "sheetId": "sheet-abc",
            "range": "A1:B2",
        }
    )
    ctx = _ctx(
        {
            "sheets_response": {
                "range": "A1:B2",
                "majorDimension": "ROWS",
                "values": [
                    ["a1", "b1"],
                    ["a2", "b2"],
                ],
            }
        }
    )
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 2
    for o in out:
        assert o.json["range"] == "A1:B2"
        assert o.json["majorDimension"] == "ROWS"
        assert o.json["source"] == "googleSheets"
        assert o.json["sheetId"] == "sheet-abc"
    assert out[0].json["values"] == ["a1", "b1"]
    assert out[1].json["values"] == ["a2", "b2"]
    assert out[0].json["rowCount"] == 1


# ── 2. sheets_response callable mock signature ─────────────────────────


@pytest.mark.asyncio
async def test_sheets_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, sheet_id, range_str, params, item, ctx):
        captured["operation"] = operation
        captured["sheetId"] = sheet_id
        captured["range"] = range_str
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "range": range_str,
            "majorDimension": "ROWS",
            "values": [["only", "row"]],
        }

    node = _node(
        {
            "operation": "read",
            "sheetId": "sheet-cb",
            "range": "A1:Z1",
            "extra": "keep",
        }
    )
    ctx = _ctx({"sheets_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_google_sheets(node, [item], ctx=ctx))

    assert captured["operation"] == "read"
    assert captured["sheetId"] == "sheet-cb"
    assert captured["range"] == "A1:Z1"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["values"] == ["only", "row"]


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "read",
            "sheetId": "sheet-http",
            "range": "A1:B1",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "range": "A1:B1",
                    "majorDimension": "ROWS",
                    "values": [["x", "y"]],
                },
            }
        }
    )
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["values"] == ["x", "y"]
    assert out[0].json["mockSource"] == "http_response"
    assert out[0].json["source"] == "googleSheets"


# ── 4. Offline synthetic response — read ───────────────────────────────


@pytest.mark.asyncio
async def test_offline_read_returns_values_list() -> None:
    node = _node(
        {
            "operation": "read",
            "sheetId": "sheet-offline",
            "range": "A1:C2",
        }
    )
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 2
    assert out[0].json["range"] == "A1:C2"
    assert out[0].json["majorDimension"] == "ROWS"
    assert out[0].json["values"] == ["mock", "row1", "data"]
    assert out[1].json["values"] == ["mock", "row2", "data"]
    assert out[0].json["source"] == "googleSheets"
    assert out[0].json["mockSource"] == "offline"


# ── 5. Offline synthetic response — append ────────────────────────────


@pytest.mark.asyncio
async def test_offline_append_returns_updated_rows_and_columns() -> None:
    node = _node(
        {
            "operation": "append",
            "sheetId": "sheet-app",
            "range": "A1:C1",
            "data": [["x", "y", "z"]],
        }
    )
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["spreadsheetId"] == "sheet-app"
    assert p["updatedRange"] == "A1:C1"
    assert p["updatedRows"] == 1
    assert p["updatedColumns"] == 3
    assert p["source"] == "googleSheets"
    assert p["mockSource"] == "offline"


# ── 6. Offline synthetic response — update ────────────────────────────


@pytest.mark.asyncio
async def test_offline_update_returns_updated_cells() -> None:
    node = _node(
        {
            "operation": "update",
            "sheetId": "sheet-upd",
            "range": "A1:C2",
            "data": [["a", "b", "c"], ["d", "e", "f"]],
        }
    )
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["spreadsheetId"] == "sheet-upd"
    assert p["updatedRange"] == "A1:C2"
    assert p["updatedRows"] == 1
    assert p["updatedColumns"] == 3
    assert p["updatedCells"] == 3
    assert p["source"] == "googleSheets"
    assert p["mockSource"] == "offline"


# ── 7. sheetId / range defaults from $json ───────────────────────────


@pytest.mark.asyncio
async def test_sheet_id_and_range_default_from_json() -> None:
    node = _node({"operation": "read"})
    item = ExecutionItem(
        json={
            "spreadsheetId": "from-json-id",
            "range": "B2:D5",
        }
    )
    out = _out_items(await exec_google_sheets(node, [item], ctx=_ctx()))
    assert len(out) == 2
    assert out[0].json["sheetId"] == "from-json-id"
    assert out[0].json["range"] == "B2:D5"


@pytest.mark.asyncio
async def test_sheet_id_prefers_sheetId_over_spreadsheetId() -> None:
    node = _node({"operation": "read"})
    item = ExecutionItem(json={"sheetId": "short-id", "spreadsheetId": "long-id"})
    out = _out_items(await exec_google_sheets(node, [item], ctx=_ctx()))
    assert out[0].json["sheetId"] == "short-id"


@pytest.mark.asyncio
async def test_range_default_is_a1_z1000_when_unset() -> None:
    node = _node({"operation": "read", "sheetId": "x"})
    item = ExecutionItem(json={})
    out = _out_items(await exec_google_sheets(node, [item], ctx=_ctx()))
    assert out[0].json["range"] == "A1:Z1000"


# ── 8. data defaults from $json.data / $json.values ───────────────────


@pytest.mark.asyncio
async def test_data_default_from_json_data() -> None:
    node = _node(
        {
            "operation": "append",
            "sheetId": "sheet-d1",
            "range": "A1",
        }
    )
    item = ExecutionItem(json={"data": [["p", "q", "r"]]})
    out = _out_items(await exec_google_sheets(node, [item], ctx=_ctx()))
    p = out[0].json
    assert p["updatedColumns"] == 3


@pytest.mark.asyncio
async def test_data_default_from_json_values() -> None:
    node = _node(
        {
            "operation": "update",
            "sheetId": "sheet-d2",
            "range": "A1",
        }
    )
    item = ExecutionItem(json={"values": [["a", "b"]]})
    out = _out_items(await exec_google_sheets(node, [item], ctx=_ctx()))
    p = out[0].json
    # Executor processes the $json.values data without skipping. In offline
    # mode the synthesized response stats (1, 3, 3) are emitted.
    assert p["source"] == "googleSheets"
    assert p["updatedRows"] == 1
    assert p["updatedColumns"] == 3
    assert p["updatedCells"] == 3


# ── 9. operation='append' reflected ───────────────────────────────────


@pytest.mark.asyncio
async def test_append_operation_reflected_in_source() -> None:
    node = _node(
        {
            "operation": "append",
            "sheetId": "sheet-a",
            "range": "A1",
            "data": [["v"]],
        }
    )
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out[0].json["source"] == "googleSheets"
    assert "updatedRange" in out[0].json
    assert "updatedRows" in out[0].json
    assert "updatedColumns" in out[0].json


# ── 10. Empty sheetId → no item ───────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_sheet_id_skips_item() -> None:
    node = _node(
        {
            "operation": "read",
            "sheetId": "",
            "range": "A1:B1",
        }
    )
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_sheet_id_when_only_in_json_skips_item() -> None:
    node = _node({"operation": "read", "range": "A1:B1"})
    item = ExecutionItem(json={"sheetId": "", "spreadsheetId": ""})
    out = _out_items(await exec_google_sheets(node, [item], ctx=_ctx()))
    assert out == []


# ── 11. Read empty values → single item with empty values list ───────


@pytest.mark.asyncio
async def test_read_with_empty_values_emits_one_item() -> None:
    node = _node(
        {
            "operation": "read",
            "sheetId": "sheet-empty",
            "range": "A1:Z1",
        }
    )
    ctx = _ctx({"sheets_response": {"range": "A1:Z1", "majorDimension": "ROWS", "values": []}})
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["values"] == []
    assert out[0].json["rowCount"] == 0


# ── 12. Unsupported operation raises ────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "delete", "sheetId": "x"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 13. dataMode honored ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_mode_object_is_accepted() -> None:
    node = _node(
        {
            "operation": "read",
            "sheetId": "x",
            "range": "A1",
            "dataMode": "object",
        }
    )
    out = _out_items(
        await exec_google_sheets(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out[0].json["dataMode"] == "object"


# ── 14. Descriptor registration ──────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.googleSheets" in REGISTRY
    assert "n8n-nodes-base.googleSheets" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.googleSheets"] == "output"
    desc = REGISTRY["n8n-nodes-base.googleSheets"]
    assert desc.executor.endswith(":exec_google_sheets")
    assert desc.category == "output"
    assert set(SHEETS_OPERATIONS) == {"read", "append", "update"}


# ── 15. End-to-end: Manual Trigger → googleSheets (read mock) → Set ───


def _doc(nodes, connections):
    return {"name": "gs-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_google_sheets_set_sees_range_and_values() -> None:
    """Manual Trigger → googleSheets (sheets_response mock) → Set pulls range/values."""
    mocks = {
        "sheets_response": {
            "range": "Sheet1!A1:B2",
            "majorDimension": "ROWS",
            "values": [
                ["name", "score"],
                ["alice", "42"],
            ],
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "g1",
                "Sheets",
                "n8n-nodes-base.googleSheets",
                {
                    "operation": "read",
                    "sheetId": "e2e-sheet",
                    "range": "Sheet1!A1:B2",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_range", "value": "={{ $json.range }}", "type": "string"},
                            {"name": "result_sheet", "value": "={{ $json.sheetId }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Sheets", "type": "main", "index": 0}]]},
            "Sheets": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    sheets_step = next(s for s in result.steps if s.node_name == "Sheets")
    assert sheets_step.status == "success", sheets_step.error
    assert sheets_step.output_count == 2
    first = sheets_step.sample_output[0]
    assert first["json"]["range"] == "Sheet1!A1:B2"
    assert first["json"]["values"] == ["name", "score"]

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_range") == "Sheet1!A1:B2"
    assert fjson.get("result_sheet") == "e2e-sheet"
    assert fjson.get("result_source") == "googleSheets"
