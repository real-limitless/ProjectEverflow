"""Tests for the JWT node executor (n8n-nodes-base.jwt)."""

from __future__ import annotations

import base64
import hmac
import hashlib

import pytest

from app.services.workflows.engine import EngineContext, WorkflowEngine
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes.transforms import exec_jwt


def _node(params: dict) -> ExecNode:
    return ExecNode(
        id="j1",
        name="Jwt",
        type="n8n-nodes-base.jwt",
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
    return {"name": "jwt-test", "nodes": nodes, "connections": connections}


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


def _b64url_decode(text: str) -> bytes:
    pad = (-len(text)) % 4
    return base64.urlsafe_b64decode(text + ("=" * pad))


def _independent_hmac_sig(token: str, secret: str) -> str:
    """Recompute the signature of ``token`` with ``secret`` (HS256) using
    stdlib only — a cross-check that the executor produced a valid signature."""
    h_b64, p_b64, _sig = token.split(".")
    mac = hmac.new(
        secret.encode("utf-8"),
        f"{h_b64}.{p_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


# ── sign ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sign_returns_flat_jwt_header_payload() -> None:
    items = [ExecutionItem(json={"sub": "user-1"})]
    node = _node({
        "action": "sign",
        "payload": {"sub": "user-1", "role": "admin", "n": 7},
        "secret": "shh",
        "algorithm": "HS256",
    })
    out = await exec_jwt(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert {"jwt", "header", "payload"} <= set(rendered.keys())
    assert rendered["header"] == {"alg": "HS256", "typ": "JWT"}
    assert rendered["payload"] == {"sub": "user-1", "role": "admin", "n": 7}
    token = rendered["jwt"]
    assert isinstance(token, str) and token.count(".") == 2
    # Verify the signature is correct via stdlib.
    h_b64, p_b64, sig_b64 = token.split(".")
    assert _b64url_decode(p_b64) == b'{"n":7,"role":"admin","sub":"user-1"}'
    assert sig_b64 == _independent_hmac_sig(token, "shh")


@pytest.mark.asyncio
async def test_sign_default_algorithm_is_hs256() -> None:
    items = [ExecutionItem(json={})]
    node = _node({
        "action": "sign",
        "payload": {"x": 1},
        "secret": "k",
    })
    out = await exec_jwt(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["header"]["alg"] == "HS256"


@pytest.mark.asyncio
async def test_sign_with_expression_payload() -> None:
    items = [ExecutionItem(json={"user": "alice", "ts": 1700000000, "key": "kk"})]
    node = _node({
        "action": "sign",
        "payload": "={{ ({ 'sub': $json.user, 'iat': $json.ts }) }}",
        "secret": "={{ $json.key }}",
        "algorithm": "HS256",
    })
    out = await exec_jwt(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["payload"] == {"sub": "alice", "iat": 1700000000}
    # Cross-check the signature was made with the resolved secret.
    assert rendered["jwt"].split(".")[2] == _independent_hmac_sig(rendered["jwt"], "kk")


@pytest.mark.asyncio
async def test_sign_with_string_payload_json() -> None:
    items = [ExecutionItem(json={})]
    node = _node({
        "action": "sign",
        "payload": '{"sub":"u-1","scope":["read","write"]}',
        "secret": "s",
    })
    out = await exec_jwt(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["payload"] == {"sub": "u-1", "scope": ["read", "write"]}


@pytest.mark.asyncio
async def test_sign_with_empty_payload() -> None:
    items = [ExecutionItem(json={})]
    node = _node({"action": "sign", "payload": {}, "secret": "s"})
    out = await exec_jwt(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["payload"] == {}


@pytest.mark.asyncio
async def test_sign_missing_secret_raises() -> None:
    items = [ExecutionItem(json={})]
    node = _node({"action": "sign", "payload": {"x": 1}})
    with pytest.raises(ValueError, match="non-empty parameters.secret"):
        await exec_jwt(node, items, ctx=_ctx())


@pytest.mark.asyncio
async def test_sign_unsupported_algorithm_raises() -> None:
    items = [ExecutionItem(json={})]
    node = _node({
        "action": "sign",
        "payload": {"x": 1},
        "secret": "s",
        "algorithm": "none",
    })
    with pytest.raises(ValueError, match="unsupported algorithm"):
        await exec_jwt(node, items, ctx=_ctx())


@pytest.mark.asyncio
async def test_sign_emits_one_item_per_input() -> None:
    items = [
        ExecutionItem(json={"n": 1}),
        ExecutionItem(json={"n": 2}),
        ExecutionItem(json={"n": 3}),
    ]
    node = _node({
        "action": "sign",
        "payload": {"i": "={{ $json.n }}"},
        "secret": "k",
    })
    out = await exec_jwt(node, items, ctx=_ctx())
    rendered = _result_items(out)
    assert len(rendered) == 3
    assert [r["payload"]["i"] for r in rendered] == [1, 2, 3]


# ── verify ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sign_then_verify_roundtrip() -> None:
    items = [ExecutionItem(json={})]
    sign_node = _node({
        "action": "sign",
        "payload": {"sub": "u-9", "role": "admin"},
        "secret": "matching-secret",
        "algorithm": "HS256",
    })
    out = await exec_jwt(sign_node, items, ctx=_ctx())
    token = _result_items(out)[0]["jwt"]

    verify_items = [ExecutionItem(json={"t": token})]
    verify_node = _node({
        "action": "verify",
        "token": "={{ $json.t }}",
        "secret": "matching-secret",
    })
    out2 = await exec_jwt(verify_node, verify_items, ctx=_ctx())
    rendered = _result_items(out2)[0]
    assert rendered["valid"] is True
    assert rendered["payload"] == {"sub": "u-9", "role": "admin"}
    assert rendered["error"] == ""


@pytest.mark.asyncio
async def test_verify_with_wrong_secret_returns_valid_false() -> None:
    items = [ExecutionItem(json={})]
    sign_node = _node({
        "action": "sign",
        "payload": {"sub": "u-1"},
        "secret": "right",
    })
    out = await exec_jwt(sign_node, items, ctx=_ctx())
    token = _result_items(out)[0]["jwt"]

    verify_node = _node({
        "action": "verify",
        "token": token,
        "secret": "wrong",
    })
    out2 = await exec_jwt(verify_node, [ExecutionItem(json={})], ctx=_ctx())
    rendered = _result_items(out2)[0]
    assert rendered["valid"] is False
    assert rendered["payload"] == {"sub": "u-1"}
    assert rendered["error"] == "signature mismatch"


@pytest.mark.asyncio
async def test_verify_with_garbage_token_returns_valid_false() -> None:
    verify_node = _node({
        "action": "verify",
        "token": "not-a-jwt",
        "secret": "k",
    })
    out = await exec_jwt(verify_node, [ExecutionItem(json={})], ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["valid"] is False
    assert rendered["payload"] == {}
    assert "three dot-separated segments" in rendered["error"]


@pytest.mark.asyncio
async def test_verify_with_empty_secret_returns_valid_false() -> None:
    verify_node = _node({
        "action": "verify",
        "token": "a.b.c",
        "secret": "",
    })
    out = await exec_jwt(verify_node, [ExecutionItem(json={})], ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["valid"] is False
    assert "secret" in rendered["error"]


@pytest.mark.asyncio
async def test_verify_rejects_alg_none() -> None:
    """A ``alg: none`` token must not be accepted (no signature)."""
    header_b64 = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(b'{"sub":"u"}').rstrip(b"=").decode()
    forged = f"{header_b64}.{payload_b64}."
    verify_node = _node({"action": "verify", "token": forged, "secret": "k"})
    out = await exec_jwt(verify_node, [ExecutionItem(json={})], ctx=_ctx())
    rendered = _result_items(out)[0]
    assert rendered["valid"] is False
    assert "unsupported algorithm" in rendered["error"]


# ── Misc ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_action_raises() -> None:
    items = [ExecutionItem(json={})]
    node = _node({"action": "decode", "secret": "k", "token": "a.b.c"})
    with pytest.raises(ValueError, match="unsupported action"):
        await exec_jwt(node, items, ctx=_ctx())


@pytest.mark.asyncio
async def test_empty_input_returns_empty_output() -> None:
    for params in (
        {"action": "sign", "payload": {"x": 1}, "secret": "k"},
        {"action": "verify", "token": "a.b.c", "secret": "k"},
    ):
        out = await exec_jwt(_node(params), [], ctx=_ctx())
        assert out == [(0, [])], params


@pytest.mark.asyncio
async def test_token_field_can_be_renamed() -> None:
    items = [ExecutionItem(json={})]
    node = _node({
        "action": "sign",
        "payload": {"sub": "u"},
        "secret": "k",
        "tokenField": "token",
    })
    out = await exec_jwt(node, items, ctx=_ctx())
    rendered = _result_items(out)[0]
    assert "token" in rendered
    assert "jwt" not in rendered
    assert rendered["header"] == {"alg": "HS256", "typ": "JWT"}


# ── Descriptor & end-to-end ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_descriptor_is_registered() -> None:
    from app.services.workflows.nodes import descriptors as _  # noqa: F401
    from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES

    assert "n8n-nodes-base.jwt" in REGISTRY
    assert "n8n-nodes-base.jwt" in SUPPORTED_NODE_TYPES
    assert SUPPORTED_NODE_TYPES["n8n-nodes-base.jwt"] == "transform"
    desc = REGISTRY["n8n-nodes-base.jwt"]
    assert desc.executor.endswith(":exec_jwt")
    assert desc.category == "transform"


@pytest.mark.asyncio
async def test_end_to_end_manual_jwt_set() -> None:
    """Manual with pinned payload → jwt (sign) → Set sees the token.

    The downstream Set pulls the JWT out of the upstream item via
    ``$json.jwt``, the same flat-field convention documented in the
    executor docstring.
    """
    doc = _doc(
        [
            _n("t1", "Start", "n8n-nodes-base.manualTrigger"),
            _n("j1", "Sign", "n8n-nodes-base.jwt", {
                "action": "sign",
                "payload": {
                    "sub": "={{ $json.user }}",
                    "iat": "={{ $json.iat }}",
                },
                "secret": "shared-secret",
                "algorithm": "HS256",
            }),
            _n("s1", "Downstream", "n8n-nodes-base.set", {
                "assignments": {"assignments": [
                    {"name": "saw_token", "value": "={{ $json.jwt }}", "type": "string"},
                    {"name": "saw_sub", "value": "={{ $json.payload.sub }}", "type": "string"},
                    {"name": "kept_user", "value": "={{ $json.user }}", "type": "string"},
                ]}
            }),
        ],
        {
            "Start": {"main": [[{"node": "Sign", "type": "main", "index": 0}]]},
            "Sign": {"main": [[{"node": "Downstream", "type": "main", "index": 0}]]},
        },
    )
    engine = WorkflowEngine(doc)
    result = await engine.run(
        trigger="manual",
        pin_data={"Start": [{"user": "alice", "iat": 1700000000}]},
    )
    assert result.status == "success", result.error_message

    sign_step = next(s for s in result.steps if s.node_name == "Sign")
    assert sign_step.status == "success"
    assert sign_step.output_count == 1

    final = result.final_items
    assert final, "expected at least one final item"
    fjson = final[0].get("json") if isinstance(final[0], dict) else None
    assert fjson is not None
    token = fjson.get("saw_token")
    assert isinstance(token, str) and token.count(".") == 2
    # Cross-check the signature matches the configured secret.
    assert token.split(".")[2] == _independent_hmac_sig(token, "shared-secret")
    assert fjson.get("saw_sub") == "alice"
    assert fjson.get("kept_user") == "alice"
