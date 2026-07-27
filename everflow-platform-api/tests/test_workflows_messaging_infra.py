"""Tests for messaging infra nodes (MQTT, Kafka, RabbitMQ, AMQP, Redis Trigger, Postgres Trigger)."""
from __future__ import annotations
from typing import Any
import pytest
from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.messaging_infra import exec_amqp, exec_kafka, exec_mqtt, exec_postgres_trigger, exec_rabbitmq, exec_redis_trigger
from app.services.workflows.registry import REGISTRY

def _node(params, *, type_="n8n-nodes-base.mqtt", id_="n1", name="MQTT"):
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
async def test_mqtt_dict_mock():
    node = _node({"operation": "publish"})
    ctx = _ctx({"mqtt_response": {"topic": "t1", "custom": True}})
    items = _out_items(await exec_mqtt(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_mqtt_offline():
    node = _node({"operation": "publish", "topic": "sensor/data"})
    items = _out_items(await exec_mqtt(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "mqtt"

@pytest.mark.asyncio
async def test_kafka_dict_mock():
    node = _node({"operation": "produce"}, type_="n8n-nodes-base.kafka", name="Kafka")
    ctx = _ctx({"kafka_response": {"topic": "t1", "custom": True}})
    items = _out_items(await exec_kafka(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_kafka_offline():
    node = _node({"operation": "produce", "topic": "events"}, type_="n8n-nodes-base.kafka")
    items = _out_items(await exec_kafka(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "kafka"

@pytest.mark.asyncio
async def test_rabbitmq_dict_mock():
    node = _node({"operation": "publish"}, type_="n8n-nodes-base.rabbitmq", name="RabbitMQ")
    ctx = _ctx({"rabbitmq_response": {"queue": "q1", "custom": True}})
    items = _out_items(await exec_rabbitmq(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_rabbitmq_offline():
    node = _node({"operation": "publish", "queue": "tasks"}, type_="n8n-nodes-base.rabbitmq")
    items = _out_items(await exec_rabbitmq(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "rabbitmq"

@pytest.mark.asyncio
async def test_amqp_dict_mock():
    node = _node({"operation": "publish"}, type_="n8n-nodes-base.amqp", name="AMQP")
    ctx = _ctx({"amqp_response": {"queue": "q1", "custom": True}})
    items = _out_items(await exec_amqp(node, [_input_item()], ctx=ctx))
    assert items[0].json["custom"] is True

@pytest.mark.asyncio
async def test_amqp_offline():
    node = _node({"operation": "publish", "queue": "tasks"}, type_="n8n-nodes-base.amqp")
    items = _out_items(await exec_amqp(node, [_input_item()], ctx=_ctx()))
    assert items[0].json["source"] == "amqp"

@pytest.mark.asyncio
async def test_redis_trigger_dict_mock():
    node = _node({}, type_="n8n-nodes-base.redisTrigger", name="Redis Trigger")
    ctx = _ctx({"redis_trigger_payload": {"event": "message", "channel": "ch1"}})
    items = _out_items(await exec_redis_trigger(node, [], ctx=ctx))
    assert items[0].json["channel"] == "ch1"

@pytest.mark.asyncio
async def test_redis_trigger_offline():
    node = _node({}, type_="n8n-nodes-base.redisTrigger")
    items = _out_items(await exec_redis_trigger(node, [], ctx=_ctx()))
    assert items[0].json["source"] == "redis"

@pytest.mark.asyncio
async def test_postgres_trigger_dict_mock():
    node = _node({}, type_="n8n-nodes-base.postgresTrigger", name="Postgres Trigger")
    ctx = _ctx({"postgres_trigger_payload": {"event": "insert", "table": "users"}})
    items = _out_items(await exec_postgres_trigger(node, [], ctx=ctx))
    assert items[0].json["table"] == "users"

@pytest.mark.asyncio
async def test_postgres_trigger_offline():
    node = _node({}, type_="n8n-nodes-base.postgresTrigger")
    items = _out_items(await exec_postgres_trigger(node, [], ctx=_ctx()))
    assert items[0].json["source"] == "postgres"

@pytest.mark.asyncio
async def test_e2e_kafka_to_set():
    doc = {
        "nodes": [
            {"id": "t", "name": "Manual", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "parameters": {}, "position": [0, 0]},
            {"id": "k", "name": "Kafka", "type": "n8n-nodes-base.kafka", "typeVersion": 1, "parameters": {"operation": "produce", "topic": "events"}, "position": [200, 0]},
            {"id": "s", "name": "Set", "type": "n8n-nodes-base.set", "typeVersion": 1, "parameters": {"assignments": {"assignments": [{"name": "result", "value": "={{ $json.source }}", "type": "string"}]}}, "position": [400, 0]},
        ],
        "connections": {"t": {"main": [[{"node": "k", "index": 0}]]}, "k": {"main": [[{"node": "s", "index": 0}]]}},
    }
    engine = WorkflowEngine(doc, mocks={})
    result = await engine.run()
    assert result.status == "success"
    assert result.final_items[0]["json"]["result"] == "kafka"

def test_descriptors_registered():
    for t in ["n8n-nodes-base.mqtt", "n8n-nodes-base.kafka", "n8n-nodes-base.rabbitmq", "n8n-nodes-base.amqp", "n8n-nodes-base.redisTrigger", "n8n-nodes-base.postgresTrigger"]:
        assert t in REGISTRY, f"{t} not registered"