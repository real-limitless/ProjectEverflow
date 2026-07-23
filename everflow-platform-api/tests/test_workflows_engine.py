"""Expression, node, and Stock Agent Emailer dry-run engine tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.core import _conditions_pass

FIXTURE = Path(__file__).parent / "fixtures" / "workflows" / "stock_agent_emailer.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_expression_json_field() -> None:
    ctx = ExpressionContext(item=ExecutionItem(json={"name": "Portfolio_Positions.csv"}))
    assert evaluate("={{ $json.name }}", ctx) == "Portfolio_Positions.csv"


def test_expression_node_ref() -> None:
    ctx = ExpressionContext(
        item=ExecutionItem(json={}),
        node_outputs={
            "Download Portfolio File": [ExecutionItem(json={"name": "foo.csv"})],
        },
    )
    assert evaluate('={{ $("Download Portfolio File").item.json.name }}', ctx) == "foo.csv"


def test_expression_to_json_string() -> None:
    ctx = ExpressionContext(item=ExecutionItem(json={"rows": [{"a": 1}, {"b": 2}]}))
    out = evaluate("={{ $json.rows.toJsonString() }}", ctx)
    assert '"a": 1' in out or '"a":1' in out.replace(" ", "")


def test_expression_now_format() -> None:
    from datetime import datetime, timezone

    ctx = ExpressionContext(
        item=ExecutionItem(json={}),
        now=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    # subject style
    subj = evaluate('=Portfolio Research Report - {{ $now.toFormat("MMMM d, yyyy") }}', ctx)
    assert "Portfolio Research Report" in subj
    assert "2026" in subj


def test_filter_conditions_or() -> None:
    params = {
        "conditions": {
            "conditions": [
                {
                    "leftValue": "={{ $json.name }}",
                    "operator": {"type": "string", "operation": "contains"},
                    "rightValue": "Portfolio_Positions",
                },
                {
                    "leftValue": "={{ $json.name }}",
                    "operator": {"type": "string", "operation": "contains"},
                    "rightValue": "History_for_Account",
                },
            ],
            "combinator": "or",
        }
    }
    ok = ExpressionContext(item=ExecutionItem(json={"name": "History_for_Account_x.csv"}))
    bad = ExpressionContext(item=ExecutionItem(json={"name": "readme.txt"}))
    assert _conditions_pass(params, ok) is True
    assert _conditions_pass(params, bad) is False


@pytest.mark.asyncio
async def test_mini_pipeline_set_filter_aggregate() -> None:
    doc = {
        "name": "mini",
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
                "id": "s1",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3,
                "position": [200, 0],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            {"name": "x", "value": "hello", "type": "string"},
                        ]
                    },
                    "includeOtherFields": True,
                },
            },
            {
                "id": "a1",
                "name": "Agg",
                "type": "n8n-nodes-base.aggregate",
                "typeVersion": 1,
                "position": [400, 0],
                "parameters": {
                    "aggregate": "aggregateAllItemData",
                    "destinationFieldName": "rows",
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
            "Set": {"main": [[{"node": "Agg", "type": "main", "index": 0}]]},
        },
    }
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    names = [s.node_name for s in result.steps]
    assert "Start" in names and "Set" in names and "Agg" in names
    # final aggregated
    assert any("Agg" == s.node_name and s.status == "success" for s in result.steps)


@pytest.mark.asyncio
async def test_code_clean_commas() -> None:
    doc = {
        "name": "code",
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
                "id": "c1",
                "name": "Clean",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [200, 0],
                "parameters": {
                    "mode": "runOnceForEachItem",
                    "jsCode": (
                        "const lines = $json.text.split(/\\r\\n|\\n/);\n"
                        "const cleaned = lines.map(line => line.replace(/,\\s*$/, '')).join('\\n');\n"
                        "return { ...$json, text: cleaned };"
                    ),
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Clean", "type": "main", "index": 0}]]},
        },
        "pinData": {
            "Start": [{"json": {"text": "a,b,\nc,d,\n"}}],
        },
    }
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message
    # sample from Clean step
    clean = next(s for s in result.steps if s.node_name == "Clean")
    assert clean.sample_output
    text = clean.sample_output[0]["json"]["text"]
    assert "a,b\nc,d" in text.replace("\r", "")


@pytest.mark.asyncio
async def test_stock_agent_emailer_dry_run() -> None:
    doc = _load_fixture()
    portfolio_csv = "Symbol,Qty,Cost\nAAPL,10,150.0,\nMSFT,5,300.0,\n"
    history_csv = "Date,Symbol,Side,Qty\n2026-01-01,AAPL,BUY,10,\n"

    mocks = {
        "ftp_files": {
            "/home/chen/Portfolio_Positions.csv": portfolio_csv.encode(),
            "/home/chen/History_for_Account.csv": history_csv.encode(),
            "/home/chen/readme.txt": b"ignore me",
        },
        "capture_email": True,
        "agent_output": (
            "# Portfolio Research\n\n## AAPL\n\n**Hold** — solid core position.\n\n"
            "## MSFT\n\n*Watch* concentration.\n"
        ),
    }

    engine = WorkflowEngine(doc, mocks=mocks, max_steps=2000)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    step_names = [s.node_name for s in result.steps]
    assert "FTP" in step_names
    assert "Filter Portfolio Files" in step_names
    assert "Single Stock Researcher" in step_names
    assert "Send Portfolio Research Email" in step_names
    assert all(s.status == "success" for s in result.steps), [
        (s.node_name, s.error) for s in result.steps if s.status != "success"
    ]

    assert result.sent_emails, "expected captured email"
    email = result.sent_emails[0]
    assert "Portfolio Research" in email.get("subject", "") or email.get("subject")
    assert email.get("html") or email.get("text")

    # research path wrote rows (table may be deleted by final cleanup node)
    insert_steps = [s for s in result.steps if s.node_name == "Insert row"]
    assert insert_steps, "expected Insert row steps"
    get_steps = [s for s in result.steps if s.node_name == "Get row(s)"]
    assert get_steps and get_steps[-1].output_count >= 1
