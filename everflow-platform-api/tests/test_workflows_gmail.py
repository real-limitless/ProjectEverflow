"""Tests for the Gmail node executor (``@n8n/n8n-nodes-langchain.gmail``).

Covers:

- ``gmail_response`` dict mock → envelope is used verbatim
- ``gmail_response`` callable mock receives ``(to, subject, body, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline synthetic response has ``id`` and ``threadId``
- ``to``, ``subject``, ``body`` defaults from ``$json``
- ``cc`` and ``bcc`` honored
- ``html`` flag reflected
- ``sendAndWait`` operation echoed on the output
- Empty subject → no item emitted
- End-to-end: Manual Trigger → gmail (mock) → Set sees ``messageId`` and ``subject``
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.gmail import GMAIL_OPERATIONS, exec_gmail


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "@n8n/n8n-nodes-langchain.gmail",
    id_: str = "gm1",
    name: str = "Gmail",
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


# ── 1. gmail_response dict mock ───────────────────────────────────────


@pytest.mark.asyncio
async def test_gmail_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "operation": "send",
            "to": "alice@example.com",
            "subject": "Hi",
            "message": "Hello Alice",
        }
    )
    ctx = _ctx(
        {
            "gmail_response": {
                "id": "<msg-001@mail.gmail.com>",
                "threadId": "<thread-xyz>",
                "labelIds": ["SENT", "IMPORTANT"],
            }
        }
    )
    out = _out_items(await exec_gmail(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    payload = out[0].json
    assert payload["messageId"] == "<msg-001@mail.gmail.com>"
    assert payload["threadId"] == "<thread-xyz>"
    assert payload["labelIds"] == ["SENT", "IMPORTANT"]
    assert payload["to"] == "alice@example.com"
    assert payload["subject"] == "Hi"
    assert payload["body"] == "Hello Alice"
    assert payload["ok"] is True
    assert payload["source"] == "gmail"
    assert payload["operation"] == "send"


# ── 2. gmail_response callable mock signature ─────────────────────────


@pytest.mark.asyncio
async def test_gmail_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(to, subject, body, params, item, ctx):
        captured["to"] = to
        captured["subject"] = subject
        captured["body"] = body
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "<captured@mail.gmail.com>",
            "threadId": "<thread-cap>",
            "labelIds": ["SENT"],
        }

    node = _node(
        {
            "operation": "send",
            "to": "bob@example.com",
            "subject": "Greetings",
            "message": "Hi Bob",
            "extra": "keep",
        }
    )
    ctx = _ctx({"gmail_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_gmail(node, [item], ctx=ctx))

    assert captured["to"] == "bob@example.com"
    assert captured["subject"] == "Greetings"
    assert captured["body"] == "Hi Bob"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["messageId"] == "<captured@mail.gmail.com>"
    assert out[0].json["threadId"] == "<thread-cap>"


# ── 3. http_response fallback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "send",
            "to": "carol@example.com",
            "subject": "Subject A",
            "message": "Body A",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "id": "<from-http@mail.gmail.com>",
                    "threadId": "<thread-http>",
                    "labelIds": ["SENT"],
                },
            }
        }
    )
    out = _out_items(await exec_gmail(node, [ExecutionItem(json={})], ctx=ctx))
    assert out[0].json["messageId"] == "<from-http@mail.gmail.com>"
    assert out[0].json["threadId"] == "<thread-http>"
    assert out[0].json["mockSource"] == "http_response"


# ── 4. Offline synthetic response ─────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_synthetic_response_has_id_and_thread_id() -> None:
    node = _node(
        {
            "operation": "send",
            "to": "dave@example.com",
            "subject": "Offline",
            "message": "Hello",
        }
    )
    out = _out_items(await exec_gmail(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    payload = out[0].json
    assert payload["messageId"].startswith("<fake-")
    assert payload["messageId"].endswith("@mail.gmail.com>")
    assert payload["threadId"].startswith("<thread-")
    assert payload["labelIds"] == ["SENT"]
    assert payload["source"] == "gmail"
    assert payload["mockSource"] == "offline"


# ── 5. $json fallbacks for to, subject, body ──────────────────────────


@pytest.mark.asyncio
async def test_to_subject_body_default_from_json() -> None:
    node = _node({"operation": "send"})  # all from $json
    item = ExecutionItem(
        json={
            "to": "erin@example.com",
            "subject": "From JSON",
            "body": "Body from body field",
        }
    )
    out = _out_items(await exec_gmail(node, [item], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["to"] == "erin@example.com"
    assert p["subject"] == "From JSON"
    assert p["body"] == "Body from body field"


@pytest.mark.asyncio
async def test_body_prefers_message_then_body_then_text() -> None:
    node = _node({"operation": "send", "subject": "x"})
    # message wins over body over text
    item = ExecutionItem(
        json={"to": "z@x.com", "message": "msg-via-message", "body": "msg-via-body", "text": "msg-via-text"}
    )
    out = _out_items(await exec_gmail(node, [item], ctx=_ctx()))
    assert out[0].json["body"] == "msg-via-message"

    # body used when no message
    item2 = ExecutionItem(json={"to": "z@x.com", "body": "msg-via-body", "text": "msg-via-text"})
    out2 = _out_items(await exec_gmail(node, [item2], ctx=_ctx()))
    assert out2[0].json["body"] == "msg-via-body"

    # text used when neither message nor body
    item3 = ExecutionItem(json={"to": "z@x.com", "text": "msg-via-text"})
    out3 = _out_items(await exec_gmail(node, [item3], ctx=_ctx()))
    assert out3[0].json["body"] == "msg-via-text"


@pytest.mark.asyncio
async def test_to_accepts_list() -> None:
    node = _node(
        {
            "operation": "send",
            "to": ["a@example.com", "b@example.com"],
            "subject": "Multi",
            "message": "Hi all",
        }
    )
    out = _out_items(await exec_gmail(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["to"] == "a@example.com, b@example.com"


# ── 6. cc and bcc honored ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cc_and_bcc_honored() -> None:
    node = _node(
        {
            "operation": "send",
            "to": "frank@example.com",
            "cc": ["cc1@example.com", "cc2@example.com"],
            "bcc": "bcc@example.com",
            "subject": "FYI",
            "message": "see below",
        }
    )
    out = _out_items(await exec_gmail(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["cc"] == "cc1@example.com, cc2@example.com"
    assert p["bcc"] == "bcc@example.com"


# ── 7. html flag reflected ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_html_flag_reflected() -> None:
    node = _node(
        {
            "operation": "send",
            "to": "g@example.com",
            "subject": "HTML",
            "message": "<p>hi</p>",
            "html": True,
        }
    )
    out = _out_items(await exec_gmail(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["html"] is True

    node_plain = _node(
        {
            "operation": "send",
            "to": "g@example.com",
            "subject": "Plain",
            "message": "hi",
        }
    )
    out_plain = _out_items(await exec_gmail(node_plain, [ExecutionItem(json={})], ctx=_ctx()))
    assert out_plain[0].json["html"] is False


# ── 8. sendAndWait operation echoed ───────────────────────────────────


@pytest.mark.asyncio
async def test_send_and_wait_operation_echoed() -> None:
    node = _node(
        {
            "operation": "sendAndWait",
            "to": "h@example.com",
            "subject": "Reply needed",
            "message": "Please confirm",
        }
    )
    out = _out_items(await exec_gmail(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["operation"] == "sendAndWait"
    # Same envelope shape as send
    assert out[0].json["messageId"].startswith("<fake-")
    assert out[0].json["subject"] == "Reply needed"


# ── 9. Empty subject → no item ───────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_subject_skips_item() -> None:
    node = _node(
        {
            "operation": "send",
            "to": "i@example.com",
            "subject": "",
            "message": "should not send",
        }
    )
    out = _out_items(await exec_gmail(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_subject_when_only_in_json_skips_item() -> None:
    node = _node({"operation": "send", "to": "i@example.com"})
    item = ExecutionItem(json={"subject": "", "message": "no subject here"})
    out = _out_items(await exec_gmail(node, [item], ctx=_ctx()))
    assert out == []


# ── 10. Multiple input items produce one envelope each ────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({"operation": "send"})
    items = [
        ExecutionItem(json={"to": "a@x.com", "subject": "A", "body": "a"}),
        ExecutionItem(json={"to": "b@x.com", "subject": "B", "body": "b"}),
        ExecutionItem(json={"to": "c@x.com", "subject": "C", "body": "c"}),
    ]
    out = _out_items(await exec_gmail(node, items, ctx=_ctx()))
    assert len(out) == 3
    subjects = [o.json["subject"] for o in out]
    assert subjects == ["A", "B", "C"]
    assert all(o.json["messageId"].startswith("<fake-") for o in out)


# ── 11. Unsupported operation raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "reply"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_gmail(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 12. Descriptor registration ───────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "@n8n/n8n-nodes-langchain.gmail" in REGISTRY
    assert "@n8n/n8n-nodes-langchain.gmail" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["@n8n/n8n-nodes-langchain.gmail"] == "output"
    desc = REGISTRY["@n8n/n8n-nodes-langchain.gmail"]
    assert desc.executor.endswith(":exec_gmail")
    assert desc.category == "output"
    assert set(GMAIL_OPERATIONS) == {"send", "sendAndWait"}


# ── 13. End-to-end: Manual Trigger → gmail (mock) → Set sees fields ──


def _doc(nodes, connections):
    return {"name": "gmail-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_gmail_set_sees_message_id_and_subject() -> None:
    """Manual Trigger → gmail (gmail_response mock) → Set pulls messageId/subject."""
    mocks = {
        "gmail_response": {
            "id": "<e2e@mail.gmail.com>",
            "threadId": "<e2e-thread>",
            "labelIds": ["SENT"],
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "g1",
                "Gmail",
                "@n8n/n8n-nodes-langchain.gmail",
                {
                    "operation": "send",
                    "to": "end@example.com",
                    "subject": "Hello E2E",
                    "message": "Body E2E",
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
                            {"name": "result_subject", "value": "={{ $json.subject }}", "type": "string"},
                            {"name": "result_to", "value": "={{ $json.to }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Gmail", "type": "main", "index": 0}]]},
            "Gmail": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    gmail_step = next(s for s in result.steps if s.node_name == "Gmail")
    assert gmail_step.status == "success", gmail_step.error
    assert gmail_step.output_count == 1
    sample = gmail_step.sample_output[0]
    assert sample["json"]["messageId"] == "<e2e@mail.gmail.com>"
    assert sample["json"]["subject"] == "Hello E2E"
    assert sample["json"]["to"] == "end@example.com"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_id") == "<e2e@mail.gmail.com>"
    assert fjson.get("result_subject") == "Hello E2E"
    assert fjson.get("result_to") == "end@example.com"
