"""Tests for the XML node executor (n8n-nodes-base.xml)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import exec_xml


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="x1",
        name="Xml",
        type="n8n-nodes-base.xml",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx() -> EngineContext:
    g = type("G", (), {})()
    g.trigger_nodes = lambda preferred=None: []  # type: ignore
    return EngineContext(graph=g)  # type: ignore[arg-type]


def _doc(nodes, connections):
    return {"name": "xml-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


def _result_items(result):
    out = []
    for _idx, items in result:
        for it in items:
            out.append(it.json)
    return out


# ── xmlToJson ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_xml_to_json_simple_string() -> None:
    items = [ExecutionItem(json={"data": "<root><name>Ada</name></root>"})]
    out = await exec_xml(_node({"action": "xmlToJson"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert rendered == [{"data": {"root": {"name": {"#text": "Ada"}}}}]


@pytest.mark.asyncio
async def test_xml_to_json_attributes_and_repeated_children() -> None:
    items = [ExecutionItem(json={"data": (
        '<root kind="x"><item>1</item><item>2</item></root>'
    )})]
    out = await exec_xml(_node({"action": "xmlToJson"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert rendered == [{
        "data": {
            "root": {
                "@attributes": {"kind": "x"},
                "item": [{"#text": "1"}, {"#text": "2"}],
            }
        }
    }]


@pytest.mark.asyncio
async def test_xml_to_json_strips_declaration_and_comments() -> None:
    items = [ExecutionItem(json={"data": (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<!-- leading comment -->"
        "<root><a>1</a></root>"
    )})]
    out = await exec_xml(_node({"action": "xmlToJson"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert rendered == [{"data": {"root": {"a": {"#text": "1"}}}}]


@pytest.mark.asyncio
async def test_xml_to_json_empty_input_yields_empty_dict() -> None:
    items = [ExecutionItem(json={"data": "   "})]
    out = await exec_xml(_node({"action": "xmlToJson"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert rendered == [{"data": {}}]


@pytest.mark.asyncio
async def test_xml_to_json_custom_data_property() -> None:
    items = [ExecutionItem(json={"raw": "<root><a>1</a></root>"})]
    out = await exec_xml(
        _node({"action": "xmlToJson", "dataProperty": "raw"}),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    assert rendered == [{"raw": {"root": {"a": {"#text": "1"}}}}]


@pytest.mark.asyncio
async def test_xml_to_json_invalid_xml_raises() -> None:
    items = [ExecutionItem(json={"data": "<root><a>1</root>"})]
    with pytest.raises(ValueError, match="parse input as XML"):
        await exec_xml(_node({"action": "xmlToJson"}), items, ctx=_ctx())


# ── jsonToXml ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_json_to_xml_basic_dict() -> None:
    items = [ExecutionItem(json={"data": {"name": {"#text": "Ada"}}})]
    out = await exec_xml(
        _node({"action": "jsonToXml", "rootName": "root"}),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    assert rendered[0]["data"] == "<root><name>Ada</name></root>"


@pytest.mark.asyncio
async def test_json_to_xml_attributes_and_repeated_children() -> None:
    items = [ExecutionItem(json={"data": {
        "@attributes": {"kind": "x"},
        "item": [{"#text": "1"}, {"#text": "2"}],
    }})]
    out = await exec_xml(
        _node({"action": "jsonToXml", "rootName": "root"}),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    assert rendered[0]["data"] == '<root kind="x"><item>1</item><item>2</item></root>'


@pytest.mark.asyncio
async def test_json_to_xml_default_root_name() -> None:
    items = [ExecutionItem(json={"data": {"x": "y"}})]
    out = await exec_xml(_node({"action": "jsonToXml"}), items, ctx=_ctx())
    rendered = _result_items(out)
    assert rendered[0]["data"] == "<root><x>y</x></root>"


@pytest.mark.asyncio
async def test_json_to_xml_roundtrip() -> None:
    """``jsonToXml(xmlToJson(s))`` round-trips when the caller unwraps the
    document key produced by ``xmlToJson`` (which mirrors the document
    root tag) before feeding the inner dict to ``jsonToXml``.
    """
    original = "<root><name>Ada</name><age>36</age></root>"
    items = [ExecutionItem(json={"data": original})]
    parsed = _result_items(
        await exec_xml(_node({"action": "xmlToJson"}), items, ctx=_ctx())
    )
    # xmlToJson wraps in a top-level key for the root tag; jsonToXml takes
    # the inner dict as the root's contents.
    inner = parsed[0]["data"]["root"]
    items2 = [ExecutionItem(json={"data": inner})]
    reserialized = _result_items(
        await exec_xml(_node({"action": "jsonToXml"}), items2, ctx=_ctx())
    )
    assert reserialized[0]["data"] == original


@pytest.mark.asyncio
async def test_json_to_xml_custom_data_property() -> None:
    items = [ExecutionItem(json={"src": {"a": "b"}})]
    out = await exec_xml(
        _node({"action": "jsonToXml", "dataProperty": "src"}),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    assert rendered == [{"src": "<root><a>b</a></root>"}]


# ── modifyXml ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_modify_xml_sets_new_attribute() -> None:
    items = [ExecutionItem(json={"data": "<root><a>1</a></root>"})]
    out = await exec_xml(
        _node({
            "action": "modifyXml",
            "elementToModify": "a",
            "attributeName": "id",
            "attributeValue": "42",
        }),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    assert rendered[0]["data"] == '<root><a id="42">1</a></root>'


@pytest.mark.asyncio
async def test_modify_xml_overwrites_existing_attribute() -> None:
    items = [ExecutionItem(json={"data": '<root><a id="1">x</a></root>'})]
    out = await exec_xml(
        _node({
            "action": "modifyXml",
            "elementToModify": "a",
            "attributeName": "id",
            "attributeValue": "99",
        }),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    assert rendered[0]["data"] == '<root><a id="99">x</a></root>'


@pytest.mark.asyncio
async def test_modify_xml_with_index_selector() -> None:
    items = [ExecutionItem(json={"data": (
        "<root><a>1</a><a>2</a><a>3</a></root>"
    )})]
    out = await exec_xml(
        _node({
            "action": "modifyXml",
            "elementToModify": "a[2]",
            "attributeName": "picked",
            "attributeValue": "yes",
        }),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    assert (
        rendered[0]["data"]
        == '<root><a>1</a><a picked="yes">2</a><a>3</a></root>'
    )


@pytest.mark.asyncio
async def test_modify_xml_append_joins_with_space() -> None:
    items = [ExecutionItem(json={"data": '<root><a id="1">x</a></root>'})]
    out = await exec_xml(
        _node({
            "action": "modifyXml",
            "elementToModify": "a",
            "attributeName": "id",
            "attributeValue": "2",
            "append": True,
        }),
        items,
        ctx=_ctx(),
    )
    rendered = _result_items(out)
    assert rendered[0]["data"] == '<root><a id="1 2">x</a></root>'


@pytest.mark.asyncio
async def test_modify_xml_missing_attribute_name_raises() -> None:
    items = [ExecutionItem(json={"data": "<root><a>1</a></root>"})]
    with pytest.raises(ValueError, match="attributeName"):
        await exec_xml(
            _node({
                "action": "modifyXml",
                "elementToModify": "a",
                "attributeValue": "x",
            }),
            items,
            ctx=_ctx(),
        )


@pytest.mark.asyncio
async def test_modify_xml_unsupported_selector_raises() -> None:
    items = [ExecutionItem(json={"data": "<root><a>1</a></root>"})]
    with pytest.raises(ValueError, match="elementToModify"):
        await exec_xml(
            _node({
                "action": "modifyXml",
                "elementToModify": "/root/a",
                "attributeName": "id",
                "attributeValue": "1",
            }),
            items,
            ctx=_ctx(),
        )


# ── unknown action / descriptor ──────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_action_raises() -> None:
    items = [ExecutionItem(json={"data": "<root/>"})]
    with pytest.raises(ValueError, match="unsupported action"):
        await exec_xml(_node({"action": "scrub"}), items, ctx=_ctx())


@pytest.mark.asyncio
async def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.xml" in REGISTRY
    assert "n8n-nodes-base.xml" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.xml"] == "transform"
    desc = REGISTRY["n8n-nodes-base.xml"]
    assert desc.executor.endswith(":exec_xml")
    assert desc.category == "transform"


# ── End-to-end ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_manual_xml_set() -> None:
    """Manual with pinned XML → xml (xmlToJson) → Set sees parsed JSON."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("x1", "Parse", "n8n-nodes-base.xml", {
                "action": "xmlToJson",
                "dataProperty": "data",
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "name", "value": "={{ $json.data.root.name['#text'] }}", "type": "string"},
                    {"name": "age", "value": "={{ $json.data.root.age['#text'] }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Parse", "type": "main", "index": 0}]]},
            "Parse": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(
        trigger="manual",
        pin_data={"Start": [{"data": "<root><name>Ada</name><age>36</age></root>"}]},
    )
    assert result.status == "success", result.error_message

    parse_step = next(s for s in result.steps if s.node_name == "Parse")
    assert parse_step.status == "success"
    assert parse_step.output_count == 1

    final = result.final_items
    assert final, "expected at least one final item"
    downstream = next(
        (it.get("json") for it in final if isinstance(it, dict) and it.get("json")),
        None,
    )
    assert isinstance(downstream, dict)
    assert downstream.get("name") == "Ada"
    assert downstream.get("age") == "36"
