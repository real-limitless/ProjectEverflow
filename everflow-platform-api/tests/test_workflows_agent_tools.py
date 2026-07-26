"""Tests for the 7 clean-room agent sub-tool executors.

Covers:
- ``agentThink``        — passthrough thinking step
- ``agentCalculator``   — safe-eval math expression
- ``agentCode``         — fenced code preview (no execution)
- ``agentHttp``         — mock-first HTTP request
- ``agentWikipedia``    — Wikipedia search stub
- ``agentWorkflow``     — sub-workflow invocation stub
- ``agentSerpApi``      — SerpAPI search stub

Each section tests:

- Mock-driven behavior (callable or static value)
- Offline fallback (no mock)
- ``$json.<field>`` default when parameter missing
- Per-tool expression / parameter evaluation
- Descriptor registration (CI invariant)
- One end-to-end run that exercises the real engine wiring
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.nodes.agent_tools import (
    exec_agent_calculator,
    exec_agent_code,
    exec_agent_http,
    exec_agent_serpapi,
    exec_agent_think,
    exec_agent_wikipedia,
    exec_agent_workflow,
)


# ── Shared helpers ────────────────────────────────────────────────────


def _node(
    type_: str,
    params: dict[str, Any] | None,
    *,
    id_: str = "t1",
    name: str = "Tool",
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


def _ctx(
    *,
    mocks: dict[str, Any] | None = None,
) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(  # type: ignore[arg-type]
        graph=g,
        credentials={},
        mocks=mocks or {},
    )


def _items(rows: list[dict[str, Any]]):
    from app.services.workflows.items import items_from_json_list

    return items_from_json_list(rows)


# ── 1. agentThink ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_think_mock_echo() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentThink",
        {"thought": "reasoning step"},
    )
    ctx = _ctx(mocks={"think_output": "mock-thought"})
    out = await exec_agent_think(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["tool"] == "agentThink"
    assert j["output"] == "mock-thought"
    assert j["input"] == "reasoning step"
    assert j["source"] == "mock"


@pytest.mark.asyncio
async def test_think_default_field_from_json_thought() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentThink", {"thought": "={{ $json.thought }}"}
    )
    ctx = _ctx()
    out = await exec_agent_think(node, _items([{"thought": "from-json"}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["output"] == "from-json"
    assert j["input"] == "from-json"
    assert j["source"] == "offline"


@pytest.mark.asyncio
async def test_think_offline_echo() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentThink", {"thought": "stay calm"}
    )
    ctx = _ctx()
    out = await exec_agent_think(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["output"] == "stay calm"
    assert j["source"] == "offline"


# ── 2. agentCalculator ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calculator_mock_returns_number() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "2+3"},
    )
    ctx = _ctx(mocks={"calculator_output": 42})
    out = await exec_agent_calculator(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["output"] == 42
    assert j["source"] == "mock"
    assert j["input"] == {"expression": "2+3"}


@pytest.mark.asyncio
async def test_calculator_offline_basic() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "2+3"},
    )
    ctx = _ctx()
    out = await exec_agent_calculator(node, _items([{}]), ctx=ctx)
    assert out[0][1][0].json["output"] == 5
    assert out[0][1][0].json["source"] == "offline"


@pytest.mark.asyncio
async def test_calculator_offline_parens_and_power() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "(2+3)*4"},
    )
    ctx = _ctx()
    out = await exec_agent_calculator(node, _items([{}]), ctx=ctx)
    assert out[0][1][0].json["output"] == 20


@pytest.mark.asyncio
async def test_calculator_offline_min_max_sum() -> None:
    node_min = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "min(1, 2, 3)"},
    )
    node_max = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "max(10, 5)"},
    )
    node_sum = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "sum((1, 2, 3, 4))"},
    )
    ctx = _ctx()
    assert (await exec_agent_calculator(node_min, _items([{}]), ctx=ctx))[0][1][0].json["output"] == 1
    assert (await exec_agent_calculator(node_max, _items([{}]), ctx=ctx))[0][1][0].json["output"] == 10
    assert (await exec_agent_calculator(node_sum, _items([{}]), ctx=ctx))[0][1][0].json["output"] == 10


@pytest.mark.asyncio
async def test_calculator_offline_rejects_import() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "__import__('os').system('echo')"},
    )
    ctx = _ctx()
    with pytest.raises(ValueError):
        await exec_agent_calculator(node, _items([{}]), ctx=ctx)


@pytest.mark.asyncio
async def test_calculator_offline_rejects_unknown_function() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "dangerous(1)"},
    )
    ctx = _ctx()
    with pytest.raises(ValueError):
        await exec_agent_calculator(node, _items([{}]), ctx=ctx)


@pytest.mark.asyncio
async def test_calculator_expression_evaluated() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCalculator",
        {"expression": "={{ $json.a + $json.b }}"},
    )
    ctx = _ctx()
    out = await exec_agent_calculator(node, _items([{"a": 7, "b": 8}]), ctx=ctx)
    assert out[0][1][0].json["output"] == 15


# ── 3. agentCode ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_code_mock_returns_string() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCode",
        {"code": "print('hi')", "language": "python"},
    )
    ctx = _ctx(mocks={"code_output": "exec-result"})
    out = await exec_agent_code(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["output"] == "exec-result"
    assert j["source"] == "mock"


@pytest.mark.asyncio
async def test_code_offline_python_preview() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCode",
        {"code": "x = 1\ny = 2", "language": "python"},
    )
    ctx = _ctx()
    out = await exec_agent_code(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "offline"
    assert "```python" in j["output"]
    assert "x = 1" in j["output"] and "y = 2" in j["output"]
    assert "mocks are required" in j["output"]


@pytest.mark.asyncio
async def test_code_offline_js_preview() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCode",
        {"code": "const x = 1;", "language": "javascript"},
    )
    ctx = _ctx()
    out = await exec_agent_code(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert "```js" in j["output"]
    assert "const x = 1;" in j["output"]


@pytest.mark.asyncio
async def test_code_default_language_is_python() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentCode",
        {"code": "pass"},
    )
    ctx = _ctx()
    out = await exec_agent_code(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["language"] == "python"
    assert "```python" in j["output"]


# ── 4. agentHttp ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_mock_returns_dict() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentHttp",
        {"url": "https://example.com/api", "method": "POST"},
    )
    ctx = _ctx(
        mocks={
            "http_response": {
                "status_code": 201,
                "body": {"ok": True},
                "headers": {"x-foo": "bar"},
            }
        }
    )
    out = await exec_agent_http(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "mock"
    assert j["output"]["status_code"] == 201
    assert j["output"]["body"] == {"ok": True}
    assert j["output"]["headers"] == {"x-foo": "bar"}
    assert j["request"] == {"url": "https://example.com/api", "method": "POST"}


@pytest.mark.asyncio
async def test_http_callable_mock_receives_args() -> None:
    captured: list[tuple[Any, ...]] = []

    def fake(url, method, headers, body, item, params, ctx):
        captured.append((url, method, headers, body, params))
        return {"status": 200, "body": "ok", "headers": {}}

    node = _node(
        "@n8n/n8n-nodes-langchain.agentHttp",
        {"url": "https://x.test/v1", "method": "get"},
    )
    ctx = _ctx(mocks={"http_response": fake})
    out = await exec_agent_http(node, _items([{}]), ctx=ctx)
    assert out[0][1][0].json["output"]["status_code"] == 200
    assert out[0][1][0].json["output"]["body"] == "ok"
    assert captured[0][0] == "https://x.test/v1"
    assert captured[0][1] == "GET"
    assert isinstance(captured[0][2], dict)
    assert captured[0][4] == {"url": "https://x.test/v1", "method": "get"}


@pytest.mark.asyncio
async def test_http_offline_returns_200_with_url_in_body() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentHttp",
        {"url": "https://api.example.com/x", "method": "GET"},
    )
    ctx = _ctx()
    out = await exec_agent_http(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "offline"
    assert j["output"]["status_code"] == 200
    assert "https://api.example.com/x" in j["output"]["body"]
    assert "GET" in j["output"]["body"]


# ── 5. agentWikipedia ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wikipedia_mock_returns_list() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentWikipedia",
        {"query": "n8n"},
    )
    canned = [{"title": "Mock", "snippet": "snip", "url": "https://x/"}]
    ctx = _ctx(mocks={"wikipedia_output": canned})
    out = await exec_agent_wikipedia(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "mock"
    assert j["output"] == canned


@pytest.mark.asyncio
async def test_wikipedia_offline_one_result() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentWikipedia",
        {"query": "open source"},
    )
    ctx = _ctx()
    out = await exec_agent_wikipedia(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "offline"
    assert len(j["output"]) == 1
    assert j["output"][0]["title"] == "Wikipedia: open source"
    assert j["output"][0]["url"] == "https://en.wikipedia.org/wiki/open_source"


@pytest.mark.asyncio
async def test_wikipedia_default_from_json_query() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentWikipedia", {"query": "={{ $json.query }}"}
    )
    ctx = _ctx()
    out = await exec_agent_wikipedia(node, _items([{"query": "fastapi"}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["input"] == {"query": "fastapi"}
    assert j["output"][0]["title"] == "Wikipedia: fastapi"


# ── 6. agentWorkflow ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_mock_returns_dict() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentWorkflow",
        {"workflowId": "wf-1", "data": {"q": "x"}},
    )
    ctx = _ctx(
        mocks={
            "workflow_output": {
                "runId": "sub-fixed00",
                "status": "completed",
                "inputData": {"echo": True},
            }
        }
    )
    out = await exec_agent_workflow(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "mock"
    assert j["output"]["runId"] == "sub-fixed00"
    assert j["output"]["workflowId"] == "wf-1"
    assert j["output"]["inputData"] == {"echo": True}


@pytest.mark.asyncio
async def test_workflow_offline_synthetic_runid() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentWorkflow",
        {"workflowId": "wf-2", "data": {"k": 1}},
    )
    ctx = _ctx()
    out = await exec_agent_workflow(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "offline"
    assert j["output"]["workflowId"] == "wf-2"
    assert j["output"]["status"] == "completed"
    assert j["output"]["runId"].startswith("sub-")
    assert len(j["output"]["runId"]) == len("sub-") + 8
    assert j["output"]["inputData"] == {"k": 1}


@pytest.mark.asyncio
async def test_workflow_callable_mock_receives_workflowid() -> None:
    captured: list[tuple[Any, ...]] = []

    def fake(wf, data, item, params, ctx):
        captured.append((wf, data, item, params))
        return {"runId": "ok"}

    node = _node(
        "@n8n/n8n-nodes-langchain.agentWorkflow",
        {"workflowId": "wf-3", "data": {"x": 1}},
    )
    ctx = _ctx(mocks={"workflow_output": fake})
    out = await exec_agent_workflow(node, _items([{}]), ctx=ctx)
    assert out[0][1][0].json["output"]["runId"] == "ok"
    assert captured[0][0] == "wf-3"
    assert captured[0][1] == {"x": 1}


# ── 7. agentSerpApi ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_serpapi_mock_returns_list() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentSerpApi",
        {"query": "everflow"},
    )
    canned = [{"title": "t", "link": "https://l", "snippet": "s"}]
    ctx = _ctx(mocks={"serp_output": canned})
    out = await exec_agent_serpapi(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "mock"
    assert j["output"] == canned


@pytest.mark.asyncio
async def test_serpapi_offline_returns_5_results() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentSerpApi",
        {"query": "ai tools"},
    )
    ctx = _ctx()
    out = await exec_agent_serpapi(node, _items([{}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["source"] == "offline"
    assert len(j["output"]) == 5
    assert j["output"][0]["title"] == "Result 1 for ai tools"
    assert j["output"][4]["link"] == "https://example.com/5"


@pytest.mark.asyncio
async def test_serpapi_default_from_json_text() -> None:
    node = _node(
        "@n8n/n8n-nodes-langchain.agentSerpApi", {"query": "={{ $json.text }}"}
    )
    ctx = _ctx()
    out = await exec_agent_serpapi(node, _items([{"text": "graphql"}]), ctx=ctx)
    j = out[0][1][0].json
    assert j["input"] == {"query": "graphql"}
    assert j["output"][0]["title"] == "Result 1 for graphql"


# ── 8. Descriptor registration (CI invariant) ────────────────────────


@pytest.mark.parametrize(
    "n8n_type,exec_name",
    [
        ("@n8n/n8n-nodes-langchain.agentThink", "exec_agent_think"),
        ("@n8n/n8n-nodes-langchain.agentCalculator", "exec_agent_calculator"),
        ("@n8n/n8n-nodes-langchain.agentCode", "exec_agent_code"),
        ("@n8n/n8n-nodes-langchain.agentHttp", "exec_agent_http"),
        ("@n8n/n8n-nodes-langchain.agentWikipedia", "exec_agent_wikipedia"),
        ("@n8n/n8n-nodes-langchain.agentWorkflow", "exec_agent_workflow"),
        ("@n8n/n8n-nodes-langchain.agentSerpApi", "exec_agent_serpapi"),
    ],
)
def test_descriptor_is_registered(n8n_type: str, exec_name: str) -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert n8n_type in REGISTRY, f"{n8n_type} missing from REGISTRY"
    assert n8n_type in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES[n8n_type] == "ai"
    desc = REGISTRY[n8n_type]
    assert desc.executor.endswith(f":{exec_name}")
    assert desc.category == "ai"


# ── 9. End-to-end: Manual Trigger → agentCalculator (mock) → Set ────


def _doc(nodes, connections):
    return {"name": "agent-tools-e2e", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_calculator_into_set() -> None:
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "c1",
                "Calc",
                "@n8n/n8n-nodes-langchain.agentCalculator",
                {"expression": "={{ $json.a + $json.b }}"},
            ),
            _n(
                "s1",
                "Edit Fields",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "answer",
                                "value": "={{ $json.output }}",
                                "type": "string",
                            }
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Calc", "type": "main", "index": 0}]]},
            "Calc": {
                "main": [[{"node": "Edit Fields", "type": "main", "index": 0}]]
            },
        },
    )
    mocks = {"calculator_output": 99}
    pin_data = {"Start": [{"a": 1, "b": 2}]}
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual", pin_data=pin_data)
    assert result.status == "success", result.error_message

    calc_step = next(s for s in result.steps if s.node_name == "Calc")
    assert calc_step.status == "success", calc_step.error
    assert calc_step.output_count == 1
    assert calc_step.sample_output[0]["json"]["output"] == 99
    assert calc_step.sample_output[0]["json"]["tool"] == "agentCalculator"

    set_step = next(s for s in result.steps if s.node_name == "Edit Fields")
    assert set_step.status == "success", set_step.error
    assert set_step.sample_output[0]["json"]["answer"] == 99
