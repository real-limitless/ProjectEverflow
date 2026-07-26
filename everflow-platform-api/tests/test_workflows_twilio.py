"""Tests for the Twilio node executor (``n8n-nodes-base.twilio``).

Covers:

- ``twilio_response`` dict mock → envelope used verbatim
- ``twilio_response`` callable mock receives
  ``(operation, from_num, to_num, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline SMS: ``sid`` starts with ``SM``, body echoed, status='queued'
- Offline call: ``sid`` starts with ``CA``, no body, status='queued'
- ``to``/``from`` defaults from ``$json`` (from/fromNumber, to/toNumber)
- ``message`` default from ``$json.body`` (and ``message``/``text``)
- ``operation='call'`` reflected on output
- Empty ``to`` → no item
- Empty ``message`` for SMS → no item
- End-to-end: Manual Trigger → twilio (SMS mock) → Set sees ``sid`` and ``body``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.twilio import TWILIO_OPERATIONS, exec_twilio


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.twilio",
    id_: str = "tw1",
    name: str = "Twilio",
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


# ── 1. twilio_response dict mock ──────────────────────────────────────


@pytest.mark.asyncio
async def test_twilio_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551112222",
            "to": "+15553334444",
            "message": "Hello via SMS",
        }
    )
    ctx = _ctx(
        {
            "twilio_response": {
                "sid": "SMabcdef0123456789abcdef0123456789",
                "status": "delivered",
                "to": "+15553334444",
                "from": "+15551112222",
                "body": "Hello via SMS",
                "date_created": "2024-01-01T00:00:00Z",
                "direction": "outbound-api",
            }
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p["sid"] == "SMabcdef0123456789abcdef0123456789"
    assert p["status"] == "delivered"
    assert p["to"] == "+15553334444"
    assert p["from"] == "+15551112222"
    assert p["body"] == "Hello via SMS"
    assert p["operation"] == "send"
    assert p["ok"] is True
    assert p["source"] == "twilio"


# ── 2. twilio_response callable mock signature ─────────────────────────


@pytest.mark.asyncio
async def test_twilio_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, from_num, to_num, params, item, ctx):
        captured["operation"] = operation
        captured["from"] = from_num
        captured["to"] = to_num
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "sid": "SMcallablemock00000000000000000000",
            "status": "sent",
            "to": to_num,
            "from": from_num,
            "body": params.get("message"),
        }

    node = _node(
        {
            "operation": "send",
            "from": "+15551110000",
            "to": "+15552220000",
            "message": "Captured",
            "extra": "keep",
        }
    )
    ctx = _ctx({"twilio_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_twilio(node, [item], ctx=ctx))

    assert captured["operation"] == "send"
    assert captured["from"] == "+15551110000"
    assert captured["to"] == "+15552220000"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx
    assert out[0].json["sid"] == "SMcallablemock00000000000000000000"
    assert out[0].json["body"] == "Captured"


# ── 3. http_response fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551112222",
            "to": "+15553334444",
            "message": "Hi via http",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 201,
                "body": {
                    "sid": "SMhttpfallback000000000000000000",
                    "status": "queued",
                    "to": "+15553334444",
                    "from": "+15551112222",
                    "body": "Hi via http",
                },
            }
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=ctx))
    assert out[0].json["sid"] == "SMhttpfallback000000000000000000"
    assert out[0].json["body"] == "Hi via http"
    assert out[0].json["mockSource"] == "http_response"


# ── 4. Offline SMS ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_sms_sid_starts_with_sm_body_echoed_queued() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551112222",
            "to": "+15553334444",
            "message": "Offline SMS body",
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["sid"].startswith("SM")
    assert p["body"] == "Offline SMS body"
    assert p["status"] == "queued"
    assert p["operation"] == "send"
    assert p["ok"] is True
    assert p["source"] == "twilio"
    assert p["mockSource"] == "offline"
    assert p["to"] == "+15553334444"
    assert p["from"] == "+15551112222"


# ── 5. Offline call ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_call_sid_starts_with_ca_no_body_queued() -> None:
    node = _node(
        {
            "operation": "call",
            "from": "+15551112222",
            "to": "+15553334444",
            "options": {"voiceUrl": "https://example.com/voice.xml"},
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["sid"].startswith("CA")
    assert "body" not in p
    assert p["status"] == "queued"
    assert p["operation"] == "call"
    assert p["ok"] is True
    assert p["source"] == "twilio"
    assert p["mockSource"] == "offline"
    assert p["options"] == {"voiceUrl": "https://example.com/voice.xml"}


# ── 6. to / from defaults from $json ──────────────────────────────────


@pytest.mark.asyncio
async def test_to_and_from_defaults_from_json() -> None:
    node = _node(
        {
            "operation": "send",
            "message": "from $json",
        }
    )
    item = ExecutionItem(
        json={
            "from": "+15559990000",
            "fromNumber": "+15559991111",
            "to": "+15558880000",
            "toNumber": "+15558881111",
        }
    )
    out = _out_items(await exec_twilio(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    # $json.from wins over $json.fromNumber
    assert p["from"] == "+15559990000"
    # $json.to wins over $json.toNumber
    assert p["to"] == "+15558880000"


@pytest.mark.asyncio
async def test_fromNumber_used_when_no_from() -> None:
    node = _node(
        {
            "operation": "send",
            "to": "+15558880000",
            "message": "hi",
        }
    )
    item = ExecutionItem(json={"fromNumber": "+15559991111"})
    out = _out_items(await exec_twilio(node, [item], ctx=_ctx()))
    assert out[0].json["from"] == "+15559991111"


@pytest.mark.asyncio
async def test_toNumber_used_when_no_to() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551110000",
            "message": "hi",
        }
    )
    item = ExecutionItem(json={"toNumber": "+15552220000"})
    out = _out_items(await exec_twilio(node, [item], ctx=_ctx()))
    assert out[0].json["to"] == "+15552220000"


# ── 7. message default from $json.body ────────────────────────────────


@pytest.mark.asyncio
async def test_message_default_from_json_body() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551110000",
            "to": "+15552220000",
        }
    )
    item = ExecutionItem(json={"body": "from $json.body"})
    out = _out_items(await exec_twilio(node, [item], ctx=_ctx()))
    assert out[0].json["body"] == "from $json.body"


@pytest.mark.asyncio
async def test_message_prefers_message_then_body_then_text() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551110000",
            "to": "+15552220000",
        }
    )
    item = ExecutionItem(
        json={
            "message": "msg-via-message",
            "body": "msg-via-body",
            "text": "msg-via-text",
        }
    )
    out = _out_items(await exec_twilio(node, [item], ctx=_ctx()))
    assert out[0].json["body"] == "msg-via-message"

    item2 = ExecutionItem(
        json={"body": "msg-via-body", "text": "msg-via-text"}
    )
    out2 = _out_items(await exec_twilio(node, [item2], ctx=_ctx()))
    assert out2[0].json["body"] == "msg-via-body"

    item3 = ExecutionItem(json={"text": "msg-via-text"})
    out3 = _out_items(await exec_twilio(node, [item3], ctx=_ctx()))
    assert out3[0].json["body"] == "msg-via-text"


# ── 8. operation='call' reflected ─────────────────────────────────────


@pytest.mark.asyncio
async def test_call_operation_reflected_no_body() -> None:
    node = _node(
        {
            "operation": "call",
            "from": "+15551110000",
            "to": "+15552220000",
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["operation"] == "call"
    assert "body" not in out[0].json
    assert out[0].json["sid"].startswith("CA")


@pytest.mark.asyncio
async def test_default_operation_is_send() -> None:
    node = _node(
        {
            "from": "+15551110000",
            "to": "+15552220000",
            "message": "default op",
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["operation"] == "send"
    assert out[0].json["sid"].startswith("SM")


# ── 9. Empty to → no item ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_to_skips_item() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551110000",
            "message": "should not send",
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_to_when_only_in_json_skips_item() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551110000",
            "message": "should not send",
        }
    )
    item = ExecutionItem(json={"to": ""})
    out = _out_items(await exec_twilio(node, [item], ctx=_ctx()))
    assert out == []


# ── 10. Empty message for SMS → no item ───────────────────────────────


@pytest.mark.asyncio
async def test_empty_message_for_sms_skips_item() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551110000",
            "to": "+15552220000",
            "message": "",
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_message_when_only_in_json_skips_item() -> None:
    node = _node(
        {
            "operation": "send",
            "from": "+15551110000",
            "to": "+15552220000",
        }
    )
    item = ExecutionItem(json={"body": ""})
    out = _out_items(await exec_twilio(node, [item], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_call_with_empty_message_still_emits() -> None:
    """Calls do not require a body — only ``to`` is mandatory."""
    node = _node(
        {
            "operation": "call",
            "from": "+15551110000",
            "to": "+15552220000",
        }
    )
    out = _out_items(await exec_twilio(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["sid"].startswith("CA")


# ── 11. Unsupported operation raises ──────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "fax"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_twilio(
            node,
            [ExecutionItem(json={"to": "+1", "from": "+2", "message": "x"})],
            ctx=_ctx(),
        )


# ── 12. Multiple input items produce one envelope each ────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({"operation": "send"})
    items = [
        ExecutionItem(
            json={
                "from": "+15550000001",
                "to": "+15551110001",
                "message": "A",
            }
        ),
        ExecutionItem(
            json={
                "from": "+15550000002",
                "to": "+15551110002",
                "message": "B",
            }
        ),
        ExecutionItem(
            json={
                "from": "+15550000003",
                "to": "+15551110003",
                "message": "C",
            }
        ),
    ]
    out = _out_items(await exec_twilio(node, items, ctx=_ctx()))
    assert len(out) == 3
    bodies = [o.json["body"] for o in out]
    assert bodies == ["A", "B", "C"]
    assert all(o.json["sid"].startswith("SM") for o in out)


# ── 13. Descriptor registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.twilio" in REGISTRY
    assert "n8n-nodes-base.twilio" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.twilio"] == "output"
    desc = REGISTRY["n8n-nodes-base.twilio"]
    assert desc.executor.endswith(":exec_twilio")
    assert desc.category == "output"
    assert set(TWILIO_OPERATIONS) == {"send", "call"}


# ── 14. End-to-end: Manual Trigger → twilio (SMS mock) → Set sees sid ─


def _doc(nodes, connections):
    return {"name": "twilio-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_twilio_set_sees_sid_and_body() -> None:
    """Manual Trigger → twilio (twilio_response mock) → Set pulls sid/body."""
    mocks = {
        "twilio_response": {
            "sid": "SMe2e000000000000000000000000000000",
            "status": "queued",
            "to": "+15553334444",
            "from": "+15551112222",
            "body": "E2E body",
            "date_created": "2024-01-01T00:00:00Z",
            "direction": "outbound-api",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "tw1",
                "Twilio",
                "n8n-nodes-base.twilio",
                {
                    "operation": "send",
                    "from": "+15551112222",
                    "to": "+15553334444",
                    "message": "E2E body",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_sid", "value": "={{ $json.sid }}", "type": "string"},
                            {"name": "result_body", "value": "={{ $json.body }}", "type": "string"},
                            {"name": "result_to", "value": "={{ $json.to }}", "type": "string"},
                            {"name": "result_op", "value": "={{ $json.operation }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Twilio", "type": "main", "index": 0}]]},
            "Twilio": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    twilio_step = next(s for s in result.steps if s.node_name == "Twilio")
    assert twilio_step.status == "success", twilio_step.error
    assert twilio_step.output_count == 1
    sample = twilio_step.sample_output[0]
    assert sample["json"]["sid"] == "SMe2e000000000000000000000000000000"
    assert sample["json"]["body"] == "E2E body"
    assert sample["json"]["to"] == "+15553334444"
    assert sample["json"]["operation"] == "send"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_sid") == "SMe2e000000000000000000000000000000"
    assert fjson.get("result_body") == "E2E body"
    assert fjson.get("result_to") == "+15553334444"
    assert fjson.get("result_op") == "send"
