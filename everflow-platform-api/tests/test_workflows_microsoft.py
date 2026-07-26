"""Tests for the Microsoft node executors.

Covers:

- ``microsoftTeams``:
    - ``teams_response`` dict mock - envelope used verbatim
    - ``teams_response`` callable mock receives ``(channelId, message, params, item, ctx)``
    - ``http_response`` fallback unwraps a JSON body
    - Offline synthetic response has ``createdDateTime`` and random id
    - ``teamId`` / ``channelId`` / ``message`` defaults from ``$json``
    - ``contentType`` reflected (``text`` / ``html``)
    - Empty ``message`` - no item emitted
    - End-to-end: Manual Trigger -> microsoftTeams (mock) -> Set sees ``messageId``
- ``microsoftOutlook``:
    - ``outlook_response`` dict mock - envelope used verbatim
    - ``outlook_response`` callable mock receives ``(to, subject, body, params, item, ctx)``
    - ``http_response`` fallback unwraps a JSON body
    - Offline synthetic response has ``internetMessageId`` and random id
    - ``to`` / ``subject`` / ``body`` defaults from ``$json``
    - ``bodyContentType`` reflected (``Text`` / ``HTML``)
    - ``cc`` / ``bcc`` honored
    - Empty ``subject`` or empty ``body`` - no item emitted
    - End-to-end: Manual Trigger -> microsoftOutlook (mock) -> Set sees ``messageId`` and ``subject``
- Both descriptors registered (CI invariant).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.microsoft import (
    MICROSOFT_OUTLOOK_BODY_CONTENT_TYPES,
    MICROSOFT_TEAMS_CONTENT_TYPES,
    exec_microsoft_outlook,
    exec_microsoft_teams,
)


# - Helpers -


def _node(
    params: dict[str, Any],
    *,
    type_: str,
    id_: str,
    name: str,
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


def _teams_node(params: dict[str, Any], **kw: Any) -> ExecNode:
    return _node(
        params, type_="n8n-nodes-base.microsoftTeams", id_="mt1", name="Teams", **kw
    )


def _outlook_node(params: dict[str, Any], **kw: Any) -> ExecNode:
    return _node(
        params,
        type_="n8n-nodes-base.microsoftOutlook",
        id_="mo1",
        name="Outlook",
        **kw,
    )


# - microsoftTeams: 1. teams_response dict mock is used verbatim -


@pytest.mark.asyncio
async def test_teams_response_dict_mock_is_used_verbatim() -> None:
    node = _teams_node(
        {
            "teamId": "team-1",
            "channelId": "channel-1",
            "message": "Hello teams",
        }
    )
    ctx = _ctx(
        {
            "teams_response": {
                "id": "mock-msg-id-001",
                "createdDateTime": "2025-01-01T00:00:00Z",
                "from": {
                    "user": {
                        "id": "U_MOCK",
                        "displayName": "Mocker",
                    }
                },
                "body": {
                    "contentType": "text",
                    "content": "Hello teams",
                },
                "channelId": "channel-1",
            }
        }
    )
    out = _out_items(
        await exec_microsoft_teams(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["messageId"] == "mock-msg-id-001"
    assert payload["teamId"] == "team-1"
    assert payload["channelId"] == "channel-1"
    assert payload["message"] == "Hello teams"
    assert payload["contentType"] == "text"
    assert payload["createdDateTime"] == "2025-01-01T00:00:00Z"
    assert payload["ok"] is True
    assert payload["source"] == "microsoftTeams"


# - microsoftTeams: 2. teams_response callable mock signature -


@pytest.mark.asyncio
async def test_teams_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(channel_id, message, params, item, ctx):
        captured["channelId"] = channel_id
        captured["message"] = message
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "callable-id",
            "createdDateTime": "2025-01-01T00:00:01Z",
            "from": {
                "user": {"id": "U_X", "displayName": "X"},
            },
            "body": {"contentType": "text", "content": message},
            "channelId": channel_id,
        }

    node = _teams_node(
        {
            "teamId": "team-2",
            "channelId": "channel-2",
            "message": "Hi callable",
            "extra": "keep",
        }
    )
    ctx = _ctx({"teams_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_microsoft_teams(node, [item], ctx=ctx))

    assert captured["channelId"] == "channel-2"
    assert captured["message"] == "Hi callable"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["messageId"] == "callable-id"
    assert out[0].json["message"] == "Hi callable"


# - microsoftTeams: 3. http_response fallback -


@pytest.mark.asyncio
async def test_teams_http_response_fallback_unwraps_json_body() -> None:
    node = _teams_node(
        {
            "teamId": "team-3",
            "channelId": "channel-3",
            "message": "http fallback",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 201,
                "body": {
                    "id": "http-id",
                    "createdDateTime": "2025-02-02T00:00:00Z",
                    "from": {
                        "user": {"id": "U_HTTP", "displayName": "Http User"},
                    },
                    "body": {"contentType": "html", "content": "<p>hi</p>"},
                },
            }
        }
    )
    out = _out_items(
        await exec_microsoft_teams(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert out[0].json["messageId"] == "http-id"
    assert out[0].json["createdDateTime"] == "2025-02-02T00:00:00Z"
    assert out[0].json["contentType"] == "html"
    assert out[0].json["mockSource"] == "http_response"


# - microsoftTeams: 4. Offline synthetic response -


@pytest.mark.asyncio
async def test_teams_offline_synthetic_response_has_created_date_time() -> None:
    node = _teams_node(
        {
            "teamId": "team-4",
            "channelId": "channel-4",
            "message": "offline",
        }
    )
    out = _out_items(
        await exec_microsoft_teams(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    payload = out[0].json
    assert isinstance(payload["messageId"], str) and payload["messageId"]
    assert payload["createdDateTime"].endswith("Z")
    assert payload["contentType"] == "text"
    assert payload["message"] == "offline"
    assert payload["channelId"] == "channel-4"
    assert payload["source"] == "microsoftTeams"
    assert payload["mockSource"] == "offline"
    assert payload["ok"] is True


# - microsoftTeams: 5. $json fallbacks for teamId/channelId/message -


@pytest.mark.asyncio
async def test_teams_team_channel_message_default_from_json() -> None:
    node = _teams_node({})  # all from $json
    item = ExecutionItem(
        json={
            "teamId": "team-json",
            "channelId": "channel-json",
            "message": "msg-json",
        }
    )
    out = _out_items(await exec_microsoft_teams(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["teamId"] == "team-json"
    assert p["channelId"] == "channel-json"
    assert p["message"] == "msg-json"


@pytest.mark.asyncio
async def test_teams_channel_id_falls_back_to_channel_id_snake() -> None:
    node = _teams_node({"teamId": "team-z", "message": "hello"})
    item = ExecutionItem(json={"channel_id": "channel-z"})
    out = _out_items(await exec_microsoft_teams(node, [item], ctx=_ctx()))
    assert out[0].json["channelId"] == "channel-z"


@pytest.mark.asyncio
async def test_teams_message_prefers_message_then_text_then_content() -> None:
    node = _teams_node({"teamId": "team-z", "channelId": "channel-z"})

    item1 = ExecutionItem(
        json={"message": "m", "text": "t", "content": "c"}
    )
    out1 = _out_items(await exec_microsoft_teams(node, [item1], ctx=_ctx()))
    assert out1[0].json["message"] == "m"

    item2 = ExecutionItem(json={"text": "t", "content": "c"})
    out2 = _out_items(await exec_microsoft_teams(node, [item2], ctx=_ctx()))
    assert out2[0].json["message"] == "t"

    item3 = ExecutionItem(json={"content": "c"})
    out3 = _out_items(await exec_microsoft_teams(node, [item3], ctx=_ctx()))
    assert out3[0].json["message"] == "c"


# - microsoftTeams: 6. contentType reflected -


@pytest.mark.asyncio
async def test_teams_content_type_reflected() -> None:
    node_html = _teams_node(
        {
            "teamId": "team-5",
            "channelId": "channel-5",
            "message": "<p>html</p>",
            "contentType": "html",
        }
    )
    out_html = _out_items(
        await exec_microsoft_teams(node_html, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out_html[0].json["contentType"] == "html"

    node_text = _teams_node(
        {
            "teamId": "team-5",
            "channelId": "channel-5",
            "message": "plain",
        }
    )
    out_text = _out_items(
        await exec_microsoft_teams(node_text, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out_text[0].json["contentType"] == "text"


# - microsoftTeams: 7. Empty message - no item -


@pytest.mark.asyncio
async def test_teams_empty_message_skips_item() -> None:
    node = _teams_node(
        {"teamId": "team-6", "channelId": "channel-6", "message": ""}
    )
    out = _out_items(
        await exec_microsoft_teams(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_teams_empty_message_only_in_json_skips_item() -> None:
    node = _teams_node({"teamId": "team-6", "channelId": "channel-6"})
    item = ExecutionItem(json={"message": ""})
    out = _out_items(await exec_microsoft_teams(node, [item], ctx=_ctx()))
    assert out == []


# - microsoftTeams: 8. Multiple input items produce one item each -


@pytest.mark.asyncio
async def test_teams_one_output_item_per_input() -> None:
    node = _teams_node(
        {"teamId": "team-multi", "channelId": "channel-multi"}
    )
    items = [
        ExecutionItem(json={"message": "A"}),
        ExecutionItem(json={"message": "B"}),
        ExecutionItem(json={"message": "C"}),
    ]
    out = _out_items(await exec_microsoft_teams(node, items, ctx=_ctx()))
    assert len(out) == 3
    assert [o.json["message"] for o in out] == ["A", "B", "C"]
    assert all(
        isinstance(o.json["messageId"], str) and o.json["messageId"] for o in out
    )


# - microsoftOutlook: 1. outlook_response dict mock used verbatim -


@pytest.mark.asyncio
async def test_outlook_response_dict_mock_is_used_verbatim() -> None:
    node = _outlook_node(
        {
            "to": "alice@example.com",
            "subject": "Hi",
            "body": "Hello Alice",
        }
    )
    ctx = _ctx(
        {
            "outlook_response": {
                "id": "outlook-msg-001",
                "conversationId": "outlook-conv-001",
                "internetMessageId": "<001@outlook.com>",
                "from": {
                    "emailAddress": {"name": "Alice", "address": "alice@outlook.com"},
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "name": "Alice",
                            "address": "alice@example.com",
                        }
                    }
                ],
            }
        }
    )
    out = _out_items(
        await exec_microsoft_outlook(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    p = out[0].json
    assert p["messageId"] == "outlook-msg-001"
    assert p["internetMessageId"] == "<001@outlook.com>"
    assert p["to"] == "alice@example.com"
    assert p["subject"] == "Hi"
    assert p["body"] == "Hello Alice"
    assert p["bodyContentType"] == "Text"
    assert p["ok"] is True
    assert p["source"] == "microsoftOutlook"


# - microsoftOutlook: 2. outlook_response callable mock signature -


@pytest.mark.asyncio
async def test_outlook_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(to, subject, body, params, item, ctx):
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "cap-id",
            "conversationId": "cap-conv",
            "internetMessageId": "<cap@outlook.com>",
            "from": {
                "emailAddress": {"name": "Cap", "address": "cap@outlook.com"},
            },
            "toRecipients": [],
        }

    node = _outlook_node(
        {
            "to": "bob@example.com",
            "subject": "Greetings",
            "body": "Hi Bob",
            "extra": "keep",
        }
    )
    ctx = _ctx({"outlook_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_microsoft_outlook(node, [item], ctx=ctx))

    assert captured["to"] == "bob@example.com"
    assert captured["subject"] == "Greetings"
    assert captured["body"] == "Hi Bob"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["messageId"] == "cap-id"
    assert out[0].json["internetMessageId"] == "<cap@outlook.com>"


# - microsoftOutlook: 3. http_response fallback -


@pytest.mark.asyncio
async def test_outlook_http_response_fallback_unwraps_json_body() -> None:
    node = _outlook_node(
        {
            "to": "carol@example.com",
            "subject": "Subject A",
            "body": "Body A",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 202,
                "body": {
                    "id": "http-out-id",
                    "conversationId": "http-out-conv",
                    "internetMessageId": "<http-out@outlook.com>",
                    "from": {
                        "emailAddress": {
                            "name": "Carol",
                            "address": "carol@outlook.com",
                        }
                    },
                    "toRecipients": [],
                },
            }
        }
    )
    out = _out_items(
        await exec_microsoft_outlook(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert out[0].json["messageId"] == "http-out-id"
    assert out[0].json["internetMessageId"] == "<http-out@outlook.com>"
    assert out[0].json["mockSource"] == "http_response"


# - microsoftOutlook: 4. Offline synthetic response -


@pytest.mark.asyncio
async def test_outlook_offline_synthetic_response_has_internet_message_id() -> None:
    node = _outlook_node(
        {
            "to": "dave@example.com",
            "subject": "Offline",
            "body": "Hello",
        }
    )
    out = _out_items(
        await exec_microsoft_outlook(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert isinstance(p["messageId"], str) and p["messageId"]
    assert p["internetMessageId"].endswith("@outlook.com>")
    assert p["internetMessageId"].startswith("<")
    assert p["to"] == "dave@example.com"
    assert p["subject"] == "Offline"
    assert p["body"] == "Hello"
    assert p["sentDateTime"].endswith("Z")
    assert p["source"] == "microsoftOutlook"
    assert p["mockSource"] == "offline"


# - microsoftOutlook: 5. $json fallbacks for to/subject/body -


@pytest.mark.asyncio
async def test_outlook_to_subject_body_default_from_json() -> None:
    node = _outlook_node({})
    item = ExecutionItem(
        json={
            "to": "erin@example.com",
            "subject": "From JSON",
            "body": "Body from body field",
        }
    )
    out = _out_items(await exec_microsoft_outlook(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["to"] == "erin@example.com"
    assert p["subject"] == "From JSON"
    assert p["body"] == "Body from body field"


@pytest.mark.asyncio
async def test_outlook_body_prefers_body_then_message_then_text() -> None:
    node = _outlook_node({"to": "z@x.com", "subject": "x"})

    item1 = ExecutionItem(
        json={"body": "body-field", "message": "m", "text": "t"}
    )
    out1 = _out_items(await exec_microsoft_outlook(node, [item1], ctx=_ctx()))
    assert out1[0].json["body"] == "body-field"

    item2 = ExecutionItem(json={"message": "m", "text": "t"})
    out2 = _out_items(await exec_microsoft_outlook(node, [item2], ctx=_ctx()))
    assert out2[0].json["body"] == "m"

    item3 = ExecutionItem(json={"text": "t"})
    out3 = _out_items(await exec_microsoft_outlook(node, [item3], ctx=_ctx()))
    assert out3[0].json["body"] == "t"


@pytest.mark.asyncio
async def test_outlook_to_accepts_list() -> None:
    node = _outlook_node(
        {
            "to": ["a@example.com", "b@example.com"],
            "subject": "Multi",
            "body": "Hi all",
        }
    )
    out = _out_items(
        await exec_microsoft_outlook(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out[0].json["to"] == "a@example.com, b@example.com"


# - microsoftOutlook: 6. bodyContentType reflected -


@pytest.mark.asyncio
async def test_outlook_body_content_type_reflected() -> None:
    node_html = _outlook_node(
        {
            "to": "html@example.com",
            "subject": "HTML",
            "body": "<p>hi</p>",
            "bodyContentType": "HTML",
        }
    )
    out_html = _out_items(
        await exec_microsoft_outlook(node_html, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out_html[0].json["bodyContentType"] == "HTML"

    node_text = _outlook_node(
        {"to": "t@example.com", "subject": "Plain", "body": "hi"}
    )
    out_text = _out_items(
        await exec_microsoft_outlook(node_text, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out_text[0].json["bodyContentType"] == "Text"


# - microsoftOutlook: 7. cc/bcc honored -


@pytest.mark.asyncio
async def test_outlook_cc_and_bcc_honored() -> None:
    node = _outlook_node(
        {
            "to": "frank@example.com",
            "cc": ["cc1@example.com", "cc2@example.com"],
            "bcc": "bcc@example.com",
            "subject": "FYI",
            "body": "see below",
        }
    )
    out = _out_items(
        await exec_microsoft_outlook(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    p = out[0].json
    assert p["cc"] == "cc1@example.com, cc2@example.com"
    assert p["bcc"] == "bcc@example.com"


# - microsoftOutlook: 8. Empty subject or body - no item -


@pytest.mark.asyncio
async def test_outlook_empty_subject_skips_item() -> None:
    node = _outlook_node(
        {"to": "i@example.com", "subject": "", "body": "should not send"}
    )
    out = _out_items(
        await exec_microsoft_outlook(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_outlook_empty_body_skips_item() -> None:
    node = _outlook_node(
        {"to": "i@example.com", "subject": "Hi", "body": ""}
    )
    out = _out_items(
        await exec_microsoft_outlook(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_outlook_empty_subject_when_only_in_json_skips_item() -> None:
    node = _outlook_node({"to": "i@example.com"})
    item = ExecutionItem(json={"subject": "", "body": "no subject here"})
    out = _out_items(await exec_microsoft_outlook(node, [item], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_outlook_empty_body_when_only_in_json_skips_item() -> None:
    node = _outlook_node({"to": "i@example.com"})
    item = ExecutionItem(json={"subject": "Hi", "body": ""})
    out = _out_items(await exec_microsoft_outlook(node, [item], ctx=_ctx()))
    assert out == []


# - microsoftOutlook: 9. Multiple input items produce one each -


@pytest.mark.asyncio
async def test_outlook_one_output_item_per_input() -> None:
    node = _outlook_node({})
    items = [
        ExecutionItem(json={"to": "a@x.com", "subject": "A", "body": "a"}),
        ExecutionItem(json={"to": "b@x.com", "subject": "B", "body": "b"}),
        ExecutionItem(json={"to": "c@x.com", "subject": "C", "body": "c"}),
    ]
    out = _out_items(await exec_microsoft_outlook(node, items, ctx=_ctx()))
    assert len(out) == 3
    assert [o.json["subject"] for o in out] == ["A", "B", "C"]
    assert all(
        isinstance(o.json["messageId"], str) and o.json["messageId"] for o in out
    )


# - 10. Descriptor registration (CI invariant) -


def test_microsoft_descriptors_are_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.microsoftTeams" in REGISTRY
    assert "n8n-nodes-base.microsoftOutlook" in REGISTRY
    assert "n8n-nodes-base.microsoftTeams" in SUPPORTED_NODE_TYPES
    assert "n8n-nodes-base.microsoftOutlook" in SUPPORTED_NODE_TYPES

    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.microsoftTeams"] == "output"
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.microsoftOutlook"] == "output"

    desc_teams = REGISTRY["n8n-nodes-base.microsoftTeams"]
    assert desc_teams.executor.endswith(":exec_microsoft_teams")
    assert desc_teams.category == "output"

    desc_outlook = REGISTRY["n8n-nodes-base.microsoftOutlook"]
    assert desc_outlook.executor.endswith(":exec_microsoft_outlook")
    assert desc_outlook.category == "output"

    assert set(MICROSOFT_TEAMS_CONTENT_TYPES) == {"text", "html"}
    assert set(MICROSOFT_OUTLOOK_BODY_CONTENT_TYPES) == {"Text", "HTML"}


# - 11. End-to-end: Manual -> microsoftTeams (mock) -> Set sees fields -


def _doc(nodes, connections):
    return {"name": "ms-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


_TEAMS_SET_ASSIGNMENTS = {
    "assignments": [
        {"name": "result_id", "value": "={{ $json.messageId }}", "type": "string"},
        {"name": "result_channel", "value": "={{ $json.channelId }}", "type": "string"},
    ]
}

_OUTLOOK_SET_ASSIGNMENTS = {
    "assignments": [
        {"name": "result_id", "value": "={{ $json.messageId }}", "type": "string"},
        {"name": "result_subject", "value": "={{ $json.subject }}", "type": "string"},
        {"name": "result_to", "value": "={{ $json.to }}", "type": "string"},
    ]
}


@pytest.mark.asyncio
async def test_end_to_end_manual_teams_set_sees_message_id() -> None:
    """Manual Trigger -> microsoftTeams (teams_response mock) -> Set pulls messageId."""
    mocks = {
        "teams_response": {
            "id": "e2e-teams-msg-id",
            "createdDateTime": "2025-01-01T00:00:00Z",
            "from": {
                "user": {"id": "U_MOCK", "displayName": "Mock User"},
            },
            "body": {"contentType": "text", "content": "E2E hello"},
            "channelId": "channel-e2e",
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "ts1",
                "Teams",
                "n8n-nodes-base.microsoftTeams",
                {
                    "teamId": "team-e2e",
                    "channelId": "channel-e2e",
                    "message": "E2E hello",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {"assignments": _TEAMS_SET_ASSIGNMENTS},
            ),
        ],
        {
            "Start": {"main": [[{"node": "Teams", "type": "main", "index": 0}]]},
            "Teams": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    teams_step = next(s for s in result.steps if s.node_name == "Teams")
    assert teams_step.status == "success", teams_step.error
    assert teams_step.output_count == 1
    sample = teams_step.sample_output[0]
    assert sample["json"]["messageId"] == "e2e-teams-msg-id"
    assert sample["json"]["channelId"] == "channel-e2e"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_id") == "e2e-teams-msg-id"
    assert fjson.get("result_channel") == "channel-e2e"


@pytest.mark.asyncio
async def test_end_to_end_manual_outlook_set_sees_message_id_and_subject() -> None:
    """Manual Trigger -> microsoftOutlook (outlook_response mock) -> Set pulls messageId and subject."""
    mocks = {
        "outlook_response": {
            "id": "e2e-outlook-msg-id",
            "conversationId": "e2e-outlook-conv",
            "internetMessageId": "<e2e-outlook@outlook.com>",
            "from": {
                "emailAddress": {"name": "Mocker", "address": "mock@outlook.com"},
            },
            "toRecipients": [],
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "mo1",
                "Outlook",
                "n8n-nodes-base.microsoftOutlook",
                {
                    "to": "end@example.com",
                    "subject": "Hello E2E",
                    "body": "Body E2E",
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {"assignments": _OUTLOOK_SET_ASSIGNMENTS},
            ),
        ],
        {
            "Start": {"main": [[{"node": "Outlook", "type": "main", "index": 0}]]},
            "Outlook": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    outlook_step = next(s for s in result.steps if s.node_name == "Outlook")
    assert outlook_step.status == "success", outlook_step.error
    assert outlook_step.output_count == 1
    sample = outlook_step.sample_output[0]
    assert sample["json"]["messageId"] == "e2e-outlook-msg-id"
    assert sample["json"]["subject"] == "Hello E2E"
    assert sample["json"]["to"] == "end@example.com"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_id") == "e2e-outlook-msg-id"
    assert fjson.get("result_subject") == "Hello E2E"
    assert fjson.get("result_to") == "end@example.com"
