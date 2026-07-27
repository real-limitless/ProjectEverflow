"""Tests for the Slack node executors (``n8n-nodes-base.slack`` and
``n8n-nodes-base.slackTrigger``).

Covers:

- ``slack``:
    - ``slack_response`` dict mock → envelope used verbatim
    - ``slack_response`` callable mock receives ``(channel, text, params, item, ctx)``
    - ``http_response`` fallback unwraps a JSON body
    - Offline synthetic response has ``ok``/``channel``/``ts``/``message``
    - ``channel``/``text`` defaults from ``$json``
    - ``asUser`` and ``linkNames`` reflected
    - Empty text + no blocks → no item
    - Blocks preserved when provided
    - End-to-end: Manual → slack (mock) → Set sees ``ts`` and ``channel``
- ``slackTrigger``:
    - ``slack_event`` dict mock → fields extracted
    - ``slack_event`` callable mock receives ``(node, ctx)``
    - ``trigger_payload`` fallback
    - Offline synthetic event
    - End-to-end: slackTrigger as workflow start → Set sees ``text``
- Descriptor registration (CI invariant) for both types
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.slack import (
    SLACK_DEFAULT_EVENTS,
    exec_slack,
    exec_slack_trigger,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.slack",
    id_: str = "sl1",
    name: str = "Slack",
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


# ── 1. slack_response dict mock ────────────────────────────────────────


@pytest.mark.asyncio
async def test_slack_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "channel": "C12345",
            "text": "Hello Slack",
        }
    )
    ctx = _ctx(
        {
            "slack_response": {
                "ok": True,
                "channel": "C12345",
                "ts": "1700000000.000200",
                "message": {
                    "type": "message",
                    "text": "Hello Slack",
                    "user": "U_MOCK_USER",
                    "ts": "1700000000.000200",
                },
            }
        }
    )
    out = _out_items(await exec_slack(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    payload = out[0].json
    assert payload["ok"] is True
    assert payload["channel"] == "C12345"
    assert payload["text"] == "Hello Slack"
    assert payload["ts"] == "1700000000.000200"
    assert payload["message"]["user"] == "U_MOCK_USER"
    assert payload["message"]["type"] == "message"
    assert payload["source"] == "slack"


# ── 2. slack_response callable mock signature ─────────────────────────


@pytest.mark.asyncio
async def test_slack_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(channel, text, params, item, ctx):
        captured["channel"] = channel
        captured["text"] = text
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "ok": True,
            "channel": channel,
            "ts": "1700000001.000001",
            "message": {
                "type": "message",
                "text": "captured",
                "user": "U_CAPTURED",
                "ts": "1700000001.000001",
            },
        }

    node = _node(
        {
            "channel": "C555",
            "text": "ping",
            "asUser": True,
            "linkNames": True,
            "extra": "keep",
        }
    )
    ctx = _ctx({"slack_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_slack(node, [item], ctx=ctx))

    assert captured["channel"] == "C555"
    assert captured["text"] == "ping"
    assert captured["params"]["extra"] == "keep"
    assert captured["params"]["asUser"] is True
    assert captured["params"]["linkNames"] is True
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["channel"] == "C555"
    assert out[0].json["text"] == "captured"
    assert out[0].json["ts"] == "1700000001.000001"
    assert out[0].json["message"]["user"] == "U_CAPTURED"
    assert out[0].json["asUser"] is True
    assert out[0].json["linkNames"] is True


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node({"channel": "C777", "text": "via http"})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "ok": True,
                    "channel": "C777",
                    "ts": "1700000002.000002",
                    "text": "via http",
                },
            }
        }
    )
    out = _out_items(await exec_slack(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["ok"] is True
    assert p["channel"] == "C777"
    assert p["text"] == "via http"
    assert p["ts"] == "1700000002.000002"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "slack"


# ── 4. Offline synthetic response ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_response_has_envelope_fields() -> None:
    node = _node({"channel": "C321", "text": "offline"})
    out = _out_items(await exec_slack(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    payload = out[0].json
    assert payload["ok"] is True
    assert payload["channel"] == "C321"
    assert payload["text"] == "offline"
    assert isinstance(payload["ts"], str)
    assert "." in payload["ts"]
    assert payload["message"]["type"] == "message"
    assert payload["message"]["text"] == "offline"
    assert payload["message"]["user"] == "U_MOCK_USER"
    assert payload["message"]["ts"] == payload["ts"]
    assert payload["source"] == "slack"
    assert payload["mockSource"] == "offline"
    assert payload["asUser"] is False
    assert payload["linkNames"] is False


# ── 5. $json fallbacks for channel and text ───────────────────────────


@pytest.mark.asyncio
async def test_channel_and_text_default_from_json() -> None:
    node = _node({})  # all from $json
    item = ExecutionItem(
        json={"channel": "C999", "text": "from json"}
    )
    out = _out_items(await exec_slack(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["channel"] == "C999"
    assert p["text"] == "from json"


@pytest.mark.asyncio
async def test_channel_accepts_channel_id_alias() -> None:
    node = _node({"text": "x"})
    item = ExecutionItem(json={"channelId": "C5555"})
    out = _out_items(await exec_slack(node, [item], ctx=_ctx()))
    assert out[0].json["channel"] == "C5555"
    assert out[0].json["text"] == "x"


@pytest.mark.asyncio
async def test_channel_accepts_channel_id_snake_alias() -> None:
    node = _node({"text": "x"})
    item = ExecutionItem(json={"channel_id": "C6666"})
    out = _out_items(await exec_slack(node, [item], ctx=_ctx()))
    assert out[0].json["channel"] == "C6666"


@pytest.mark.asyncio
async def test_channel_accepts_hash_prefix() -> None:
    node = _node({"text": "x"})
    out = _out_items(
        await exec_slack(node, [ExecutionItem(json={"channel": "#general"})], ctx=_ctx())
    )
    assert out[0].json["channel"] == "#general"


@pytest.mark.asyncio
async def test_text_prefers_text_then_message() -> None:
    node = _node({"channel": "C1"})  # no text parameter
    # text wins over message
    item = ExecutionItem(
        json={"text": "via-text", "message": "via-message"}
    )
    out = _out_items(await exec_slack(node, [item], ctx=_ctx()))
    assert out[0].json["text"] == "via-text"

    # message used when no text
    item2 = ExecutionItem(json={"message": "via-message"})
    out2 = _out_items(await exec_slack(node, [item2], ctx=_ctx()))
    assert out2[0].json["text"] == "via-message"


# ── 6. asUser and linkNames reflected ─────────────────────────────────


@pytest.mark.asyncio
async def test_as_user_and_link_names_reflected() -> None:
    node = _node(
        {
            "channel": "C1",
            "text": "x",
            "asUser": True,
            "linkNames": True,
        }
    )
    out = _out_items(await exec_slack(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["asUser"] is True
    assert p["linkNames"] is True


@pytest.mark.asyncio
async def test_as_user_default_false() -> None:
    node = _node({"channel": "C1", "text": "x"})
    out = _out_items(await exec_slack(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["asUser"] is False
    assert out[0].json["linkNames"] is False


@pytest.mark.asyncio
async def test_as_user_string_truthy() -> None:
    node = _node({"channel": "C1", "text": "x", "asUser": "true", "linkNames": "1"})
    out = _out_items(await exec_slack(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["asUser"] is True
    assert out[0].json["linkNames"] is True


# ── 7. Empty text + no blocks → no item ───────────────────────────────


@pytest.mark.asyncio
async def test_empty_text_no_blocks_skips_item() -> None:
    node = _node({"channel": "C1", "text": ""})
    out = _out_items(await exec_slack(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_text_when_all_paths_empty_skips_item() -> None:
    node = _node({"channel": "C1"})
    item = ExecutionItem(json={"text": "", "message": ""})
    out = _out_items(await exec_slack(node, [item], ctx=_ctx()))
    assert out == []


# ── 8. Blocks preserve a text-less send ───────────────────────────────


@pytest.mark.asyncio
async def test_blocks_only_send_does_not_skip() -> None:
    node = _node(
        {
            "channel": "C1",
            "text": "",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}
            ],
        }
    )
    out = _out_items(await exec_slack(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["blocks"] == [
        {"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}
    ]


# ── 9. One output item per input ──────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({})
    items = [
        ExecutionItem(json={"channel": "C1", "text": "a"}),
        ExecutionItem(json={"channel": "C2", "text": "b"}),
        ExecutionItem(json={"channel": "C3", "text": "c"}),
    ]
    out = _out_items(await exec_slack(node, items, ctx=_ctx()))
    assert len(out) == 3
    texts = [o.json["text"] for o in out]
    assert texts == ["a", "b", "c"]
    assert all(o.json["source"] == "slack" for o in out)


# ── 10. Descriptor registration (action) ──────────────────────────────


def test_slack_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.slack" in REGISTRY
    assert "n8n-nodes-base.slack" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.slack"] == "output"
    desc = REGISTRY["n8n-nodes-base.slack"]
    assert desc.executor.endswith(":exec_slack")
    assert desc.category == "output"
    assert "message" in SLACK_DEFAULT_EVENTS


# ── 11. End-to-end: Manual Trigger → slack (mock) → Set ──────────────


def _doc(nodes, connections):
    return {"name": "slack-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_slack_set_sees_ts_and_channel() -> None:
    """Manual Trigger → slack (slack_response mock) → Set pulls ts/channel/text."""
    mocks = {
        "slack_response": {
            "ok": True,
            "channel": "C12345",
            "ts": "1700000100.000100",
            "message": {
                "type": "message",
                "text": "Hello E2E",
                "user": "U_E2E",
                "ts": "1700000100.000100",
            },
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "sl1",
                "Slack",
                "n8n-nodes-base.slack",
                {
                    "channel": "C12345",
                    "text": "Hello E2E",
                    "asUser": True,
                    "linkNames": True,
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_ts", "value": "={{ $json.ts }}", "type": "string"},
                            {"name": "result_channel", "value": "={{ $json.channel }}", "type": "string"},
                            {"name": "result_text", "value": "={{ $json.text }}", "type": "string"},
                            {"name": "result_ok", "value": "={{ $json.ok }}", "type": "boolean"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Slack", "type": "main", "index": 0}]]},
            "Slack": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    slack_step = next(s for s in result.steps if s.node_name == "Slack")
    assert slack_step.status == "success", slack_step.error
    assert slack_step.output_count == 1
    sample = slack_step.sample_output[0]
    assert sample["json"]["ts"] == "1700000100.000100"
    assert sample["json"]["channel"] == "C12345"
    assert sample["json"]["text"] == "Hello E2E"
    assert sample["json"]["ok"] is True
    assert sample["json"]["asUser"] is True
    assert sample["json"]["linkNames"] is True

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_ts") == "1700000100.000100"
    assert fjson.get("result_channel") == "C12345"
    assert fjson.get("result_text") == "Hello E2E"
    assert fjson.get("result_ok") is True


# ══════════════════════════════════════════════════════════════════════
#  slackTrigger
# ══════════════════════════════════════════════════════════════════════


def _trigger_node(
    params: dict[str, Any] | None = None,
    *,
    id_: str = "st1",
    name: str = "SlackTrigger",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="n8n-nodes-base.slackTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


# ── 12. slack_event dict mock → fields extracted ─────────────────────


@pytest.mark.asyncio
async def test_slack_event_dict_mock_extracts_fields() -> None:
    event = {
        "type": "message",
        "channel": "C999",
        "user": "U999",
        "text": "Hi from Slack",
        "ts": "1700000200.000200",
        "event_ts": "1700000200.000200",
    }
    ctx = _ctx({"slack_event": event})
    node = _trigger_node({"event": "message"})

    out = await exec_slack_trigger(node, items=[], ctx=ctx)
    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["type"] == "message"
    assert payload["channel"] == "C999"
    assert payload["user"] == "U999"
    assert payload["text"] == "Hi from Slack"
    assert payload["ts"] == "1700000200.000200"
    assert payload["source"] == "slackTrigger"


# ── 13. slack_event callable mock signature ──────────────────────────


@pytest.mark.asyncio
async def test_slack_event_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(node, ctx):
        captured["node"] = node
        captured["ctx"] = ctx
        return {
            "type": "message",
            "channel": "C1",
            "user": "U1",
            "text": "callable mock",
            "ts": "1700000210.000210",
            "event_ts": "1700000210.000210",
        }

    ctx = _ctx({"slack_event": _mock})
    node = _trigger_node()

    out = await exec_slack_trigger(node, items=[], ctx=ctx)
    assert captured["node"] is node
    assert captured["ctx"] is ctx

    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["channel"] == "C1"
    assert payload["text"] == "callable mock"
    assert payload["ts"] == "1700000210.000210"


# ── 14. trigger_payload fallback ─────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_payload_fallback_used() -> None:
    fallback = {
        "type": "app_mention",
        "channel": "C77",
        "user": "U77",
        "text": "fallback text",
        "ts": "1700000220.000220",
        "event_ts": "1700000220.000220",
    }
    ctx = _ctx({"trigger_payload": fallback})
    node = _trigger_node()

    out = await exec_slack_trigger(node, items=[], ctx=ctx)
    items = out[0][1]
    payload = items[0].json
    assert payload["type"] == "app_mention"
    assert payload["channel"] == "C77"
    assert payload["text"] == "fallback text"


# ── 15. Offline synthetic event ──────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_event_emits_mock_event() -> None:
    node = _trigger_node()
    out = await exec_slack_trigger(node, items=[], ctx=_ctx())
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["type"] == "message"
    assert payload["channel"] == "C12345"
    assert payload["user"] == "U12345"
    assert payload["text"] == "Mock Slack message"
    assert isinstance(payload["ts"], str)
    assert "." in payload["ts"]
    assert payload["source"] == "slackTrigger"


@pytest.mark.asyncio
async def test_offline_event_respects_event_param() -> None:
    node = _trigger_node({"event": "reaction_added"})
    out = await exec_slack_trigger(node, items=[], ctx=_ctx())
    items = out[0][1]
    payload = items[0].json
    assert payload["type"] == "reaction_added"


# ── 16. Input items are passed through with trigger context merged ──


@pytest.mark.asyncio
async def test_input_items_passed_through_with_context() -> None:
    event = {
        "type": "message",
        "channel": "C3",
        "user": "U3",
        "text": "merge me",
        "ts": "1700000240.000240",
        "event_ts": "1700000240.000240",
    }
    ctx = _ctx({"slack_event": event})
    node = _trigger_node()
    in_items = [ExecutionItem(json={"existing": "data"})]

    out = await exec_slack_trigger(node, items=in_items, ctx=ctx)
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["existing"] == "data"
    assert payload["text"] == "merge me"
    assert payload["source"] == "slackTrigger"


# ── 17. Descriptor registration (trigger) ───────────────────────────


def test_slack_trigger_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.slackTrigger" in REGISTRY
    assert "n8n-nodes-base.slackTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.slackTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.slackTrigger"]
    assert desc.executor.endswith(":exec_slack_trigger")
    assert desc.category == "trigger"


# ── 18. End-to-end: slackTrigger as workflow start → Set sees text ───


@pytest.mark.asyncio
async def test_end_to_end_slack_trigger_set_sees_text() -> None:
    """slackTrigger → Set: a fresh run that starts with the Slack
    trigger should drive a downstream Set to see the message ``text``."""
    mocks = {
        "slack_event": {
            "type": "message",
            "channel": "C333",
            "user": "U333",
            "text": "Triggered hello",
            "ts": "1700000250.000250",
            "event_ts": "1700000250.000250",
        }
    }
    doc = _doc(
        [
            _n(
                "st1",
                "SlackTrigger",
                "n8n-nodes-base.slackTrigger",
                {"event": "message"},
            ),
            _n(
                "s1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_text", "value": "={{ $json.text }}", "type": "string"},
                            {"name": "result_channel", "value": "={{ $json.channel }}", "type": "string"},
                            {"name": "result_user", "value": "={{ $json.user }}", "type": "string"},
                            {"name": "result_ts", "value": "={{ $json.ts }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "SlackTrigger": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="slackTrigger")
    assert result.status == "success", result.error_message

    trigger_step = next(s for s in result.steps if s.node_name == "SlackTrigger")
    assert trigger_step.status == "success", trigger_step.error
    assert trigger_step.output_count == 1
    sample = trigger_step.sample_output[0]
    assert sample["json"]["text"] == "Triggered hello"
    assert sample["json"]["channel"] == "C333"
    assert sample["json"]["user"] == "U333"

    final = result.final_items
    assert final, "expected final items from Stamp"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_text") == "Triggered hello"
    assert fjson.get("result_channel") == "C333"
    assert fjson.get("result_user") == "U333"
    assert fjson.get("result_ts") == "1700000250.000250"
