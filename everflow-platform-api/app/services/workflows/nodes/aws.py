"""AWS executors (clean-room ``n8n-nodes-base.*``).

Implements AWS S3, AWS Lambda, AWS SES, AWS SQS, AWS SNS, Snowflake, Elasticsearch.
All mock-driven — no real network I/O.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


def _ectx(item, ctx):
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)

def _coerce_str(value):
    if value is None: return ""
    if isinstance(value, str): return value
    if isinstance(value, (int, float, bool)): return str(value)
    if isinstance(value, (list, tuple)): return ", ".join(_coerce_str(v) for v in value if v is not None)
    return str(value)

def _resolve_param(key, params, item, ctx, *, default=""):
    raw = params.get(key)
    if raw is None: return default
    return _coerce_str(evaluate(raw, _ectx(item, ctx)))

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _gen_id(*parts):
    return str(abs(hash("".join(parts) + _now_iso())) % 100000)

def _mock_response(mock_key, operation, params, item, ctx):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is None: return None
    if callable(mock):
        result = mock(operation, params, item, ctx)
        return result if isinstance(result, dict) else None
    return mock if isinstance(mock, dict) else None

def _http_response(ctx):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    hr = mocks.get("http_response")
    if isinstance(hr, dict):
        body = hr.get("body")
        if isinstance(body, dict): return body
    return None


AWS_S3_OPERATIONS = ("download", "upload", "list", "delete", "createBucket", "deleteBucket")
AWS_S3_DEFAULT_OPERATION = "download"

async def exec_aws_s3(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_S3_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_s3_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        bucket = _resolve_param("bucketName", params, item, ctx)
        key = _resolve_param("fileName", params, item, ctx)
        out.append(ExecutionItem(json={"bucketName": bucket, "fileName": key, "fileSize": 4096, "operation": operation, "source": "aws_s3", "updatedAt": _now_iso()}))
    return [(0, out)]


AWS_LAMBDA_OPERATIONS = ("invoke", "list", "get")
AWS_LAMBDA_DEFAULT_OPERATION = "invoke"

async def exec_aws_lambda(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_LAMBDA_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_lambda_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        fn_name = _resolve_param("functionName", params, item, ctx)
        out.append(ExecutionItem(json={"functionName": fn_name, "status": 200, "operation": operation, "source": "aws_lambda", "executedAt": _now_iso()}))
    return [(0, out)]


AWS_SES_OPERATIONS = ("send", "sendTemplate", "sendBulk")
AWS_SES_DEFAULT_OPERATION = "send"

async def exec_aws_ses(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_SES_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_ses_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        out.append(ExecutionItem(json={"messageId": _gen_id("ses", to), "status": "sent", "to": to, "subject": subject, "operation": operation, "source": "aws_ses", "sentAt": _now_iso()}))
    return [(0, out)]


AWS_SQS_OPERATIONS = ("sendMessage", "receiveMessage", "deleteMessage", "purge")
AWS_SQS_DEFAULT_OPERATION = "sendMessage"

async def exec_aws_sqs(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_SQS_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_sqs_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        out.append(ExecutionItem(json={"messageId": _gen_id("sqs"), "operation": operation, "source": "aws_sqs", "sentAt": _now_iso()}))
    return [(0, out)]


AWS_SNS_OPERATIONS = ("publish", "createTopic", "subscribe", "unsubscribe", "deleteTopic")
AWS_SNS_DEFAULT_OPERATION = "publish"

async def exec_aws_sns(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_SNS_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_sns_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        out.append(ExecutionItem(json={"messageId": _gen_id("sns"), "operation": operation, "source": "aws_sns", "publishedAt": _now_iso()}))
    return [(0, out)]


SNOWFLAKE_OPERATIONS = ("executeQuery", "insert", "update", "delete", "listTables")
SNOWFLAKE_DEFAULT_OPERATION = "executeQuery"

async def exec_snowflake(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", SNOWFLAKE_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("snowflake_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        if operation == "executeQuery":
            rows = [{"id": i, "val": f"row-{i}"} for i in range(3)]
            out.append(ExecutionItem(json={"rows": rows, "totalRows": len(rows), "operation": operation, "source": "snowflake", "executedAt": _now_iso()}))
        else:
            out.append(ExecutionItem(json={"affectedRows": 1, "operation": operation, "source": "snowflake", "executedAt": _now_iso()}))
    return [(0, out)]


ELASTICSEARCH_OPERATIONS = ("index", "search", "get", "update", "delete", "createIndex", "deleteIndex")
ELASTICSEARCH_DEFAULT_OPERATION = "search"

async def exec_elasticsearch(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", ELASTICSEARCH_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("elasticsearch_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        index = _resolve_param("index", params, item, ctx)
        if operation == "search":
            hits = [{"_id": f"hit-{i}", "_source": {"name": f"doc-{i}"}} for i in range(3)]
            out.append(ExecutionItem(json={"hits": hits, "total": len(hits), "index": index, "operation": operation, "source": "elasticsearch", "queriedAt": _now_iso()}))
        else:
            out.append(ExecutionItem(json={"index": index, "operation": operation, "source": "elasticsearch", "updatedAt": _now_iso()}))
    return [(0, out)]