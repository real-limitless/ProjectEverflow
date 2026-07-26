"""Tests for the Redis node executor (``n8n-nodes-base.redis``).

Covers:

- ``redis_response`` dict mock → envelope used per operation
- ``redis_response`` callable mock receives
  ``(operation, key, params, item, ctx)``
- ``db_response`` fallback
- ``http_response`` fallback unwraps a JSON body
- Offline get: value present, exists=True
- Offline set: ok=True
- Offline delete: deleted=1
- Offline incr: value=1
- Offline decr: value=-1
- Offline keys: returns 3 keys
- Offline publish: subscribers=1
- ``operation='get'`` reflected on output
- ``key`` default from ``$json``
- Empty key → no item
- End-to-end: Manual Trigger → redis (get mock) → Set sees value
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.redis import (
    REDIS_DEFAULT_OPERATION,
    REDIS_OPERATIONS,
    exec_redis,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.redis",
    id_: str = "rd1",
    name: str = "Redis",
    credentials: dict[str, Any] | None = None,
) -> ExecNode:
    return ExecNode(
        id=id_,
        name=name,
        type=type_,
        type_version=1,
        parameters=params,
        credentials=credentials,
        position={"x": 0, "y": 0},
    )


def _ctx(mocks: dict[str, Any] | None = None) -> EngineContext:
    g = type("G", (), {})()
    g.ai_inputs = lambda *a, **k: []
    g.trigger_nodes = lambda preferred=None: []
    g.nodes_by_id = {}
    g.out_edges = {}
    g.main_successors = lambda *a, **k: []
    return EngineContext(graph=g, mocks=mocks or {})  # type: ignore[arg-type]


def _out_items(result) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── 1. redis_response dict mock (get) ────────────────────────────────


@pytest.mark.asyncio
async def test_redis_response_dict_mock_get_used_verbatim() -> None:
    node = _node({"operation": "get", "key": "mykey"})
    ctx = _ctx(
        {
            "redis_response": {
                "value": "mocked-value",
                "exists": True,
                "ttl": 30,
            }
        }
    )
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["value"] == "mocked-value"
    assert out[0].json["exists"] is True
    assert out[0].json["ttl"] == 30
    assert out[0].json["key"] == "mykey"
    assert out[0].json["source"] == "redis"
    assert out[0].json["operation"] == "get"


# ── 2. redis_response callable mock signature ───────────────────────


@pytest.mark.asyncio
async def test_redis_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, key, params, item, ctx):
        captured["operation"] = operation
        captured["key"] = key
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {"value": "from-callable", "exists": True, "ttl": -1}

    node = _node(
        {"operation": "get", "key": "k1", "extra": "keep"}
    )
    ctx = _ctx({"redis_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_redis(node, [item], ctx=ctx))

    assert captured["operation"] == "get"
    assert captured["key"] == "k1"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert len(out) == 1
    assert out[0].json["value"] == "from-callable"


# ── 3. db_response fallback ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_db_response_fallback_used() -> None:
    node = _node({"operation": "get", "key": "k2"})
    ctx = _ctx(
        {"db_response": {"value": "from-db", "exists": True, "ttl": -1}}
    )
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["value"] == "from-db"
    assert out[0].json["source"] == "redis"


# ── 4. http_response fallback ────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node({"operation": "get", "key": "k3"})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "value": "from-http",
                    "exists": True,
                    "ttl": -1,
                },
            }
        }
    )
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=ctx)
    )
    assert len(out) == 1
    assert out[0].json["value"] == "from-http"
    assert out[0].json["source"] == "redis"


# ── 5. Offline get: value present, exists=True ──────────────────────


@pytest.mark.asyncio
async def test_offline_get_value_present_exists_true() -> None:
    node = _node({"operation": "get", "key": "g1"})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["value"] == "mock_value_for_g1"
    assert p["exists"] is True
    assert p["ttl"] == -1
    assert p["key"] == "g1"
    assert p["source"] == "redis"
    assert p["operation"] == "get"


# ── 6. Offline set: ok=True ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_set_ok_true() -> None:
    node = _node(
        {"operation": "set", "key": "s1", "value": "v1", "expire": 60}
    )
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["ok"] is True
    assert p["key"] == "s1"
    assert p["value"] == "v1"
    assert p["expire"] == 60
    assert p["source"] == "redis"
    assert p["operation"] == "set"


@pytest.mark.asyncio
async def test_offline_set_default_expire_zero() -> None:
    node = _node({"operation": "set", "key": "s2", "value": "v2"})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    assert out[0].json["expire"] == 0


# ── 7. Offline delete: deleted=1 ────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_delete_deleted_one() -> None:
    node = _node({"operation": "delete", "key": "d1"})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["deleted"] == 1
    assert p["key"] == "d1"
    assert p["source"] == "redis"
    assert p["operation"] == "delete"


# ── 8. Offline incr: value=1 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_incr_value_one() -> None:
    node = _node({"operation": "incr", "key": "i1", "by": 5})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["value"] == 1
    assert p["key"] == "i1"
    assert p["incrementedBy"] == 5
    assert p["source"] == "redis"
    assert p["operation"] == "incr"


# ── 9. Offline decr: value=-1 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_decr_value_neg_one() -> None:
    node = _node({"operation": "decr", "key": "i2", "by": 3})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["value"] == -1
    assert p["key"] == "i2"
    assert p["decrementedBy"] == 3
    assert p["source"] == "redis"
    assert p["operation"] == "decr"


# ── 10. Offline keys: returns 3 keys ────────────────────────────────


@pytest.mark.asyncio
async def test_offline_keys_returns_three_keys() -> None:
    node = _node({"operation": "keys", "pattern": "user:*"})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["count"] == 3
    assert p["keys"] == ["mock_key_1", "mock_key_2", "mock_key_3"]
    assert p["source"] == "redis"
    assert p["operation"] == "keys"


# ── 11. Offline publish: subscribers=1 ──────────────────────────────


@pytest.mark.asyncio
async def test_offline_publish_subscribers_one() -> None:
    node = _node(
        {"operation": "publish", "channel": "ch1", "message": "hello"}
    )
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    p = out[0].json
    assert p["subscribers"] == 1
    assert p["channel"] == "ch1"
    assert p["message"] == "hello"
    assert p["source"] == "redis"
    assert p["operation"] == "publish"


# ── 12. operation='get' reflected ───────────────────────────────────


@pytest.mark.asyncio
async def test_operation_get_reflected() -> None:
    node = _node({"operation": "get", "key": "r1"})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) > 0
    assert out[0].json["operation"] == "get"
    assert out[0].json["source"] == "redis"


# ── 13. key default from $json ──────────────────────────────────────


@pytest.mark.asyncio
async def test_key_default_from_json() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"key": "from-json-key"})
    out = _out_items(await exec_redis(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["key"] == "from-json-key"
    assert out[0].json["value"] == "mock_value_for_from-json-key"


@pytest.mark.asyncio
async def test_redis_key_default_from_json() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"redisKey": "from-redis-key"})
    out = _out_items(await exec_redis(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["key"] == "from-redis-key"


@pytest.mark.asyncio
async def test_set_value_default_from_json() -> None:
    node = _node({"operation": "set", "key": "sv1"})
    item = ExecutionItem(json={"value": "val-from-json"})
    out = _out_items(await exec_redis(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["value"] == "val-from-json"


@pytest.mark.asyncio
async def test_publish_channel_default_from_json() -> None:
    node = _node({"operation": "publish", "message": "m"})
    item = ExecutionItem(json={"channel": "json-channel"})
    out = _out_items(await exec_redis(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["channel"] == "json-channel"


# ── 14. Empty key → no item ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_key_skips_get() -> None:
    node = _node({"operation": "get", "key": ""})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_key_skips_set() -> None:
    node = _node({"operation": "set", "key": "", "value": "x"})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_key_skips_delete() -> None:
    node = _node({"operation": "delete", "key": ""})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_key_skips_incr() -> None:
    node = _node({"operation": "incr", "key": ""})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_key_skips_decr() -> None:
    node = _node({"operation": "decr", "key": ""})
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_channel_skips_publish() -> None:
    node = _node(
        {"operation": "publish", "channel": "", "message": "x"}
    )
    out = _out_items(
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


# ── 15. Unsupported operation raises ─────────────────────────────────


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "hset", "key": "k"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_redis(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 16. Default operation is 'get' ───────────────────────────────────


def test_default_operation_is_get() -> None:
    assert REDIS_DEFAULT_OPERATION == "get"
    assert set(REDIS_OPERATIONS) == {
        "get",
        "set",
        "delete",
        "incr",
        "decr",
        "keys",
        "publish",
    }


# ── 17. Multiple input items ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input_for_get() -> None:
    node = _node({"operation": "get"})
    items = [
        ExecutionItem(json={"key": "a"}),
        ExecutionItem(json={"key": "b"}),
        ExecutionItem(json={"key": "c"}),
    ]
    out = _out_items(await exec_redis(node, items, ctx=_ctx()))
    assert len(out) == 3
    assert [o.json["key"] for o in out] == ["a", "b", "c"]
    assert [o.json["value"] for o in out] == [
        "mock_value_for_a",
        "mock_value_for_b",
        "mock_value_for_c",
    ]


# ── 18. Descriptor registration ─────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.redis" in REGISTRY
    assert "n8n-nodes-base.redis" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.redis"] == "output"
    desc = REGISTRY["n8n-nodes-base.redis"]
    assert desc.executor.endswith(":exec_redis")
    assert desc.category == "output"


# ── 19. End-to-end: Manual Trigger → redis (get mock) → Set ────────


def _doc(nodes, connections):
    return {"name": "redis-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_redis_get_set_sees_value() -> None:
    """Manual Trigger → redis (get, redis_response mock) → Set pulls value/source."""
    mocks = {
        "redis_response": {
            "value": "e2e-value",
            "exists": True,
            "ttl": -1,
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "r1",
                "Redis",
                "n8n-nodes-base.redis",
                {"operation": "get", "key": "e2e"},
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {
                                "name": "result_value",
                                "value": "={{ $json.value }}",
                                "type": "string",
                            },
                            {
                                "name": "result_source",
                                "value": "={{ $json.source }}",
                                "type": "string",
                            },
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {
                "main": [[{"node": "Redis", "type": "main", "index": 0}]]
            },
            "Redis": {
                "main": [[{"node": "Downstream", "type": "main", "index": 0}]]
            },
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    redis_step = next(s for s in result.steps if s.node_name == "Redis")
    assert redis_step.status == "success", redis_step.error
    assert redis_step.output_count == 1

    final = result.final_items
    assert final, "expected at least one final item"
    assert final[0].get("json", {}).get("result_value") == "e2e-value"
    assert final[0].get("json", {}).get("result_source") == "redis"