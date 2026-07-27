"""Tests for Google extra executors (List B)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import items_from_json_list
from app.services.workflows.nodes.google_extra import (
    exec_google_ads,
    exec_google_analytics,
    exec_google_bigquery,
    exec_google_business_profile,
    exec_google_chat,
    exec_google_cloud_storage,
    exec_google_contacts,
    exec_google_slides,
    exec_google_tasks,
    exec_google_translate,
    exec_g_suite_admin,
)


def _node(
    type_: str,
    params: dict[str, Any] | None = None,
    id_: str = "n1",
    name: str = "Node",
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params or {},
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
    return EngineContext(graph=g, mocks=mocks or {}, run_id="test")  # type: ignore[arg-type]


def _items(rows: list[dict] | None = None):
    return items_from_json_list(rows or [])


def _out_items(result):
    out = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── Google Analytics ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_analytics_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleAnalytics", {"propertyId": "prop1"})
    ctx = _ctx({"google_analytics_response": {"reports": [{"rows": []}]}})
    result = await exec_google_analytics(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["reports"] == [{"rows": []}]
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_analytics_callable_receives_args() -> None:
    seen = []

    def mock(operation, params, item, ctx):
        seen.append((operation, params, item, ctx))
        return {"reports": [{"x": 1}]}

    node = _node(
        "n8n-nodes-base.googleAnalytics",
        {"operation": "getReport", "propertyId": "p"},
    )
    ctx = _ctx({"google_analytics_response": mock})
    await exec_google_analytics(node, _items([{"a": 1}]), ctx=ctx)
    assert seen[0][0] == "getReport"
    assert seen[0][2].json == {"a": 1}
    assert seen[0][3] is ctx


@pytest.mark.asyncio
async def test_google_analytics_offline() -> None:
    node = _node("n8n-nodes-base.googleAnalytics", {"propertyId": "prop1"})
    ctx = _ctx()
    result = await exec_google_analytics(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["propertyId"] == "prop1"
    assert out[0].json["operation"] == "getReport"
    assert out[0].json["source"] == "google_analytics"
    assert "reports" in out[0].json


@pytest.mark.asyncio
async def test_google_analytics_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleAnalytics", {"propertyId": "p"})
    ctx = _ctx({"http_response": {"body": {"reports": [{"fb": 1}]}}})
    result = await exec_google_analytics(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["reports"] == [{"fb": 1}]
    assert out[0].json["mockSource"] == "http_response"


# ── Google Slides ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_slides_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleSlides", {"presentationId": "pres1"})
    ctx = _ctx({"google_slides_response": {"presentationId": "pres9"}})
    result = await exec_google_slides(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["presentationId"] == "pres9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_slides_offline() -> None:
    node = _node(
        "n8n-nodes-base.googleSlides", {"presentationId": "p1", "title": "T"}
    )
    ctx = _ctx()
    result = await exec_google_slides(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["presentationId"] == "p1"
    assert out[0].json["title"] == "T"
    assert out[0].json["operation"] == "get"
    assert out[0].json["source"] == "google_slides"


@pytest.mark.asyncio
async def test_google_slides_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleSlides", {"presentationId": "p"})
    ctx = _ctx({"http_response": {"body": {"presentationId": "fb1"}}})
    result = await exec_google_slides(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["presentationId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Google Tasks ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_tasks_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleTasks", {"taskTitle": "Buy milk"})
    ctx = _ctx({"google_tasks_response": {"taskId": "t9"}})
    result = await exec_google_tasks(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["taskId"] == "t9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_tasks_offline() -> None:
    node = _node(
        "n8n-nodes-base.googleTasks",
        {"taskTitle": "Buy milk", "taskListId": "tl1"},
    )
    ctx = _ctx()
    result = await exec_google_tasks(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["taskTitle"] == "Buy milk"
    assert out[0].json["taskListId"] == "tl1"
    assert out[0].json["operation"] == "create"
    assert out[0].json["source"] == "google_tasks"
    assert "taskId" in out[0].json


@pytest.mark.asyncio
async def test_google_tasks_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleTasks", {"taskTitle": "t"})
    ctx = _ctx({"http_response": {"body": {"taskId": "fb1"}}})
    result = await exec_google_tasks(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["taskId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Google Contacts ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_contacts_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleContacts", {"name": "Alice"})
    ctx = _ctx({"google_contacts_response": {"contactId": "c9"}})
    result = await exec_google_contacts(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["contactId"] == "c9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_contacts_offline() -> None:
    node = _node(
        "n8n-nodes-base.googleContacts",
        {"name": "Alice", "email": "alice@example.com"},
    )
    ctx = _ctx()
    result = await exec_google_contacts(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["name"] == "Alice"
    assert out[0].json["email"] == "alice@example.com"
    assert out[0].json["operation"] == "create"
    assert out[0].json["source"] == "google_contacts"
    assert "contactId" in out[0].json


@pytest.mark.asyncio
async def test_google_contacts_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleContacts", {"name": "n"})
    ctx = _ctx({"http_response": {"body": {"contactId": "fb1"}}})
    result = await exec_google_contacts(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["contactId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Google Translate ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_translate_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleTranslate", {"text": "hola"})
    ctx = _ctx({"google_translate_response": {"translatedText": "hello"}})
    result = await exec_google_translate(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["translatedText"] == "hello"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_translate_offline() -> None:
    node = _node(
        "n8n-nodes-base.googleTranslate",
        {"text": "hola", "target": "en"},
    )
    ctx = _ctx()
    result = await exec_google_translate(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["text"] == "hola"
    assert out[0].json["target"] == "en"
    assert out[0].json["operation"] == "translate"
    assert out[0].json["source"] == "google_translate"
    assert "translatedText" in out[0].json


@pytest.mark.asyncio
async def test_google_translate_default_target() -> None:
    node = _node("n8n-nodes-base.googleTranslate", {"text": "hola"})
    ctx = _ctx()
    result = await exec_google_translate(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["target"] == "en"


@pytest.mark.asyncio
async def test_google_translate_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleTranslate", {"text": "hola"})
    ctx = _ctx({"http_response": {"body": {"translatedText": "fb1"}}})
    result = await exec_google_translate(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["translatedText"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Google Ads ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_ads_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleAds", {"customerId": "c1"})
    ctx = _ctx({"google_ads_response": {"results": [{"x": 1}]}})
    result = await exec_google_ads(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["results"] == [{"x": 1}]
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_ads_offline() -> None:
    node = _node("n8n-nodes-base.googleAds", {"customerId": "c1"})
    ctx = _ctx()
    result = await exec_google_ads(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["customerId"] == "c1"
    assert out[0].json["operation"] == "query"
    assert out[0].json["source"] == "google_ads"
    assert "results" in out[0].json


@pytest.mark.asyncio
async def test_google_ads_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleAds", {"customerId": "c"})
    ctx = _ctx({"http_response": {"body": {"results": [{"fb": 1}]}}})
    result = await exec_google_ads(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["results"] == [{"fb": 1}]
    assert out[0].json["mockSource"] == "http_response"


# ── Google BigQuery ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_bigquery_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleBigQuery", {"projectId": "p1"})
    ctx = _ctx({"google_bigquery_response": {"rows": [{"r": 1}]}})
    result = await exec_google_bigquery(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["rows"] == [{"r": 1}]
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_bigquery_offline() -> None:
    node = _node("n8n-nodes-base.googleBigQuery", {"projectId": "p1"})
    ctx = _ctx()
    result = await exec_google_bigquery(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "executeQuery"
    assert out[0].json["source"] == "google_bigquery"
    assert "rows" in out[0].json
    assert "totalRows" in out[0].json


@pytest.mark.asyncio
async def test_google_bigquery_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleBigQuery", {"projectId": "p"})
    ctx = _ctx({"http_response": {"body": {"rows": [{"fb": 1}]}}})
    result = await exec_google_bigquery(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["rows"] == [{"fb": 1}]
    assert out[0].json["mockSource"] == "http_response"


# ── Google Cloud Storage ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_cloud_storage_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleCloudStorage", {"bucketName": "b1"})
    ctx = _ctx({"google_cloud_storage_response": {"fileSize": 999}})
    result = await exec_google_cloud_storage(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["fileSize"] == 999
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_cloud_storage_offline() -> None:
    node = _node(
        "n8n-nodes-base.googleCloudStorage",
        {"bucketName": "b1", "fileName": "f.txt"},
    )
    ctx = _ctx()
    result = await exec_google_cloud_storage(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["bucketName"] == "b1"
    assert out[0].json["fileName"] == "f.txt"
    assert out[0].json["operation"] == "download"
    assert out[0].json["source"] == "google_cloud_storage"
    assert "fileSize" in out[0].json


@pytest.mark.asyncio
async def test_google_cloud_storage_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleCloudStorage", {"bucketName": "b"})
    ctx = _ctx({"http_response": {"body": {"fileSize": 42}}})
    result = await exec_google_cloud_storage(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["fileSize"] == 42
    assert out[0].json["mockSource"] == "http_response"


# ── Google Business Profile ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_business_profile_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleBusinessProfile", {"locationId": "l1"})
    ctx = _ctx({"google_business_profile_response": {"name": "Mock Co"}})
    result = await exec_google_business_profile(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["name"] == "Mock Co"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_business_profile_offline() -> None:
    node = _node("n8n-nodes-base.googleBusinessProfile", {"locationId": "l1"})
    ctx = _ctx()
    result = await exec_google_business_profile(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["locationId"] == "l1"
    assert out[0].json["operation"] == "get"
    assert out[0].json["source"] == "google_business_profile"
    assert "name" in out[0].json


@pytest.mark.asyncio
async def test_google_business_profile_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleBusinessProfile", {"locationId": "l"})
    ctx = _ctx({"http_response": {"body": {"name": "fb1"}}})
    result = await exec_google_business_profile(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["name"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── Google Chat ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_chat_mock_dict() -> None:
    node = _node("n8n-nodes-base.googleChat", {"spaceId": "s1", "text": "hi"})
    ctx = _ctx({"google_chat_response": {"messageId": "m9"}})
    result = await exec_google_chat(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "m9"
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_google_chat_offline() -> None:
    node = _node("n8n-nodes-base.googleChat", {"spaceId": "s1", "text": "hi"})
    ctx = _ctx()
    result = await exec_google_chat(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["spaceId"] == "s1"
    assert out[0].json["text"] == "hi"
    assert out[0].json["operation"] == "sendMessage"
    assert out[0].json["source"] == "google_chat"
    assert "messageId" in out[0].json


@pytest.mark.asyncio
async def test_google_chat_http_fallback() -> None:
    node = _node("n8n-nodes-base.googleChat", {"spaceId": "s", "text": "t"})
    ctx = _ctx({"http_response": {"body": {"messageId": "fb1"}}})
    result = await exec_google_chat(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["messageId"] == "fb1"
    assert out[0].json["mockSource"] == "http_response"


# ── G Suite Admin ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_g_suite_admin_mock_dict() -> None:
    node = _node("n8n-nodes-base.gSuiteAdmin", {"operation": "listUsers"})
    ctx = _ctx({"g_suite_admin_response": {"users": [{"id": "u9"}]}})
    result = await exec_g_suite_admin(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["users"] == [{"id": "u9"}]
    assert "mockSource" not in out[0].json


@pytest.mark.asyncio
async def test_g_suite_admin_offline_list_users() -> None:
    node = _node("n8n-nodes-base.gSuiteAdmin", {"operation": "listUsers"})
    ctx = _ctx()
    result = await exec_g_suite_admin(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "listUsers"
    assert out[0].json["source"] == "g_suite_admin"
    assert "users" in out[0].json
    assert len(out[0].json["users"]) == 3


@pytest.mark.asyncio
async def test_g_suite_admin_offline_get_user() -> None:
    node = _node(
        "n8n-nodes-base.gSuiteAdmin",
        {"operation": "getUser", "userKey": "alice@example.com"},
    )
    ctx = _ctx()
    result = await exec_g_suite_admin(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["primaryEmail"] == "alice@example.com"
    assert out[0].json["operation"] == "getUser"
    assert out[0].json["source"] == "g_suite_admin"


@pytest.mark.asyncio
async def test_g_suite_admin_offline_list_groups() -> None:
    node = _node("n8n-nodes-base.gSuiteAdmin", {"operation": "listGroups"})
    ctx = _ctx()
    result = await exec_g_suite_admin(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "listGroups"
    assert "groups" in out[0].json
    assert len(out[0].json["groups"]) == 3


@pytest.mark.asyncio
async def test_g_suite_admin_http_fallback() -> None:
    node = _node("n8n-nodes-base.gSuiteAdmin", {"operation": "listUsers"})
    ctx = _ctx({"http_response": {"body": {"users": [{"id": "fb1"}]}}})
    result = await exec_g_suite_admin(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["users"] == [{"id": "fb1"}]
    assert out[0].json["mockSource"] == "http_response"


# ── Operation selection ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_google_analytics_default_operation() -> None:
    node = _node("n8n-nodes-base.googleAnalytics", {"propertyId": "p"})
    ctx = _ctx()
    result = await exec_google_analytics(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "getReport"


@pytest.mark.asyncio
async def test_google_slides_default_operation() -> None:
    node = _node("n8n-nodes-base.googleSlides", {"presentationId": "p"})
    ctx = _ctx()
    result = await exec_google_slides(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "get"


@pytest.mark.asyncio
async def test_google_tasks_default_operation() -> None:
    node = _node("n8n-nodes-base.googleTasks", {"taskTitle": "t"})
    ctx = _ctx()
    result = await exec_google_tasks(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "create"


@pytest.mark.asyncio
async def test_google_contacts_default_operation() -> None:
    node = _node("n8n-nodes-base.googleContacts", {"name": "n"})
    ctx = _ctx()
    result = await exec_google_contacts(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "create"


@pytest.mark.asyncio
async def test_google_translate_default_operation() -> None:
    node = _node("n8n-nodes-base.googleTranslate", {"text": "hola"})
    ctx = _ctx()
    result = await exec_google_translate(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "translate"


@pytest.mark.asyncio
async def test_google_ads_default_operation() -> None:
    node = _node("n8n-nodes-base.googleAds", {"customerId": "c"})
    ctx = _ctx()
    result = await exec_google_ads(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "query"


@pytest.mark.asyncio
async def test_google_bigquery_default_operation() -> None:
    node = _node("n8n-nodes-base.googleBigQuery", {"projectId": "p"})
    ctx = _ctx()
    result = await exec_google_bigquery(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "executeQuery"


@pytest.mark.asyncio
async def test_google_cloud_storage_default_operation() -> None:
    node = _node("n8n-nodes-base.googleCloudStorage", {"bucketName": "b"})
    ctx = _ctx()
    result = await exec_google_cloud_storage(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "download"


@pytest.mark.asyncio
async def test_google_business_profile_default_operation() -> None:
    node = _node("n8n-nodes-base.googleBusinessProfile", {"locationId": "l"})
    ctx = _ctx()
    result = await exec_google_business_profile(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "get"


@pytest.mark.asyncio
async def test_google_chat_default_operation() -> None:
    node = _node("n8n-nodes-base.googleChat", {"spaceId": "s", "text": "t"})
    ctx = _ctx()
    result = await exec_google_chat(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "sendMessage"


@pytest.mark.asyncio
async def test_g_suite_admin_default_operation() -> None:
    node = _node("n8n-nodes-base.gSuiteAdmin", {})
    ctx = _ctx()
    result = await exec_g_suite_admin(node, _items([{}]), ctx=ctx)
    out = _out_items(result)
    assert out[0].json["operation"] == "listUsers"


# ── Descriptor registration (CI invariant) ───────────────────────────


def test_descriptors_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    expected = {
        "n8n-nodes-base.googleAnalytics": "action",
        "n8n-nodes-base.googleSlides": "action",
        "n8n-nodes-base.googleTasks": "action",
        "n8n-nodes-base.googleContacts": "action",
        "n8n-nodes-base.googleTranslate": "action",
        "n8n-nodes-base.googleAds": "action",
        "n8n-nodes-base.googleBigQuery": "action",
        "n8n-nodes-base.googleCloudStorage": "action",
        "n8n-nodes-base.googleBusinessProfile": "action",
        "n8n-nodes-base.googleChat": "action",
        "n8n-nodes-base.gSuiteAdmin": "action",
    }
    for ntype, category in expected.items():
        assert ntype in REGISTRY, f"{ntype} not in REGISTRY"
        assert ntype in SUPPORTED_NODE_TYPES, f"{ntype} not in SUPPORTED_NODE_TYPES"
        assert REGISTRY[ntype].category == category, (
            f"{ntype} category mismatch: expected {category}, got {REGISTRY[ntype].category}"
        )


# ── End-to-end ───────────────────────────────────────────────────────


def _doc(nodes, connections):
    return {"name": "g-extra-e2e", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": [0, 0],
        "parameters": params or {},
    }


@pytest.mark.asyncio
async def test_e2e_google_translate_to_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "tr1",
                "Translate",
                "n8n-nodes-base.googleTranslate",
                {"text": "hola", "target": "en"},
            ),
            _n(
                "s1",
                "Set",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "src",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Translate", "type": "main", "index": 0}]]},
            "Translate": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["src"] == "google_translate"


@pytest.mark.asyncio
async def test_e2e_google_chat_to_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "c1",
                "Chat",
                "n8n-nodes-base.googleChat",
                {"spaceId": "spaces/mock", "text": "hello"},
            ),
            _n(
                "s1",
                "Set",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "op",
                                "value": "={{ $json.operation }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Chat", "type": "main", "index": 0}]]},
            "Chat": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    set_step = next(s for s in result.steps if s.node_name == "Set")
    assert set_step.sample_output[0]["json"]["op"] == "sendMessage"