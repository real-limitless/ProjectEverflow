"""Tests for the Form Trigger node executor (n8n-nodes-base.formTrigger)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.core import exec_form_trigger


# ── Helpers ───────────────────────────────────────────────────────────


def _node(name: str = "Form", params: dict | None = None) -> ExecNode:
    return ExecNode(
        id="f1",
        name=name,
        type="n8n-nodes-base.formTrigger",
        type_version=1,
        parameters=params or {},
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    form_submission: dict | None = None,
    mocks: dict | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    if mocks is None and form_submission is not None:
        mocks = {"form_submission": form_submission}
    return EngineContext(graph=g, mocks=mocks or {})


def _doc(nodes, connections):
    return {"name": "form-trigger-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


# ── Unit tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_emits_item_with_fields_from_mock_submission() -> None:
    submission = {
        "submittedAt": "2026-07-25T12:00:00Z",
        "formId": "contact-form",
        "fields": {"name": "Alice", "email": "a@b.com"},
    }
    ctx = _ctx(form_submission=submission)
    node = _node()

    out = await exec_form_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    assert out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["submittedAt"] == "2026-07-25T12:00:00Z"
    assert payload["formId"] == "contact-form"
    # Fields promoted to top level so $json.name works
    assert payload["name"] == "Alice"
    assert payload["email"] == "a@b.com"


@pytest.mark.asyncio
async def test_falls_back_when_no_mock_submission() -> None:
    ctx = _ctx()
    node = _node()

    out = await exec_form_trigger(node, items=[], ctx=ctx)

    assert len(out) == 1
    items = out[0][1]
    assert len(items) == 1
    assert items[0].json == {"formId": "default"}


@pytest.mark.asyncio
async def test_form_id_defaults_to_parameter_value() -> None:
    ctx = _ctx()
    node = _node(params={"formId": "my-survey"})

    out = await exec_form_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["formId"] == "my-survey"


@pytest.mark.asyncio
async def test_form_id_from_mock_overrides_parameter() -> None:
    submission = {
        "submittedAt": "2026-01-01T00:00:00Z",
        "formId": "from-mock",
        "fields": {"x": 1},
    }
    ctx = _ctx(form_submission=submission)
    node = _node(params={"formId": "from-param"})

    out = await exec_form_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["formId"] == "from-mock"
    assert payload["x"] == 1


@pytest.mark.asyncio
async def test_input_items_are_dropped() -> None:
    """Form Trigger is a clean slate; upstream items are not propagated."""
    submission = {
        "submittedAt": "2026-01-01T00:00:00Z",
        "formId": "f",
        "fields": {"k": "v"},
    }
    ctx = _ctx(form_submission=submission)
    node = _node()

    in_items = [ExecutionItem(json={"foo": 1}), ExecutionItem(json={"bar": 2})]
    out = await exec_form_trigger(node, items=in_items, ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    assert "submittedAt" in items[0].json
    # No carry-through of upstream items
    assert "foo" not in items[0].json
    assert "bar" not in items[0].json


@pytest.mark.asyncio
async def test_submission_without_fields_still_emits_one_item() -> None:
    submission = {"submittedAt": "2026-07-25T12:00:00Z", "formId": "f"}
    ctx = _ctx(form_submission=submission)
    node = _node()

    out = await exec_form_trigger(node, items=[], ctx=ctx)

    items = out[0][1]
    assert len(items) == 1
    payload = items[0].json
    assert payload["formId"] == "f"
    assert payload["submittedAt"] == "2026-07-25T12:00:00Z"
    # No fields key smuggled in
    assert "fields" not in payload


@pytest.mark.asyncio
async def test_submission_with_non_dict_fields_falls_back_safely() -> None:
    submission = {
        "submittedAt": "2026-07-25T12:00:00Z",
        "formId": "f",
        "fields": "not a dict",
    }
    ctx = _ctx(form_submission=submission)
    node = _node()

    out = await exec_form_trigger(node, items=[], ctx=ctx)

    payload = out[0][1][0].json
    assert payload["formId"] == "f"
    assert payload["submittedAt"] == "2026-07-25T12:00:00Z"


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401  side-effect import
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.formTrigger" in REGISTRY
    assert "n8n-nodes-base.formTrigger" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.formTrigger"] == "trigger"
    desc = REGISTRY["n8n-nodes-base.formTrigger"]
    assert desc.executor.endswith(":exec_form_trigger")
    assert desc.category == "trigger"


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_form_trigger_seeds_downstream_set() -> None:
    """Manual → formTrigger → Set. The form trigger reads the pinned
    submission via mocks and the downstream Set should see ``$json.name``
    in scope because fields are promoted to the top level."""
    doc = _doc(
        [
            _n("m1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "f1",
                "Form",
                "n8n-nodes-base.formTrigger",
                {"formId": "contact-form"},
            ),
            _n(
                "s1",
                "Stamp",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {"name": "greeting", "value": "={{ 'hi ' + $json.name }}", "type": "string"},
                    ]}
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "Form", "type": "main", "index": 0}]]},
            "Form": {"main": [[{"node": "Stamp", "type": "main", "index": 0}]]},
        },
    )
    mocks = {
        "form_submission": {
            "submittedAt": "2026-07-25T12:00:00Z",
            "formId": "contact-form",
            "fields": {"name": "Alice", "email": "a@b.com"},
        }
    }
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message
    assert result.final_items, "expected final items from Stamp"
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("greeting") == "hi Alice"
    # formId is preserved on the item
    assert final_json.get("formId") == "contact-form"
    assert final_json.get("email") == "a@b.com"


@pytest.mark.asyncio
async def test_end_to_end_form_trigger_without_mock_emits_default_formid() -> None:
    """End-to-end with no form_submission mock: downstream still receives
    one item with the default formId from the node parameter."""
    doc = _doc(
        [
            _n("m1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "f1",
                "Form",
                "n8n-nodes-base.formTrigger",
                {"formId": "default-form"},
            ),
        ],
        {
            "Start": {"main": [[{"node": "Form", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")

    assert result.status == "success", result.error_message
    assert result.final_items
    final_json = result.final_items[0].get("json") or {}
    assert final_json.get("formId") == "default-form"
