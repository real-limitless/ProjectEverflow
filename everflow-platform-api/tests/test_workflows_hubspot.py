"""Tests for the HubSpot node executor (``n8n-nodes-base.hubspot``).

Covers:

- ``hubspot_response`` dict mock → response used verbatim
- ``hubspot_response`` callable mock receives ``(operation, resourceType, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline ``create`` (objectId present, properties echoed)
- Offline ``get`` (objectId echoed, properties present)
- Offline ``update`` (properties echoed)
- Offline ``list`` (returns up to 3 results)
- Offline ``delete`` (archived=True)
- Operation reflected in emitted item
- ``objectId`` default from ``$json``
- ``resourceType`` default is ``contact``
- ``limit`` honored
- Empty ``objectId`` for get → no item
- End-to-end: Manual → hubspot (list mock) → Set sees results
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.hubspot import (
    HUBSPOT_DEFAULT_OPERATION,
    HUBSPOT_DEFAULT_RESOURCE_TYPE,
    HUBSPOT_OPERATIONS,
    exec_hubspot,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.hubspot",
    id_: str = "hubspot1",
    name: str = "HubSpot",
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


# ══════════════════════════════════════════════════════════════════════
#  1. hubspot_response dict mock
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hubspot_response_dict_mock_is_used_verbatim() -> None:
    node = _node(
        {
            "operation": "get",
            "resourceType": "contact",
            "objectId": "42",
        }
    )
    ctx = _ctx(
        {
            "hubspot_response": {
                "id": "42",
                "properties": {
                    "firstname": "Ada",
                    "lastname": "Lovelace",
                    "email": "ada@example.com",
                },
                "createdAt": "2024-01-01T00:00:00.000Z",
                "updatedAt": "2024-06-01T00:00:00.000Z",
                "archived": False,
            }
        }
    )
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    p = out[0].json
    assert p["objectId"] == "42"
    assert p["properties"]["firstname"] == "Ada"
    assert p["properties"]["lastname"] == "Lovelace"
    assert p["properties"]["email"] == "ada@example.com"
    assert p["resourceType"] == "contact"
    assert p["source"] == "hubspot"


# ══════════════════════════════════════════════════════════════════════
#  2. hubspot_response callable mock signature
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hubspot_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, resource_type, params, item, ctx):
        captured["operation"] = operation
        captured["resource_type"] = resource_type
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "id": "7",
            "properties": {"firstname": "from callable"},
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-02T00:00:00.000Z",
            "archived": False,
        }

    node = _node(
        {
            "operation": "get",
            "resourceType": "company",
            "objectId": "7",
            "extra": "keep",
        }
    )
    ctx = _ctx({"hubspot_response": _mock})
    item = ExecutionItem(json={"hint": 1})
    out = _out_items(await exec_hubspot(node, [item], ctx=ctx))

    assert captured["operation"] == "get"
    assert captured["resource_type"] == "company"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx

    assert out[0].json["objectId"] == "7"
    assert out[0].json["properties"]["firstname"] == "from callable"
    assert out[0].json["resourceType"] == "company"


# ══════════════════════════════════════════════════════════════════════
#  3. http_response fallback
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_json_body() -> None:
    node = _node(
        {
            "operation": "get",
            "objectId": "99",
        }
    )
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "id": "99",
                    "properties": {
                        "firstname": "via http",
                        "email": "http@example.com",
                    },
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "updatedAt": "2024-01-01T00:00:00.000Z",
                    "archived": False,
                },
            }
        }
    )
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=ctx))
    p = out[0].json
    assert p["objectId"] == "99"
    assert p["properties"]["firstname"] == "via http"
    assert p["mockSource"] == "http_response"
    assert p["source"] == "hubspot"


# ══════════════════════════════════════════════════════════════════════
#  4. Offline create
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_create_object_id_present_and_properties_echoed() -> None:
    node = _node(
        {
            "operation": "create",
            "resourceType": "contact",
            "properties": {
                "firstname": "Grace",
                "lastname": "Hopper",
                "email": "grace@example.com",
            },
        }
    )
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["objectId"]
    assert p["properties"]["firstname"] == "Grace"
    assert p["properties"]["lastname"] == "Hopper"
    assert p["properties"]["email"] == "grace@example.com"
    assert p["resourceType"] == "contact"
    assert p["createdAt"]
    assert p["updatedAt"]
    assert p["source"] == "hubspot"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_create_defaults_properties_when_empty() -> None:
    node = _node({"operation": "create"})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["properties"]["firstname"] == "Mock"
    assert p["properties"]["lastname"] == "User"
    assert p["properties"]["email"] == "mock@example.com"


# ══════════════════════════════════════════════════════════════════════
#  5. Offline get
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_get_object_id_echoed_and_properties_present() -> None:
    node = _node(
        {
            "operation": "get",
            "objectId": "55",
        }
    )
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["objectId"] == "55"
    assert p["properties"]["firstname"] == "Mock"
    assert p["properties"]["lastname"] == "User"
    assert p["properties"]["email"] == "mock@example.com"
    assert p["properties"]["company"] == "Mock Co"
    assert p["createdAt"]
    assert p["updatedAt"]
    assert p["source"] == "hubspot"
    assert p["mockSource"] == "offline"


# ══════════════════════════════════════════════════════════════════════
#  6. Offline update
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_update_properties_echoed() -> None:
    node = _node(
        {
            "operation": "update",
            "objectId": "33",
            "properties": {"firstname": "Updated", "lifecyclestage": "customer"},
        }
    )
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["objectId"] == "33"
    assert p["properties"]["firstname"] == "Updated"
    assert p["properties"]["lifecyclestage"] == "customer"
    assert p["updatedAt"]
    assert p["source"] == "hubspot"
    assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_update_defaults_properties_when_empty() -> None:
    node = _node({"operation": "update", "objectId": "10"})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    p = out[0].json
    assert p["properties"]["firstname"] == "Updated"


# ══════════════════════════════════════════════════════════════════════
#  7. Offline list
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_list_returns_up_to_3_results() -> None:
    node = _node(
        {
            "operation": "list",
            "limit": 10,
        }
    )
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 3
    for i, item in enumerate(out, start=1):
        p = item.json
        assert p["objectId"] == str(i)
        assert p["properties"]["firstname"] == f"Mock{i}"
        assert p["properties"]["lastname"] == "User"
        assert p["properties"]["email"] == f"mock{i}@example.com"
        assert p["resourceType"] == "contact"
        assert p["source"] == "hubspot"
        assert p["mockSource"] == "offline"


@pytest.mark.asyncio
async def test_offline_list_data_mode_object() -> None:
    node = _node(
        {
            "operation": "list",
            "dataMode": "object",
        }
    )
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert "results" in p
    assert isinstance(p["results"], list)
    assert len(p["results"]) == 3
    assert p["paging"] == {"next": {"after": ""}}
    assert p["resourceType"] == "contact"
    assert p["source"] == "hubspot"


# ══════════════════════════════════════════════════════════════════════
#  8. Offline delete
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_offline_delete_archived_true() -> None:
    node = _node(
        {
            "operation": "delete",
            "objectId": "77",
        }
    )
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    p = out[0].json
    assert p["objectId"] == "77"
    assert p["archived"] is True
    assert "archivedAt" in p
    assert p["source"] == "hubspot"
    assert p["mockSource"] == "offline"


# ══════════════════════════════════════════════════════════════════════
#  9. Operation reflected
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_operation_reflected_in_emitted_item() -> None:
    for op in HUBSPOT_OPERATIONS:
        params: dict[str, Any] = {
            "operation": op,
            "objectId": "1",
            "properties": {"firstname": "T"},
            "limit": 5,
        }
        node = _node(params)
        out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
        assert len(out) >= 1, f"no output for {op}"
        assert out[0].json["source"] == "hubspot"


# ══════════════════════════════════════════════════════════════════════
#  10. objectId default from $json
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_object_id_default_from_json_object_id() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"objectId": "123"})
    out = _out_items(await exec_hubspot(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["objectId"] == "123"


@pytest.mark.asyncio
async def test_object_id_default_from_json_id_alias() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"id": "456"})
    out = _out_items(await exec_hubspot(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["objectId"] == "456"


@pytest.mark.asyncio
async def test_object_id_default_from_json_contact_id_alias() -> None:
    node = _node({"operation": "get"})
    item = ExecutionItem(json={"contactId": "789"})
    out = _out_items(await exec_hubspot(node, [item], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["objectId"] == "789"


# ══════════════════════════════════════════════════════════════════════
#  11. resourceType default is contact
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resource_type_default_is_contact() -> None:
    node = _node({"operation": "get", "objectId": "1"})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["resourceType"] == "contact"
    assert HUBSPOT_DEFAULT_RESOURCE_TYPE == "contact"


@pytest.mark.asyncio
async def test_resource_type_company_reflected() -> None:
    node = _node({"operation": "get", "resourceType": "company", "objectId": "1"})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out[0].json["resourceType"] == "company"


# ══════════════════════════════════════════════════════════════════════
#  12. limit honored
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_limit_honored() -> None:
    node = _node({"operation": "list", "limit": 2})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 2


@pytest.mark.asyncio
async def test_limit_honored_from_json() -> None:
    node = _node({"operation": "list"})
    item = ExecutionItem(json={"limit": 1})
    out = _out_items(await exec_hubspot(node, [item], ctx=_ctx()))
    assert len(out) == 1


# ══════════════════════════════════════════════════════════════════════
#  13. Empty objectId for get → no item
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_empty_object_id_for_get_skips_item() -> None:
    node = _node({"operation": "get", "objectId": ""})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_object_id_for_update_skips_item() -> None:
    node = _node({"operation": "update", "objectId": ""})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


@pytest.mark.asyncio
async def test_empty_object_id_for_delete_skips_item() -> None:
    node = _node({"operation": "delete", "objectId": ""})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert out == []


# ══════════════════════════════════════════════════════════════════════
#  14. Default operation is get
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_default_operation_is_get() -> None:
    node = _node({"objectId": "1"})
    out = _out_items(await exec_hubspot(node, [ExecutionItem(json={})], ctx=_ctx()))
    assert len(out) == 1
    assert out[0].json["objectId"] == "1"
    assert HUBSPOT_DEFAULT_OPERATION == "get"


# ══════════════════════════════════════════════════════════════════════
#  15. One output item per input (for get)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_one_output_item_per_input() -> None:
    node = _node({"operation": "get"})
    items = [
        ExecutionItem(json={"objectId": "10"}),
        ExecutionItem(json={"objectId": "20"}),
        ExecutionItem(json={"objectId": "30"}),
    ]
    out = _out_items(await exec_hubspot(node, items, ctx=_ctx()))
    assert len(out) == 3
    ids = [o.json["objectId"] for o in out]
    assert ids == ["10", "20", "30"]
    assert all(o.json["source"] == "hubspot" for o in out)


# ══════════════════════════════════════════════════════════════════════
#  16. Descriptor registration
# ══════════════════════════════════════════════════════════════════════


def test_hubspot_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.hubspot" in REGISTRY
    assert "n8n-nodes-base.hubspot" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.hubspot"] == "output"
    desc = REGISTRY["n8n-nodes-base.hubspot"]
    assert desc.executor.endswith(":exec_hubspot")
    assert desc.category == "output"


# ══════════════════════════════════════════════════════════════════════
#  17. End-to-end: Manual → hubspot (list mock) → Set sees results
# ══════════════════════════════════════════════════════════════════════


def _doc(nodes, connections):
    return {"name": "hubspot-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_hubspot_list_set_sees_results() -> None:
    mocks = {
        "hubspot_response": {
            "results": [
                {
                    "id": "1",
                    "properties": {
                        "firstname": "E2E Contact 1",
                        "email": "e2e1@example.com",
                    },
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "updatedAt": "2024-01-01T00:00:00.000Z",
                },
                {
                    "id": "2",
                    "properties": {
                        "firstname": "E2E Contact 2",
                        "email": "e2e2@example.com",
                    },
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "updatedAt": "2024-01-01T00:00:00.000Z",
                },
            ],
            "paging": {"next": {"after": ""}},
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "h1",
                "HubSpot",
                "n8n-nodes-base.hubspot",
                {
                    "operation": "list",
                    "resourceType": "contact",
                    "limit": 10,
                },
            ),
            _n(
                "s1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_id", "value": "={{ $json.objectId }}", "type": "string"},
                            {"name": "result_name", "value": "={{ $json.properties.firstname }}", "type": "string"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "HubSpot", "type": "main", "index": 0}]]},
            "HubSpot": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    hubspot_step = next(s for s in result.steps if s.node_name == "HubSpot")
    assert hubspot_step.status == "success", hubspot_step.error
    assert hubspot_step.output_count == 2
    sample = hubspot_step.sample_output[0]
    assert sample["json"]["objectId"] == "1"
    assert sample["json"]["properties"]["firstname"] == "E2E Contact 1"
    assert sample["json"]["source"] == "hubspot"

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("result_id") == "1"
    assert fjson.get("result_name") == "E2E Contact 1"
    assert fjson.get("result_source") == "hubspot"