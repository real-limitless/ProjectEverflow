"""Tests for the Edit Image node executor (n8n-nodes-base.editImage)."""

from __future__ import annotations

import base64
import io

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem
from app.services.workflows.nodes.image import (
    _EDIT_IMAGE_OPERATIONS,
    _PIL,
    _mock_key,
    _normalise_params,
    exec_edit_image,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(params: dict, name: str = "EditImage") -> ExecNode:
    return ExecNode(
        id="ei1",
        name=name,
        type="n8n-nodes-base.editImage",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    mocks: dict | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    return EngineContext(graph=g, mocks=mocks or {})


def _item_with_bytes(data: bytes, *, name: str = "image.png") -> ExecutionItem:
    return ExecutionItem(
        json={},
        binary={"data": BinaryFile.from_bytes(data, file_name=name, mime_type="image/png")},
    )


def _out_items(result) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


def _png_bytes(width: int, height: int, color=(255, 0, 0)) -> bytes:
    """Build a tiny valid PNG using Pillow (test fixture). Skips if PIL missing."""
    if _PIL is None:  # pragma: no cover - guarded by skip
        pytest.skip("Pillow is not installed")
    img = _PIL.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── With Pillow: real transforms ──────────────────────────────────────


@pytest.mark.skipif(_PIL is None, reason="Pillow not installed")
@pytest.mark.asyncio
async def test_resize_produces_valid_png_bytes() -> None:
    raw = _png_bytes(20, 10)
    item = _item_with_bytes(raw)
    node = _node({"operation": "resize", "width": 5, "height": 4})

    out = await exec_edit_image(node, [item], ctx=_ctx())
    (produced,) = _out_items(out)

    out_bytes = produced.binary["data"].to_bytes()
    # Valid PNG header
    assert out_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    # And Pillow can decode the result
    decoded = _PIL.open(io.BytesIO(out_bytes))
    assert decoded.size == (5, 4)


@pytest.mark.skipif(_PIL is None, reason="Pillow not installed")
@pytest.mark.asyncio
async def test_rotate_default_90_degrees() -> None:
    raw = _png_bytes(8, 4)
    item = _item_with_bytes(raw)
    node = _node({"operation": "rotate"})

    out = await exec_edit_image(node, [item], ctx=_ctx())
    (produced,) = _out_items(out)
    decoded = _PIL.open(io.BytesIO(produced.binary["data"].to_bytes()))
    # 8x4 rotated 90° → 4x8
    assert decoded.size == (4, 8)


@pytest.mark.skipif(_PIL is None, reason="Pillow not installed")
@pytest.mark.asyncio
async def test_rotate_with_explicit_degrees() -> None:
    raw = _png_bytes(6, 2)
    item = _item_with_bytes(raw)
    node = _node({"operation": "rotate", "degrees": 180})

    out = await exec_edit_image(node, [item], ctx=_ctx())
    (produced,) = _out_items(out)
    decoded = _PIL.open(io.BytesIO(produced.binary["data"].to_bytes()))
    # 180° rotation of 6x2 stays 6x2
    assert decoded.size == (6, 2)


@pytest.mark.skipif(_PIL is None, reason="Pillow not installed")
@pytest.mark.asyncio
async def test_flip_horizontal_and_vertical_produce_same_dimensions() -> None:
    # Build a non-symmetric image so flipping actually changes pixel data.
    assert _PIL is not None
    img = _PIL.new("RGB", (8, 4))
    for x in range(img.width):
        for y in range(img.height):
            img.putpixel((x, y), (x * 30, y * 50, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    item_h = _item_with_bytes(raw)
    item_v = _item_with_bytes(raw)

    h_node = _node({"operation": "flip", "direction": "horizontal"})
    v_node = _node({"operation": "flip", "direction": "vertical"})

    h_out = _out_items(await exec_edit_image(h_node, [item_h], ctx=_ctx()))[0]
    v_out = _out_items(await exec_edit_image(v_node, [item_v], ctx=_ctx()))[0]

    h_img = _PIL.open(io.BytesIO(h_out.binary["data"].to_bytes()))
    v_img = _PIL.open(io.BytesIO(v_out.binary["data"].to_bytes()))
    # Flipping preserves canvas size
    assert h_img.size == (8, 4)
    assert v_img.size == (8, 4)
    # And the bytes differ from each other (the pixels moved).
    assert h_out.binary["data"].to_bytes() != v_out.binary["data"].to_bytes()
    # And the original differs from each transform too
    assert h_out.binary["data"].to_bytes() != raw
    assert v_out.binary["data"].to_bytes() != raw


@pytest.mark.skipif(_PIL is None, reason="Pillow not installed")
@pytest.mark.asyncio
async def test_blur_default_radius_2_does_not_crash() -> None:
    raw = _png_bytes(4, 4, color=(100, 100, 100))
    item = _item_with_bytes(raw)
    node = _node({"operation": "blur"})

    out = await exec_edit_image(node, [item], ctx=_ctx())
    (produced,) = _out_items(out)
    decoded = _PIL.open(io.BytesIO(produced.binary["data"].to_bytes()))
    assert decoded.size == (4, 4)


@pytest.mark.skipif(_PIL is None, reason="Pillow not installed")
@pytest.mark.asyncio
async def test_grayscale_converts_to_l_mode() -> None:
    raw = _png_bytes(3, 3, color=(200, 100, 50))
    item = _item_with_bytes(raw)
    node = _node({"operation": "grayscale"})

    out = await exec_edit_image(node, [item], ctx=_ctx())
    (produced,) = _out_items(out)
    decoded = _PIL.open(io.BytesIO(produced.binary["data"].to_bytes()))
    assert decoded.mode == "L"


@pytest.mark.skipif(_PIL is None, reason="Pillow not installed")
@pytest.mark.asyncio
async def test_format_converts_png_to_jpeg() -> None:
    raw = _png_bytes(4, 4, color=(255, 255, 0))
    item = _item_with_bytes(raw)
    node = _node({"operation": "format", "format": "jpeg"})

    out = await exec_edit_image(node, [item], ctx=_ctx())
    (produced,) = _out_items(out)
    out_bytes = produced.binary["data"].to_bytes()
    # JPEG magic (FFD8FF)
    assert out_bytes[:3] == b"\xff\xd8\xff"
    # Output filename should reflect the new extension
    assert produced.binary["data"].file_name.endswith(".jpg")
    assert produced.binary["data"].mime_type == "image/jpeg"


@pytest.mark.skipif(_PIL is None, reason="Pillow not installed")
@pytest.mark.asyncio
async def test_resize_aspect_ratio_preserved_when_only_width_given() -> None:
    raw = _png_bytes(10, 4)
    item = _item_with_bytes(raw)
    node = _node({"operation": "resize", "width": 5})

    out = await exec_edit_image(node, [item], ctx=_ctx())
    (produced,) = _out_items(out)
    decoded = _PIL.open(io.BytesIO(produced.binary["data"].to_bytes()))
    # 10:4 → 5:2 aspect ratio preserved
    assert decoded.size == (5, 2)


# ── Without Pillow: mock-driven path ──────────────────────────────────


@pytest.mark.skipif(_PIL is not None, reason="Mock-driven path only when Pillow is missing")
@pytest.mark.asyncio
async def test_mock_driven_resize_returns_canned_bytes() -> None:
    item = _item_with_bytes(b"INPUT-FAKE")
    node = _node({"operation": "resize", "width": 1, "height": 1})
    key = _mock_key("resize", _normalise_params(node.parameters))
    mocks = {"image_output": {key: b"FAKE-RESIZED"}}
    out = await exec_edit_image(node, [item], ctx=_ctx(mocks=mocks))
    (produced,) = _out_items(out)
    assert produced.binary["data"].to_bytes() == b"FAKE-RESIZED"


@pytest.mark.asyncio
async def test_mock_lookup_returns_canned_bytes_when_pillow_unavailable(monkeypatch) -> None:
    """Force the no-Pillow code path and assert the mock is consulted."""
    import app.services.workflows.nodes.image as image_mod

    monkeypatch.setattr(image_mod, "_PIL", None)
    item = _item_with_bytes(b"INPUT-FAKE")
    node = _node({"operation": "rotate", "degrees": 45})
    key = _mock_key("rotate", _normalise_params(node.parameters))
    mocks = {"image_output": {key: b"FAKE-ROTATED"}}
    out = await exec_edit_image(node, [item], ctx=_ctx(mocks=mocks))
    (produced,) = _out_items(out)
    assert produced.binary["data"].to_bytes() == b"FAKE-ROTATED"


@pytest.mark.asyncio
async def test_missing_mock_raises_clear_error(monkeypatch) -> None:
    import app.services.workflows.nodes.image as image_mod

    monkeypatch.setattr(image_mod, "_PIL", None)
    item = _item_with_bytes(b"INPUT-FAKE")
    node = _node({"operation": "resize", "width": 8, "height": 8})
    with pytest.raises(RuntimeError, match="no mock entry was found"):
        await exec_edit_image(node, [item], ctx=_ctx(mocks={}))


# ── Per-item behaviour / output property / pass-through ───────────────


@pytest.mark.asyncio
async def test_emits_one_item_per_input() -> None:
    # Force the mock-driven path so we can assert canned bytes per item
    # regardless of whether Pillow is installed.
    import app.services.workflows.nodes.image as image_mod

    saved_pil = image_mod._PIL
    image_mod._PIL = None
    try:
        items = [
            _item_with_bytes(b"a"),
            _item_with_bytes(b"b"),
            _item_with_bytes(b"c"),
        ]
        params = {"operation": "resize", "width": 1, "height": 1}
        key = _mock_key("resize", _normalise_params(params))
        mocks = {"image_output": {key: b"MOCKED"}}
        node = _node(params)
        out = await exec_edit_image(node, items, ctx=_ctx(mocks=mocks))
        produced = _out_items(out)
        assert len(produced) == 3
        assert all(p.binary["data"].to_bytes() == b"MOCKED" for p in produced)
    finally:
        image_mod._PIL = saved_pil


@pytest.mark.asyncio
async def test_missing_input_binary_passes_item_through() -> None:
    """No input binary on ``binaryPropertyName`` → the item is unchanged."""
    item = ExecutionItem(json={"note": "no binary"}, binary={})
    node = _node({"operation": "resize", "width": 1, "height": 1})
    out = await exec_edit_image(node, [item], ctx=_ctx())
    (returned,) = _out_items(out)
    assert returned.json == {"note": "no binary"}
    assert returned.binary == {}


@pytest.mark.asyncio
async def test_custom_output_property_name(monkeypatch) -> None:
    # Force the mock path so the test does not depend on whether Pillow
    # is installed in the test environment.
    import app.services.workflows.nodes.image as image_mod

    monkeypatch.setattr(image_mod, "_PIL", None)
    item = _item_with_bytes(b"INPUT")
    params = {
        "operation": "resize",
        "width": 1,
        "height": 1,
        "outputBinaryPropertyName": "resized",
    }
    key = _mock_key("resize", _normalise_params(params))
    mocks = {"image_output": {key: b"OUT"}}
    node = _node(params)
    out = await exec_edit_image(node, [item], ctx=_ctx(mocks=mocks))
    (produced,) = _out_items(out)
    # Output goes to the configured key.
    assert "resized" in produced.binary
    assert produced.binary["resized"].to_bytes() == b"OUT"
    # Input binary is preserved under its own key.
    assert "data" in produced.binary
    assert produced.binary["data"].to_bytes() == b"INPUT"


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    item = _item_with_bytes(b"x")
    node = _node({"operation": "sepia"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_edit_image(node, [item], ctx=_ctx())


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.editImage" in REGISTRY
    assert "n8n-nodes-base.editImage" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.editImage"] == "transform"
    desc = REGISTRY["n8n-nodes-base.editImage"]
    assert desc.executor.endswith(":exec_edit_image")
    assert desc.category == "transform"
    # Operation set matches what the executor advertises
    assert set(_EDIT_IMAGE_OPERATIONS) == {
        "resize",
        "rotate",
        "flip",
        "blur",
        "grayscale",
        "format",
    }


# ── End-to-end: Manual → Set (inject PNG) → editImage → Set ───────────


def _doc(nodes, connections):
    return {"name": "edit-image-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


def _b64_png(width: int, height: int) -> str:
    raw = _png_bytes(width, height)
    return base64.b64encode(raw).decode("ascii")


@pytest.mark.skipif(_PIL is None, reason="Pillow needed to build fixture PNG for e2e")
@pytest.mark.asyncio
async def test_end_to_end_manual_edit_image_set() -> None:
    """Manual Trigger → Set (b64 PNG) → readWriteFile (read from mock fs) →
    editImage (resize) → Set sees the resized binary metadata surfaced on
    the JSON side.

    The Set writes a base64 PNG into ``item.json.data``. ``readWriteFile``
    (read) loads the PNG bytes from ``ctx.mocks['filesystem']`` and emits
    them on ``item.binary.data``. ``editImage`` then resizes. The final
    Set pulls a marker and the ``fileName``/``mimeType`` that the
    ``readWriteFile`` step put on the item JSON, confirming the bytes
    flowed through the engine. The actual binary contents are validated
    via the resize step's ``sample_output``.
    """
    assert _PIL is not None
    png_bytes = _png_bytes(20, 10)
    b64 = base64.b64encode(png_bytes).decode("ascii")

    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("p1", "Produce", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "data", "value": b64, "type": "string"},
                    {"name": "marker", "value": "from-start", "type": "string"},
                ]}
            }),
            _n("r1", "Load", "n8n-nodes-base.readWriteFile", {
                "operation": "read",
                "filePath": "/tmp/source.png",
            }),
            _n("e1", "Resize", "n8n-nodes-base.editImage", {
                "operation": "resize",
                "width": 5,
                "height": 4,
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "saw_marker", "value": "={{ $json.marker }}", "type": "string"},
                    {"name": "saw_filename", "value": "={{ $json.fileName }}", "type": "string"},
                    {"name": "saw_mime", "value": "={{ $json.mimeType }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Produce", "type": "main", "index": 0}]]},
            "Produce": {"main": [[{"node": "Load", "type": "main", "index": 0}]]},
            "Load": {"main": [[{"node": "Resize", "type": "main", "index": 0}]]},
            "Resize": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )

    engine = WorkflowEngine(
        doc,
        mocks={"filesystem": {"/tmp/source.png": png_bytes}},
    )
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    resize_step = next(s for s in result.steps if s.node_name == "Resize")
    assert resize_step.status == "success", resize_step.error
    assert resize_step.output_count == 1

    # Resize step sample_output shows the binary metadata is on the item
    sample = resize_step.sample_output[0]
    assert "binary" in sample
    bin_meta = sample["binary"]["data"]
    assert bin_meta["fileName"].endswith(".png")
    assert bin_meta["mimeType"] == "image/png"
    # The bytes pointed to by the data are a real resized PNG.
    sample_bytes_b64 = bin_meta["data"]
    decoded_bytes = base64.b64decode(sample_bytes_b64.rstrip("…"))
    decoded_img = _PIL.open(io.BytesIO(decoded_bytes))
    assert decoded_img.size == (5, 4)

    # The downstream Set observes metadata that flowed through the engine.
    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    assert fjson.get("saw_marker") == "from-start"
    assert fjson.get("saw_filename", "").endswith(".png")
    assert fjson.get("saw_mime") == "image/png"


@pytest.mark.asyncio
async def test_end_to_end_manual_edit_image_mock_only() -> None:
    """End-to-end with the mock-driven path (Pillow deliberately disabled).

    The upstream Set writes a base64 marker into ``item.json.data``; the
    readWriteFile load maps it to ``item.binary.data`` so the editImage
    executor has a real binary to operate on. The editImage executor then
    consumes ``ctx.mocks['image_output']`` and emits a canned payload.
    """
    import app.services.workflows.nodes.image as image_mod

    saved_pil = image_mod._PIL
    image_mod._PIL = None
    try:
        marker_bytes = b"INPUT-MARKER"
        marker_b64 = base64.b64encode(marker_bytes).decode("ascii")
        params = {"operation": "rotate", "degrees": 90}
        key = _mock_key("rotate", _normalise_params(params))
        mocks = {
            "filesystem": {"/tmp/marker.bin": marker_bytes},
            "image_output": {key: b"ROTATED-OUTPUT"},
        }

        doc = _doc(
            [
                _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
                _n("p1", "Produce", "n8n-nodes-base.set", {
                    "assignments": {"assignments": [
                        {"name": "data", "value": marker_b64, "type": "string"},
                    ]}
                }),
                _n("r1", "Load", "n8n-nodes-base.readWriteFile", {
                    "operation": "read",
                    "filePath": "/tmp/marker.bin",
                }),
                _n("e1", "Rotate", "n8n-nodes-base.editImage", {
                    "operation": "rotate",
                    "degrees": 90,
                }),
                _n("s1", "Downstream", "n8n-nodes-base.set", {
                    "assignments": {"assignments": [
                        {"name": "kept", "value": "={{ $json.data }}", "type": "string"},
                    ]}
                }),
            ],
            {
                "Start": {"main": [[{"node": "Produce", "type": "main", "index": 0}]]},
                "Produce": {"main": [[{"node": "Load", "type": "main", "index": 0}]]},
                "Load": {"main": [[{"node": "Rotate", "type": "main", "index": 0}]]},
                "Rotate": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
            },
        )

        engine = WorkflowEngine(doc, mocks=mocks)
        result = await engine.run(trigger="manual")
        assert result.status == "success", result.error_message

        rotate_step = next(s for s in result.steps if s.node_name == "Rotate")
        assert rotate_step.status == "success", rotate_step.error
        sample = rotate_step.sample_output[0]
        assert "binary" in sample
        out_data_b64 = sample["binary"]["data"]["data"]
        out_bytes = base64.b64decode(out_data_b64.rstrip("…"))
        assert out_bytes == b"ROTATED-OUTPUT"

        final = result.final_items
        assert final
        fjson = final[0].get("json") if isinstance(final[0], dict) else None
        assert fjson is not None
        assert isinstance(fjson.get("kept"), str)
    finally:
        image_mod._PIL = saved_pil
