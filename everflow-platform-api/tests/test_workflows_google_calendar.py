"""Tests for the Google Calendar node executor (``n8n-nodes-base.googleCalendar``).

Covers:

- ``calendar_response`` dict mock → envelope used per operation
- ``calendar_response`` callable mock receives ``(operation, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline create: eventId present, summary echoed
- Offline list: returns up to 3 events
- Offline get: eventId echoed
- Offline delete: success=True
- ``operation='create'`` reflected
- ``calendarId`` default 'primary'
- ``eventId`` default from ``$json``
- ``maxResults`` honored
- Empty ``calendarId`` → no item emitted
- End-to-end: Manual Trigger → googleCalendar (list mock) → Set sees events
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.google_calendar import (
    CALENDAR_DEFAULT_CALENDAR_ID,
    CALENDAR_DEFAULT_OPERATION,
    CALENDAR_OFFLINE_MAX_EVENTS,
    CALENDAR_OPERATIONS,
    exec_google_calendar,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.googleCalendar",
    id_: str = "gc1",
    name: str = "Google Calendar",
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


# ── 1. calendar_response dict mock (create) ───────────────────────────


@pytest.mark.asyncio
async def test_calendar_response_dict_mock_create_used_verbatim() -> None:
    node = _node(
        {
            "operation": "create",
            "calendarId": "primary",
            "summary": "Team Sync",
            "start": "2025-01-15T10:00:00Z",
            "end": "2025-01-15T11:00:00Z",
        }
    )
    ctx = _ctx(
        {
            "calendar_response": {
                "id": "cal-event-001",
                "summary": "Team Sync",
                "start": {"dateTime": "2025-01-15T10:00:00Z", "timeZone": "UTC"},
                "end": {"dateTime": "2025-01-15T11:00:00Z", "timeZone": "UTC"},
                "htmlLink": "https://calendar.google.com/event?eid=cal-event-001",
            }
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    p = out[0].json
    assert p["eventId"] == "cal-event-001"
    assert p["summary"] == "Team Sync"
    assert p["start"]["dateTime"] == "2025-01-15T10:00:00Z"
    assert p["end"]["dateTime"] == "2025-01-15T11:00:00Z"
    assert p["htmlLink"] == "https://calendar.google.com/event?eid=cal-event-001"
    assert p["source"] == "googleCalendar"
    assert p["operation"] == "create"
    assert p["calendarId"] == "primary"


# ── 2. calendar_response callable mock signature ──────────────────────


@pytest.mark.asyncio
async def test_calendar_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, params, item, ctx):
        captured["operation"] = operation
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "mock-evt-1",
            "summary": "Mock",
            "start": {"dateTime": "2025-01-15T10:00:00Z", "timeZone": "UTC"},
            "end": {"dateTime": "2025-01-15T11:00:00Z", "timeZone": "UTC"},
            "htmlLink": "https://calendar.google.com/event?eid=mock-evt-1",
        }

    node = _node(
        {
            "operation": "create",
            "calendarId": "primary",
            "summary": "S",
            "start": "2025-01-15T10:00:00Z",
            "end": "2025-01-15T11:00:00Z",
            "extra": "keep",
        }
    )
    ctx = _ctx({"calendar_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_google_calendar(node, [item], ctx=ctx))

    assert captured["operation"] == "create"
    assert captured["params"]["extra"] == "keep"
    assert captured["params"]["summary"] == "S"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["eventId"] == "mock-evt-1"


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "list",
            "calendarId": "primary",
            "maxResults": 5,
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "items": [
                        {
                            "id": "http-evt-1",
                            "summary": "From HTTP",
                            "start": {"dateTime": "2025-01-15T10:00:00Z", "timeZone": "UTC"},
                            "end": {"dateTime": "2025-01-15T11:00:00Z", "timeZone": "UTC"},
                        }
                    ],
                    "nextPageToken": None,
                },
            }
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["eventId"] == "http-evt-1"
    assert out[0].json["summary"] == "From HTTP"
    assert out[0].json["mockSource"] == "http_response"
    assert out[0].json["source"] == "googleCalendar"


# ── 4. Offline synthetic response — create ────────────────────────────


@pytest.mark.asyncio
async def test_offline_create_returns_event_id_and_summary() -> None:
    node = _node(
        {
            "operation": "create",
            "calendarId": "primary",
            "summary": "Standup",
            "start": "2025-02-01T09:00:00Z",
            "end": "2025-02-01T09:30:00Z",
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["eventId"].startswith("mock_event_")
    assert p["summary"] == "Standup"
    assert p["start"]["dateTime"] == "2025-02-01T09:00:00Z"
    assert p["end"]["dateTime"] == "2025-02-01T09:30:00Z"
    assert p["htmlLink"].startswith("https://calendar.google.com/event?eid=")
    assert p["source"] == "googleCalendar"
    assert p["mockSource"] == "offline"
    assert p["ok"] is True


# ── 5. Offline synthetic response — list ──────────────────────────────


@pytest.mark.asyncio
async def test_offline_list_returns_up_to_three_events() -> None:
    node = _node({"operation": "list", "calendarId": "primary"})
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    # offline cap is min(maxResults=10, CALENDAR_OFFLINE_MAX_EVENTS=3) = 3
    assert len(out) == CALENDAR_OFFLINE_MAX_EVENTS
    for o in out:
        assert o.json["source"] == "googleCalendar"
        assert o.json["eventId"].startswith("mock_event_")
        assert o.json["summary"].startswith("Mock Event")
        assert o.json["htmlLink"].startswith("https://calendar.google.com/event?eid=")
        assert o.json["mockSource"] == "offline"
        assert o.json["calendarId"] == "primary"


# ── 6. Offline synthetic response — get ───────────────────────────────


@pytest.mark.asyncio
async def test_offline_get_returns_event_with_id() -> None:
    node = _node(
        {
            "operation": "get",
            "calendarId": "primary",
            "eventId": "specific-evt-42",
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["eventId"] == "specific-evt-42"
    assert p["summary"] == "Mock Event"
    assert p["start"]["timeZone"] == "UTC"
    assert p["end"]["timeZone"] == "UTC"
    assert p["source"] == "googleCalendar"
    assert p["mockSource"] == "offline"


# ── 7. Offline synthetic response — delete ────────────────────────────


@pytest.mark.asyncio
async def test_offline_delete_returns_success() -> None:
    node = _node(
        {
            "operation": "delete",
            "calendarId": "primary",
            "eventId": "del-evt-9",
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["success"] is True
    assert p["eventId"] == "del-evt-9"
    assert p["deletedAt"].endswith("Z")
    assert p["source"] == "googleCalendar"
    assert p["mockSource"] == "offline"
    assert p["ok"] is True


# ── 8. operation='create' reflected ───────────────────────────────────


@pytest.mark.asyncio
async def test_create_operation_reflected_in_source() -> None:
    node = _node(
        {
            "operation": "create",
            "calendarId": "primary",
            "summary": "X",
            "start": "2025-01-15T10:00:00Z",
            "end": "2025-01-15T11:00:00Z",
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out[0].json["source"] == "googleCalendar"
    assert out[0].json["operation"] == "create"
    assert "eventId" in out[0].json
    assert "summary" in out[0].json


# ── 9. calendarId default 'primary' ───────────────────────────────────


@pytest.mark.asyncio
async def test_calendar_id_default_is_primary() -> None:
    node = _node(
        {
            "operation": "list",
            "maxResults": 1,
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out[0].json["calendarId"] == CALENDAR_DEFAULT_CALENDAR_ID
    assert CALENDAR_DEFAULT_CALENDAR_ID == "primary"


@pytest.mark.asyncio
async def test_calendar_id_default_from_json() -> None:
    node = _node({"operation": "list", "maxResults": 1})
    item = ExecutionItem(json={"calendarId": "team-cal@group.calendar.google.com"})
    out = _out_items(await exec_google_calendar(node, [item], ctx=_ctx()))
    assert out[0].json["calendarId"] == "team-cal@group.calendar.google.com"


# ── 10. eventId default from $json ────────────────────────────────────


@pytest.mark.asyncio
async def test_event_id_default_from_json() -> None:
    node = _node({"operation": "get", "calendarId": "primary"})
    item = ExecutionItem(json={"eventId": "from-json-evt-1"})
    out = _out_items(await exec_google_calendar(node, [item], ctx=_ctx()))
    assert out[0].json["eventId"] == "from-json-evt-1"


@pytest.mark.asyncio
async def test_event_id_falls_back_to_id_key() -> None:
    node = _node({"operation": "delete", "calendarId": "primary"})
    item = ExecutionItem(json={"id": "id-key-evt-7"})
    out = _out_items(await exec_google_calendar(node, [item], ctx=_ctx()))
    assert out[0].json["eventId"] == "id-key-evt-7"


# ── 11. maxResults honored ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_results_honored_with_caps() -> None:
    node = _node(
        {
            "operation": "list",
            "calendarId": "primary",
            "maxResults": 100,
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    # offline caps at CALENDAR_OFFLINE_MAX_EVENTS (3)
    assert len(out) == CALENDAR_OFFLINE_MAX_EVENTS


@pytest.mark.asyncio
async def test_max_results_two() -> None:
    node = _node(
        {
            "operation": "list",
            "calendarId": "primary",
            "maxResults": 2,
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 2


@pytest.mark.asyncio
async def test_max_results_one_via_mock() -> None:
    node = _node(
        {
            "operation": "list",
            "calendarId": "primary",
            "maxResults": 1,
        }
    )
    ctx = _ctx(
        {
            "calendar_response": {
                "items": [
                    {
                        "id": "mock-1",
                        "summary": "S1",
                        "start": {"dateTime": "2025-01-15T10:00:00Z", "timeZone": "UTC"},
                        "end": {"dateTime": "2025-01-15T11:00:00Z", "timeZone": "UTC"},
                    },
                    {
                        "id": "mock-2",
                        "summary": "S2",
                        "start": {"dateTime": "2025-01-16T10:00:00Z", "timeZone": "UTC"},
                        "end": {"dateTime": "2025-01-16T11:00:00Z", "timeZone": "UTC"},
                    },
                ]
            }
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["eventId"] == "mock-1"


# ── 12. Empty calendarId → no item ────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_calendar_id_skips_item() -> None:
    node = _node(
        {
            "operation": "list",
            "calendarId": "",
            "maxResults": 1,
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_calendar_id_when_only_in_json_skips_item() -> None:
    node = _node({"operation": "list", "maxResults": 1})
    item = ExecutionItem(json={"calendarId": "", "calendar_id": ""})
    out = _out_items(await exec_google_calendar(node, [item], ctx=_ctx()))
    assert out == []


# ── 13. Empty eventId for get/delete → no item ───────────────────────


@pytest.mark.asyncio
async def test_empty_event_id_for_get_skips_item() -> None:
    node = _node({"operation": "get", "calendarId": "primary"})
    item = ExecutionItem(json={"eventId": "", "id": ""})
    out = _out_items(await exec_google_calendar(node, [item], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_event_id_for_delete_skips_item() -> None:
    node = _node({"operation": "delete", "calendarId": "primary"})
    item = ExecutionItem(json={"eventId": "", "id": ""})
    out = _out_items(await exec_google_calendar(node, [item], ctx=_ctx()))
    assert out == []


# ── 14. Default operation is 'list' ──────────────────────────────────


@pytest.mark.asyncio
async def test_default_operation_is_list() -> None:
    assert CALENDAR_DEFAULT_OPERATION == "list"
    node = _node({"calendarId": "primary", "maxResults": 1})
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out[0].json["operation"] == "list"
    assert "eventId" in out[0].json


# ── 15. dataMode='object' emits single item with items[] ──────────────


@pytest.mark.asyncio
async def test_list_data_mode_object_emits_single_item() -> None:
    node = _node(
        {
            "operation": "list",
            "calendarId": "primary",
            "dataMode": "object",
            "maxResults": 5,
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["items"], list)
    assert len(p["items"]) == CALENDAR_OFFLINE_MAX_EVENTS
    assert p["source"] == "googleCalendar"


# ── 16. description / location / attendees honored on create ──────────


@pytest.mark.asyncio
async def test_create_includes_optional_fields() -> None:
    node = _node(
        {
            "operation": "create",
            "calendarId": "primary",
            "summary": "Review",
            "start": "2025-03-01T10:00:00Z",
            "end": "2025-03-01T11:00:00Z",
            "description": "Quarterly review",
            "location": "Room A",
            "attendees": ["a@example.com", "b@example.com"],
        }
    )
    out = _out_items(
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["description"] == "Quarterly review"
    assert p["location"] == "Room A"
    assert p["attendees"] == [
        {"email": "a@example.com"},
        {"email": "b@example.com"},
    ]


# ── 17. Descriptor registration ──────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.googleCalendar" in REGISTRY
    assert "n8n-nodes-base.googleCalendar" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.googleCalendar"] == "output"
    desc = REGISTRY["n8n-nodes-base.googleCalendar"]
    assert desc.executor.endswith(":exec_google_calendar")
    assert desc.category == "output"
    assert set(CALENDAR_OPERATIONS) == {"create", "list", "get", "delete"}


# ── 18. Unsupported operation raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "patch", "calendarId": "primary"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_google_calendar(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 19. End-to-end: Manual Trigger → googleCalendar (list mock) → Set ─


def _doc(nodes, connections):
    return {"name": "gc-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_google_calendar_set_sees_events() -> None:
    """Manual Trigger → googleCalendar (calendar_response mock) → Set pulls events."""
    mocks = {
        "calendar_response": {
            "items": [
                {
                    "id": "e2e-evt-1",
                    "summary": "E2E Event 1",
                    "start": {"dateTime": "2025-04-01T10:00:00Z", "timeZone": "UTC"},
                    "end": {"dateTime": "2025-04-01T11:00:00Z", "timeZone": "UTC"},
                    "htmlLink": "https://calendar.google.com/event?eid=e2e-evt-1",
                },
                {
                    "id": "e2e-evt-2",
                    "summary": "E2E Event 2",
                    "start": {"dateTime": "2025-04-02T10:00:00Z", "timeZone": "UTC"},
                    "end": {"dateTime": "2025-04-02T11:00:00Z", "timeZone": "UTC"},
                    "htmlLink": "https://calendar.google.com/event?eid=e2e-evt-2",
                },
            ]
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "gc1",
                "Calendar",
                "n8n-nodes-base.googleCalendar",
                {
                    "operation": "list",
                    "calendarId": "primary",
                    "maxResults": 5,
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_event_id", "value": "={{ $json.eventId }}", "type": "string"},
                            {"name": "result_summary", "value": "={{ $json.summary }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                            {"name": "result_calendar", "value": "={{ $json.calendarId }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Calendar", "type": "main", "index": 0}]]},
            "Calendar": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    cal_step = next(s for s in result.steps if s.node_name == "Calendar")
    assert cal_step.status == "success", cal_step.error
    assert cal_step.output_count == 2
    first = cal_step.sample_output[0]
    assert first["json"]["eventId"] == "e2e-evt-1"
    assert first["json"]["summary"] == "E2E Event 1"
    assert first["json"]["source"] == "googleCalendar"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_event_id") == "e2e-evt-1"
    assert fjson.get("result_summary") == "E2E Event 1"
    assert fjson.get("result_source") == "googleCalendar"
    assert fjson.get("result_calendar") == "primary"
