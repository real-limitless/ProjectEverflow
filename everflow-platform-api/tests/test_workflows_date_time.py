"""Tests for the DateTime node executor (n8n-nodes-base.dateTime)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import exec_date_time


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="d1",
        name="DateTime",
        type="n8n-nodes-base.dateTime",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(*, now: datetime | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.trigger_nodes = lambda preferred=None: []  # type: ignore
    return EngineContext(graph=g, now=now or datetime(2026, 7, 25, tzinfo=timezone.utc))  # type: ignore[arg-type]


def _doc(nodes, connections):
    return {"name": "datetime-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


def _result_items(result):
    """Pull the .json dicts from an exec result."""
    out = []
    for _idx, items in result:
        for it in items:
            out.append(it.json)
    return out


# ── format ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_format_with_strftime_and_fixed_now() -> None:
    items = []
    node = _node({"action": "format", "value": "={{ $now }}", "format": "%Y-%m-%d"})
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out) == [{"date": "2026-07-25"}]


@pytest.mark.asyncio
async def test_format_value_from_json_field() -> None:
    items = [ExecutionItem(json={"created_at": "2026-01-15T08:30:00+00:00"})]
    node = _node({
        "action": "format",
        "value": "={{ $json.created_at }}",
        "format": "%Y/%m/%d %H:%M",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out) == [{"date": "2026/01/15 08:30", "created_at": "2026-01-15T08:30:00+00:00"}]


@pytest.mark.asyncio
async def test_format_with_custom_output_field() -> None:
    items = []
    node = _node({
        "action": "format",
        "value": "={{ $now }}",
        "format": "%d-%b-%Y",
        "outputFieldName": "pretty",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out) == [{"pretty": "25-Jul-2026"}]


@pytest.mark.asyncio
async def test_format_with_tz_offset() -> None:
    items = [ExecutionItem(json={"iso": "2026-07-25T12:00:00+00:00"})]
    node = _node({
        "action": "format",
        "value": "={{ $json.iso }}",
        "format": "%H:%M %Z",
        "tz": "+02:00",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]["date"]
    # 12:00 UTC → 14:00 in +02:00
    assert rendered.startswith("14:00")


@pytest.mark.asyncio
async def test_format_with_unknown_tz_falls_back_silently() -> None:
    items = []
    node = _node({
        "action": "format",
        "value": "={{ $now }}",
        "format": "%Y-%m-%d",
        "tz": "Mars/Olympus_Mons",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out) == [{"date": "2026-07-25"}]


# ── parse ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_from_strftime() -> None:
    items = [ExecutionItem(json={"stamp": "2026-07-25 14:00"})]
    node = _node({
        "action": "parse",
        "value": "={{ $json.stamp }}",
        "format": "%Y-%m-%d %H:%M",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]["date"]
    # Result is an ISO 8601 string; parsed value should round-trip.
    assert rendered.startswith("2026-07-25T14:00:00")


@pytest.mark.asyncio
async def test_parse_with_tz_returns_localized_iso() -> None:
    items = [ExecutionItem(json={"stamp": "2026-07-25 14:00"})]
    node = _node({
        "action": "parse",
        "value": "={{ $json.stamp }}",
        "format": "%Y-%m-%d %H:%M",
        "tz": "+02:00",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]["date"]
    # 14:00 in +02:00 is 12:00 UTC → ISO string carries +02:00
    assert rendered.startswith("2026-07-25T14:00:00+02:00")


# ── addToDate / subtractFromDate ──────────────────────────────────────


@pytest.mark.asyncio
async def test_add_one_day_from_fixed_date() -> None:
    items = [ExecutionItem(json={"when": "2026-01-15T08:00:00+00:00"})]
    node = _node({
        "action": "addToDate",
        "value": "={{ $json.when }}",
        "duration": 1,
        "timeUnit": "days",
        "outputFieldName": "next",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out)[0]["next"].startswith("2026-01-16T08:00:00")


@pytest.mark.asyncio
async def test_subtract_two_hours() -> None:
    items = [ExecutionItem(json={"when": "2026-07-25T12:00:00+00:00"})]
    node = _node({
        "action": "subtractFromDate",
        "value": "={{ $json.when }}",
        "duration": 2,
        "timeUnit": "hours",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out)[0]["date"].startswith("2026-07-25T10:00:00")


@pytest.mark.asyncio
async def test_add_weeks_and_months_and_years() -> None:
    items = [ExecutionItem(json={"base": "2026-01-15T00:00:00+00:00"})]
    # months
    node_m = _node({
        "action": "addToDate",
        "value": "={{ $json.base }}",
        "duration": 2,
        "timeUnit": "months",
    })
    out_m = await exec_date_time(node_m, items, ctx=_ctx())
    assert _result_items(out_m)[0]["date"].startswith("2026-03-15T00:00:00")
    # years
    node_y = _node({
        "action": "addToDate",
        "value": "={{ $json.base }}",
        "duration": 1,
        "timeUnit": "years",
    })
    out_y = await exec_date_time(node_y, items, ctx=_ctx())
    assert _result_items(out_y)[0]["date"].startswith("2027-01-15T00:00:00")
    # weeks
    node_w = _node({
        "action": "addToDate",
        "value": "={{ $json.base }}",
        "duration": 3,
        "timeUnit": "weeks",
    })
    out_w = await exec_date_time(node_w, items, ctx=_ctx())
    assert _result_items(out_w)[0]["date"].startswith("2026-02-05T00:00:00")


@pytest.mark.asyncio
async def test_add_months_clamps_to_month_end() -> None:
    items = [ExecutionItem(json={"base": "2026-01-31T00:00:00+00:00"})]
    node = _node({
        "action": "addToDate",
        "value": "={{ $json.base }}",
        "duration": 1,
        "timeUnit": "months",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    # Jan 31 + 1 month → Feb 28 (non-leap year)
    assert _result_items(out)[0]["date"].startswith("2026-02-28T00:00:00")


# ── toIso ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_to_iso_on_fixed_now() -> None:
    items = []
    node = _node({"action": "toIso"})
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out) == [{"date": "2026-07-25T00:00:00+00:00"}]


@pytest.mark.asyncio
async def test_to_iso_with_value_from_json() -> None:
    items = [ExecutionItem(json={"when": "2026-03-10T15:30:00+00:00"})]
    node = _node({
        "action": "toIso",
        "value": "={{ $json.when }}",
        "outputFieldName": "iso",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out)[0]["iso"] == "2026-03-10T15:30:00+00:00"


# ── toUnix / fromUnix ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_to_unix_from_iso_string() -> None:
    items = [ExecutionItem(json={"when": "2026-01-01T00:00:00+00:00"})]
    node = _node({
        "action": "toUnix",
        "value": "={{ $json.when }}",
        "outputFieldName": "ts",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    # 2026-01-01T00:00:00Z = 1767225600
    assert _result_items(out)[0]["ts"] == 1767225600


@pytest.mark.asyncio
async def test_from_unix_seconds() -> None:
    items = [ExecutionItem(json={"ts": 1767225600})]
    node = _node({
        "action": "fromUnix",
        "value": "={{ $json.ts }}",
        "outputFieldName": "iso",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out)[0]["iso"] == "2026-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_unix_roundtrip() -> None:
    items = [ExecutionItem(json={"iso": "2026-07-25T12:34:56+00:00"})]
    to_unix = _node({
        "action": "toUnix",
        "value": "={{ $json.iso }}",
        "outputFieldName": "ts",
    })
    out1 = await exec_date_time(to_unix, items, ctx=_ctx())
    ts = out1[0][1][0].json["ts"]

    items2 = [ExecutionItem(json={"ts": ts})]
    from_unix = _node({
        "action": "fromUnix",
        "value": "={{ $json.ts }}",
        "outputFieldName": "iso",
    })
    out2 = await exec_date_time(from_unix, items2, ctx=_ctx())
    assert out2[0][1][0].json["iso"] == "2026-07-25T12:34:56+00:00"


# ── Edge cases ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_output_field_name_does_not_mutate_item() -> None:
    items = [ExecutionItem(json={"x": 1})]
    node = _node({
        "action": "format",
        "value": "={{ $now }}",
        "format": "%Y",
        "outputFieldName": "",
    })
    out = await exec_date_time(node, items, ctx=_ctx())
    assert _result_items(out) == [{"x": 1}]


@pytest.mark.asyncio
async def test_unknown_action_raises() -> None:
    items = [ExecutionItem(json={})]
    node = _node({"action": "reformat", "format": "%Y"})
    with pytest.raises(ValueError, match="unsupported action"):
        await exec_date_time(node, items, ctx=_ctx())


@pytest.mark.asyncio
async def test_parse_requires_format() -> None:
    items = [ExecutionItem(json={"x": "2026-01-01"})]
    node = _node({"action": "parse", "value": "={{ $json.x }}"})
    with pytest.raises(ValueError, match="requires parameters.format"):
        await exec_date_time(node, items, ctx=_ctx())


@pytest.mark.asyncio
async def test_invalid_value_for_to_iso_raises() -> None:
    items = [ExecutionItem(json={"x": [1, 2, 3]})]
    node = _node({"action": "toIso", "value": "={{ $json.x }}"})
    with pytest.raises(ValueError):
        await exec_date_time(node, items, ctx=_ctx())


# ── Descriptor & end-to-end ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.dateTime" in REGISTRY
    assert "n8n-nodes-base.dateTime" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.dateTime"] == "transform"
    desc = REGISTRY["n8n-nodes-base.dateTime"]
    assert desc.executor.endswith(":exec_date_time")


@pytest.mark.asyncio
async def test_end_to_end_manual_trigger_datetime_set() -> None:
    """Manual (with pin data) → dateTime → Set sees formatted string."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("p1", "Produce", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "iso", "value": "2026-07-25T12:00:00+00:00", "type": "string"},
                ]}
            }),
            _n("d1", "DateTime", "n8n-nodes-base.dateTime", {
                "action": "format",
                "value": "={{ $json.iso }}",
                "format": "%Y-%m-%d",
                "outputFieldName": "date",
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "saw_date", "value": "={{ $json.date }}", "type": "string"},
                    {"name": "kept_iso", "value": "={{ $json.iso }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Produce", "type": "main", "index": 0}]]},
            "Produce": {"main": [[{"node": "DateTime", "type": "main", "index": 0}]]},
            "DateTime": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    dt_step = next(s for s in result.steps if s.node_name == "DateTime")
    assert dt_step.status == "success"
    assert dt_step.output_count == 1

    downstream_step = next(s for s in result.steps if s.node_name == "Downstream")
    assert downstream_step.input_count == 1
    assert downstream_step.output_count == 1

    final = result.final_items
    assert final, "expected at least one final item"
    final_json = final[0].get("json") if isinstance(final[0], dict) else None
    assert final_json is not None
    assert final_json.get("saw_date") == "2026-07-25"
    assert final_json.get("kept_iso") == "2026-07-25T12:00:00+00:00"


@pytest.mark.asyncio
async def test_end_to_end_pin_data_format_to_unix() -> None:
    """Manual with pin data → dateTime (toUnix) → Set sees integer seconds."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("d1", "DateTime", "n8n-nodes-base.dateTime", {
                "action": "toUnix",
                "value": "={{ $json.iso }}",
                "outputFieldName": "ts",
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "saw_ts", "value": "={{ $json.ts }}", "type": "number"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "DateTime", "type": "main", "index": 0}]]},
            "DateTime": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(
        trigger="manual",
        pin_data={"Start": [{"iso": "2026-01-01T00:00:00+00:00"}]},
    )
    assert result.status == "success", result.error_message
    final_json = result.final_items[0]["json"]
    assert final_json["saw_ts"] == 1767225600
