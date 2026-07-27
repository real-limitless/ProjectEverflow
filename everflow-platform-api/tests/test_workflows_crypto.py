"""Tests for the Crypto node executor (n8n-nodes-base.crypto)."""

from __future__ import annotations

import hashlib
import hmac as _hmac
import re

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import exec_crypto


_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="c1",
        name="Crypto",
        type="n8n-nodes-base.crypto",
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
    return {"name": "crypto-test", "nodes": nodes, "connections": connections}


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


# ── hash ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hash_sha256_of_hello_matches_known_digest() -> None:
    items = [ExecutionItem(json={"value": "hello"})]
    node = _node({"action": "hash", "value": "={{ $json.value }}", "algorithm": "sha256"})
    out = await exec_crypto(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["data"] == hashlib.sha256(b"hello").hexdigest()
    assert rendered["value"] == "hello"


@pytest.mark.asyncio
async def test_hash_supports_md5_sha1_sha512() -> None:
    items = [ExecutionItem(json={"v": "abc"})]
    for algo, expected in (
        ("md5", hashlib.md5(b"abc").hexdigest()),
        ("sha1", hashlib.sha1(b"abc").hexdigest()),
        ("sha512", hashlib.sha512(b"abc").hexdigest()),
    ):
        node = _node({"action": "hash", "value": "={{ $json.v }}", "algorithm": algo})
        out = await exec_crypto(node, items, ctx=_ctx())
        assert _result_items(out)[0]["data"] == expected


@pytest.mark.asyncio
async def test_hash_with_literal_value() -> None:
    items = [ExecutionItem(json={})]
    node = _node({"action": "hash", "value": "hello", "algorithm": "sha256"})
    out = await exec_crypto(node, items, ctx=_ctx())
    assert _result_items(out) == [{"data": hashlib.sha256(b"hello").hexdigest()}]


@pytest.mark.asyncio
async def test_hash_custom_output_field() -> None:
    items = [ExecutionItem(json={"v": "x"})]
    node = _node({
        "action": "hash",
        "value": "={{ $json.v }}",
        "algorithm": "sha1",
        "outputFieldName": "digest",
    })
    out = await exec_crypto(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["digest"] == hashlib.sha1(b"x").hexdigest()
    assert "data" not in rendered


@pytest.mark.asyncio
async def test_hash_unknown_algorithm_raises() -> None:
    items = [ExecutionItem(json={})]
    node = _node({"action": "hash", "value": "x", "algorithm": "whirlpool"})
    with pytest.raises(ValueError, match="unsupported hash algorithm"):
        await exec_crypto(node, items, ctx=_ctx())


# ── hmac ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hmac_sha256_with_string_key() -> None:
    items = [ExecutionItem(json={"message": "hello", "key": "topsecret"})]
    node = _node({
        "action": "hmac",
        "value": "={{ $json.message }}",
        "key": "={{ $json.key }}",
        "algorithm": "sha256",
    })
    out = await exec_crypto(node, items, ctx=_ctx())
    expected = _hmac.new(b"topsecret", b"hello", hashlib.sha256).hexdigest()
    assert _result_items(out)[0]["data"] == expected


@pytest.mark.asyncio
async def test_hmac_sha512_matches_python_hmac() -> None:
    items = [ExecutionItem(json={})]
    node = _node({
        "action": "hmac",
        "value": "payload",
        "key": "k",
        "algorithm": "sha512",
        "outputFieldName": "sig",
    })
    out = await exec_crypto(node, items, ctx=_ctx())
    expected = _hmac.new(b"k", b"payload", hashlib.sha512).hexdigest()
    assert _result_items(out)[0]["sig"] == expected


@pytest.mark.asyncio
async def test_hmac_requires_key() -> None:
    items = [ExecutionItem(json={})]
    node = _node({"action": "hmac", "value": "x", "algorithm": "sha256"})
    with pytest.raises(ValueError, match="requires parameters.key"):
        await exec_crypto(node, items, ctx=_ctx())


# ── encrypt / decrypt ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_encrypt_then_decrypt_roundtrip() -> None:
    items = [ExecutionItem(json={"secret": "the eagle has landed"})]
    enc_node = _node({
        "action": "encrypt",
        "value": "={{ $json.secret }}",
        "key": "correct horse battery staple",
        "outputFieldName": "blob",
    })
    enc_out = await exec_crypto(enc_node, items, ctx=_ctx())
    blob = _result_items(enc_out)[0]["blob"]
    assert isinstance(blob, str) and len(blob) > 0

    items2 = [ExecutionItem(json={"blob": blob})]
    dec_node = _node({
        "action": "decrypt",
        "value": "={{ $json.blob }}",
        "key": "correct horse battery staple",
        "outputFieldName": "plain",
    })
    dec_out = await exec_crypto(dec_node, items2, ctx=_ctx())
    assert _result_items(dec_out)[0]["plain"] == "the eagle has landed"


@pytest.mark.asyncio
async def test_encrypt_produces_unique_ivs() -> None:
    items = [ExecutionItem(json={"secret": "same plaintext"})]
    node = _node({
        "action": "encrypt",
        "value": "={{ $json.secret }}",
        "key": "k",
        "outputFieldName": "blob",
    })
    out = await exec_crypto(node, items, ctx=_ctx())
    blob = _result_items(out)[0]["blob"]

    items2 = [ExecutionItem(json={"secret": "same plaintext"})]
    out2 = await exec_crypto(node, items2, ctx=_ctx())
    blob2 = _result_items(out2)[0]["blob"]
    # Random IV → same plaintext encrypts to a different blob each run.
    assert blob != blob2


@pytest.mark.asyncio
async def test_decrypt_with_wrong_key_raises() -> None:
    items = [ExecutionItem(json={"secret": "hi"})]
    enc_node = _node({
        "action": "encrypt",
        "value": "={{ $json.secret }}",
        "key": "right",
        "outputFieldName": "blob",
    })
    blob = _result_items(await exec_crypto(enc_node, items, ctx=_ctx()))[0]["blob"]

    items2 = [ExecutionItem(json={"blob": blob})]
    dec_node = _node({
        "action": "decrypt",
        "value": "={{ $json.blob }}",
        "key": "wrong",
        "outputFieldName": "plain",
    })
    with pytest.raises(ValueError, match="decryption failed"):
        await exec_crypto(dec_node, items2, ctx=_ctx())


@pytest.mark.asyncio
async def test_decrypt_requires_value_and_key() -> None:
    items = [ExecutionItem(json={})]
    with pytest.raises(ValueError, match="requires parameters.key"):
        await exec_crypto(
            _node({"action": "decrypt", "value": "abcd", "key": None}),
            items,
            ctx=_ctx(),
        )
    with pytest.raises(ValueError, match="requires parameters.value"):
        await exec_crypto(
            _node({"action": "decrypt", "key": "k"}),
            items,
            ctx=_ctx(),
        )


# ── generateUuid ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_uuid_emits_uuid4_per_item() -> None:
    items = [
        ExecutionItem(json={"a": 1}),
        ExecutionItem(json={"a": 2}),
        ExecutionItem(json={"a": 3}),
    ]
    node = _node({"action": "generateUuid", "outputFieldName": "uuid"})
    out = await exec_crypto(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert len(rendered) == 3
    seen = set()
    for row in rendered:
        assert _UUID4_RE.match(row["uuid"]), row["uuid"]
        seen.add(row["uuid"])
    assert len(seen) == 3, "expected three unique UUIDs"


@pytest.mark.asyncio
async def test_generate_uuid_with_empty_input_still_emits_one() -> None:
    items = []
    node = _node({"action": "generateUuid"})
    out = await exec_crypto(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert len(rendered) == 1
    assert _UUID4_RE.match(rendered[0]["data"]), rendered[0]["data"]


# ── Edge cases ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_input_returns_empty_output() -> None:
    for action, params in (
        ("hash", {"action": "hash", "value": "x"}),
        ("hmac", {"action": "hmac", "value": "x", "key": "k"}),
        ("encrypt", {"action": "encrypt", "value": "x", "key": "k"}),
    ):
        out = await exec_crypto(_node(params), [], ctx=_ctx())
        assert out == [(0, [])], action


@pytest.mark.asyncio
async def test_empty_output_field_passes_item_through() -> None:
    items = [ExecutionItem(json={"v": "hello"})]
    node = _node({
        "action": "hash",
        "value": "={{ $json.v }}",
        "algorithm": "sha256",
        "outputFieldName": "",
    })
    out = await exec_crypto(node, items, ctx=_ctx())
    assert _result_items(out) == [{"v": "hello"}]


@pytest.mark.asyncio
async def test_unknown_action_raises() -> None:
    items = [ExecutionItem(json={})]
    with pytest.raises(ValueError, match="unsupported action"):
        await exec_crypto(_node({"action": "sign"}), items, ctx=_ctx())


# ── Descriptor & end-to-end ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.crypto" in REGISTRY
    assert "n8n-nodes-base.crypto" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.crypto"] == "transform"
    desc = REGISTRY["n8n-nodes-base.crypto"]
    assert desc.executor.endswith(":exec_crypto")
    assert desc.category == "transform"


@pytest.mark.asyncio
async def test_end_to_end_manual_set_crypto_hmac_set() -> None:
    """Manual → Set (with secret) → crypto (hmac) → Set (verify hash field)."""
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("p1", "Produce", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "secret", "value": "shh", "type": "string"},
                    {"name": "message", "value": "hello", "type": "string"},
                ]}
            }),
            _n("h1", "HashIt", "n8n-nodes-base.crypto", {
                "action": "hmac",
                "value": "={{ $json.message }}",
                "key": "={{ $json.secret }}",
                "algorithm": "sha256",
                "outputFieldName": "mac",
            }),
            _n("d1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "saw_mac", "value": "={{ $json.mac }}", "type": "string"},
                    {"name": "kept_message", "value": "={{ $json.message }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Produce", "type": "main", "index": 0}]]},
            "Produce": {"main": [[{"node": "HashIt", "type": "main", "index": 0}]]},
            "HashIt": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(trigger="manual")
    assert result.status == "success", result.error_message

    hash_step = next(s for s in result.steps if s.node_name == "HashIt")
    assert hash_step.status == "success"
    assert hash_step.output_count == 1

    downstream_step = next(s for s in result.steps if s.node_name == "Downstream")
    assert downstream_step.input_count == 1
    assert downstream_step.output_count == 1

    expected = _hmac.new(b"shh", b"hello", hashlib.sha256).hexdigest()
    final = result.final_items
    assert final, "expected at least one final item"
    final_json = final[0].get("json") if isinstance(final[0], dict) else None
    assert final_json is not None
    assert final_json.get("saw_mac") == expected
    assert final_json.get("kept_message") == "hello"
