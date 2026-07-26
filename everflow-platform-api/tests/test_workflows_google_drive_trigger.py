"""Tests for the Google Drive Trigger node executor (``n8n-nodes-base.googleDriveTrigger``).

Covers:

- ``drive_changes`` dict mock → raw changes payload is used
- ``drive_changes`` callable mock receives ``(node, ctx)``
- ``drive_response`` mock fallback (treated as ``changes``)
- ``trigger_payload`` mock fallback
- Offline: synthetic 3-file changes list
- ``folderId`` default ``'root'`` (and only echoed for ``specificFolder``)
- ``event`` default ``'fileCreated'``
- ``fileTypes`` filter echoed into the emitted item
- ``triggerOn`` resolution + pass-through behavior
- End-to-end: Manual → googleDriveTrigger → Set sees ``fileName`` / ``changeType``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.google_drive_trigger import (
    DRIVE_TRIGGER_DEFAULT_EVENT,
    DRIVE_TRIGGER_DEFAULT_TRIGGER_ON,
    DRIVE_TRIGGER_EVENTS,
    DRIVE_TRIGGER_OFFLINE_COUNT,
    DRIVE_TRIGGER_ONS,
    exec_google_drive_trigger,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any] | None = None,
    *,
    id_: str = "gdt1",
    name: str = "DriveTrigger",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="n8n-nodes-base.googleDriveTrigger",
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
    return EngineContext(graph=g, mocks=mocks or {})  # type: ignore[arg-type]


def _out_items(result) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── 1. drive_changes dict mock ────────────────────────────────────────


@pytest.mark.asyncio
async def test_drive_changes_dict_mock_returns_changes_verbatim() -> None:
    payload = {
        "changes": [
            {
                "fileId": "alpha",
                "file": {
                    "id": "alpha",
                    "name": "alpha.txt",
                    "mimeType": "text/plain",
                    "modifiedTime": "2026-01-01T00:00:00Z",
                    "parents": ["root"],
                },
                "changeType": "file",
                "time": "2026-01-01T00:00:00Z",
            },
            {
                "fileId": "beta",
                "file": {
                    "id": "beta",
                    "name": "beta.txt",
                    "mimeType": "text/plain",
                    "modifiedTime": "2026-01-01T00:01:00Z",
                    "parents": ["root"],
                },
                "changeType": "file",
                "time": "2026-01-01T00:01:00Z",
            },
        ],
        "newStartPageToken": "tok_42",
        "kind": "drive#changeList",
    }
    node = _node()
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx({"drive_changes": payload})))

    assert len(out) == 2
    assert out[0].json["fileId"] == "alpha"
    assert out[0].json["fileName"] == "alpha.txt"
    assert out[0].json["mimeType"] == "text/plain"
    assert out[0].json["modifiedTime"] == "2026-01-01T00:00:00Z"
    assert out[0].json["parents"] == ["root"]
    assert out[0].json["newStartPageToken"] == "tok_42"
    assert out[0].json["source"] == "googleDriveTrigger"
    assert out[0].json["mockSource"] == "drive_changes"
    assert out[1].json["fileId"] == "beta"
    assert out[1].json["fileName"] == "beta.txt"


# ── 2. drive_changes callable mock receives (node, ctx) ───────────────


@pytest.mark.asyncio
async def test_drive_changes_callable_mock_receives_node_and_ctx() -> None:
    captured: dict[str, Any] = {}

    def producer(node, ctx):
        captured["node"] = node
        captured["ctx"] = ctx
        return {
            "changes": [
                {
                    "fileId": "from-callable",
                    "file": {
                        "id": "from-callable",
                        "name": "from-callable.txt",
                        "mimeType": "text/plain",
                        "modifiedTime": "2026-02-02T02:02:02Z",
                        "parents": ["root"],
                    },
                    "changeType": "file",
                    "time": "2026-02-02T02:02:02Z",
                }
            ],
            "newStartPageToken": "tok_callable",
            "kind": "drive#changeList",
        }

    node = _node(params={"event": "fileUpdated"})
    ctx = _ctx({"drive_changes": producer})

    out = _out_items(await exec_google_drive_trigger(node, [], ctx=ctx))

    assert captured["node"] is node
    assert captured["ctx"] is ctx
    assert len(out) == 1
    assert out[0].json["fileId"] == "from-callable"
    assert out[0].json["event"] == "fileUpdated"
    assert out[0].json["mockSource"] == "drive_changes"


# ── 3. drive_response mock fallback (treated as changes) ──────────────


@pytest.mark.asyncio
async def test_drive_response_mock_fallback_with_files_list() -> None:
    payload = {
        "files": [
            {"id": "fa", "name": "fa.txt", "mimeType": "text/plain"},
            {"id": "fb", "name": "fb.txt", "mimeType": "text/plain"},
        ],
        "nextPageToken": None,
    }
    node = _node()
    out = _out_items(
        await exec_google_drive_trigger(node, [], ctx=_ctx({"drive_response": payload}))
    )

    assert len(out) == 2
    assert out[0].json["fileId"] == "fa"
    assert out[0].json["fileName"] == "fa.txt"
    assert out[0].json["mimeType"] == "text/plain"
    assert out[0].json["mockSource"] == "drive_response"


@pytest.mark.asyncio
async def test_drive_response_mock_fallback_with_single_change_shape() -> None:
    payload = {
        "id": "only-one",
        "file": {
            "id": "only-one",
            "name": "only-one.txt",
            "mimeType": "text/plain",
            "parents": ["root"],
        },
    }
    node = _node()
    out = _out_items(
        await exec_google_drive_trigger(node, [], ctx=_ctx({"drive_response": payload}))
    )
    assert len(out) == 1
    assert out[0].json["fileId"] == "only-one"
    assert out[0].json["mockSource"] == "drive_response"


# ── 4. trigger_payload mock fallback ──────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_payload_mock_fallback_emits_items() -> None:
    payload = {
        "changes": [
            {
                "fileId": "tp1",
                "file": {
                    "id": "tp1",
                    "name": "tp1.txt",
                    "mimeType": "text/plain",
                    "parents": ["root"],
                },
                "changeType": "file",
            }
        ],
        "newStartPageToken": "tok_tp",
    }
    node = _node()
    out = _out_items(
        await exec_google_drive_trigger(node, [], ctx=_ctx({"trigger_payload": payload}))
    )
    assert len(out) == 1
    assert out[0].json["fileId"] == "tp1"
    assert out[0].json["fileName"] == "tp1.txt"
    assert out[0].json["mockSource"] == "trigger_payload"


# ── 5. Offline synthetic changes ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthesizes_three_file_changes() -> None:
    node = _node()
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))

    assert len(out) == DRIVE_TRIGGER_OFFLINE_COUNT
    assert [o.json["fileId"] for o in out] == [
        "mock_file_1",
        "mock_file_2",
        "mock_file_3",
    ]
    for o in out:
        assert o.json["fileName"] == f"{o.json['fileId']}.txt"
        assert o.json["mimeType"] == "text/plain"
        assert o.json["parents"] == ["root"]
        assert o.json["changeType"] == "file"
        assert o.json["modifiedTime"]
        assert o.json["source"] == "googleDriveTrigger"
    # mockSource is NOT echoed when offline (so downstream can tell it's
    # the synthetic path)
    assert "mockSource" not in out[0].json


# ── 6. folderId default 'root' ───────────────────────────────────────


@pytest.mark.asyncio
async def test_folder_id_default_root_for_specific_folder() -> None:
    node = _node(params={"triggerOn": "specificFolder"})
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))

    assert len(out) == DRIVE_TRIGGER_OFFLINE_COUNT
    for o in out:
        assert o.json["folderId"] == "root"


@pytest.mark.asyncio
async def test_folder_id_explicit_value_for_specific_folder() -> None:
    node = _node(
        params={"triggerOn": "specificFolder", "folderId": "my-folder-xyz"}
    )
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))
    for o in out:
        assert o.json["folderId"] == "my-folder-xyz"


@pytest.mark.asyncio
async def test_folder_id_not_echoed_for_watch_all() -> None:
    node = _node(params={"triggerOn": "watchAll"})
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))
    for o in out:
        assert "folderId" not in o.json


# ── 7. event default 'fileCreated' ───────────────────────────────────


@pytest.mark.asyncio
async def test_event_default_file_created() -> None:
    node = _node()
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))

    assert out[0].json["event"] == "fileCreated"
    assert out[0].json["changeType"] == "file"  # raw Drive changeType wins


@pytest.mark.asyncio
async def test_event_explicit_value_is_echoed() -> None:
    node = _node(params={"event": "fileDeleted"})
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))
    for o in out:
        assert o.json["event"] == "fileDeleted"


def test_default_event_is_file_created() -> None:
    assert DRIVE_TRIGGER_DEFAULT_EVENT == "fileCreated"
    assert DRIVE_TRIGGER_DEFAULT_TRIGGER_ON == "watchAll"
    assert set(DRIVE_TRIGGER_ONS) == {
        "specificFolder",
        "watchAll",
        "fileCreated",
        "fileUpdated",
    }
    assert set(DRIVE_TRIGGER_EVENTS) == {
        "fileCreated",
        "fileUpdated",
        "fileDeleted",
        "fileShared",
    }


# ── 8. fileTypes filter echoed ───────────────────────────────────────


@pytest.mark.asyncio
async def test_file_types_list_is_echoed_on_items() -> None:
    node = _node(
        params={
            "triggerOn": "specificFolder",
            "folderId": "root",
            "fileTypes": ["text/plain", "application/json"],
        }
    )
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))

    assert len(out) == DRIVE_TRIGGER_OFFLINE_COUNT
    for o in out:
        assert o.json["fileTypes"] == ["text/plain", "application/json"]


@pytest.mark.asyncio
async def test_file_types_not_echoed_when_not_set() -> None:
    node = _node()
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))
    for o in out:
        assert "fileTypes" not in o.json


@pytest.mark.asyncio
async def test_file_types_passed_to_callable_mock() -> None:
    captured: dict[str, Any] = {}

    def producer(node, ctx):
        captured["fileTypes"] = (ctx.mocks or {}).get("__file_types_marker__")
        return {
            "changes": [
                {
                    "fileId": "x",
                    "file": {
                        "id": "x",
                        "name": "x.txt",
                        "mimeType": "text/plain",
                        "parents": ["root"],
                    },
                }
            ]
        }

    node = _node(params={"fileTypes": ["text/plain"]})
    out = _out_items(
        await exec_google_drive_trigger(
            node,
            [],
            ctx=_ctx({"drive_changes": producer, "__file_types_marker__": ["text/plain"]}),
        )
    )
    assert captured["fileTypes"] == ["text/plain"]
    # And the echo lands on the item
    assert out[0].json["fileTypes"] == ["text/plain"]


# ── 9. Pass-through when items list is non-empty ──────────────────────


@pytest.mark.asyncio
async def test_upstream_items_pass_through_with_trigger_context() -> None:
    node = _node()
    in_items = [ExecutionItem(json={"foo": 1, "fileName": "kept-name"})]
    out = _out_items(
        await exec_google_drive_trigger(node, in_items, ctx=_ctx())
    )

    assert len(out) == 1
    item = out[0].json
    assert item["foo"] == 1
    # upstream value wins on conflict
    assert item["fileName"] == "kept-name"
    # other trigger context added
    assert item["event"] == "fileCreated"
    assert item["triggerOn"] == "watchAll"
    assert item["source"] == "googleDriveTrigger"


# ── 10. triggerOn resolution ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_on_explicit_value_reflected_on_items() -> None:
    node = _node(params={"triggerOn": "fileCreated"})
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))
    for o in out:
        assert o.json["triggerOn"] == "fileCreated"


# ── 11. pollTimes echoed ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_times_echoed_when_dict() -> None:
    node = _node(params={"pollTimes": {"item": [{"mode": "everyMinute"}]}})
    out = _out_items(await exec_google_drive_trigger(node, [], ctx=_ctx()))
    for o in out:
        assert o.json["pollTimes"] == {"item": [{"mode": "everyMinute"}]}


# ── 12. Empty changes still emits one item ───────────────────────────


@pytest.mark.asyncio
async def test_empty_changes_payload_still_emits_one_item() -> None:
    node = _node()
    out = _out_items(
        await exec_google_drive_trigger(
            node, [], ctx=_ctx({"drive_changes": {"changes": []}})
        )
    )
    assert len(out) == 1
    assert out[0].json["source"] == "googleDriveTrigger"
    assert out[0].json["fileId"] == ""


# ── 13. Descriptor registration ──────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.googleDriveTrigger" in REGISTRY
    assert "n8n-nodes-base.googleDriveTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.googleDriveTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.googleDriveTrigger"]
    assert desc.executor.endswith(":exec_google_drive_trigger")
    assert desc.category == "trigger"


# ── 14. End-to-end: Manual → googleDriveTrigger → Set sees fileName/changeType


def _doc(nodes, connections):
    return {"name": "drive-trigger-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_drive_trigger_to_set_sees_file_name_and_change_type() -> None:
    """Manual → googleDriveTrigger (drive_changes mock) → Set sees the change fields."""
    mocks = {
        "drive_changes": {
            "changes": [
                {
                    "fileId": "f1",
                    "file": {
                        "id": "f1",
                        "name": "first.txt",
                        "mimeType": "text/plain",
                        "modifiedTime": "2026-03-03T03:03:03Z",
                        "parents": ["root"],
                    },
                    "changeType": "file",
                    "time": "2026-03-03T03:03:03Z",
                },
                {
                    "fileId": "f2",
                    "file": {
                        "id": "f2",
                        "name": "second.txt",
                        "mimeType": "text/plain",
                        "modifiedTime": "2026-03-03T03:03:04Z",
                        "parents": ["root"],
                    },
                    "changeType": "file",
                    "time": "2026-03-03T03:03:04Z",
                },
            ],
            "newStartPageToken": "tok_e2e",
            "kind": "drive#changeList",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "g1",
                "DriveTrigger",
                "n8n-nodes-base.googleDriveTrigger",
                {"event": "fileCreated", "triggerOn": "watchAll"},
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_fileName", "value": "={{ $json.fileName }}", "type": "string"},
                            {"name": "result_changeType", "value": "={{ $json.changeType }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "DriveTrigger", "type": "main", "index": 0}]]},
            "DriveTrigger": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message

    trigger_step = next(s for s in result.steps if s.node_name == "DriveTrigger")
    assert trigger_step.status == "success", trigger_step.error
    assert trigger_step.output_count == 2

    final = result.final_items
    assert final, "expected at least one final item"
    names = [f.get("json", {}).get("result_fileName") for f in final]
    change_types = [f.get("json", {}).get("result_changeType") for f in final]
    sources = [f.get("json", {}).get("result_source") for f in final]
    assert names == ["first.txt", "second.txt"]
    assert change_types == ["file", "file"]
    assert sources == ["googleDriveTrigger", "googleDriveTrigger"]
