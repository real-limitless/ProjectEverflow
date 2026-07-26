"""Tests for the S3 node executor (``n8n-nodes-base.s3``).

Covers:

- ``s3_response`` dict mock → envelope is used per operation
- ``s3_response`` callable mock receives ``(operation, bucket, params, item, ctx)``
- ``http_response`` fallback unwraps a JSON body
- Offline upload: etag present, location contains bucket
- Offline download: body base64-decodes to ``b'mock s3 file content'``
- Offline list: returns 3 files
- Offline delete: deleted present
- ``operation='upload'`` reflected on the payload
- ``bucket`` default from ``$json``
- ``key`` default from ``$json``
- Empty bucket → no item
- End-to-end: Manual Trigger → s3 (list mock) → Set sees contents
- Descriptor registration (CI invariant)
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.s3 import (
    S3_DEFAULT_OPERATION,
    S3_OPERATIONS,
    exec_s3,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _node(
    params: dict[str, Any],
    *,
    type_: str = "n8n-nodes-base.s3",
    id_: str = "s1",
    name: str = "S3",
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


# ── 1. s3_response dict mock (upload) ────────────────────────────────


@pytest.mark.asyncio
async def test_s3_response_dict_mock_upload_used_verbatim() -> None:
    node = _node(
        {
            "operation": "upload",
            "bucket": "my-bucket",
            "key": "report.txt",
            "contentType": "text/plain",
        }
    )
    ctx = _ctx(
        {
            "s3_response": {
                "ETag": '"etag-001"',
                "LOCATION": "https://my-bucket.s3.amazonaws.com/report.txt",
                "key": "report.txt",
                "bucket": "my-bucket",
                "size": 4096,
            }
        }
    )
    out = _out_items(
        await exec_s3(
            node, [ExecutionItem(json={"content": "aGk="})], ctx=ctx
        )
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["etag"] == '"etag-001"'
    assert payload["location"] == "https://my-bucket.s3.amazonaws.com/report.txt"
    assert payload["key"] == "report.txt"
    assert payload["bucket"] == "my-bucket"
    assert payload["size"] == 4096
    assert payload["source"] == "s3"
    assert payload["operation"] == "upload"


# ── 2. s3_response callable mock signature ───────────────────────────


@pytest.mark.asyncio
async def test_s3_response_callable_mock_receives_args() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, bucket, params, item, ctx):
        captured["operation"] = operation
        captured["bucket"] = bucket
        captured["params"] = params
        captured["item"] = item
        captured["ctx"] = ctx
        return {
            "ETag": '"captured-001"',
            "LOCATION": f"https://{bucket}.s3.amazonaws.com/{params.get('key')}",
            "key": params.get("key"),
            "bucket": bucket,
            "size": 2048,
        }

    node = _node(
        {
            "operation": "upload",
            "bucket": "uploads",
            "key": "from-mock.txt",
            "contentType": "text/plain",
            "extra": "keep",
        }
    )
    ctx = _ctx({"s3_response": _mock})
    item = ExecutionItem(json={"hint": 1, "content": "aGk="})
    out = _out_items(await exec_s3(node, [item], ctx=ctx))

    assert captured["operation"] == "upload"
    assert captured["bucket"] == "uploads"
    assert captured["params"]["key"] == "from-mock.txt"
    assert captured["params"]["extra"] == "keep"
    assert captured["item"] is item
    assert captured["ctx"] is ctx
    assert out[0].json["etag"] == '"captured-001"'
    assert out[0].json["location"].endswith("/from-mock.txt")


@pytest.mark.asyncio
async def test_s3_response_callable_for_list() -> None:
    captured: dict[str, Any] = {}

    def _mock(operation, bucket, params, item, ctx):
        captured["operation"] = operation
        captured["bucket"] = bucket
        captured["params"] = params
        return {
            "Contents": [
                {"Key": "alpha.txt", "LastModified": "2024-01-01T00:00:00Z", "ETag": '"a"', "Size": 10},
                {"Key": "beta.txt", "LastModified": "2024-01-02T00:00:00Z", "ETag": '"b"', "Size": 20},
            ],
            "IsTruncated": False,
            "KeyCount": 2,
        }

    node = _node({"operation": "list", "bucket": "files", "maxKeys": 5})
    out = _out_items(
        await exec_s3(
            node, [ExecutionItem(json={})], ctx=_ctx({"s3_response": _mock})
        )
    )
    assert captured["operation"] == "list"
    assert captured["bucket"] == "files"
    assert captured["params"]["maxKeys"] == 5
    assert len(out) == 2
    assert out[0].json["key"] == "alpha.txt"
    assert out[1].json["key"] == "beta.txt"


# ── 3. http_response fallback (list) ──────────────────────────────────


@pytest.mark.asyncio
async def test_http_response_fallback_unwraps_list_body() -> None:
    node = _node({"operation": "list", "bucket": "fb", "maxKeys": 2})
    ctx = _ctx(
        {
            "http_response": {
                "status_code": 200,
                "body": {
                    "Contents": [
                        {"Key": "x.txt", "LastModified": "2024-01-01T00:00:00Z", "ETag": '"x"', "Size": 1},
                    ],
                    "IsTruncated": False,
                    "KeyCount": 1,
                },
            }
        }
    )
    out = _out_items(await exec_s3(node, [ExecutionItem(json={})], ctx=ctx))
    assert len(out) == 1
    assert out[0].json["key"] == "x.txt"
    assert out[0].json["mockSource"] == "http_response"


# ── 4. Offline upload ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_upload_etag_present_location_contains_bucket() -> None:
    node = _node(
        {
            "operation": "upload",
            "bucket": "offline-bucket",
            "key": "offline.txt",
            "contentType": "text/plain",
        }
    )
    out = _out_items(
        await exec_s3(
            node, [ExecutionItem(json={"content": "aGk="})], ctx=_ctx()
        )
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["etag"].startswith('"') and payload["etag"].endswith('"')
    assert "offline-bucket" in payload["location"]
    assert payload["key"] == "offline.txt"
    assert payload["bucket"] == "offline-bucket"
    assert payload["size"] == 2  # len(b"hi") from base64 "aGk="
    assert payload["source"] == "s3"
    assert payload["operation"] == "upload"
    assert payload["mockSource"] == "offline"


# ── 5. Offline download ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_offline_download_body_base64_decodes() -> None:
    node = _node({"operation": "download", "bucket": "dl-bucket", "key": "file-007"})
    out = _out_items(
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["key"] == "file-007"
    assert payload["bucket"] == "dl-bucket"
    assert base64.b64decode(payload["body"]) == b"mock s3 file content"
    assert payload["contentType"] == "application/octet-stream"
    assert payload["contentLength"] == 22
    assert payload["etag"].startswith('"')
    assert payload["source"] == "s3"
    assert payload["operation"] == "download"


# ── 6. Offline list returns 3 files ──────────────────────────────────


@pytest.mark.asyncio
async def test_offline_list_returns_three_files() -> None:
    node = _node({"operation": "list", "bucket": "list-bucket"})
    out = _out_items(
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 3
    keys = [o.json["key"] for o in out]
    assert keys == ["mock_file_1.txt", "mock_file_2.txt", "mock_file_3.txt"]
    for o in out:
        assert o.json["etag"].startswith('"')
        assert o.json["lastModified"].endswith("Z")
        assert o.json["source"] == "s3"
        assert o.json["operation"] == "list"
    assert out[0].json["size"] == 1024
    assert out[1].json["size"] == 2048
    assert out[2].json["size"] == 3072


@pytest.mark.asyncio
async def test_offline_list_data_mode_object() -> None:
    node = _node({"operation": "list", "bucket": "obj-bucket", "dataMode": "object"})
    out = _out_items(
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    payload = out[0].json
    assert isinstance(payload["contents"], list)
    assert len(payload["contents"]) == 3
    assert payload["keyCount"] == 3
    assert payload["bucket"] == "obj-bucket"
    assert payload["source"] == "s3"


# ── 7. Offline delete: deleted present ───────────────────────────────


@pytest.mark.asyncio
async def test_offline_delete_deleted_present() -> None:
    node = _node({"operation": "delete", "bucket": "del-bucket", "key": "file-xyz"})
    out = _out_items(
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert len(out) == 1
    payload = out[0].json
    assert payload["key"] == "file-xyz"
    assert payload["bucket"] == "del-bucket"
    assert isinstance(payload["deleted"], list)
    assert payload["deleted"][0]["Key"] == "file-xyz"
    assert payload["source"] == "s3"
    assert payload["operation"] == "delete"


# ── 8. operation='upload' reflected on output ────────────────────────


@pytest.mark.asyncio
async def test_operation_upload_reflected_on_output() -> None:
    node = _node(
        {
            "operation": "upload",
            "bucket": "b",
            "key": "x.txt",
            "contentType": "text/plain",
        }
    )
    out = _out_items(
        await exec_s3(
            node, [ExecutionItem(json={"content": "aGk="})], ctx=_ctx()
        )
    )
    assert out[0].json["operation"] == "upload"


# ── 9. bucket default from $json ─────────────────────────────────────


@pytest.mark.asyncio
async def test_bucket_default_from_json() -> None:
    node = _node({"operation": "list"})
    out = _out_items(
        await exec_s3(
            node, [ExecutionItem(json={"bucket": "from-json"})], ctx=_ctx()
        )
    )
    assert len(out) == 3
    assert out[0].json["bucket"] == "from-json"


@pytest.mark.asyncio
async def test_bucket_default_from_json_bucketName() -> None:
    node = _node({"operation": "list"})
    out = _out_items(
        await exec_s3(
            node, [ExecutionItem(json={"bucketName": "alt-name"})], ctx=_ctx()
        )
    )
    assert len(out) == 3
    assert out[0].json["bucket"] == "alt-name"


# ── 10. key default from $json ───────────────────────────────────────


@pytest.mark.asyncio
async def test_key_default_from_json() -> None:
    node = _node({"operation": "download", "bucket": "b"})
    out = _out_items(
        await exec_s3(
            node, [ExecutionItem(json={"key": "from-json-key"})], ctx=_ctx()
        )
    )
    assert out[0].json["key"] == "from-json-key"


@pytest.mark.asyncio
async def test_key_default_from_json_fileName() -> None:
    node = _node({"operation": "delete", "bucket": "b"})
    out = _out_items(
        await exec_s3(
            node, [ExecutionItem(json={"fileName": "fallback.txt"})], ctx=_ctx()
        )
    )
    assert out[0].json["key"] == "fallback.txt"


# ── 11. Empty bucket → no item ───────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_bucket_skips_item() -> None:
    node = _node({"operation": "list"})
    out = _out_items(
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_bucket_skips_download() -> None:
    node = _node({"operation": "download", "key": "k"})
    out = _out_items(
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_key_skips_download() -> None:
    node = _node({"operation": "download", "bucket": "b"})
    out = _out_items(
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_empty_key_skips_delete() -> None:
    node = _node({"operation": "delete", "bucket": "b"})
    out = _out_items(
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())
    )
    assert out == []


@pytest.mark.asyncio
async def test_unsupported_operation_raises() -> None:
    node = _node({"operation": "copy", "bucket": "b"})
    with pytest.raises(ValueError, match="unsupported operation"):
        await exec_s3(node, [ExecutionItem(json={})], ctx=_ctx())


# ── 12. Default operation is 'list' ──────────────────────────────────


def test_default_operation_is_list() -> None:
    assert S3_DEFAULT_OPERATION == "list"
    assert set(S3_OPERATIONS) == {"upload", "download", "list", "delete"}


# ── 13. Multiple input items produce one envelope each ───────────────


@pytest.mark.asyncio
async def test_one_output_item_per_input_for_download() -> None:
    node = _node({"operation": "download", "bucket": "b"})
    items = [
        ExecutionItem(json={"key": "a"}),
        ExecutionItem(json={"key": "b"}),
        ExecutionItem(json={"key": "c"}),
    ]
    out = _out_items(await exec_s3(node, items, ctx=_ctx()))
    assert len(out) == 3
    assert [o.json["key"] for o in out] == ["a", "b", "c"]


# ── 14. Descriptor registration ──────────────────────────────────────


def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.s3" in REGISTRY
    assert "n8n-nodes-base.s3" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.s3"] == "output"
    desc = REGISTRY["n8n-nodes-base.s3"]
    assert desc.executor.endswith(":exec_s3")
    assert desc.category == "output"


# ── 15. End-to-end: Manual Trigger → s3 (list mock) → Set sees contents


def _doc(nodes, connections):
    return {"name": "s3-test", "nodes": nodes, "connections": connections}


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
async def test_end_to_end_manual_s3_list_set_sees_contents() -> None:
    """Manual Trigger → s3 (list, s3_response mock) → Set sees file info."""
    mocks = {
        "s3_response": {
            "Contents": [
                {"Key": "first.txt", "LastModified": "2024-01-01T00:00:00Z", "ETag": '"f1"', "Size": 11},
                {"Key": "second.txt", "LastModified": "2024-01-02T00:00:00Z", "ETag": '"f2"', "Size": 22},
            ],
            "IsTruncated": False,
            "KeyCount": 2,
        }
    }
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n(
                "s1",
                "S3",
                "n8n-nodes-base.s3",
                {"operation": "list", "bucket": "e2e-bucket", "maxKeys": 5},
            ),
            _n(
                "d1",
                "Downstream",
                "n8n-nodes-base.set",
                {
                    "assignments": {
                        "assignments": [
                            {"name": "result_key", "value": "={{ $json.key }}", "type": "string"},
                            {"name": "result_size", "value": "={{ $json.size }}", "type": "number"},
                            {"name": "result_source", "value": "={{ $json.source }}", "type": "string"},
                        ]
                    }
                },
            ),
        ],
        {
            "Start": {"main": [[{"node": "S3", "type": "main", "index": 0}]]},
            "S3": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc, mocks=mocks)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    s3_step = next(s for s in result.steps if s.node_name == "S3")
    assert s3_step.status == "success", s3_step.error
    assert s3_step.output_count == 2

    final = result.final_items
    assert final, "expected at least one final item"
    keys = [f.get("json", {}).get("result_key") for f in final]
    sizes = [f.get("json", {}).get("result_size") for f in final]
    sources = [f.get("json", {}).get("result_source") for f in final]
    assert keys == ["first.txt", "second.txt"]
    assert sizes == [11, 22]
    assert sources == ["s3", "s3"]