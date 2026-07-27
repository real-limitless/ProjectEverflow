"""Tests for the Read/Write File node executor (n8n-nodes-base.readWriteFile)."""

from __future__ import annotations

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecGraph, ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem
from app.services.workflows.nodes.files import exec_read_write_file


# ── Helpers ───────────────────────────────────────────────────────────


def _node(params: dict, name: str = "ReadWriteFile") -> ExecNode:
    return ExecNode(
        id="rwf1",
        name=name,
        type="n8n-nodes-base.readWriteFile",
        type_version=1,
        parameters=params,
        credentials=None,
        position={"x": 0, "y": 0},
    )


def _ctx(
    *,
    filesystem: dict | None = None,
    base_dir: str | None = None,
    mocks: dict | None = None,
) -> EngineContext:
    g = ExecGraph(nodes_by_id={}, nodes_by_name={})
    if mocks is None:
        mocks = {}
    if filesystem is not None:
        mocks["filesystem"] = filesystem
    if base_dir is not None:
        mocks["baseDir"] = base_dir
    return EngineContext(graph=g, mocks=mocks)


def _doc(nodes, connections):
    return {"name": "read-write-file-test", "nodes": nodes, "connections": connections}


def _n(id_, name, type_, params=None, position=(0, 0)):
    return {
        "id": id_,
        "name": name,
        "type": type_,
        "typeVersion": 1,
        "position": list(position),
        "parameters": params or {},
    }


# ── read from mock filesystem ────────────────────────────────────────


@pytest.mark.asyncio
async def test_read_from_mock_filesystem_puts_binary_on_item() -> None:
    ctx = _ctx(filesystem={"/tmp/greeting.txt": b"hello world"})
    node = _node({"operation": "read", "filePath": "/tmp/greeting.txt"})

    out = await exec_read_write_file(node, items=[ExecutionItem(json={})], ctx=ctx)

    assert len(out) == 1 and out[0][0] == 0
    items = out[0][1]
    assert len(items) == 1
    assert "data" in items[0].binary
    bf = items[0].binary["data"]
    assert bf.to_bytes() == b"hello world"
    assert bf.file_name == "greeting.txt"
    assert bf.mime_type == "text/plain"
    assert items[0].json["fileName"] == "greeting.txt"
    assert items[0].json["mimeType"] == "text/plain"
    assert items[0].json["filePath"] == "/tmp/greeting.txt"


@pytest.mark.asyncio
async def test_read_honors_custom_data_property_name() -> None:
    ctx = _ctx(filesystem={"/tmp/a.csv": b"a,b\n1,2\n"})
    node = _node(
        {
            "operation": "read",
            "filePath": "/tmp/a.csv",
            "dataPropertyName": "attachment",
        }
    )

    out = await exec_read_write_file(node, items=[ExecutionItem(json={})], ctx=ctx)

    bf = out[0][1][0].binary["attachment"]
    assert bf.to_bytes() == b"a,b\n1,2\n"
    assert bf.mime_type == "text/csv"


@pytest.mark.asyncio
async def test_read_with_basename_fallback() -> None:
    """Read by basename when the mock key is by basename only."""
    ctx = _ctx(filesystem={"greeting.txt": b"hi"})
    node = _node({"operation": "read", "filePath": "/some/dir/greeting.txt"})

    out = await exec_read_write_file(node, items=[ExecutionItem(json={})], ctx=ctx)
    bf = out[0][1][0].binary["data"]
    assert bf.to_bytes() == b"hi"


# ── write to mock filesystem ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_text_field_records_in_mock_filesystem() -> None:
    fs: dict[str, bytes] = {}
    ctx = _ctx(filesystem=fs)
    node = _node({"operation": "write", "filePath": "/tmp/out.txt"})

    out = await exec_read_write_file(
        node,
        items=[ExecutionItem(json={"data": "hello"})],
        ctx=ctx,
    )

    assert out[0][1][0].json["filePath"] == "/tmp/out.txt"
    assert out[0][1][0].json["fileName"] == "out.txt"
    assert out[0][1][0].json["mimeType"] == "text/plain"
    assert out[0][1][0].json["size"] == 5
    assert fs["/tmp/out.txt"] == b"hello"


@pytest.mark.asyncio
async def test_write_with_directory_and_per_item_filename() -> None:
    fs: dict[str, bytes] = {}
    ctx = _ctx(filesystem=fs)
    node = _node(
        {
            "operation": "write",
            "directory": "/tmp/out",
            "fileName": "={{ $json.name }}.txt",
        }
    )

    items = [
        ExecutionItem(json={"name": "alpha", "data": "first"}),
        ExecutionItem(json={"name": "beta", "data": "second"}),
    ]
    out = await exec_read_write_file(node, items=items, ctx=ctx)

    assert fs["/tmp/out/alpha.txt"] == b"first"
    assert fs["/tmp/out/beta.txt"] == b"second"
    assert [it.json["fileName"] for it in out[0][1]] == ["alpha.txt", "beta.txt"]


@pytest.mark.asyncio
async def test_write_picks_up_data_from_binary_property() -> None:
    fs: dict[str, bytes] = {}
    ctx = _ctx(filesystem=fs)
    node = _node({"operation": "write", "filePath": "/tmp/from_binary.txt"})

    item = ExecutionItem(json={"fileName": "ignored.txt"})
    item.binary["data"] = BinaryFile.from_bytes(
        b"from-binary",
        file_name="from_binary.txt",
        mime_type="text/plain",
    )

    out = await exec_read_write_file(node, items=[item], ctx=ctx)
    assert fs["/tmp/from_binary.txt"] == b"from-binary"
    assert out[0][1][0].json["fileName"] == "from_binary.txt"


# ── expression path resolution ───────────────────────────────────────


@pytest.mark.asyncio
async def test_read_with_expression_path() -> None:
    fs = {"/data/alpha.txt": b"alpha-content"}
    ctx = _ctx(filesystem=fs)
    node = _node(
        {
            "operation": "read",
            "filePath": "={{ '/data/' + $json.which + '.txt' }}",
        }
    )

    out = await exec_read_write_file(
        node,
        items=[ExecutionItem(json={"which": "alpha"})],
        ctx=ctx,
    )
    bf = out[0][1][0].binary["data"]
    assert bf.to_bytes() == b"alpha-content"
    assert bf.file_name == "alpha.txt"


# ── error cases ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_without_mock_or_base_dir_raises() -> None:
    ctx = _ctx()
    node = _node({"operation": "write", "filePath": "/tmp/out.txt"})

    with pytest.raises(RuntimeError) as exc:
        await exec_read_write_file(
            node,
            items=[ExecutionItem(json={"data": "x"})],
            ctx=ctx,
        )
    assert "mocks['filesystem']" in str(exc.value)
    assert "baseDir" in str(exc.value)


@pytest.mark.asyncio
async def test_read_without_mock_or_base_dir_raises() -> None:
    ctx = _ctx()
    node = _node({"operation": "read", "filePath": "/tmp/missing.txt"})

    with pytest.raises(RuntimeError) as exc:
        await exec_read_write_file(node, items=[ExecutionItem(json={})], ctx=ctx)
    assert "mocks['filesystem']" in str(exc.value)


@pytest.mark.asyncio
async def test_read_missing_path_raises() -> None:
    ctx = _ctx(filesystem={"/tmp/a.txt": b"a"})
    node = _node({"operation": "read", "filePath": "/tmp/missing.txt"})

    with pytest.raises(FileNotFoundError):
        await exec_read_write_file(node, items=[ExecutionItem(json={})], ctx=ctx)


@pytest.mark.asyncio
async def test_write_without_payload_raises() -> None:
    ctx = _ctx(filesystem={})
    node = _node({"operation": "write", "filePath": "/tmp/x.txt"})

    with pytest.raises(ValueError):
        await exec_read_write_file(
            node,
            items=[ExecutionItem(json={"unrelated": "field"})],
            ctx=ctx,
        )


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    ctx = _ctx(filesystem={})
    node = _node({"operation": "frobnicate", "filePath": "/tmp/x.txt"})

    with pytest.raises(ValueError):
        await exec_read_write_file(
            node,
            items=[ExecutionItem(json={"data": "x"})],
            ctx=ctx,
        )


# ── descriptor ───────────────────────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.readWriteFile" in REGISTRY
    assert "n8n-nodes-base.readWriteFile" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.readWriteFile"] == "input"
    desc = REGISTRY["n8n-nodes-base.readWriteFile"]
    assert desc.executor.endswith(":exec_read_write_file")
    assert desc.category == "input"


# ── end-to-end ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_to_end_write_then_read_set_sees_recovered_text() -> None:
    """Manual (pin data: ``{data: 'hello'}``) → write → read → Set sees text.

    The write step records the bytes into ``mocks['filesystem']``; the
    read step loads them back onto ``item.binary['data']`` and surfaces
    metadata (``fileName``/``mimeType``/``filePath``) on JSON so the
    downstream Set can read it. The recovered text is verified by
    inspecting the read step's ``sample_output`` binary directly.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "w1",
                "WriteFile",
                "n8n-nodes-base.readWriteFile",
                {
                    "operation": "write",
                    "filePath": "/tmp/from-e2e.txt",
                    "dataPropertyName": "data",
                },
            ),
            _n(
                "r1",
                "ReadFile",
                "n8n-nodes-base.readWriteFile",
                {
                    "operation": "read",
                    "filePath": "/tmp/from-e2e.txt",
                    "dataPropertyName": "data",
                },
            ),
            _n(
                "s1",
                "Inspect",
                "n8n-nodes-base.set",
                {
                    "assignments": {"assignments": [
                        {
                            "name": "seen_name",
                            "value": "={{ $json.fileName }}",
                            "type": "string",
                        },
                        {
                            "name": "seen_mime",
                            "value": "={{ $json.mimeType }}",
                            "type": "string",
                        },
                        {
                            "name": "seen_path",
                            "value": "={{ $json.filePath }}",
                            "type": "string",
                        },
                    ]}
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "WriteFile", "type": "main", "index": 0}]]},
            "WriteFile": {"main": [[{"node": "ReadFile", "type": "main", "index": 0}]]},
            "ReadFile": {"main": [[{"node": "Inspect", "type": "main", "index": 0}]]},
        },
    )
    fs: dict[str, bytes] = {}
    engine = WorkflowEngine(doc, mocks={"filesystem": fs})
    result = await engine.run(
        trigger="manual",
        pin_data={"Start": [{"data": "hello"}]},
    )
    assert result.status == "success", result.error_message

    write_step = next(s for s in result.steps if s.node_name == "WriteFile")
    assert write_step.status == "success"
    assert write_step.output_count == 1
    # the write went to the mock fs
    assert fs["/tmp/from-e2e.txt"] == b"hello"

    read_step = next(s for s in result.steps if s.node_name == "ReadFile")
    assert read_step.status == "success"
    assert read_step.output_count == 1
    # the read recovered the text on item.binary
    sample = read_step.sample_output
    assert sample, "expected sample_output on read step"
    bin_data = sample[0].get("binary") or {}
    assert "data" in bin_data
    assert bin_data["data"]["fileName"] == "from-e2e.txt"
    assert bin_data["data"]["mimeType"] == "text/plain"
    assert bin_data["data"]["size"] == 5
    recovered = bin_data["data"]["data"]
    import base64

    assert base64.b64decode(recovered) == b"hello"

    # downstream Set sees the JSON metadata surfaced by the read
    final = result.final_items
    assert final, "expected at least one final item from Inspect"
    final_json = final[0].get("json") or {}
    assert final_json.get("seen_name") == "from-e2e.txt"
    assert final_json.get("seen_mime") == "text/plain"
    assert final_json.get("seen_path") == "/tmp/from-e2e.txt"
