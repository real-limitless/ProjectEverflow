"""Messaging infrastructure executors (clean-room ``n8n-nodes-base.*``).

Implements MQTT, Kafka, RabbitMQ, AMQP, Redis Trigger, Postgres Trigger.
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

def _trigger_payload(ctx, *keys):
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    for key in keys:
        val = mocks.get(key)
        if isinstance(val, dict): return val
        if callable(val):
            result = val()
            if isinstance(result, dict): return result
    return None


MQTT_OPERATIONS = ("publish", "subscribe")
MQTT_DEFAULT_OPERATION = "publish"

async def exec_mqtt(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", MQTT_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("mqtt_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        topic = _resolve_param("topic", params, item, ctx)
        out.append(ExecutionItem(json={"topic": topic, "operation": operation, "source": "mqtt", "publishedAt": _now_iso()}))
    return [(0, out)]


KAFKA_OPERATIONS = ("produce", "consume", "listTopics", "createTopic")
KAFKA_DEFAULT_OPERATION = "produce"

async def exec_kafka(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", KAFKA_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("kafka_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        topic = _resolve_param("topic", params, item, ctx)
        out.append(ExecutionItem(json={"topic": topic, "partition": 0, "offset": 0, "operation": operation, "source": "kafka", "publishedAt": _now_iso()}))
    return [(0, out)]


RABBITMQ_OPERATIONS = ("publish", "consume", "createQueue", "deleteQueue", "bindQueue")
RABBITMQ_DEFAULT_OPERATION = "publish"

async def exec_rabbitmq(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", RABBITMQ_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("rabbitmq_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        queue = _resolve_param("queue", params, item, ctx)
        out.append(ExecutionItem(json={"queue": queue, "operation": operation, "source": "rabbitmq", "publishedAt": _now_iso()}))
    return [(0, out)]


AMQP_OPERATIONS = ("publish", "consume", "createQueue", "deleteQueue")
AMQP_DEFAULT_OPERATION = "publish"

async def exec_amqp(node, items, *, ctx):
    params = node.parameters or {}
    operation = params.get("operation", AMQP_DEFAULT_OPERATION)
    out = []
    for item in items:
        mock = _mock_response("amqp_response", operation, params, item, ctx)
        if mock: out.append(ExecutionItem(json=mock)); continue
        http = _http_response(ctx)
        if http: out.append(ExecutionItem(json=http)); continue
        queue = _resolve_param("queue", params, item, ctx)
        out.append(ExecutionItem(json={"queue": queue, "operation": operation, "source": "amqp", "publishedAt": _now_iso()}))
    return [(0, out)]


async def exec_redis_trigger(node, items, *, ctx):
    payload = _trigger_payload(ctx, "redis_trigger_payload", "trigger_payload")
    if payload is not None:
        return [(0, [ExecutionItem(json=payload)])]
    return [(0, [ExecutionItem(json={"event": "message", "channel": "default", "message": "synthetic", "source": "redis", "receivedAt": _now_iso()})])]


async def exec_postgres_trigger(node, items, *, ctx):
    payload = _trigger_payload(ctx, "postgres_trigger_payload", "trigger_payload")
    if payload is not None:
        return [(0, [ExecutionItem(json=payload)])]
    return [(0, [ExecutionItem(json={"event": "insert", "table": "default", "row": {"id": 1}, "source": "postgres", "receivedAt": _now_iso()})])]