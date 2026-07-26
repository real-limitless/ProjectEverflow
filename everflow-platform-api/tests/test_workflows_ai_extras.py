"""Tests for AI extras nodes (LangChain Code, Model Selector, Guardrails, memories, agent tools, CMS, misc)."""
from __future__ import annotations
from typing import Any
import pytest
from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.ai_extras import (
    exec_calendly_trigger, exec_contentful, exec_ghost, exec_guardrails, exec_home_assistant,
    exec_jina_ai, exec_langchain_code, exec_memory_manager, exec_memory_mongodb_chat,
    exec_memory_postgres_chat, exec_memory_redis_chat, exec_mistral_ai, exec_model_selector,
    exec_output_parser_autofixing, exec_output_parser_item_list, exec_perplexity,
    exec_retriever_vector_store, exec_spotify, exec_strapi, exec_tool_searxng,
    exec_tool_wolfram_alpha, exec_typeform_trigger, exec_webflow, exec_zoom,
)
from app.services.workflows.registry import REGISTRY

def _node(params, *, type_="@n8n/n8n-nodes-langchain.code", id_="n1", name="Code"):
    return ExecNode(id=id_, name=name, type=type_, type_version=1, parameters=params, credentials=None, position={"x": 0, "y": 0})
def _ctx(mocks=None):
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {})
def _out_items(result):
    out = []
    for _idx, items in result: out.extend(items)
    return out
def _input_item(**kw): return ExecutionItem(json=kw)

@pytest.mark.asyncio
async def test_langchain_code_offline():
    node = _node({"jsCode": "return items;"})
    items = _out_items(await exec_langchain_code(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "langchain_code"

@pytest.mark.asyncio
async def test_model_selector_passthrough():
    node = _node({"model": "gpt-4o"}, type_="@n8n/n8n-nodes-langchain.modelSelector", name="Model")
    items = _out_items(await exec_model_selector(node, [_input_item(text="hi")], ctx=_ctx()))
    assert items[0].json["_selectedModel"] == "gpt-4o"
    assert items[0].json["text"] == "hi"

@pytest.mark.asyncio
async def test_guardrails_offline():
    node = _node({"text": "hello"}, type_="@n8n/n8n-nodes-langchain.guardrails", name="Guardrails")
    items = _out_items(await exec_guardrails(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["passed"] is True
    assert items[0].json["source"] == "guardrails"

@pytest.mark.asyncio
async def test_memory_postgres_chat_passthrough():
    node = _node({"sessionId": "s1"}, type_="@n8n/n8n-nodes-langchain.memoryPostgresChat", name="MemPG")
    items = _out_items(await exec_memory_postgres_chat(node, [_input_item(text="hi")], ctx=_ctx()))
    assert len(items) == 1

@pytest.mark.asyncio
async def test_memory_redis_chat_passthrough():
    node = _node({}, type_="@n8n/n8n-nodes-langchain.memoryRedisChat", name="MemRedis")
    items = _out_items(await exec_memory_redis_chat(node, [_input_item()], ctx=_ctx()))
    assert len(items) == 1

@pytest.mark.asyncio
async def test_memory_mongodb_chat_passthrough():
    node = _node({}, type_="@n8n/n8n-nodes-langchain.memoryMongoDbChat", name="MemMongo")
    items = _out_items(await exec_memory_mongodb_chat(node, [_input_item()], ctx=_ctx()))
    assert len(items) == 1

@pytest.mark.asyncio
async def test_perplexity_offline():
    node = _node({"prompt": "What is AI?"}, type_="n8n-nodes-base.perplexity", name="Perplexity")
    items = _out_items(await exec_perplexity(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "perplexity"

@pytest.mark.asyncio
async def test_jina_ai_offline():
    node = _node({}, type_="n8n-nodes-base.jinaAi", name="Jina")
    items = _out_items(await exec_jina_ai(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "jinaAi"

@pytest.mark.asyncio
async def test_mistral_ai_offline():
    node = _node({"prompt": "Hello"}, type_="n8n-nodes-base.mistralAi", name="Mistral")
    items = _out_items(await exec_mistral_ai(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "mistralAi"

@pytest.mark.asyncio
async def test_webflow_offline():
    node = _node({"operation": "create"}, type_="n8n-nodes-base.webflow", name="Webflow")
    items = _out_items(await exec_webflow(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "webflow"

@pytest.mark.asyncio
async def test_ghost_offline():
    node = _node({"operation": "create", "title": "Post"}, type_="n8n-nodes-base.ghost", name="Ghost")
    items = _out_items(await exec_ghost(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "ghost"

@pytest.mark.asyncio
async def test_strapi_offline():
    node = _node({"operation": "create"}, type_="n8n-nodes-base.strapi", name="Strapi")
    items = _out_items(await exec_strapi(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "strapi"

@pytest.mark.asyncio
async def test_contentful_offline():
    node = _node({"operation": "create"}, type_="n8n-nodes-base.contentful", name="Contentful")
    items = _out_items(await exec_contentful(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "contentful"

@pytest.mark.asyncio
async def test_home_assistant_offline():
    node = _node({"operation": "callService", "entityId": "light.living_room"}, type_="n8n-nodes-base.homeAssistant", name="HA")
    items = _out_items(await exec_home_assistant(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "homeAssistant"

@pytest.mark.asyncio
async def test_spotify_offline():
    node = _node({"operation": "play"}, type_="n8n-nodes-base.spotify", name="Spotify")
    items = _out_items(await exec_spotify(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "spotify"

@pytest.mark.asyncio
async def test_zoom_offline():
    node = _node({"operation": "createMeeting", "topic": "Standup"}, type_="n8n-nodes-base.zoom", name="Zoom")
    items = _out_items(await exec_zoom(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "zoom"

@pytest.mark.asyncio
async def test_typeform_trigger_offline():
    node = _node({}, type_="n8n-nodes-base.typeformTrigger", name="Typeform")
    items = _out_items(await exec_typeform_trigger(node, [], ctx=_ctx()))
    assert items[0].json["source"] == "typeform"

@pytest.mark.asyncio
async def test_calendly_trigger_offline():
    node = _node({}, type_="n8n-nodes-base.calendlyTrigger", name="Calendly")
    items = _out_items(await exec_calendly_trigger(node, [], ctx=_ctx()))
    assert items[0].json["source"] == "calendly"

@pytest.mark.asyncio
async def test_searxng_offline():
    node = _node({"query": "test"}, type_="@n8n/n8n-nodes-langchain.toolSearXng", name="SearXNG")
    items = _out_items(await exec_tool_searxng(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "searxng"

@pytest.mark.asyncio
async def test_wolfram_offline():
    node = _node({"query": "2+2"}, type_="@n8n/n8n-nodes-langchain.toolWolframAlpha", name="Wolfram")
    items = _out_items(await exec_tool_wolfram_alpha(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "wolframAlpha"

@pytest.mark.asyncio
async def test_output_parser_item_list_offline():
    node = _node({}, type_="@n8n/n8n-nodes-langchain.outputParserItemList", name="Parser")
    items = _out_items(await exec_output_parser_item_list(node, [_input_item(text="hello")], ctx=_ctx()))
    assert items[0].json["source"] == "outputParserItemList"

@pytest.mark.asyncio
async def test_output_parser_autofixing_offline():
    node = _node({}, type_="@n8n/n8n-nodes-langchain.outputParserAutofixing", name="Autofix")
    items = _out_items(await exec_output_parser_autofixing(node, [_input_item(text="hello")], ctx=_ctx()))
    assert items[0].json["source"] == "outputParserAutofixing"

@pytest.mark.asyncio
async def test_retriever_vector_store_offline():
    node = _node({"query": "test"}, type_="@n8n/n8n-nodes-langchain.retrieverVectorStore", name="Retriever")
    items = _out_items(await exec_retriever_vector_store(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "retrieverVectorStore"

@pytest.mark.asyncio
async def test_memory_manager_passthrough():
    node = _node({"mode": "load"}, type_="@n8n/n8n-nodes-langchain.memoryManager", name="MemMgr")
    items = _out_items(await exec_memory_manager(node, [_input_item()], ctx=_ctx()))
    assert len(items) == 1

@pytest.mark.asyncio
async def test_e2e_guardrails_to_set():
    doc = {
        "nodes": [
            {"id": "t", "name": "Manual", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "parameters": {}, "position": [0, 0]},
            {"id": "g", "name": "Guardrails", "type": "@n8n/n8n-nodes-langchain.guardrails", "typeVersion": 1, "parameters": {"text": "hello"}, "position": [200, 0]},
            {"id": "s", "name": "Set", "type": "n8n-nodes-base.set", "typeVersion": 1, "parameters": {"assignments": {"assignments": [{"name": "result", "value": "={{ $json.source }}", "type": "string"}]}}, "position": [400, 0]},
        ],
        "connections": {"t": {"main": [[{"node": "g", "index": 0}]]}, "g": {"main": [[{"node": "s", "index": 0}]]}},
    }
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run()
    assert result.status == "success"
    assert result.final_items[0]["json"]["result"] == "guardrails"

def test_descriptors_registered():
    types = [
        "@n8n/n8n-nodes-langchain.code",
        "@n8n/n8n-nodes-langchain.modelSelector",
        "@n8n/n8n-nodes-langchain.guardrails",
        "@n8n/n8n-nodes-langchain.memoryPostgresChat",
        "@n8n/n8n-nodes-langchain.memoryRedisChat",
        "@n8n/n8n-nodes-langchain.memoryMongoDbChat",
        "n8n-nodes-base.perplexity",
        "n8n-nodes-base.jinaAi",
        "n8n-nodes-base.mistralAi",
        "n8n-nodes-base.webflow",
        "n8n-nodes-base.ghost",
        "n8n-nodes-base.strapi",
        "n8n-nodes-base.contentful",
        "n8n-nodes-base.homeAssistant",
        "n8n-nodes-base.spotify",
        "n8n-nodes-base.zoom",
        "n8n-nodes-base.typeformTrigger",
        "n8n-nodes-base.calendlyTrigger",
        "@n8n/n8n-nodes-langchain.toolSearXng",
        "@n8n/n8n-nodes-langchain.toolWolframAlpha",
        "@n8n/n8n-nodes-langchain.outputParserItemList",
        "@n8n/n8n-nodes-langchain.outputParserAutofixing",
        "@n8n/n8n-nodes-langchain.retrieverVectorStore",
        "@n8n/n8n-nodes-langchain.memoryManager",
    ]
    for t in types:
        assert t in REGISTRY, f"{t} not registered"