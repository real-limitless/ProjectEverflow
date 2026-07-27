"""Tests for the Compression node executor (n8n-nodes-base.compression)."""

from __future__ import annotations

import gzip
import io
import zipfile
import zlib

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem
from app.services.workflows.nodes.transforms import exec_compression


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="c1",
        name="Compression",
        type="n8n-nodes-base.compression",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx() -> EngineContext:
    g = type("G", (), {})()
    g.trigger_nodes = lambda preferred=None: []  # type: ignore
    return EngineContext(graph=g)  # type: ignore[arg-type]


def _item_with_bytes(data: bytes, *, name: str = "file") -> ExecutionItem:
    return ExecutionItem(
        json={},
        binary={"data": BinaryFile.from_bytes(data, file_name=name)},
    )


def _out_item(result) -> ExecutionItem:
    assert result, "expected a result batch"
    for _idx, items in result:
        for it in items:
            return it
    raise AssertionError("no output items produced")


def _out_items(result) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for _idx, items in result:
        out.extend(items)
    return out


# ── gzip roundtrip ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gzip_compress_then_decompress_roundtrip() -> None:
    payload = ("hello compression world — 你好 " * 16).encode("utf-8")
    item = _item_with_bytes(payload)

    compress_node = _node(
        {
            "action": "compress",
            "operation": "gzip",
            "binaryPropertyName": "data",
            "outputBinaryPropertyName": "data",
        }
    )
    compress_out = await exec_compression(compress_node, [item], ctx=_ctx())
    assert len(compress_out) == 1
    assert compress_out[0][0] == 0
    compressed_items = compress_out[0][1]
    assert len(compressed_items) == 1
    compressed_bytes = compressed_items[0].binary["data"].to_bytes()
    # Compressed bytes must be a valid gzip stream and shorter than the input.
    assert compressed_bytes[:2] == b"\x1f\x8b"
    assert len(compressed_bytes) < len(payload)
    # And it must round-trip through stdlib gzip.
    assert gzip.decompress(compressed_bytes) == payload
    # Output name picks up a .gz suffix.
    assert compressed_items[0].binary["data"].file_name.endswith(".gz")

    decompress_node = _node(
        {
            "action": "decompress",
            "operation": "gzip",
            "binaryPropertyName": "data",
            "outputBinaryPropertyName": "data",
        }
    )
    decompress_out = await exec_compression(decompress_node, compressed_items, ctx=_ctx())
    recovered = _out_item(decompress_out).binary["data"].to_bytes()
    assert recovered == payload
    # The recovered file name should no longer carry the .gz suffix.
    final_name = _out_item(decompress_out).binary["data"].file_name
    assert not final_name.endswith(".gz")


# ── deflate roundtrip ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deflate_compress_then_decompress_roundtrip() -> None:
    payload = b"deflate payload round trip " * 8
    item = _item_with_bytes(payload)

    compress_node = _node(
        {
            "action": "compress",
            "operation": "deflate",
            "outputBinaryPropertyName": "data",
        }
    )
    compress_out = await exec_compression(compress_node, [item], ctx=_ctx())
    compressed_bytes = compress_out[0][1][0].binary["data"].to_bytes()
    # zlib wraps the raw deflate with a 2-byte header (typically 0x78 0x9c
    # for default compression) + 4-byte adler32 checksum. We just check
    # the standard zlib magic-prefix and that the stream decodes back.
    assert compressed_bytes[0] == 0x78
    assert zlib.decompress(compressed_bytes) == payload

    decompress_node = _node(
        {
            "action": "decompress",
            "operation": "deflate",
            "outputBinaryPropertyName": "data",
        }
    )
    decompress_out = await exec_compression(
        decompress_node, compress_out[0][1], ctx=_ctx()
    )
    recovered = _out_item(decompress_out).binary["data"].to_bytes()
    assert recovered == payload


# ── zip roundtrip ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zip_compress_then_decompress_roundtrip() -> None:
    payload = b"zip payload contents"
    item = _item_with_bytes(payload, name="payload.txt")

    compress_node = _node(
        {
            "action": "compress",
            "operation": "zip",
            "outputBinaryPropertyName": "data",
        }
    )
    compress_out = await exec_compression(compress_node, [item], ctx=_ctx())
    zipped_bytes = compress_out[0][1][0].binary["data"].to_bytes()
    # Must be a valid zip with one entry.
    with zipfile.ZipFile(io.BytesIO(zipped_bytes)) as zf:
        names = zf.namelist()
        assert names == ["file"]
        with zf.open("file") as fp:
            assert fp.read() == payload
    # Output file_name should advertise .zip.
    out_name = compress_out[0][1][0].binary["data"].file_name
    assert out_name.lower().endswith(".zip")

    decompress_node = _node(
        {
            "action": "decompress",
            "operation": "zip",
            "outputBinaryPropertyName": "data",
        }
    )
    decompress_out = await exec_compression(
        decompress_node, compress_out[0][1], ctx=_ctx()
    )
    recovered = _out_item(decompress_out).binary["data"].to_bytes()
    assert recovered == payload


# ── misc: missing input, custom output key, validation ───────────────


@pytest.mark.asyncio
async def test_missing_input_binary_passes_item_through() -> None:
    """No input binary → the item is returned unchanged."""
    item = ExecutionItem(json={"note": "no binary here"})
    node = _node({"action": "compress", "operation": "gzip"})
    out = await exec_compression(node, [item], ctx=_ctx())
    (returned,) = _out_items(out)
    assert returned.json == {"note": "no binary here"}
    assert returned.binary == {}


@pytest.mark.asyncio
async def test_custom_output_property_name() -> None:
    payload = b"abc"
    item = _item_with_bytes(payload)
    node = _node(
        {
            "action": "compress",
            "operation": "gzip",
            "binaryPropertyName": "data",
            "outputBinaryPropertyName": "zipped",
        }
    )
    out = await exec_compression(node, [item], ctx=_ctx())
    (produced,) = _out_items(out)
    # The compressed payload is written to the new property.
    assert "zipped" in produced.binary
    assert gzip.decompress(produced.binary["zipped"].to_bytes()) == payload
    # The original input binary is preserved under its own property.
    assert "data" in produced.binary
    assert produced.binary["data"].to_bytes() == payload


@pytest.mark.asyncio
async def test_invalid_operation_raises() -> None:
    item = _item_with_bytes(b"x")
    node = _node({"action": "compress", "operation": "rar"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_compression(node, [item], ctx=_ctx())


@pytest.mark.asyncio
async def test_invalid_action_raises() -> None:
    item = _item_with_bytes(b"x")
    node = _node({"action": "scramble", "operation": "gzip"})
    with pytest.raises(ValueError, match="unsupported action"):
        await exec_compression(node, [item], ctx=_ctx())


@pytest.mark.asyncio
async def test_corrupt_gzip_payload_raises() -> None:
    item = _item_with_bytes(b"not actually gzip")
    node = _node({"action": "decompress", "operation": "gzip"})
    with pytest.raises(ValueError, match="gzip decode failed"):
        await exec_compression(node, [item], ctx=_ctx())


# ── Descriptor ────────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.compression" in REGISTRY
    assert "n8n-nodes-base.compression" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.compression"] == "transform"
    desc = REGISTRY["n8n-nodes-base.compression"]
    assert desc.executor.endswith(":exec_compression")
    assert desc.category == "transform"


# ── End-to-end ────────────────────────────────────────────────────────


def _doc(nodes, connections):
    return {"name": "compression-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_set_convert_compress_decompress_extract_set() -> None:
    """Manual → Set → convertToFile → compression(compress) → compression(decompress)
    → extractFromFile → Set. The final Set must observe the recovered text.

    This exercises the full engine: binary produced by convertToFile travels
    through the compression pair, gets decoded back to the original bytes,
    and the final Set reads the recovered string out of the JSON field that
    extractFromFile wrote.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("p1", "Produce", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "data", "value": "hello compression", "type": "string"},
                ]}
            }),
            _n("f1", "ToFile", "n8n-nodes-base.convertToFile", {
                "operation": "toText",
                "sourceProperty": "data",
            }),
            _n("cp1", "Compress", "n8n-nodes-base.compression", {
                "action": "compress",
                "operation": "gzip",
                "binaryPropertyName": "data",
                "outputBinaryPropertyName": "data",
            }),
            _n("dc1", "Decompress", "n8n-nodes-base.compression", {
                "action": "decompress",
                "operation": "gzip",
                "binaryPropertyName": "data",
                "outputBinaryPropertyName": "data",
            }),
            _n("ex1", "Extract", "n8n-nodes-base.extractFromFile", {
                "operation": "text",
                "destinationKey": "recovered",
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "saw", "value": "={{ $json.recovered }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Produce", "type": "main", "index": 0}]]},
            "Produce": {"main": [[{"node": "ToFile", "type": "main", "index": 0}]]},
            "ToFile": {"main": [[{"node": "Compress", "type": "main", "index": 0}]]},
            "Compress": {"main": [[{"node": "Decompress", "type": "main", "index": 0}]]},
            "Decompress": {"main": [[{"node": "Extract", "type": "main", "index": 0}]]},
            "Extract": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    # Every step ran to completion.
    step_names = {s.node_name for s in result.steps}
    assert {"Compress", "Decompress", "Extract", "Downstream"} <= step_names
    for name in ("Compress", "Decompress", "Extract", "Downstream"):
        step = next(s for s in result.steps if s.node_name == name)
        assert step.status == "success", f"{name} step failed: {step.error}"
        assert step.output_count == 1

    # Final Set must have observed the original string.
    final = result.final_items
    assert final, "expected at least one final item"
    final_json = final[0].get("json") if isinstance(final[0], dict) else None
    assert final_json is not None
    assert final_json.get("saw") == "hello compression"
