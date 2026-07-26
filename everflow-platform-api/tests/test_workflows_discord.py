"""Tests for the Discord node executors
(``n8n-nodes-base.discord`` and ``n8n-nodes-base.discordTrigger``).

Covers:

- ``discord``:
    - ``discord_response`` dict mock → envelope used verbatim
    - ``discord_response`` callable mock receives
      ``(channelId, content, params, item, ctx)``
    - ``http_response`` fallback unwraps a JSON body
    - Offline synthetic response has ``id`` / ``author.bot=True`` /
      ``channel_id`` / ``content`` / ``tts`` / ``embeds`` / ``timestamp``
    - ``channelId``/``content`` defaults from ``$json`` (channelId/channel_id,
      content/text/message)
    - ``username`` override reflected
    - ``tts`` reflected
    - ``embeds`` passed through
    - Empty content + no embeds → no item
    - End-to-end: Manual → discord (mock) → Set sees ``messageId``
- ``discordTrigger``:
    - ``discord_event`` dict mock → fields extracted
    - ``discord_event`` callable mock receives ``(node, ctx)``
    - ``trigger_payload`` fallback
    - Offline synthetic event with ``t='MESSAGE_CREATE'``
    - End-to-end: discordTrigger as workflow start → Set sees ``content``
- Descriptor registration (CI invariant) for both types
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.discord import (
    DISCORD_DEFAULT_EVENT,
    MOCK_BOT_ID,
    exec_discord,
    exec_discord_trigger,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.discord",
    id_: str = "d1",
    name: str = "Discord",
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


# ── 1. discord_response dict mock ─────────────────────────────────────


@pytest.mark.asyncio
async def test_discord_response_dict_mock_is_used_verbatim() -> None:
    node = _node({"channelId": "12345", "content": "Hello from Discord"})
    ctx = _ctx(
        {
            "discord_response": {
                "id": "987654321098765432",
                "channel_id": "12345",
                "content": "Hello from Discord",
                "author": {
                    "id": "MOCK_BOT_ID",
                    "username": "mock-bot",
                    "bot": True,
                },
                "timestamp": "2024-01-01T00:00:00Z",
                "tts": False,
                "embeds": [],
            }
        }
    )
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    payload = out[0].json
    assert payload["messageId"] == "987654321098765432"
    assert payload["channelId"] == "12345"
    assert payload["content"] == "Hello from Discord"
    assert payload["ok"] is True
    assert payload["source"] == "discord"
    assert payload["author"]["bot"] is True
    assert payload["author"]["username"] == "mock-bot"
    assert payload["tts"] is False
    assert payload["embeds"] == []


# ── 2. discord_response callable mock signature ──────────────────────


@pytest.mark.asyncio
async def test_discord_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(channel_id, content, params, item, ctx):
        captured["channelId"] = channel_id
        captured["content"] = content
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "42",
            "channel_id": channel_id,
            "content": "captured",
            "author": {
                "id": MOCK_BOT_ID,
                "username": "mock-bot",
                "bot": True,
            },
            "timestamp": "2024-01-01T00:00:00Z",
            "tts": False,
            "embeds": [],
        }

    node = _node(
        {
            "channelId": "555",
            "content": "ping",
            "username": "alt-bot",
            "extra": "keep",
        }
    )
    ctx = _ctx({"discord_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_discord(node, [item], ctx=ctx))

    assert captured["channelId"] == "555"
    assert captured["content"] == "ping"
    assert captured["params"]["username"] == "alt-bot"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["messageId"] == "42"
    assert out[0].json["content"] == "captured"
    assert out[0].json["username"] == "alt-bot"


# ── 3. http_response fallback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node({"channelId": "777", "content": "via http"})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "id": "1234",
                    "channel_id": "777",
                    "content": "via http",
                    "author": {
                        "id": MOCK_BOT_ID,
                        "username": "mock-bot",
                        "bot": True,
                    },
                    "timestamp": "2024-01-01T00:00:00Z",
                    "tts": False,
                    "embeds": [],
                },
            }
        }
    )
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["messageId"] == "1234"
    assert p["channelId"] == "777"
    assert p["content"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "discord"


# ── 4. Offline synthetic response ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_response_has_envelope_fields() -> None:
    node = _node({"channelId": "321", "content": "offline"})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    payload = out[0].json
    assert isinstance(payload["messageId"], str)
    assert payload["messageId"].isdigit()
    assert len(payload["messageId"]) <= 18
    assert payload["channelId"] == "321"
    assert payload["content"] == "offline"
    assert payload["ok"] is True
    assert payload["author"]["bot"] is True
    assert payload["author"]["id"] == MOCK_BOT_ID
    assert payload["tts"] is False
    assert payload["embeds"] == []
    assert payload["timestamp"].endswith("Z")
    assert payload["source"] == "discord"
    assert payload["mockSource"] == "offline"


# ── 5. $json fallbacks for channelId and content ─────────────────────


@pytest.mark.asyncio
async def test_channel_id_and_content_default_from_json() -> None:
    node = _node({})  # all from $json
    item = ExecutionItem(json={"channelId": "999", "content": "from json"})
    out = _out_items(await exec_discord(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["channelId"] == "999"
    assert p["content"] == "from json"


@pytest.mark.asyncio
async def test_channel_id_accepts_channel_id_alias() -> None:
    node = _node({"content": "x"})
    item = ExecutionItem(json={"channel_id": 5555})
    out = _out_items(await exec_discord(node, [item], ctx=_ctx()))
    assert out[0].json["channelId"] == "5555"
    assert out[0].json["content"] == "x"


@pytest.mark.asyncio
async def test_content_prefers_content_then_text_then_message() -> None:
    node = _node({"channelId": "1"})  # no content parameter
    # content wins over text and message
    item = ExecutionItem(
        json={
            "content": "via-content",
            "text": "via-text",
            "message": "via-message",
        }
    )
    out = _out_items(await exec_discord(node, [item], ctx=_ctx()))
    assert out[0].json["content"] == "via-content"

    # text used when no content
    item2 = ExecutionItem(json={"text": "via-text", "message": "via-message"})
    out2 = _out_items(await exec_discord(node, [item2], ctx=_ctx()))
    assert out2[0].json["content"] == "via-text"

    # message used when no content or text
    item3 = ExecutionItem(json={"message": "via-message"})
    out3 = _out_items(await exec_discord(node, [item3], ctx=_ctx()))
    assert out3[0].json["content"] == "via-message"


@pytest.mark.asyncio
async def test_channel_id_accepts_int() -> None:
    node = _node({"content": "x", "channelId": 4242})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["channelId"] == "4242"


# ── 6. username override reflected ───────────────────────────────────


@pytest.mark.asyncio
async def test_username_override_reflected() -> None:
    node = _node({"channelId": "1", "content": "x", "username": "alt-bot"})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["username"] == "alt-bot"


@pytest.mark.asyncio
async def test_username_default_empty() -> None:
    node = _node({"channelId": "1", "content": "x"})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["username"] == ""


# ── 7. tts reflected ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tts_reflected_true() -> None:
    node = _node({"channelId": "1", "content": "x", "tts": True})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["tts"] is True


@pytest.mark.asyncio
async def test_tts_reflected_false_default() -> None:
    node = _node({"channelId": "1", "content": "x"})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["tts"] is False


@pytest.mark.asyncio
async def test_tts_string_parsed() -> None:
    node = _node({"channelId": "1", "content": "x", "tts": "true"})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["tts"] is True


# ── 8. embeds passed through ────────────────────────────────────────


@pytest.mark.asyncio
async def test_embeds_passed_through() -> None:
    embeds = [
        {"title": "Hello", "description": "World", "color": 0xFF0000},
        {"title": "Another"},
    ]
    node = _node({"channelId": "1", "content": "x", "embeds": embeds})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["embeds"] == embeds


@pytest.mark.asyncio
async def test_embeds_default_empty() -> None:
    node = _node({"channelId": "1", "content": "x"})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["embeds"] == []


# ── 9. Empty content + no embeds → no item ──────────────────────────


@pytest.mark.asyncio
async def test_empty_content_no_embeds_skips_item() -> None:
    node = _node({"channelId": "1", "content": ""})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_content_with_embeds_emits_item() -> None:
    node = _node({"channelId": "1", "content": "", "embeds": [{"title": "hi"}]})
    out = _out_items(await exec_discord(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["embeds"] == [{"title": "hi"}]


@pytest.mark.asyncio
async def test_empty_content_when_all_paths_empty_skips_item() -> None:
    node = _node({"channelId": "1"})
    item = ExecutionItem(json={"content": "", "text": "", "message": ""})
    out = _out_items(await exec_discord(node, [item], ctx=_ctx()))
    assert out == []


# ── 10. One output item per input ────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({})
    items = [
        ExecutionItem(json={"channelId": "1", "content": "a"}),
        ExecutionItem(json={"channelId": "2", "content": "b"}),
        ExecutionItem(json={"channelId": "3", "content": "c"}),
    ]
    out = _out_items(await exec_discord(node, items, ctx=_ctx()))
    assert len(out) == 3
    contents = [o.json["content"] for o in out]
    assert contents == ["a", "b", "c"]
    assert all(o.json["source"] == "discord" for o in out)


# ── 11. Descriptor registration (action) ────────────────────────────


def test_discord_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.discord" in REGISTRY
    assert "n8n-nodes-base.discord" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.discord"] == "output"
    desc = REGISTRY["n8n-nodes-base.discord"]
    assert desc.executor.endswith(":exec_discord")
    assert desc.category == "output"
    assert DISCORD_DEFAULT_EVENT == "MESSAGE_CREATE"
    assert MOCK_BOT_ID == "MOCK_BOT_ID"


# ── 12. End-to-end: Manual Trigger → discord (mock) → Set ───────────


def _doc(nodes, connections):
    return {"name": "discord-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_discord_set_sees_message_id() -> None:
    """Manual Trigger → discord (discord_response mock) → Set pulls
    messageId/channelId/content/tts."""
    mocks = {
        "discord_response": {
            "id": "4242",
            "channel_id": "12345",
            "content": "Hello E2E",
            "author": {
                "id": MOCK_BOT_ID,
                "username": "mock-bot",
                "bot": True,
            },
            "timestamp": "2024-01-01T00:00:00Z",
            "tts": True,
            "embeds": [],
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "d1",
                "Discord",
                "n8n-nodes-base.discord",
                {
                    "channelId": "12345",
                    "content": "Hello E2E",
                    "tts": True,
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
                            {"name": "result_channel", "value": "={{ $json.channelId }}", "type": "string"},
                            {"name": "result_content", "value": "={{ $json.content }}", "type": "string"},
                            {"name": "result_tts", "value": "={{ $json.tts }}", "type": "boolean"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Discord", "type": "main", "index": 0}]]},
            "Discord": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    discord_step = next(s for s in result.steps if s.node_name == "Discord")
    assert discord_step.status == "success", discord_step.error
    assert discord_step.output_count == 1
    sample = discord_step.sample_output[0]
    assert sample["json"]["messageId"] == "4242"
    assert sample["json"]["channelId"] == "12345"
    assert sample["json"]["content"] == "Hello E2E"
    assert sample["json"]["tts"] is True

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_id") == "4242"
    assert fjson.get("result_channel") == "12345"
    assert fjson.get("result_content") == "Hello E2E"
    assert fjson.get("result_tts") is True


# ══════════════════════════════════════════════════════════════════════
#  discordTrigger
# ══════════════════════════════════════════════════════════════════════


def _trigger_node(
    params: dict[str, Any] | None = None,
    *,
    id_: str = "dt1",
    name: str = "DiscordTrigger",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type="n8n-nodes-base.discordTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


# ── 13. discord_event dict mock → fields extracted ───────────────────


@pytest.mark.asyncio
async def test_discord_event_dict_mock_extracts_fields() -> None:
    event = {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": "777",
            "channel_id": "12345",
            "guild_id": "67890",
            "author": {
                "id": "11111",
                "username": "Alice",
                "bot": False,
            },
            "content": "Hi from Discord",
            "timestamp": "2024-01-01T00:00:00Z",
        },
        "s": 5,
        "op": 0,
    }
    ctx = _ctx({"discord_event": event})
    node = _trigger_node({"event": "MESSAGE_CREATE"})

    out = await exec_discord_trigger(node, items=[], ctx=ctx)
    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["eventType"] == "MESSAGE_CREATE"
    assert payload["messageId"] == "777"
    assert payload["channelId"] == "12345"
    assert payload["guildId"] == "67890"
    assert payload["authorId"] == "11111"
    assert payload["authorUsername"] == "Alice"
    assert payload["content"] == "Hi from Discord"
    assert payload["timestamp"] == "2024-01-01T00:00:00Z"
    assert payload["source"] == "discordTrigger"


# ── 14. discord_event callable mock signature ──────────────────────


@pytest.mark.asyncio
async def test_discord_event_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(node, ctx):
        captured["node"] = node
        captured["ctx"] = ctx
        return {
            "t": "MESSAGE_CREATE",
            "d": {
                "id": "100",
                "channel_id": "1",
                "guild_id": "2",
                "author": {"id": "1", "username": "Bot", "bot": False},
                "content": "callable mock",
                "timestamp": "2024-01-01T00:00:00Z",
            },
            "s": 1,
            "op": 0,
        }

    ctx = _ctx({"discord_event": _mock})
    node = _trigger_node()

    out = await exec_discord_trigger(node, items=[], ctx=ctx)
    assert captured["node"] is node
    assert captured["ctx"] is ctx

    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["eventType"] == "MESSAGE_CREATE"
    assert payload["messageId"] == "100"
    assert payload["authorUsername"] == "Bot"
    assert payload["content"] == "callable mock"


# ── 15. trigger_payload fallback ────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_payload_fallback_used() -> None:
    fallback = {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": "555",
            "channel_id": "9",
            "guild_id": "10",
            "author": {"id": "9", "username": "Carol", "bot": False},
            "content": "fallback content",
            "timestamp": "2024-01-01T00:00:00Z",
        },
        "s": 1,
        "op": 0,
    }
    ctx = _ctx({"trigger_payload": fallback})
    node = _trigger_node()

    out = await exec_discord_trigger(node, items=[], ctx=ctx)
    items = out[0][1]
    payload = items[0].json
    assert payload["messageId"] == "555"
    assert payload["channelId"] == "9"
    assert payload["authorUsername"] == "Carol"
    assert payload["content"] == "fallback content"


# ── 16. Offline synthetic event ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_event_emits_mock_message() -> None:
    node = _trigger_node()
    out = await exec_discord_trigger(node, items=[], ctx=_ctx())
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["eventType"] == "MESSAGE_CREATE"
    assert isinstance(payload["messageId"], str)
    assert payload["messageId"].isdigit()
    assert payload["channelId"] == "12345"
    assert payload["guildId"] == "67890"
    assert payload["authorId"] == "11111"
    assert payload["authorUsername"] == "mockuser"
    assert payload["content"] == "Mock Discord message"
    assert payload["timestamp"].endswith("Z")
    assert payload["source"] == "discordTrigger"


# ── 17. Input items are passed through with trigger context merged ───


@pytest.mark.asyncio
async def test_input_items_passed_through_with_context() -> None:
    event = {
        "t": "MESSAGE_CREATE",
        "d": {
            "id": "4",
            "channel_id": "6",
            "guild_id": "7",
            "author": {"id": "6", "username": "X", "bot": False},
            "content": "merge me",
            "timestamp": "2024-01-01T00:00:00Z",
        },
        "s": 1,
        "op": 0,
    }
    ctx = _ctx({"discord_event": event})
    node = _trigger_node()
    in_items = [ExecutionItem(json={"existing": "data"})]

    out = await exec_discord_trigger(node, items=in_items, ctx=ctx)
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["existing"] == "data"
    assert payload["content"] == "merge me"
    assert payload["source"] == "discordTrigger"


# ── 18. Descriptor registration (trigger) ───────────────────────────


def test_discord_trigger_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.discordTrigger" in REGISTRY
    assert "n8n-nodes-base.discordTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.discordTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.discordTrigger"]
    assert desc.executor.endswith(":exec_discord_trigger")
    assert desc.category == "trigger"


# ── 19. End-to-end: discordTrigger as workflow start → Set sees content ─


@pytest.mark.asyncio
async def test_end_to_end_discord_trigger_set_sees_content() -> None:
    """discordTrigger → Set: a fresh run that starts with the Discord
    trigger should drive a downstream Set to see the message ``content``."""
    mocks = {
        "discord_event": {
            "t": "MESSAGE_CREATE",
            "d": {
                "id": "22",
                "channel_id": "33",
                "guild_id": "44",
                "author": {"id": "33", "username": "Dana", "bot": False},
                "content": "Triggered hello",
                "timestamp": "2024-01-01T00:00:00Z",
            },
            "s": 1,
            "op": 0,
        }
    }
    doc = _doc(
        [
            _n(
                "dt1",
                "DiscordTrigger",
                "n8n-nodes-base.discordTrigger",
                {"event": "MESSAGE_CREATE"},
            ),
            _n(
                "s1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_content", "value": "={{ $json.content }}", "type": "string"},
                            {"name": "result_channel", "value": "={{ $json.channelId }}", "type": "string"},
                            {"name": "result_author", "value": "={{ $json.authorUsername }}", "type": "string"},
                            {"name": "result_msg", "value": "={{ $json.messageId }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "DiscordTrigger": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="discordTrigger")
    assert result.status == "success", result.error_message

    trigger_step = next(s for s in result.steps if s.node_name == "DiscordTrigger")
    assert trigger_step.status == "success", trigger_step.error
    assert trigger_step.output_count == 1
    sample = trigger_step.sample_output[0]
    assert sample["json"]["content"] == "Triggered hello"
    assert sample["json"]["authorUsername"] == "Dana"

    final = result.final_items
    assert final, "expected final items from Stamp"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_content") == "Triggered hello"
    assert fjson.get("result_channel") == "33"
    assert fjson.get("result_author") == "Dana"
    assert fjson.get("result_msg") == "22"
