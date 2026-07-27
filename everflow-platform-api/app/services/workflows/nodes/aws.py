"""AWS executors (clean-room ``n8n-nodes-base.*``).

Implements AWS S3, AWS Lambda, AWS SES, AWS SQS, AWS SNS, Snowflake,
Elasticsearch.

When the appropriate credential (``aws`` for S3/Lambda/SES/SQS/SNS,
``snowflakeApi`` for Snowflake, ``elasticSearchApi`` for Elasticsearch) is
attached and no mock is present, real calls are made to the respective API
via :func:`execute_http_request`. Otherwise the executor is mock-driven with
an offline synthetic fallback.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

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


def _aws_auth_headers(cred: dict[str, Any]) -> dict[str, str] | None:
    """Build AWS auth headers from a pre-signed ``authorization`` header or
    ``sessionToken`` in the credential. Returns ``None`` when no auth can
    be derived."""
    headers: dict[str, str] = {}
    auth = cred.get("authorization")
    if auth:
        headers["Authorization"] = str(auth)
    session_token = cred.get("sessionToken")
    if session_token:
        headers["X-Amz-Security-Token"] = str(session_token)
    if not headers:
        return None
    return headers


# ── AWS S3 ─────────────────────────────────────────────────────────────

AWS_S3_OPERATIONS = ("download", "upload", "list", "delete", "createBucket", "deleteBucket")
AWS_S3_DEFAULT_OPERATION = "download"


def _build_aws_s3_request(cred, operation, params, item, ctx):
    """Build a real AWS S3 request. Returns ``None`` when auth or required
    parameters are missing."""
    region = str(cred.get("region") or "")
    bucket = _resolve_param("bucketName", params, item, ctx)
    if not region or not bucket:
        return None
    headers = _aws_auth_headers(cred)
    if headers is None:
        return None
    if operation == "list":
        url = f"https://{bucket}.s3.{region}.amazonaws.com/?list-type=2"
        return HttpRequestConfig(url=url, method="GET", headers=headers, response_mode="json", timeout=30.0)
    if operation in ("createBucket", "deleteBucket"):
        url = f"https://{bucket}.s3.{region}.amazonaws.com"
        method = "PUT" if operation == "createBucket" else "DELETE"
        return HttpRequestConfig(url=url, method=method, headers=headers, response_mode="json", timeout=30.0)
    key = _resolve_param("fileName", params, item, ctx)
    url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
    method = {"download": "GET", "upload": "PUT", "delete": "DELETE"}.get(operation, "GET")
    return HttpRequestConfig(url=url, method=method, headers=headers, response_mode="json", timeout=30.0)


def _envelope_from_aws_s3_api(data, operation, params, item, ctx):
    bucket = _resolve_param("bucketName", params, item, ctx)
    key = _resolve_param("fileName", params, item, ctx)
    return {
        "bucketName": bucket,
        "fileName": key,
        "operation": operation,
        "source": "aws_s3_api",
        "updatedAt": _now_iso(),
        "raw": data,
    }


async def exec_aws_s3(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_S3_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_s3_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "aws")
        if cred:
            cfg = _build_aws_s3_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_aws_s3_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("aws_s3 HTTP call failed: %s", exc)
        bucket = _resolve_param("bucketName", params, item, ctx)
        key = _resolve_param("fileName", params, item, ctx)
        out.append(ExecutionItem(json={"bucketName": bucket, "fileName": key, "fileSize": 4096, "operation": operation, "source": "aws_s3", "updatedAt": _now_iso()}))
    return [(0, out)]


# ── AWS Lambda ─────────────────────────────────────────────────────────

AWS_LAMBDA_OPERATIONS = ("invoke", "list", "get")
AWS_LAMBDA_DEFAULT_OPERATION = "invoke"


def _build_aws_lambda_request(cred, operation, params, item, ctx):
    """Build a real AWS Lambda request. Returns ``None`` when auth or
    required parameters are missing."""
    region = str(cred.get("region") or "")
    if not region:
        return None
    headers = _aws_auth_headers(cred)
    if headers is None:
        return None
    fn_name = _resolve_param("functionName", params, item, ctx)
    if operation == "invoke":
        if not fn_name:
            return None
        url = f"https://lambda.{region}.amazonaws.com/2015-03-31/functions/{fn_name}/invocations"
        return HttpRequestConfig(url=url, method="POST", headers=headers, response_mode="json", timeout=30.0)
    if operation == "list":
        url = f"https://lambda.{region}.amazonaws.com/2015-03-31/functions"
        return HttpRequestConfig(url=url, method="GET", headers=headers, response_mode="json", timeout=30.0)
    if operation == "get":
        if not fn_name:
            return None
        url = f"https://lambda.{region}.amazonaws.com/2015-03-31/functions/{fn_name}"
        return HttpRequestConfig(url=url, method="GET", headers=headers, response_mode="json", timeout=30.0)
    return None


def _envelope_from_aws_lambda_api(data, operation, params, item, ctx):
    fn_name = _resolve_param("functionName", params, item, ctx)
    return {
        "functionName": fn_name,
        "status": 200,
        "operation": operation,
        "source": "aws_lambda_api",
        "executedAt": _now_iso(),
        "raw": data,
    }


async def exec_aws_lambda(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_LAMBDA_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_lambda_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "aws")
        if cred:
            cfg = _build_aws_lambda_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_aws_lambda_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("aws_lambda HTTP call failed: %s", exc)
        fn_name = _resolve_param("functionName", params, item, ctx)
        out.append(ExecutionItem(json={"functionName": fn_name, "status": 200, "operation": operation, "source": "aws_lambda", "executedAt": _now_iso()}))
    return [(0, out)]


# ── AWS SES ────────────────────────────────────────────────────────────

AWS_SES_OPERATIONS = ("send", "sendTemplate", "sendBulk")
AWS_SES_DEFAULT_OPERATION = "send"


def _build_aws_ses_request(cred, operation, params, item, ctx):
    """Build a real AWS SES v2 request. Returns ``None`` when auth or
    required parameters are missing."""
    region = str(cred.get("region") or "")
    if not region:
        return None
    headers = _aws_auth_headers(cred)
    if headers is None:
        return None
    to = _resolve_param("to", params, item, ctx)
    subject = _resolve_param("subject", params, item, ctx)
    body_text = _resolve_param("body", params, item, ctx) or _resolve_param("text", params, item, ctx)
    body: dict[str, Any] = {
        "Content": {
            "Simple": {
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body_text}},
            }
        },
        "Destination": {"ToAddresses": [to] if to else []},
    }
    url = f"https://email.{region}.amazonaws.com/v2/email/outbound-emails"
    return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="json", response_mode="json", timeout=30.0)


def _envelope_from_aws_ses_api(data, operation, params, item, ctx):
    to = _resolve_param("to", params, item, ctx)
    subject = _resolve_param("subject", params, item, ctx)
    return {
        "messageId": data.get("MessageId") or _gen_id("ses", to),
        "status": "sent",
        "to": to,
        "subject": subject,
        "operation": operation,
        "source": "aws_ses_api",
        "sentAt": _now_iso(),
        "raw": data,
    }


async def exec_aws_ses(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_SES_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_ses_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "aws")
        if cred:
            cfg = _build_aws_ses_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_aws_ses_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("aws_ses HTTP call failed: %s", exc)
        to = _resolve_param("to", params, item, ctx)
        subject = _resolve_param("subject", params, item, ctx)
        out.append(ExecutionItem(json={"messageId": _gen_id("ses", to), "status": "sent", "to": to, "subject": subject, "operation": operation, "source": "aws_ses", "sentAt": _now_iso()}))
    return [(0, out)]


# ── AWS SQS ────────────────────────────────────────────────────────────

AWS_SQS_OPERATIONS = ("sendMessage", "receiveMessage", "deleteMessage", "purge")
AWS_SQS_DEFAULT_OPERATION = "sendMessage"


def _build_aws_sqs_request(cred, operation, params, item, ctx):
    """Build a real AWS SQS request. Returns ``None`` when auth or required
    parameters are missing."""
    region = str(cred.get("region") or "")
    account_id = str(cred.get("accountId") or "")
    queue_name = _resolve_param("queueName", params, item, ctx)
    if not region or not account_id or not queue_name:
        return None
    headers = _aws_auth_headers(cred)
    if headers is None:
        return None
    url = f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"
    if operation == "sendMessage":
        message_body = _resolve_param("messageBody", params, item, ctx) or _resolve_param("body", params, item, ctx)
        body = {"Action": "SendMessage", "MessageBody": message_body}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    if operation == "receiveMessage":
        body = {"Action": "ReceiveMessage"}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    if operation == "deleteMessage":
        receipt_handle = _resolve_param("receiptHandle", params, item, ctx)
        body = {"Action": "DeleteMessage", "ReceiptHandle": receipt_handle}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    if operation == "purge":
        body = {"Action": "PurgeQueue"}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    return None


def _envelope_from_aws_sqs_api(data, operation, params, item, ctx):
    return {
        "messageId": _gen_id("sqs"),
        "operation": operation,
        "source": "aws_sqs_api",
        "sentAt": _now_iso(),
        "raw": data,
    }


async def exec_aws_sqs(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_SQS_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_sqs_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "aws")
        if cred:
            cfg = _build_aws_sqs_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_aws_sqs_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("aws_sqs HTTP call failed: %s", exc)
        out.append(ExecutionItem(json={"messageId": _gen_id("sqs"), "operation": operation, "source": "aws_sqs", "sentAt": _now_iso()}))
    return [(0, out)]


# ── AWS SNS ────────────────────────────────────────────────────────────

AWS_SNS_OPERATIONS = ("publish", "createTopic", "subscribe", "unsubscribe", "deleteTopic")
AWS_SNS_DEFAULT_OPERATION = "publish"


def _build_aws_sns_request(cred, operation, params, item, ctx):
    """Build a real AWS SNS request. Returns ``None`` when auth or required
    parameters are missing."""
    region = str(cred.get("region") or "")
    if not region:
        return None
    headers = _aws_auth_headers(cred)
    if headers is None:
        return None
    url = f"https://sns.{region}.amazonaws.com/"
    if operation == "publish":
        topic_arn = _resolve_param("topicArn", params, item, ctx)
        message = _resolve_param("message", params, item, ctx) or _resolve_param("body", params, item, ctx)
        body = {"Action": "Publish", "TopicArn": topic_arn, "Message": message}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    if operation == "createTopic":
        name = _resolve_param("name", params, item, ctx)
        body = {"Action": "CreateTopic", "Name": name}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    if operation == "subscribe":
        topic_arn = _resolve_param("topicArn", params, item, ctx)
        protocol = _resolve_param("protocol", params, item, ctx) or "https"
        endpoint = _resolve_param("endpoint", params, item, ctx)
        body = {"Action": "Subscribe", "TopicArn": topic_arn, "Protocol": protocol, "Endpoint": endpoint}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    if operation == "unsubscribe":
        subscription_arn = _resolve_param("subscriptionArn", params, item, ctx)
        body = {"Action": "Unsubscribe", "SubscriptionArn": subscription_arn}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    if operation == "deleteTopic":
        topic_arn = _resolve_param("topicArn", params, item, ctx)
        body = {"Action": "DeleteTopic", "TopicArn": topic_arn}
        return HttpRequestConfig(url=url, method="POST", headers=headers, body=body, body_mode="form", response_mode="json", timeout=30.0)
    return None


def _envelope_from_aws_sns_api(data, operation, params, item, ctx):
    return {
        "messageId": _gen_id("sns"),
        "operation": operation,
        "source": "aws_sns_api",
        "publishedAt": _now_iso(),
        "raw": data,
    }


async def exec_aws_sns(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AWS_SNS_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("aws_sns_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "aws")
        if cred:
            cfg = _build_aws_sns_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_aws_sns_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("aws_sns HTTP call failed: %s", exc)
        out.append(ExecutionItem(json={"messageId": _gen_id("sns"), "operation": operation, "source": "aws_sns", "publishedAt": _now_iso()}))
    return [(0, out)]


# ── Snowflake ──────────────────────────────────────────────────────────

SNOWFLAKE_OPERATIONS = ("executeQuery", "insert", "update", "delete", "listTables")
SNOWFLAKE_DEFAULT_OPERATION = "executeQuery"


def _build_snowflake_request(cred, operation, params, item, ctx):
    """Build a real Snowflake SQL API request. Returns ``None`` when auth
    or required parameters are missing."""
    account = str(cred.get("account") or "")
    username = str(cred.get("username") or "")
    password = str(cred.get("password") or "")
    if not account or not username or not password:
        return None
    url = f"https://{account}.snowflakecomputing.com/api/v2/statements"
    if operation == "listTables":
        sql = "SHOW TABLES"
    else:
        sql = _resolve_param("query", params, item, ctx) or _resolve_param("sql", params, item, ctx)
    body: dict[str, Any] = {
        "statement": sql,
        "warehouse": str(cred.get("warehouse") or "COMPUTE_WH"),
        "database": str(cred.get("database") or ""),
        "schema": str(cred.get("schema") or "PUBLIC"),
    }
    return HttpRequestConfig(
        url=url, method="POST", body=body, body_mode="json",
        auth="basic", auth_credential={"username": username, "password": password},
        response_mode="json", timeout=30.0,
    )


def _envelope_from_snowflake_api(data, operation, params, item, ctx):
    if operation == "executeQuery":
        inner = data.get("data") if isinstance(data.get("data"), dict) else {}
        rows = inner.get("rows") if isinstance(inner.get("rows"), list) else []
        return {
            "rows": rows,
            "totalRows": len(rows),
            "operation": operation,
            "source": "snowflake_api",
            "executedAt": _now_iso(),
            "raw": data,
        }
    inner = data.get("data") if isinstance(data.get("data"), dict) else {}
    affected = inner.get("rowcount", 1) if isinstance(inner.get("rowcount"), int) else 1
    return {
        "affectedRows": affected,
        "operation": operation,
        "source": "snowflake_api",
        "executedAt": _now_iso(),
        "raw": data,
    }


async def exec_snowflake(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", SNOWFLAKE_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("snowflake_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "snowflakeApi")
        if cred:
            cfg = _build_snowflake_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_snowflake_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("snowflake HTTP call failed: %s", exc)
        if operation == "executeQuery":
            rows = [{"id": i, "val": f"row-{i}"} for i in range(3)]
            out.append(ExecutionItem(json={"rows": rows, "totalRows": len(rows), "operation": operation, "source": "snowflake", "executedAt": _now_iso()}))
        else:
            out.append(ExecutionItem(json={"affectedRows": 1, "operation": operation, "source": "snowflake", "executedAt": _now_iso()}))
    return [(0, out)]


# ── Elasticsearch ──────────────────────────────────────────────────────

ELASTICSEARCH_OPERATIONS = ("index", "search", "get", "update", "delete", "createIndex", "deleteIndex")
ELASTICSEARCH_DEFAULT_OPERATION = "search"


def _build_elasticsearch_request(cred, operation, params, item, ctx):
    """Build a real Elasticsearch request. Returns ``None`` when auth or
    required parameters are missing."""
    base_url = str(cred.get("baseUrl") or "").rstrip("/")
    api_key = str(cred.get("apiKey") or "")
    if not base_url or not api_key:
        return None
    index = _resolve_param("index", params, item, ctx)
    auth_cred = {"apiKey": api_key}
    if operation == "search":
        url = f"{base_url}/{index}/_search"
        body = _resolve_param("query", params, item, ctx) or {}
        if isinstance(body, str):
            return HttpRequestConfig(url=url, method="POST", body=body, body_mode="raw",
                                     auth="bearer", auth_credential=auth_cred,
                                     response_mode="json", timeout=30.0)
        return HttpRequestConfig(url=url, method="POST", body=body, body_mode="json",
                                 auth="bearer", auth_credential=auth_cred,
                                 response_mode="json", timeout=30.0)
    if operation in ("index", "create"):
        url = f"{base_url}/{index}/_doc"
        body = _resolve_param("body", params, item, ctx) or item.json
        return HttpRequestConfig(url=url, method="POST", body=body, body_mode="json",
                                 auth="bearer", auth_credential=auth_cred,
                                 response_mode="json", timeout=30.0)
    if operation == "get":
        doc_id = _resolve_param("id", params, item, ctx)
        url = f"{base_url}/{index}/_doc/{doc_id}"
        return HttpRequestConfig(url=url, method="GET",
                                 auth="bearer", auth_credential=auth_cred,
                                 response_mode="json", timeout=30.0)
    if operation == "update":
        doc_id = _resolve_param("id", params, item, ctx)
        url = f"{base_url}/{index}/_update/{doc_id}"
        body = {"doc": item.json}
        return HttpRequestConfig(url=url, method="POST", body=body, body_mode="json",
                                 auth="bearer", auth_credential=auth_cred,
                                 response_mode="json", timeout=30.0)
    if operation == "delete":
        doc_id = _resolve_param("id", params, item, ctx)
        url = f"{base_url}/{index}/_doc/{doc_id}"
        return HttpRequestConfig(url=url, method="DELETE",
                                 auth="bearer", auth_credential=auth_cred,
                                 response_mode="json", timeout=30.0)
    if operation == "createIndex":
        url = f"{base_url}/{index}"
        return HttpRequestConfig(url=url, method="PUT",
                                 auth="bearer", auth_credential=auth_cred,
                                 response_mode="json", timeout=30.0)
    if operation == "deleteIndex":
        url = f"{base_url}/{index}"
        return HttpRequestConfig(url=url, method="DELETE",
                                 auth="bearer", auth_credential=auth_cred,
                                 response_mode="json", timeout=30.0)
    return None


def _envelope_from_elasticsearch_api(data, operation, params, item, ctx):
    index = _resolve_param("index", params, item, ctx)
    if operation == "search":
        hits_obj = data.get("hits") if isinstance(data.get("hits"), dict) else {}
        hits = hits_obj.get("hits", []) if isinstance(hits_obj.get("hits"), list) else []
        return {
            "hits": hits,
            "total": len(hits),
            "index": index,
            "operation": operation,
            "source": "elasticsearch_api",
            "queriedAt": _now_iso(),
            "raw": data,
        }
    return {
        "index": index,
        "operation": operation,
        "source": "elasticsearch_api",
        "updatedAt": _now_iso(),
        "raw": data,
    }


async def exec_elasticsearch(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", ELASTICSEARCH_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("elasticsearch_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        cred = resolve_credential(node, ctx, "elasticSearchApi")
        if cred:
            cfg = _build_elasticsearch_request(cred, operation, params, item, ctx)
            if cfg is not None:
                try:
                    resp = await execute_http_request(cfg, ctx=ctx)
                    if isinstance(resp.body, dict):
                        out.append(ExecutionItem(json=_envelope_from_elasticsearch_api(resp.body, operation, params, item, ctx)))
                        continue
                except Exception as exc:
                    logger.warning("elasticsearch HTTP call failed: %s", exc)
        index = _resolve_param("index", params, item, ctx)
        if operation == "search":
            hits = [{"_id": f"hit-{i}", "_source": {"name": f"doc-{i}"}} for i in range(3)]
            out.append(ExecutionItem(json={"hits": hits, "total": len(hits), "index": index, "operation": operation, "source": "elasticsearch", "queriedAt": _now_iso()}))
        else:
            out.append(ExecutionItem(json={"index": index, "operation": operation, "source": "elasticsearch", "updatedAt": _now_iso()}))
    return [(0, out)]