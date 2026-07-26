"""Tests for email service nodes (``n8n-nodes-base.*`` email extras).

Covers SendGrid, Brevo, Mailgun, Mailchimp, Mailjet, Postmark Trigger,
and Email IMAP Trigger.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.email_extra import (
    exec_brevo,
    exec_email_read_imap,
    exec_mailchimp,
    exec_mailgun,
    exec_mailjet,
    exec_postmark_trigger,
    exec_sendgrid,
)
from app.services.workflows.registry import REGISTRY


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.sendGrid",
    id_: str = "n1",
    name: str = "SendGrid",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params,
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


def _input_item(**kw) -> ExecutionItem:
    return ExecutionItem(json=kw)


# ── 1. SendGrid ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sendgrid_dict_mock_used_verbatim() -> None:
    node = _node({"operation": "send", "to": "a@b.com", "subject": "Hi"})
    ctx = _ctx({"sendgrid_response": {"messageId": "sg-1", "status": "queued"}})
    items = _out_items(await exec_sendgrid(node, [_input_item()], ctx=ctx))
    assert len(items) == 1
    assert items[0].json["messageId"] == "sg-1"


@pytest.mark.asyncio
async def test_sendgrid_callable_mock_receives_args() -> None:
    calls: list[tuple] = []

    def mock(op, params, item, c):
        calls.append((op, params.get("to")))
        return {"messageId": "sg-2", "custom": True}

    node = _node({"operation": "send", "to": "x@y.com"})
    ctx = _ctx({"sendgrid_response": mock})
    items = _out_items(await exec_sendgrid(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True
    assert calls[0][0] == "send"
    assert calls[0][1] == "x@y.com"


@pytest.mark.asyncio
async def test_sendgrid_http_response_fallback() -> None:
    node = _node({"operation": "send"})
    ctx = _ctx({"http_response": {"status_code": 200, "body": {"messageId": "hr-1"}}})
    items = _out_items(await exec_sendgrid(node, [_input_item()], ctx=ctx))
    assert items[0].json["messageId"] == "hr-1"


@pytest.mark.asyncio
async def test_sendgrid_offline_has_fields() -> None:
    node = _node({"operation": "send", "to": "a@b.com", "subject": "Hello"})
    items = _out_items(await exec_sendgrid(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["status"] == "sent"
    assert items[0].json["source"] == "sendgrid"
    assert items[0].json["to"] == "a@b.com"
    assert items[0].json["subject"] == "Hello"


# ── 2. Brevo ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_brevo_dict_mock_used_verbatim() -> None:
    node = _node({"operation": "send"}, type_="n8n-nodes-base.sendInBlue", name="Brevo")
    ctx = _ctx({"brevo_response": {"messageId": "br-1"}})
    items = _out_items(await exec_brevo(node, [_input_item()], ctx=ctx))
    assert items[0].json["messageId"] == "br-1"


@pytest.mark.asyncio
async def test_brevo_sendinblue_alias_mock() -> None:
    node = _node({"operation": "send"}, type_="n8n-nodes-base.sendInBlue", name="Brevo")
    ctx = _ctx({"sendinblue_response": {"messageId": "sb-1"}})
    items = _out_items(await exec_brevo(node, [_input_item()], ctx=ctx))
    assert items[0].json["messageId"] == "sb-1"


@pytest.mark.asyncio
async def test_brevo_offline_has_fields() -> None:
    node = _node({"operation": "send", "to": "a@b.com", "subject": "Hi"}, type_="n8n-nodes-base.sendInBlue")
    items = _out_items(await exec_brevo(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "brevo"
    assert items[0].json["status"] == "sent"


# ── 3. Mailgun ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mailgun_dict_mock_used_verbatim() -> None:
    node = _node({"operation": "send"}, type_="n8n-nodes-base.mailgun", name="Mailgun")
    ctx = _ctx({"mailgun_response": {"messageId": "mg-1"}})
    items = _out_items(await exec_mailgun(node, [_input_item()], ctx=ctx))
    assert items[0].json["messageId"] == "mg-1"


@pytest.mark.asyncio
async def test_mailgun_offline_has_fields() -> None:
    node = _node({"operation": "send", "to": "a@b.com", "subject": "Hi"}, type_="n8n-nodes-base.mailgun")
    items = _out_items(await exec_mailgun(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "mailgun"
    assert items[0].json["status"] == "sent"


# ── 4. Mailchimp ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mailchimp_dict_mock_used_verbatim() -> None:
    node = _node({"operation": "subscribe"}, type_="n8n-nodes-base.mailchimp", name="Mailchimp")
    ctx = _ctx({"mailchimp_response": {"email": "sub@example.com", "status": "subscribed"}})
    items = _out_items(await exec_mailchimp(node, [_input_item()], ctx=ctx))
    assert items[0].json["email"] == "sub@example.com"


@pytest.mark.asyncio
async def test_mailchimp_offline_subscribe() -> None:
    node = _node(
        {"operation": "subscribe", "email": "user@test.com", "listId": "list-1"},
        type_="n8n-nodes-base.mailchimp",
    )
    items = _out_items(await exec_mailchimp(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["status"] == "subscribed"
    assert items[0].json["source"] == "mailchimp"
    assert items[0].json["operation"] == "subscribe"


@pytest.mark.asyncio
async def test_mailchimp_offline_unsubscribe() -> None:
    node = _node(
        {"operation": "unsubscribe", "email": "user@test.com", "listId": "list-1"},
        type_="n8n-nodes-base.mailchimp",
    )
    items = _out_items(await exec_mailchimp(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["status"] == "unsubscribed"


# ── 5. Mailjet ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mailjet_dict_mock_used_verbatim() -> None:
    node = _node({"operation": "send"}, type_="n8n-nodes-base.mailjet", name="Mailjet")
    ctx = _ctx({"mailjet_response": {"messageId": "mj-1"}})
    items = _out_items(await exec_mailjet(node, [_input_item()], ctx=ctx))
    assert items[0].json["messageId"] == "mj-1"


@pytest.mark.asyncio
async def test_mailjet_offline_has_fields() -> None:
    node = _node(
        {"operation": "send", "to": "a@b.com", "subject": "Hi"},
        type_="n8n-nodes-base.mailjet",
    )
    items = _out_items(await exec_mailjet(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "mailjet"
    assert items[0].json["status"] == "sent"


# ── 6. Postmark Trigger ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_postmark_trigger_dict_mock() -> None:
    node = _node({}, type_="n8n-nodes-base.postmarkTrigger", name="Postmark Trigger")
    ctx = _ctx({"postmark_trigger_payload": {"from": "real@test.com", "subject": "Mock"}})
    items = _out_items(await exec_postmark_trigger(node, [], ctx=ctx))
    assert len(items) == 1
    assert items[0].json["from"] == "real@test.com"


@pytest.mark.asyncio
async def test_postmark_trigger_trigger_payload_alias() -> None:
    node = _node({}, type_="n8n-nodes-base.postmarkTrigger")
    ctx = _ctx({"trigger_payload": {"from": "alias@test.com"}})
    items = _out_items(await exec_postmark_trigger(node, [], ctx=ctx))
    assert items[0].json["from"] == "alias@test.com"


@pytest.mark.asyncio
async def test_postmark_trigger_offline() -> None:
    node = _node({}, type_="n8n-nodes-base.postmarkTrigger")
    items = _out_items(await exec_postmark_trigger(node, [], ctx=_ctx()))
    assert len(items) == 1
    assert items[0].json["source"] == "postmark"
    assert "from" in items[0].json


# ── 7. Email IMAP Trigger ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_imap_trigger_dict_mock() -> None:
    node = _node({"mailbox": "INBOX"}, type_="n8n-nodes-base.emailReadImap", name="IMAP")
    ctx = _ctx({"imap_trigger_payload": {"from": "imap@test.com", "subject": "Mock"}})
    items = _out_items(await exec_email_read_imap(node, [], ctx=ctx))
    assert items[0].json["from"] == "imap@test.com"


@pytest.mark.asyncio
async def test_imap_trigger_offline_has_mailbox() -> None:
    node = _node({"mailbox": "Custom"}, type_="n8n-nodes-base.emailReadImap")
    items = _out_items(await exec_email_read_imap(node, [], ctx=_ctx()))
    assert items[0].json["mailbox"] == "Custom"
    assert items[0].json["source"] == "imap"


@pytest.mark.asyncio
async def test_imap_trigger_offline_default_mailbox() -> None:
    node = _node({}, type_="n8n-nodes-base.emailReadImap")
    items = _out_items(await exec_email_read_imap(node, [], ctx=_ctx()))
    assert items[0].json["mailbox"] == "INBOX"


# ── 8. End-to-end ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_sendgrid_to_set() -> None:
    doc = {
        "nodes": [
            {
                "id": "t",
                "name": "Manual",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "parameters": {},
                "position": [0, 0],
            },
            {
                "id": "s",
                "name": "SendGrid",
                "type": "n8n-nodes-base.sendGrid",
                "typeVersion": 1,
                "parameters": {"operation": "send", "to": "test@example.com", "subject": "E2E"},
                "position": [200, 0],
            },
            {
                "id": "set",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 1,
                "parameters": {"assignments": {"assignments": [{"name": "result", "value": "={{ $json.status }}", "type": "string"}]}},
                "position": [400, 0],
            },
        ],
        "connections": {
            "t": {"main": [[{"node": "s", "index": 0}]]},
            "s": {"main": [[{"node": "set", "index": 0}]]},
        },
    }
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run()
    assert result.status == "success"
    assert len(result.final_items) == 1
    assert result.final_items[0]["json"]["result"] == "sent"


# ── 9. Descriptor registration (CI invariant) ────────────────────────


def test_descriptors_registered() -> None:
    types = [
        "n8n-nodes-base.sendGrid",
        "n8n-nodes-base.sendInBlue",
        "n8n-nodes-base.mailgun",
        "n8n-nodes-base.mailchimp",
        "n8n-nodes-base.mailjet",
        "n8n-nodes-base.postmarkTrigger",
        "n8n-nodes-base.emailReadImap",
    ]
    for t in types:
        assert t in REGISTRY, f"{t} not registered"