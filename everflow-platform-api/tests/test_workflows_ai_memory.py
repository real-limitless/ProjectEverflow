"""Tests for AI memory and structured output parser sub-nodes."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.ai_memory import (
    apply_structured_parser,
    exec_memory_buffer_window,
    exec_output_parser_structured,
    memory_window_for,
    push_memory_message,
)
from app.services.workflows.engine import EngineContext


def _node(params: dict, *, type_: str, id_: str, name: str = "X") -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx() -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    return EngineContext(graph=g)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_memory_buffer_window_registers_config() -> None:
    node = _node(
        {"contextWindowLength": 3, "sessionId": "s1"},
        type_="@n8n/n8n-nodes-langchain.memoryBufferWindow",
        id_="m1",
        name="Memory",
    )
    ctx = _ctx()
    out = await exec_memory_buffer_window(node, [], ctx=ctx)
    assert out[0][1] == []
    assert "m1" in ctx.memory_configs
    assert ctx.memory_configs["m1"]["contextWindowLength"] == 3
    assert ctx.memory_configs["m1"]["sessionId"] == "s1"


@pytest.mark.asyncio
async def test_output_parser_structured_registers_schema() -> None:
    schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}, "score": {"type": "number"}},
    }
    node = _node(
        {"jsonSchema": schema},
        type_="@n8n/n8n-nodes-langchain.outputParserStructured",
        id_="p1",
        name="Parser",
    )
    ctx = _ctx()
    out = await exec_output_parser_structured(node, [], ctx=ctx)
    assert out[0][1] == []
    assert "p1" in ctx.output_parsers
    assert ctx.output_parsers["p1"]["schema"] == schema


def test_apply_structured_parser_full_json() -> None:
    parsed = apply_structured_parser(
        '{"summary": "ok", "score": 0.9}',
        {"schema": {"properties": {"summary": {}, "score": {}}}},
    )
    assert parsed == {"summary": "ok", "score": 0.9}


def test_apply_structured_parser_from_fenced_block() -> None:
    text = (
        "Here is the answer:\n"
        "```json\n{\"summary\": \"ok\", \"score\": 0.5}\n```\n"
    )
    parsed = apply_structured_parser(
        text,
        {"schema": {"properties": {"summary": {}, "score": {}}}},
    )
    assert parsed == {"summary": "ok", "score": 0.5}


def test_apply_structured_parser_heuristic_fallback() -> None:
    text = (
        "Analysis:\n"
        "summary: this is a fine report\n"
        "score: 0.42\n"
    )
    parsed = apply_structured_parser(
        text,
        {"schema": {"properties": {"summary": {}, "score": {}}}},
    )
    assert parsed["summary"].startswith("this is a fine report")
    assert parsed["score"] == 0.42


def test_memory_window_round_trip() -> None:
    ctx = _ctx()
    push_memory_message(ctx, session_id="s", role="user", content="hi")
    push_memory_message(ctx, session_id="s", role="assistant", content="hello")
    push_memory_message(ctx, session_id="s", role="user", content="how are you?")
    msgs = memory_window_for(ctx, session_id="s", limit=2)
    assert len(msgs) == 2
    assert msgs[-1]["content"] == "how are you?"


@pytest.mark.asyncio
async def test_agent_with_memory_and_parser_in_full_workflow() -> None:
    doc = {
        "name": "agent-mem",
        "nodes": [
            {
                "id": "t1",
                "name": "Start",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
                "parameters": {},
            },
            {
                "id": "lm1",
                "name": "LM",
                "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
                "typeVersion": 1,
                "position": [200, -100],
                "parameters": {"model": "gpt-4o-mini"},
            },
            {
                "id": "mem1",
                "name": "Memory",
                "type": "@n8n/n8n-nodes-langchain.memoryBufferWindow",
                "typeVersion": 1,
                "position": [200, 0],
                "parameters": {"contextWindowLength": 3, "sessionId": "s1"},
            },
            {
                "id": "pa1",
                "name": "Parser",
                "type": "@n8n/n8n-nodes-langchain.outputParserStructured",
                "typeVersion": 1,
                "position": [200, 100],
                "parameters": {
                    "jsonSchema": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                    }
                },
            },
            {
                "id": "a1",
                "name": "Agent",
                "type": "@n8n/n8n-nodes-langchain.agent",
                "typeVersion": 1,
                "position": [400, 0],
                "parameters": {"text": "={{ $json.q }}"},
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Agent", "type": "main", "index": 0}]]},
            "LM": {"ai_languageModel": [[{"node": "Agent", "type": "ai_languageModel", "index": 0}]]},
            "Memory": {"ai_memory": [[{"node": "Agent", "type": "ai_memory", "index": 0}]]},
            "Parser": {"ai_outputParser": [[{"node": "Agent", "type": "ai_outputParser", "index": 0}]]},
        },
        "pinData": {
            "Start": [{"json": {"q": "What is AI?"}}],
        },
    }
    mocks = {
        "agent_output": '{"summary": "AI is the study of intelligent agents."}',
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    agent_step = next(s for s in result.steps if s.node_name == "Agent")
    sample = agent_step.sample_output[0]
    assert "parsed" in sample["json"]
    assert sample["json"]["parsed"]["summary"].startswith("AI is the study")
