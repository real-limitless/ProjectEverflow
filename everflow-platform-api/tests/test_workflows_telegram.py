"""Tests for the Telegram node executors (``n8n-nodes-base.telegram`` and
``n8n-nodes-base.telegramTrigger``).

Covers:

- ``telegram``:
    - ``telegram_response`` dict mock → envelope used verbatim
    - ``telegram_response`` callable mock receives ``(chatId, text, params, item, ctx)``
    - ``http_response`` fallback unwraps a JSON body
    - Offline synthetic response has ``message_id``/``chat``/``date``/``text``
    - ``chatId``/``text`` defaults from ``$json`` (chatId/chat_id, text/message)
    - ``parseMode`` reflected and normalized
    - Empty text → no item
    - End-to-end: Manual → telegram (mock) → Set sees ``messageId``
- ``telegramTrigger``:
    - ``telegram_update`` dict mock → fields extracted
    - ``telegram_update`` callable mock receives ``(node, ctx)``
    - ``trigger_payload`` fallback
    - Offline synthetic update
    - End-to-end: telegramTrigger as workflow start → Set sees ``text``
- Descriptor registration (CI invariant) for both types
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.telegram import (
    TELEGRAM_PARSE_MODES,
    exec_telegram,
    exec_telegram_trigger,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.telegram",
    id_: str = "tg1",
    name: str = "Telegram",
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


# ── 1. telegram_response dict mock ────────────────────────────────────


@pytest.mark.asyncio
async def test_telegram_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "chatId": "12345",
            "text": "Hello from Telegram",
            "parseMode": "HTML",
        }
    )
    ctx = _ctx(
        {
            "telegram_response": {
                "message_id": 987,
                "chat": {"id": 12345, "type": "private"},
                "date": 1700000000,
                "text": "Hello from Telegram",
            }
        }
    )
    out = _out_items(await exec_telegram(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    payload = out[0].json
    assert payload["messageId"] == 987
    assert payload["chatId"] == "12345"
    assert payload["text"] == "Hello from Telegram"
    assert payload["parseMode"] == "HTML"
    assert payload["ok"] is True
    assert payload["source"] == "telegram"
    assert payload["chat"] == {"id": 12345, "type": "private"}


# ── 2. telegram_response callable mock signature ──────────────────────


@pytest.mark.asyncio
async def test_telegram_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(chat_id, text, params, item, ctx):
        captured["chatId"] = chat_id
        captured["text"] = text
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "message_id": 42,
            "chat": {"id": int(chat_id), "type": "private"},
            "date": 1700000001,
            "text": "captured",
        }

    node = _node(
        {
            "chatId": "555",
            "text": "ping",
            "parseMode": "Markdown",
            "extra": "keep",
        }
    )
    ctx = _ctx({"telegram_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_telegram(node, [item], ctx=ctx))

    assert captured["chatId"] == "555"
    assert captured["text"] == "ping"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["messageId"] == 42
    assert out[0].json["text"] == "captured"
    assert out[0].json["parseMode"] == "Markdown"


# ── 3. http_response fallback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node({"chatId": "777", "text": "via http", "parseMode": "HTML"})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "message_id": 1234,
                    "chat": {"id": 777, "type": "private"},
                    "date": 1700000002,
                    "text": "via http",
                },
            }
        }
    )
    out = _out_items(await exec_telegram(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["messageId"] == 1234
    assert p["chatId"] == "777"
    assert p["text"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "telegram"


# ── 4. Offline synthetic response ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_response_has_envelope_fields() -> None:
    node = _node({"chatId": "321", "text": "offline"})
    out = _out_items(await exec_telegram(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    payload = out[0].json
    assert isinstance(payload["messageId"], int)
    assert 1 <= payload["messageId"] <= 10**9
    assert payload["chatId"] == "321"
    assert payload["text"] == "offline"
    assert payload["parseMode"] == "Markdown"
    assert payload["chat"] == {"id": 321, "type": "private"}
    assert isinstance(payload["chat"], dict)
    assert payload["source"] == "telegram"
    assert payload["mockSource"] == "offline"


# ── 5. $json fallbacks for chatId and text ────────────────────────────


@pytest.mark.asyncio
async def test_chat_id_and_text_default_from_json() -> None:
    node = _node({"parseMode": "HTML"})  # all from $json
    item = ExecutionItem(
        json={"chatId": "999", "text": "from json"}
    )
    out = _out_items(await exec_telegram(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["chatId"] == "999"
    assert p["text"] == "from json"
    assert p["parseMode"] == "HTML"


@pytest.mark.asyncio
async def test_chat_id_accepts_chat_id_alias() -> None:
    node = _node({"text": "x"})
    item = ExecutionItem(json={"chat_id": 5555})
    out = _out_items(await exec_telegram(node, [item], ctx=_ctx()))
    assert out[0].json["chatId"] == "5555"
    assert out[0].json["text"] == "x"


@pytest.mark.asyncio
async def test_text_prefers_text_then_message() -> None:
    node = _node({"chatId": "1"})  # no text parameter
    # text wins over message
    item = ExecutionItem(
        json={"text": "via-text", "message": "via-message"}
    )
    out = _out_items(await exec_telegram(node, [item], ctx=_ctx()))
    assert out[0].json["text"] == "via-text"

    # message used when no text
    item2 = ExecutionItem(json={"message": "via-message"})
    out2 = _out_items(await exec_telegram(node, [item2], ctx=_ctx()))
    assert out2[0].json["text"] == "via-message"


@pytest.mark.asyncio
async def test_chat_id_accepts_int() -> None:
    node = _node({"text": "x", "chatId": 4242})
    out = _out_items(await exec_telegram(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["chatId"] == "4242"


# ── 6. parseMode reflected and normalized ────────────────────────────


@pytest.mark.asyncio
async def test_parse_mode_reflected() -> None:
    for mode in ("Markdown", "HTML", "MarkdownV2"):
        node = _node({"chatId": "1", "text": "x", "parseMode": mode})
        out = _out_items(await exec_telegram(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert out[0].json["parseMode"] == mode


@pytest.mark.asyncio
async def test_parse_mode_default_markdown() -> None:
    node = _node({"chatId": "1", "text": "x"})  # no parseMode
    out = _out_items(await exec_telegram(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["parseMode"] == "Markdown"


@pytest.mark.asyncio
async def test_parse_mode_aliases_normalized() -> None:
    node = _node({"chatId": "1", "text": "x", "parseMode": "md"})
    out = _out_items(await exec_telegram(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["parseMode"] == "Markdown"

    node_html = _node({"chatId": "1", "text": "x", "parseMode": "html"})
    out_html = _out_items(
        await exec_telegram(node_html, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out_html[0].json["parseMode"] == "HTML"

    node_v2 = _node({"chatId": "1", "text": "x", "parseMode": "markdownV2"})
    out_v2 = _out_items(
        await exec_telegram(node_v2, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out_v2[0].json["parseMode"] == "MarkdownV2"


# ── 7. Empty text → no item ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_text_skips_item() -> None:
    node = _node({"chatId": "1", "text": "", "parseMode": "HTML"})
    out = _out_items(await exec_telegram(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_text_when_all_paths_empty_skips_item() -> None:
    node = _node({"chatId": "1"})
    item = ExecutionItem(json={"text": "", "message": ""})
    out = _out_items(await exec_telegram(node, [item], ctx=_ctx()))
    assert out == []


# ── 8. One output item per input ──────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({"parseMode": "HTML"})
    items = [
        ExecutionItem(json={"chatId": "1", "text": "a"}),
        ExecutionItem(json={"chatId": "2", "text": "b"}),
        ExecutionItem(json={"chatId": "3", "text": "c"}),
    ]
    out = _out_items(await exec_telegram(node, items, ctx=_ctx()))
    assert len(out) == 3
    texts = [o.json["text"] for o in out]
    assert texts == ["a", "b", "c"]
    assert all(o.json["source"] == "telegram" for o in out)


# ── 9. Descriptor registration (action) ──────────────────────────────


def test_telegram_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.telegram" in REGISTRY
    assert "n8n-nodes-base.telegram" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.telegram"] == "output"
    desc = REGISTRY["n8n-nodes-base.telegram"]
    assert desc.executor.endswith(":exec_telegram")
    assert desc.category == "output"
    assert set(TELEGRAM_PARSE_MODES) == {"Markdown", "HTML", "MarkdownV2"}


# ── 10. End-to-end: Manual Trigger → telegram (mock) → Set ──────────


def _doc(nodes, connections):
    return {"name": "telegram-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_telegram_set_sees_message_id() -> None:
    """Manual Trigger → telegram (telegram_response mock) → Set pulls messageId/chatId/text."""
    mocks = {
        "telegram_response": {
            "message_id": 4242,
            "chat": {"id": 12345, "type": "private"},
            "date": 1700000000,
            "text": "Hello E2E",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "tg1",
                "Telegram",
                "n8n-nodes-base.telegram",
                {
                    "chatId": "12345",
                    "text": "Hello E2E",
                    "parseMode": "HTML",
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
                            {"name": "result_chat", "value": "={{ $json.chatId }}", "type": "string"},
                            {"name": "result_text", "value": "={{ $json.text }}", "type": "string"},
                            {"name": "result_mode", "value": "={{ $json.parseMode }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Telegram", "type": "main", "index": 0}]]},
            "Telegram": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    telegram_step = next(s for s in result.steps if s.node_name == "Telegram")
    assert telegram_step.status == "success", telegram_step.error
    assert telegram_step.output_count == 1
    sample = telegram_step.sample_output[0]
    assert sample["json"]["messageId"] == 4242
    assert sample["json"]["chatId"] == "12345"
    assert sample["json"]["text"] == "Hello E2E"
    assert sample["json"]["parseMode"] == "HTML"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_id") == 4242
    assert fjson.get("result_chat") == "12345"
    assert fjson.get("result_text") == "Hello E2E"
    assert fjson.get("result_mode") == "HTML"


# ══════════════════════════════════════════════════════════════════════
#  telegramTrigger
# ══════════════════════════════════════════════════════════════════════


def _trigger_node(
    params: dict[str, Any] | None = None,
    *,
    id_: str = "tt1",
    name: str = "TelegramTrigger",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="n8n-nodes-base.telegramTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


# ── 11. telegram_update dict mock → fields extracted ──────────────────


@pytest.mark.asyncio
async def test_telegram_update_dict_mock_extracts_fields() -> None:
    update = {
        "update_id": 999,
        "message": {
            "message_id": 7,
            "from": {
                "id": 42,
                "first_name": "Alice",
                "is_bot": False,
            },
            "chat": {"id": 42, "type": "private"},
            "date": 1700000005,
            "text": "Hi from Telegram",
        },
    }
    ctx = _ctx({"telegram_update": update})
    node = _trigger_node({"webhookUrl": "https://example.com/webhook"})

    out = await exec_telegram_trigger(node, items=[], ctx=ctx)
    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["updateId"] == 999
    assert payload["messageId"] == 7
    assert payload["fromId"] == 42
    assert payload["fromName"] == "Alice"
    assert payload["chatId"] == "42"
    assert payload["text"] == "Hi from Telegram"
    assert payload["webhookUrl"] == "https://example.com/webhook"
    assert payload["source"] == "telegramTrigger"


# ── 12. telegram_update callable mock signature ─────────────────────


@pytest.mark.asyncio
async def test_telegram_update_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(node, ctx):
        captured["node"] = node
        captured["ctx"] = ctx
        return {
            "update_id": 1,
            "message": {
                "message_id": 100,
                "from": {"id": 1, "first_name": "Bot"},
                "chat": {"id": 1, "type": "private"},
                "date": 1700000010,
                "text": "callable mock",
            },
        }

    ctx = _ctx({"telegram_update": _mock})
    node = _trigger_node()

    out = await exec_telegram_trigger(node, items=[], ctx=ctx)
    assert captured["node"] is node
    assert captured["ctx"] is ctx

    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["updateId"] == 1
    assert payload["messageId"] == 100
    assert payload["fromName"] == "Bot"
    assert payload["text"] == "callable mock"


# ── 13. trigger_payload fallback ─────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_payload_fallback_used() -> None:
    fallback = {
        "update_id": 555,
        "message": {
            "message_id": 8,
            "from": {"id": 9, "first_name": "Carol"},
            "chat": {"id": 9, "type": "private"},
            "date": 1700000020,
            "text": "fallback text",
        },
    }
    ctx = _ctx({"trigger_payload": fallback})
    node = _trigger_node()

    out = await exec_telegram_trigger(node, items=[], ctx=ctx)
    items = out[0][1]
    payload = items[0].json
    assert payload["updateId"] == 555
    assert payload["fromName"] == "Carol"
    assert payload["text"] == "fallback text"


# ── 14. Offline synthetic update ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_update_emits_mock_message() -> None:
    node = _trigger_node()
    out = await exec_telegram_trigger(node, items=[], ctx=_ctx())
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert isinstance(payload["updateId"], int)
    assert payload["messageId"] == 1
    assert payload["fromId"] == 12345
    assert payload["fromName"] == "Mock"
    assert payload["chatId"] == "12345"
    assert payload["text"] == "Mock Telegram message"
    assert payload["source"] == "telegramTrigger"


# ── 15. Update with edited_message extracted ─────────────────────────


@pytest.mark.asyncio
async def test_edited_message_extracted_as_fallback() -> None:
    update = {
        "update_id": 12,
        "edited_message": {
            "message_id": 77,
            "from": {"id": 5, "first_name": "Edit"},
            "chat": {"id": 5, "type": "private"},
            "date": 1700000030,
            "text": "edited content",
        },
    }
    ctx = _ctx({"telegram_update": update})
    node = _trigger_node()
    out = await exec_telegram_trigger(node, items=[], ctx=ctx)
    payload = out[0][1][0].json
    assert payload["messageId"] == 77
    assert payload["text"] == "edited content"
    assert payload["fromName"] == "Edit"


# ── 16. Input items are passed through with trigger context merged ──


@pytest.mark.asyncio
async def test_input_items_passed_through_with_context() -> None:
    update = {
        "update_id": 3,
        "message": {
            "message_id": 4,
            "from": {"id": 6, "first_name": "X"},
            "chat": {"id": 6, "type": "private"},
            "date": 1700000040,
            "text": "merge me",
        },
    }
    ctx = _ctx({"telegram_update": update})
    node = _trigger_node()
    in_items = [ExecutionItem(json={"existing": "data"})]

    out = await exec_telegram_trigger(node, items=in_items, ctx=ctx)
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["existing"] == "data"
    assert payload["text"] == "merge me"
    assert payload["source"] == "telegramTrigger"


# ── 17. Descriptor registration (trigger) ───────────────────────────


def test_telegram_trigger_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.telegramTrigger" in REGISTRY
    assert "n8n-nodes-base.telegramTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.telegramTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.telegramTrigger"]
    assert desc.executor.endswith(":exec_telegram_trigger")
    assert desc.category == "trigger"


# ── 18. End-to-end: telegramTrigger as workflow start → Set sees text ─


@pytest.mark.asyncio
async def test_end_to_end_telegram_trigger_set_sees_text() -> None:
    """telegramTrigger → Set: a fresh run that starts with the Telegram
    trigger should drive a downstream Set to see the message ``text``."""
    mocks = {
        "telegram_update": {
            "update_id": 11,
            "message": {
                "message_id": 22,
                "from": {"id": 33, "first_name": "Dana"},
                "chat": {"id": 33, "type": "private"},
                "date": 1700000050,
                "text": "Triggered hello",
            },
        }
    }
    doc = _doc(
        [
            _n(
                "tt1",
                "TelegramTrigger",
                "n8n-nodes-base.telegramTrigger",
                {"webhookUrl": "https://example.com/tg-hook"},
            ),
            _n(
                "s1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_text", "value": "={{ $json.text }}", "type": "string"},
                            {"name": "result_chat", "value": "={{ $json.chatId }}", "type": "string"},
                            {"name": "result_from", "value": "={{ $json.fromName }}", "type": "string"},
                            {"name": "result_msg", "value": "={{ $json.messageId }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "TelegramTrigger": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="telegramTrigger")
    assert result.status == "success", result.error_message

    trigger_step = next(s for s in result.steps if s.node_name == "TelegramTrigger")
    assert trigger_step.status == "success", trigger_step.error
    assert trigger_step.output_count == 1
    sample = trigger_step.sample_output[0]
    assert sample["json"]["text"] == "Triggered hello"
    assert sample["json"]["fromName"] == "Dana"

    final = result.final_items
    assert final, "expected final items from Stamp"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_text") == "Triggered hello"
    assert fjson.get("result_chat") == "33"
    assert fjson.get("result_from") == "Dana"
    assert fjson.get("result_msg") == 22
