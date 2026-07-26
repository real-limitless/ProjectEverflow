"""Tests for the WhatsApp node executors (``n8n-nodes-base.whatsApp`` and
``n8n-nodes-base.whatsAppTrigger``).

Covers:

- ``whatsApp``:
    - ``whatsapp_response`` dict mock → envelope used verbatim
    - ``whatsapp_response`` callable mock receives ``(phoneNumber, text, params, item, ctx)``
    - ``http_response`` fallback unwraps a JSON body
    - Offline synthetic response has ``messaging_product='whatsapp'``
    - ``phoneNumber``/``text`` defaults from ``$json`` (phoneNumber/from/to, text/message/body)
    - ``messageType`` reflected and defaults to ``text``
    - ``phoneNumber`` digits-only stripping
    - Empty text → no item
    - End-to-end: Manual → whatsApp (mock) → Set sees ``messageId``
- ``whatsAppTrigger``:
    - ``whatsapp_webhook`` dict mock → fields extracted
    - ``whatsapp_webhook`` callable mock receives ``(node, ctx)``
    - ``trigger_payload`` fallback
    - Offline synthetic webhook
    - End-to-end: whatsAppTrigger as workflow start → Set sees ``text``
- Descriptor registration (CI invariant) for both types
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.whatsapp import (
    WHATSAPP_MESSAGE_TYPES,
    exec_whatsapp,
    exec_whatsapp_trigger,
)


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.whatsApp",
    id_: str = "wa1",
    name: str = "WhatsApp",
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


# ── 1. whatsapp_response dict mock ────────────────────────────────────


@pytest.mark.asyncio
async def test_whatsapp_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "phoneNumber": "+1 555-123-4567",
            "text": "Hello WhatsApp",
            "messageType": "text",
        }
    )
    ctx = _ctx(
        {
            "whatsapp_response": {
                "messaging_product": "whatsapp",
                "contacts": [{"input": "+1 555-123-4567", "wa_id": "15551234567"}],
                "messages": [
                    {
                        "id": "wamid.ABCDEFGHIJKLMNOP",
                        "from": "15551234567",
                        "timestamp": 1700000000,
                    }
                ],
            }
        }
    )
    out = _out_items(await exec_whatsapp(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    payload = out[0].json
    assert payload["messageId"] == "wamid.ABCDEFGHIJKLMNOP"
    assert payload["phoneNumber"] == "+1 555-123-4567"
    assert payload["text"] == "Hello WhatsApp"
    assert payload["messageType"] == "text"
    assert payload["ok"] is True
    assert payload["source"] == "whatsApp"
    assert payload["contacts"] == [
        {"input": "+1 555-123-4567", "wa_id": "15551234567"}
    ]


# ── 2. whatsapp_response callable mock signature ──────────────────────


@pytest.mark.asyncio
async def test_whatsapp_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(phone_number, text, params, item, ctx):
        captured["phoneNumber"] = phone_number
        captured["text"] = text
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": phone_number, "wa_id": "15551234567"}],
            "messages": [
                {
                    "id": "wamid.MOCK",
                    "from": "15551234567",
                    "timestamp": 1700000001,
                }
            ],
        }

    node = _node(
        {
            "phoneNumber": "+1 555-123-4567",
            "text": "ping",
            "messageType": "text",
            "extra": "keep",
        }
    )
    ctx = _ctx({"whatsapp_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_whatsapp(node, [item], ctx=ctx))

    assert captured["phoneNumber"] == "+1 555-123-4567"
    assert captured["text"] == "ping"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["messageId"] == "wamid.MOCK"
    assert out[0].json["text"] == "ping"
    assert out[0].json["messageType"] == "text"


# ── 3. http_response fallback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node({"phoneNumber": "+1 555-123-4567", "text": "via http"})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "messaging_product": "whatsapp",
                    "contacts": [{"input": "+1 555-123-4567", "wa_id": "15551234567"}],
                    "messages": [
                        {
                            "id": "wamid.HTTP",
                            "from": "15551234567",
                            "timestamp": 1700000002,
                        }
                    ],
                },
            }
        }
    )
    out = _out_items(await exec_whatsapp(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["messageId"] == "wamid.HTTP"
    assert p["phoneNumber"] == "+1 555-123-4567"
    assert p["text"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "whatsApp"


# ── 4. Offline synthetic response ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_response_has_envelope_fields() -> None:
    node = _node({"phoneNumber": "+1 555-123-4567", "text": "offline"})
    out = _out_items(await exec_whatsapp(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    payload = out[0].json
    assert isinstance(payload["messageId"], str)
    assert payload["messageId"].startswith("wamid.")
    assert len(payload["messageId"]) == len("wamid.") + 16
    assert payload["phoneNumber"] == "+1 555-123-4567"
    assert payload["text"] == "offline"
    assert payload["messageType"] == "text"
    assert payload["ok"] is True
    assert payload["source"] == "whatsApp"
    assert payload["mockSource"] == "offline"
    assert payload["contacts"] == [
        {"input": "+1 555-123-4567", "wa_id": "15551234567"}
    ]


# ── 5. $json fallbacks for phoneNumber and text ────────────────────────


@pytest.mark.asyncio
async def test_phone_number_and_text_default_from_json() -> None:
    node = _node({"messageType": "text"})
    item = ExecutionItem(
        json={"phoneNumber": "+1 555-999-0000", "text": "from json"}
    )
    out = _out_items(await exec_whatsapp(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["phoneNumber"] == "+1 555-999-0000"
    assert p["text"] == "from json"
    assert p["messageType"] == "text"


@pytest.mark.asyncio
async def test_phone_number_accepts_from_alias() -> None:
    node = _node({"text": "x"})
    item = ExecutionItem(json={"from": "+1 555-111-2222"})
    out = _out_items(await exec_whatsapp(node, [item], ctx=_ctx()))
    assert out[0].json["phoneNumber"] == "+1 555-111-2222"
    assert out[0].json["text"] == "x"


@pytest.mark.asyncio
async def test_phone_number_accepts_to_alias() -> None:
    node = _node({"text": "x"})
    item = ExecutionItem(json={"to": "+1 555-333-4444"})
    out = _out_items(await exec_whatsapp(node, [item], ctx=_ctx()))
    assert out[0].json["phoneNumber"] == "+1 555-333-4444"


@pytest.mark.asyncio
async def test_text_prefers_text_then_message_then_body() -> None:
    node = _node({"phoneNumber": "+1 555-123-4567"})
    item = ExecutionItem(
        json={
            "text": "via-text",
            "message": "via-message",
            "body": "via-body",
        }
    )
    out = _out_items(await exec_whatsapp(node, [item], ctx=_ctx()))
    assert out[0].json["text"] == "via-text"

    item2 = ExecutionItem(json={"message": "via-message", "body": "via-body"})
    out2 = _out_items(await exec_whatsapp(node, [item2], ctx=_ctx()))
    assert out2[0].json["text"] == "via-message"

    item3 = ExecutionItem(json={"body": "via-body"})
    out3 = _out_items(await exec_whatsapp(node, [item3], ctx=_ctx()))
    assert out3[0].json["text"] == "via-body"


# ── 6. messageType reflected and defaults ────────────────────────────


@pytest.mark.asyncio
async def test_message_type_reflected() -> None:
    for mt in ("text", "template"):
        node = _node(
            {
                "phoneNumber": "+1 555-123-4567",
                "text": "x",
                "messageType": mt,
            }
        )
        out = _out_items(
            await exec_whatsapp(node, [ExecutionItem(json={})], ctx=_ctx())
        )
        assert out[0].json["messageType"] == mt


@pytest.mark.asyncio
async def test_message_type_default_text() -> None:
    node = _node({"phoneNumber": "+1 555-123-4567", "text": "x"})
    out = _out_items(await exec_whatsapp(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["messageType"] == "text"


@pytest.mark.asyncio
async def test_message_type_invalid_falls_back_to_text() -> None:
    node = _node(
        {
            "phoneNumber": "+1 555-123-4567",
            "text": "x",
            "messageType": "image",
        }
    )
    out = _out_items(await exec_whatsapp(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["messageType"] == "text"


# ── 7. phoneNumber digits-only stripping ─────────────────────────────


@pytest.mark.asyncio
async def test_phone_number_digits_only_stripping_in_offline() -> None:
    node = _node(
        {
            "phoneNumber": "+1 (555) 123-4567",
            "text": "strip me",
        }
    )
    out = _out_items(await exec_whatsapp(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["phoneNumber"] == "+1 (555) 123-4567"
    assert p["contacts"] == [
        {"input": "+1 (555) 123-4567", "wa_id": "15551234567"}
    ]
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_phone_number_digits_only_stripping_in_http_fallback() -> None:
    node = _node(
        {
            "phoneNumber": "+1 (555) 123-4567",
            "text": "strip me http",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "messaging_product": "whatsapp",
                    "messages": [
                        {
                            "id": "wamid.STRIP",
                            "timestamp": 1700000100,
                        }
                    ],
                },
            }
        }
    )
    out = _out_items(await exec_whatsapp(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["mockSource"] == "http_response"
    assert p["contacts"][0]["wa_id"] == "15551234567"
    assert p["contacts"][0]["input"] == "+1 (555) 123-4567"


# ── 8. Empty text → no item ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_text_skips_item() -> None:
    node = _node(
        {
            "phoneNumber": "+1 555-123-4567",
            "text": "",
        }
    )
    out = _out_items(await exec_whatsapp(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_text_when_all_paths_empty_skips_item() -> None:
    node = _node({"phoneNumber": "+1 555-123-4567"})
    item = ExecutionItem(json={"text": "", "message": "", "body": ""})
    out = _out_items(await exec_whatsapp(node, [item], ctx=_ctx()))
    assert out == []


# ── 9. One output item per input ──────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({"messageType": "text"})
    items = [
        ExecutionItem(json={"phoneNumber": "+1 555-123-4567", "text": "a"}),
        ExecutionItem(json={"phoneNumber": "+1 555-123-4567", "text": "b"}),
        ExecutionItem(json={"phoneNumber": "+1 555-123-4567", "text": "c"}),
    ]
    out = _out_items(await exec_whatsapp(node, items, ctx=_ctx()))
    assert len(out) == 3
    texts = [o.json["text"] for o in out]
    assert texts == ["a", "b", "c"]
    assert all(o.json["source"] == "whatsApp" for o in out)


# ── 10. Descriptor registration (action) ──────────────────────────────


def test_whatsapp_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.whatsApp" in REGISTRY
    assert "n8n-nodes-base.whatsApp" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.whatsApp"] == "output"
    desc = REGISTRY["n8n-nodes-base.whatsApp"]
    assert desc.executor.endswith(":exec_whatsapp")
    assert desc.category == "output"
    assert set(WHATSAPP_MESSAGE_TYPES) == {"text", "template"}


# ── 11. End-to-end: Manual Trigger → whatsApp (mock) → Set ──────────


def _doc(nodes, connections):
    return {"name": "whatsapp-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_whatsapp_set_sees_message_id() -> None:
    mocks = {
        "whatsapp_response": {
            "messaging_product": "whatsapp",
            "contacts": [
                {"input": "+1 555-123-4567", "wa_id": "15551234567"}
            ],
            "messages": [
                {
                    "id": "wamid.E2E4242",
                    "from": "15551234567",
                    "timestamp": 1700000000,
                }
            ],
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "wa1",
                "WhatsApp",
                "n8n-nodes-base.whatsApp",
                {
                    "phoneNumber": "+1 555-123-4567",
                    "text": "Hello E2E",
                    "messageType": "text",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_id", "value": "={{ $json.messageId }}", "type": "string"},
                            {"name": "result_phone", "value": "={{ $json.phoneNumber }}", "type": "string"},
                            {"name": "result_text", "value": "={{ $json.text }}", "type": "string"},
                            {"name": "result_type", "value": "={{ $json.messageType }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "WhatsApp", "type": "main", "index": 0}]]},
            "WhatsApp": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    wa_step = next(s for s in result.steps if s.node_name == "WhatsApp")
    assert wa_step.status == "success", wa_step.error
    assert wa_step.output_count == 1
    sample = wa_step.sample_output[0]
    assert sample["json"]["messageId"] == "wamid.E2E4242"
    assert sample["json"]["phoneNumber"] == "+1 555-123-4567"
    assert sample["json"]["text"] == "Hello E2E"
    assert sample["json"]["messageType"] == "text"

    final = result.final_items
    assert final
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_id") == "wamid.E2E4242"
    assert fjson.get("result_phone") == "+1 555-123-4567"
    assert fjson.get("result_text") == "Hello E2E"
    assert fjson.get("result_type") == "text"


# ══════════════════════════════════════════════════════════════════════
#  whatsAppTrigger
# ══════════════════════════════════════════════════════════════════════


def _trigger_node(
    params: dict[str, Any] | None = None,
    *,
    id_: str = "wt1",
    name: str = "WhatsAppTrigger",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="n8n-nodes-base.whatsAppTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _webhook_payload(
    *,
    entry_id: str = "ENTRY-1",
    phone_id: str = "PHONE-ID-1",
    sender: str = "15559998888",
    msg_id: str = "wamid.WEBHOOK-7",
    ts: str = "1700000005",
    body: str = "Hi from WhatsApp",
) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": entry_id,
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551230000",
                                "phone_number_id": phone_id,
                            },
                            "messages": [
                                {
                                    "from": sender,
                                    "id": msg_id,
                                    "timestamp": ts,
                                    "text": {"body": body},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


# ── 12. whatsapp_webhook dict mock → fields extracted ──────────────────


@pytest.mark.asyncio
async def test_whatsapp_webhook_dict_mock_extracts_fields() -> None:
    webhook = _webhook_payload()
    ctx = _ctx({"whatsapp_webhook": webhook})
    node = _trigger_node({"webhookUrl": "https://example.com/wa-hook"})

    out = await exec_whatsapp_trigger(node, items=[], ctx=ctx)
    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["object"] == "whatsapp_business_account"
    assert payload["phoneNumberId"] == "PHONE-ID-1"
    assert payload["displayPhoneNumber"] == "15551230000"
    assert payload["from"] == "15559998888"
    assert payload["messageId"] == "wamid.WEBHOOK-7"
    assert payload["text"] == "Hi from WhatsApp"
    assert payload["timestamp"] == "1700000005"
    assert payload["webhookUrl"] == "https://example.com/wa-hook"
    assert payload["source"] == "whatsAppTrigger"


# ── 13. whatsapp_webhook callable mock signature ─────────────────────


@pytest.mark.asyncio
async def test_whatsapp_webhook_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(node, ctx):
        captured["node"] = node
        captured["ctx"] = ctx
        return _webhook_payload(
            entry_id="ENTRY-2",
            phone_id="PHONE-ID-2",
            sender="15557776666",
            msg_id="wamid.CALLABLE-1",
            ts="1700000010",
            body="callable mock",
        )

    ctx = _ctx({"whatsapp_webhook": _mock})
    node = _trigger_node()

    out = await exec_whatsapp_trigger(node, items=[], ctx=ctx)
    assert captured["node"] is node
    assert captured["ctx"] is ctx

    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["messageId"] == "wamid.CALLABLE-1"
    assert payload["text"] == "callable mock"
    assert payload["from"] == "15557776666"


# ── 14. trigger_payload fallback ─────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_payload_fallback_used() -> None:
    fallback = _webhook_payload(
        entry_id="ENTRY-3",
        phone_id="PHONE-ID-3",
        sender="15551112222",
        msg_id="wamid.FALLBACK-1",
        ts="1700000020",
        body="fallback text",
    )
    ctx = _ctx({"trigger_payload": fallback})
    node = _trigger_node()

    out = await exec_whatsapp_trigger(node, items=[], ctx=ctx)
    items = out[0][1]
    payload = items[0].json
    assert payload["messageId"] == "wamid.FALLBACK-1"
    assert payload["from"] == "15551112222"
    assert payload["text"] == "fallback text"
    assert payload["phoneNumberId"] == "PHONE-ID-3"


# ── 15. Offline synthetic webhook ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_webhook_emits_mock_message() -> None:
    node = _trigger_node()
    out = await exec_whatsapp_trigger(node, items=[], ctx=_ctx())
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["object"] == "whatsapp_business_account"
    assert payload["phoneNumberId"] == "12345"
    assert payload["displayPhoneNumber"] == "15551234567"
    assert payload["from"] == "15559876543"
    assert isinstance(payload["messageId"], str)
    assert payload["messageId"].startswith("wamid.")
    assert payload["text"] == "Mock WhatsApp message"
    assert isinstance(payload["timestamp"], str)
    assert payload["source"] == "whatsAppTrigger"


# ── 16. Input items are passed through with trigger context merged ──


@pytest.mark.asyncio
async def test_input_items_passed_through_with_context() -> None:
    webhook = _webhook_payload(
        entry_id="ENTRY-4",
        phone_id="PHONE-ID-4",
        sender="15554443333",
        msg_id="wamid.MERGE-1",
        ts="1700000030",
        body="merge me",
    )
    ctx = _ctx({"whatsapp_webhook": webhook})
    node = _trigger_node()
    in_items = [ExecutionItem(json={"existing": "data"})]

    out = await exec_whatsapp_trigger(node, items=in_items, ctx=ctx)
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["existing"] == "data"
    assert payload["text"] == "merge me"
    assert payload["source"] == "whatsAppTrigger"


# ── 17. Descriptor registration (trigger) ───────────────────────────


def test_whatsapp_trigger_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.whatsAppTrigger" in REGISTRY
    assert "n8n-nodes-base.whatsAppTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.whatsAppTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.whatsAppTrigger"]
    assert desc.executor.endswith(":exec_whatsapp_trigger")
    assert desc.category == "trigger"


# ── 18. End-to-end: whatsAppTrigger as workflow start → Set sees text ─


@pytest.mark.asyncio
async def test_end_to_end_whatsapp_trigger_set_sees_text() -> None:
    mocks = {
        "whatsapp_webhook": _webhook_payload(
            entry_id="ENTRY-E2E",
            phone_id="PHONE-ID-E2E",
            sender="15553334444",
            msg_id="wamid.E2E-22",
            ts="1700000050",
            body="Triggered hello",
        )
    }
    doc = _doc(
        [
            _n(
                "wt1",
                "WhatsAppTrigger",
                "n8n-nodes-base.whatsAppTrigger",
                {"webhookUrl": "https://example.com/wa-hook"},
            ),
            _n(
                "s1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_text", "value": "={{ $json.text }}", "type": "string"},
                            {"name": "result_from", "value": "={{ $json[\"from\"] }}", "type": "string"},
                            {"name": "result_msg", "value": "={{ $json.messageId }}", "type": "string"},
                            {"name": "result_pid", "value": "={{ $json.phoneNumberId }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "WhatsAppTrigger": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="whatsAppTrigger")
    assert result.status == "success", result.error_message

    trigger_step = next(s for s in result.steps if s.node_name == "WhatsAppTrigger")
    assert trigger_step.status == "success", trigger_step.error
    assert trigger_step.output_count == 1
    sample = trigger_step.sample_output[0]
    assert sample["json"]["text"] == "Triggered hello"
    assert sample["json"]["from"] == "15553334444"

    final = result.final_items
    assert final
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_text") == "Triggered hello"
    assert fjson.get("result_from") == "15553334444"
    assert fjson.get("result_msg") == "wamid.E2E-22"
    assert fjson.get("result_pid") == "PHONE-ID-E2E"
