"""Tests for AWS / cloud infra nodes (S3, Lambda, SES, SQS, SNS, Snowflake, Elasticsearch)."""
from __future__ import annotations
from typing import Any
import pytest
from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.aws import exec_aws_lambda, exec_aws_s3, exec_aws_ses, exec_aws_sns, exec_aws_sqs, exec_elasticsearch, exec_snowflake
from app.services.workflows.registry import REGISTRY

def _node(params, *, type_="n8n-nodes-base.awsS3", id_="n1", name="AWS S3"):
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
async def test_aws_s3_dict_mock():
    node = _node({"operation": "upload"})
    ctx = _ctx({"aws_s3_response": {"bucketName": "b1", "custom": True}})
    items = _out_items(await exec_aws_s3(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_aws_s3_offline():
    node = _node({"operation": "download", "bucketName": "b1", "fileName": "f.txt"})
    items = _out_items(await exec_aws_s3(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "aws_s3"

@pytest.mark.asyncio
async def test_aws_lambda_dict_mock():
    node = _node({"operation": "invoke"}, type_="n8n-nodes-base.awsLambda", name="Lambda")
    ctx = _ctx({"aws_lambda_response": {"functionName": "fn1", "custom": True}})
    items = _out_items(await exec_aws_lambda(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_aws_lambda_offline():
    node = _node({"operation": "invoke", "functionName": "myFn"}, type_="n8n-nodes-base.awsLambda")
    items = _out_items(await exec_aws_lambda(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "aws_lambda"

@pytest.mark.asyncio
async def test_aws_ses_dict_mock():
    node = _node({"operation": "send"}, type_="n8n-nodes-base.awsSes", name="SES")
    ctx = _ctx({"aws_ses_response": {"messageId": "m1", "custom": True}})
    items = _out_items(await exec_aws_ses(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_aws_ses_offline():
    node = _node({"operation": "send", "to": "a@b.com", "subject": "Hi"}, type_="n8n-nodes-base.awsSes")
    items = _out_items(await exec_aws_ses(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "aws_ses"

@pytest.mark.asyncio
async def test_aws_sqs_dict_mock():
    node = _node({"operation": "sendMessage"}, type_="n8n-nodes-base.awsSqs", name="SQS")
    ctx = _ctx({"aws_sqs_response": {"messageId": "m1", "custom": True}})
    items = _out_items(await exec_aws_sqs(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_aws_sqs_offline():
    node = _node({"operation": "sendMessage"}, type_="n8n-nodes-base.awsSqs")
    items = _out_items(await exec_aws_sqs(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "aws_sqs"

@pytest.mark.asyncio
async def test_aws_sns_dict_mock():
    node = _node({"operation": "publish"}, type_="n8n-nodes-base.awsSns", name="SNS")
    ctx = _ctx({"aws_sns_response": {"messageId": "m1", "custom": True}})
    items = _out_items(await exec_aws_sns(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_aws_sns_offline():
    node = _node({"operation": "publish"}, type_="n8n-nodes-base.awsSns")
    items = _out_items(await exec_aws_sns(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "aws_sns"

@pytest.mark.asyncio
async def test_snowflake_dict_mock():
    node = _node({"operation": "executeQuery"}, type_="n8n-nodes-base.snowflake", name="Snowflake")
    ctx = _ctx({"snowflake_response": {"rows": [{"x": 1}], "custom": True}})
    items = _out_items(await exec_snowflake(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_snowflake_offline_query():
    node = _node({"operation": "executeQuery"}, type_="n8n-nodes-base.snowflake")
    items = _out_items(await exec_snowflake(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "snowflake"
    assert "rows" in items[0].json

@pytest.mark.asyncio
async def test_elasticsearch_dict_mock():
    node = _node({"operation": "search"}, type_="n8n-nodes-base.elasticsearch", name="ES")
    ctx = _ctx({"elasticsearch_response": {"hits": [{"_id": "h1"}], "custom": True}})
    items = _out_items(await exec_elasticsearch(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_elasticsearch_offline_search():
    node = _node({"operation": "search", "index": "myindex"}, type_="n8n-nodes-base.elasticsearch")
    items = _out_items(await exec_elasticsearch(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "elasticsearch"
    assert "hits" in items[0].json

@pytest.mark.asyncio
async def test_e2e_snowflake_to_set():
    doc = {
        "nodes": [
            {"id": "t", "name": "Manual", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "parameters": {}, "position": [0, 0]},
            {"id": "sf", "name": "Snowflake", "type": "n8n-nodes-base.snowflake", "typeVersion": 1, "parameters": {"operation": "executeQuery"}, "position": [200, 0]},
            {"id": "s", "name": "Set", "type": "n8n-nodes-base.set", "typeVersion": 1, "parameters": {"assignments": {"assignments": [{"name": "result", "value": "={{ $json.source }}", "type": "string"}]}}, "position": [400, 0]},
        ],
        "connections": {"t": {"main": [[{"node": "sf", "index": 0}]]}, "sf": {"main": [[{"node": "s", "index": 0}]]}},
    }
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run()
    assert result.status == "success"
    assert result.final_items[0]["json"]["result"] == "snowflake"

def test_descriptors_registered():
    for t in ["n8n-nodes-base.awsS3", "n8n-nodes-base.awsLambda", "n8n-nodes-base.awsSes", "n8n-nodes-base.awsSqs", "n8n-nodes-base.awsSns", "n8n-nodes-base.snowflake", "n8n-nodes-base.elasticsearch"]:
        assert t in REGISTRY, f"{t} not registered"