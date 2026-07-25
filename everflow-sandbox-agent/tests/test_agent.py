"""Sandbox-agent mock-mode API tests."""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient

# Force mock before app import side effects
os.environ.setdefault("SANDBOX_MOCK", "true")
# Mock tests have no real OpenCode CLI; allow fake harness for ensure/proxy unit tests only.
os.environ.setdefault("OPENCODE_ALLOW_FAKE", "true")
os.environ.setdefault("SANDBOX_AGENT_TOKEN", "test-token")
os.environ.setdefault("WORKSPACE_ROOT", "/tmp/everflow-agent-test-ws")

from app.config import Settings, get_settings
from app.main import create_app
from app.msb import (
    MicrosandboxBackend,
    guest_entry_relpath,
    normalize_guest_path,
    remember_volume_strategy,
    volume_attempt_order,
)


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_MOCK", "true")
    monkeypatch.setenv("SANDBOX_AGENT_TOKEN", "test-token")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "ws"))
    get_settings.cache_clear()

    application = create_app()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Trigger lifespan
        async with application.router.lifespan_context(application):
            yield ac
    get_settings.cache_clear()


HEADERS = {"Authorization": "Bearer test-token"}


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["mock"] is True


@pytest.mark.asyncio
async def test_auth_required(client: AsyncClient) -> None:
    res = await client.post("/v1/sandboxes", json={"name": "x"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_inject_provider_secrets(client: AsyncClient) -> None:
    create = await client.post(
        "/v1/sandboxes",
        headers=HEADERS,
        json={"name": "ef-secrets", "harnesses": []},
    )
    assert create.status_code == 201, create.text

    res = await client.post(
        "/v1/sandboxes/ef-secrets/secrets/providers",
        headers=HEADERS,
        json={
            "env": {"OPENAI_API_KEY": "sk-test-secret-value"},
            "providers": {"openai": "sk-test-secret-value"},
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["written"] is True
    assert "OPENAI_API_KEY" in body["env_keys"]
    assert "sk-test-secret-value" not in res.text

    # Env file readable via FS
    content = await client.get(
        "/v1/sandboxes/ef-secrets/fs/content",
        headers=HEADERS,
        params={"path": ".everflow/secrets/providers.env"},
    )
    assert content.status_code == 200
    assert "OPENAI_API_KEY=" in content.text
    assert "sk-test-secret-value" in content.text


@pytest.mark.asyncio
async def test_sandbox_lifecycle(client: AsyncClient) -> None:
    create = await client.post(
        "/v1/sandboxes",
        headers=HEADERS,
        json={
            "name": "ef-test-proj",
            "harnesses": ["agent-claude-code", "agent-opencode"],
            "labels": {"everflow.project_id": "abc"},
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["name"] == "ef-test-proj"
    assert body["status"] == "running"
    assert "agent-claude-code" in body["harnesses"]

    got = await client.get("/v1/sandboxes/ef-test-proj", headers=HEADERS)
    assert got.status_code == 200

    exe = await client.post(
        "/v1/sandboxes/ef-test-proj/exec",
        headers=HEADERS,
        json={"cmd": "echo", "args": ["hello-everflow"]},
    )
    assert exe.status_code == 200, exe.text
    assert "hello-everflow" in exe.json()["stdout"]

    # Harness stubs on PATH
    claude = await client.post(
        "/v1/sandboxes/ef-test-proj/exec",
        headers=HEADERS,
        json={"cmd": "claude", "args": []},
    )
    assert claude.status_code == 200
    assert claude.json()["exit_code"] == 0

    stop = await client.post("/v1/sandboxes/ef-test-proj/stop", headers=HEADERS)
    assert stop.status_code == 200
    assert stop.json()["status"] == "stopped"

    start = await client.post("/v1/sandboxes/ef-test-proj/start", headers=HEADERS)
    assert start.status_code == 200
    assert start.json()["status"] == "running"

    # FS write/read
    put = await client.put(
        "/v1/sandboxes/ef-test-proj/fs/content",
        headers=HEADERS,
        params={"path": "src/main.txt"},
        json={"content": "print('hi')\n"},
    )
    assert put.status_code == 204

    get_file = await client.get(
        "/v1/sandboxes/ef-test-proj/fs/content",
        headers=HEADERS,
        params={"path": "src/main.txt"},
    )
    assert get_file.status_code == 200
    assert "print" in get_file.text

    missing = await client.get(
        "/v1/sandboxes/ef-test-proj/fs/content",
        headers=HEADERS,
        params={"path": ".everflow/database.json"},
    )
    assert missing.status_code == 404, missing.text
    detail = missing.json().get("detail", "")
    assert "not found" in detail.lower()
    assert ".everflow/database.json" in detail

    listing = await client.get(
        "/v1/sandboxes/ef-test-proj/fs",
        headers=HEADERS,
        params={"path": "."},
    )
    assert listing.status_code == 200
    entries = listing.json()
    names = {e["name"] for e in entries}
    assert "README.md" in names or "src" in names
    # Contract: no . / .., workspace-relative paths without ./ prefix
    assert "." not in names and ".." not in names
    for e in entries:
        assert not e["path"].startswith("./")
        assert e["path"] != "." and e["path"] != ".."
        assert "/" not in e["name"]

    nested = await client.get(
        "/v1/sandboxes/ef-test-proj/fs",
        headers=HEADERS,
        params={"path": "src"},
    )
    assert nested.status_code == 200
    nested_entries = nested.json()
    assert any(e["name"] == "main.txt" for e in nested_entries)
    for e in nested_entries:
        assert e["path"] == f"src/{e['name']}" or e["path"].endswith(f"/{e['name']}")
        assert not e["path"].startswith("./")

    # replace=true recreates same name
    again = await client.post(
        "/v1/sandboxes",
        headers=HEADERS,
        json={"name": "ef-test-proj", "replace": True, "harnesses": ["agent-claude-code"]},
    )
    assert again.status_code == 201, again.text
    assert again.json()["status"] == "running"

    rm = await client.post("/v1/sandboxes/ef-test-proj/remove", headers=HEADERS)
    assert rm.status_code == 204


def test_volume_attempt_order_fixed() -> None:
    assert volume_attempt_order("bind") == ["bind"]
    assert volume_attempt_order("named-volume") == ["named-volume"]
    assert volume_attempt_order("no-volumes") == ["no-volumes"]


def test_normalize_guest_path() -> None:
    assert normalize_guest_path(None) == "/workspace"
    assert normalize_guest_path(".") == "/workspace"
    assert normalize_guest_path("./") == "/workspace"
    assert normalize_guest_path("src/main.py") == "/workspace/src/main.py"
    assert normalize_guest_path("./src/foo") == "/workspace/src/foo"
    assert normalize_guest_path("/workspace") == "/workspace"
    assert normalize_guest_path("/workspace/a") == "/workspace/a"
    assert normalize_guest_path("workspace/x") == "/workspace/x"
    assert normalize_guest_path("a/../b") == "/workspace/b"
    assert normalize_guest_path("/tmp/install.sh", allow_tmp=True) == "/tmp/install.sh"
    try:
        normalize_guest_path("/etc/passwd")
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
    try:
        normalize_guest_path("../escape")
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass


def test_guest_entry_relpath() -> None:
    assert guest_entry_relpath("/workspace", "README.md") == "README.md"
    assert guest_entry_relpath("/workspace/", "src") == "src"
    assert guest_entry_relpath("/workspace/src", "main.py") == "src/main.py"
    assert guest_entry_relpath("/workspace/a/b", "c.txt") == "a/b/c.txt"


def test_volume_attempt_order_auto_prefers_last_success() -> None:
    # Fixed order when no cache
    base = volume_attempt_order("auto", last_success=None)
    assert base[0] == "named-volume"
    assert set(base) == {"named-volume", "bind", "no-volumes"}

    # Cached strategy first
    ordered = volume_attempt_order("auto", last_success="bind")
    assert ordered[0] == "bind"
    assert ordered[1:] == ["named-volume", "no-volumes"]


@pytest.mark.asyncio
async def test_guest_sse_streams_chunks() -> None:
    """Guest /event must stream OpenCode SSE, not a one-shot stub."""
    from app.opencode_proxy import proxy_to_opencode_guest
    from starlette.requests import Request

    chunks = [
        b'data: {"type":"server.connected"}\n\n',
        b'data: {"type":"message.part.delta","properties":{"messageID":"m1","delta":"Hel"}}\n\n',
        b'data: {"type":"message.part.delta","properties":{"messageID":"m1","delta":"lo"}}\n\n',
    ]

    async def fake_stream(name, cmd, args, **kwargs):
        for c in chunks:
            yield c

    async def fake_exec(*a, **k):
        return 0, "", ""

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/event",
        "raw_path": b"/event",
        "query_string": b"",
        "headers": [(b"accept", b"text/event-stream")],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    req = Request(scope, receive)
    res = await proxy_to_opencode_guest(
        req,
        exec_fn=fake_exec,
        sandbox_name="ef",
        path="event",
        port=4096,
        stream_exec_fn=fake_stream,
    )
    assert res.media_type == "text/event-stream"
    body = b""
    async for part in res.body_iterator:
        body += part if isinstance(part, bytes) else part.encode()
    assert b"message.part.delta" in body
    assert b"Hel" in body and b"lo" in body
    assert b"guest-sse" in body


@pytest.mark.asyncio
async def test_opencode_guest_proxy_via_exec() -> None:
    """Low-level guest exec proxy still works when explicitly invoked (tests/opt-in)."""
    import base64
    import json

    from app.opencode_proxy import proxy_to_opencode_guest
    from starlette.requests import Request

    async def fake_exec(name, cmd, args, **kwargs):
        body = json.dumps([{"id": "s1", "title": "Guest session"}]).encode()
        payload = {
            "status": 200,
            "ctype": "application/json",
            "body_b64": base64.b64encode(body).decode(),
        }
        return 0, json.dumps(payload) + "\n", ""

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/session",
        "raw_path": b"/session",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    req = Request(scope, receive)
    res = await proxy_to_opencode_guest(
        req,
        exec_fn=fake_exec,
        sandbox_name="ef-oc-guest",
        path="session",
        port=4096,
    )
    assert res.status_code == 200
    assert b"Guest session" in res.body


@pytest.mark.asyncio
async def test_opencode_guest_proxy_fails_fast_without_tunnel(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Product path must not hang on guest exec when TCP tunnel is missing."""
    monkeypatch.setenv("SANDBOX_MOCK", "true")
    monkeypatch.setenv("SANDBOX_AGENT_TOKEN", "test-token")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "ws"))
    monkeypatch.delenv("OPENCODE_ALLOW_EXEC_PROXY", raising=False)
    get_settings.cache_clear()

    application = create_app()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with application.router.lifespan_context(application):
            create = await ac.post(
                "/v1/sandboxes",
                headers=HEADERS,
                json={"name": "ef-no-tunnel", "harnesses": ["agent-opencode"]},
            )
            assert create.status_code == 201, create.text

            from app.opencode_mgr import OpenCodeInstance, get_opencode_manager

            mgr = get_opencode_manager()
            mgr._instances["ef-no-tunnel"] = OpenCodeInstance(
                sandbox_name="ef-no-tunnel",
                port=4096,
                workspace="/workspace",
                mode="guest",
                version="test",
                host_port=None,
            )

            async def _no_tunnel(*_a, **_k):
                return None

            monkeypatch.setattr(mgr, "attach_guest_tunnel", _no_tunnel)

            res = await ac.get(
                "/v1/sandboxes/ef-no-tunnel/opencode/session",
                headers=HEADERS,
            )
            assert res.status_code == 503, res.text
            body = res.json()
            assert body.get("tunnel") is False
            assert "tunnel" in (body.get("detail") or "").lower()

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_opencode_harness_pack(client: AsyncClient) -> None:
    create = await client.post(
        "/v1/sandboxes",
        headers=HEADERS,
        json={"name": "ef-harness", "harnesses": ["agent-opencode"]},
    )
    assert create.status_code == 201, create.text

    empty = await client.get(
        "/v1/sandboxes/ef-harness/harness/opencode",
        headers=HEADERS,
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["agents"] == []

    put = await client.put(
        "/v1/sandboxes/ef-harness/harness/opencode",
        headers=HEADERS,
        json={
            "agents": [
                {
                    "id": "security-reviewer",
                    "description": "Security-focused review",
                    "mode": "subagent",
                    "model": "anthropic/claude-sonnet-4",
                    "prompt": "Review for security issues only.",
                    "permission": {"edit": "deny"},
                    "mcpIds": ["github"],
                }
            ],
            "skills": [
                {
                    "id": "pr-review",
                    "description": "Review pull requests",
                    "body": "Check diff carefully.",
                }
            ],
            "mcp": {
                "github": {
                    "type": "remote",
                    "url": "https://example.com/mcp",
                    "enabled": True,
                }
            },
        },
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert any(a["id"] == "security-reviewer" for a in body["agents"])
    assert any(s["id"] == "pr-review" for s in body["skills"])
    assert body["mcp"]["github"]["enabled"] is True
    assert "security-reviewer" in (body.get("written") or {}).get("agents", [])

    got = await client.get(
        "/v1/sandboxes/ef-harness/harness/opencode",
        headers=HEADERS,
    )
    assert got.status_code == 200
    assert any(a["id"] == "security-reviewer" for a in got.json()["agents"])

    await client.post("/v1/sandboxes/ef-harness/remove", headers=HEADERS)


@pytest.mark.asyncio
async def test_opencode_ensure_and_proxy(client: AsyncClient) -> None:
    create = await client.post(
        "/v1/sandboxes",
        headers=HEADERS,
        json={"name": "ef-oc", "harnesses": ["agent-opencode"]},
    )
    assert create.status_code == 201, create.text

    ensure = await client.post(
        "/v1/sandboxes/ef-oc/opencode/ensure",
        headers=HEADERS,
        json={},
    )
    assert ensure.status_code == 200, ensure.text
    body = ensure.json()
    assert body["healthy"] is True
    assert body["port"]

    health = await client.get(
        "/v1/sandboxes/ef-oc/opencode/global/health",
        headers=HEADERS,
    )
    assert health.status_code == 200, health.text
    assert health.json().get("healthy") is True

    sess = await client.post(
        "/v1/sandboxes/ef-oc/opencode/session",
        headers=HEADERS,
        json={"title": "Test chat"},
    )
    assert sess.status_code == 200, sess.text
    sid = sess.json()["id"]

    sessions = await client.get(
        "/v1/sandboxes/ef-oc/opencode/session",
        headers=HEADERS,
    )
    assert sessions.status_code == 200
    assert any(s["id"] == sid for s in sessions.json())

    await client.post("/v1/sandboxes/ef-oc/remove", headers=HEADERS)


@pytest.mark.asyncio
async def test_opencode_ensure_guest_mcp_skips_without_tunnel(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guest MCP must not be configured with compose DNS when the reverse tunnel fails."""
    from unittest.mock import AsyncMock

    monkeypatch.setenv("SANDBOX_MOCK", "true")
    monkeypatch.setenv("SANDBOX_AGENT_TOKEN", "test-token")
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path / "ws"))
    get_settings.cache_clear()

    application = create_app()
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        async with application.router.lifespan_context(application):
            create = await ac.post(
                "/v1/sandboxes",
                headers=HEADERS,
                json={"name": "ef-mcp-tunnel", "harnesses": ["agent-opencode"]},
            )
            assert create.status_code == 201, create.text

            backend = application.state.backend
            rec = backend._sandboxes["ef-mcp-tunnel"]
            rec.workspace_path = "(guest-only)"

            class _FailTunnel:
                async def ensure(self, *_a, **_k):
                    return {
                        "ok": False,
                        "error": "tunnel boom",
                        "listen_port": 18765,
                        "target": "backend:8000",
                    }

            monkeypatch.setattr(
                "app.api_tunnel.get_api_tunnel_manager",
                lambda: _FailTunnel(),
            )
            monkeypatch.setattr(
                "app.everflow_mcp_inject.ensure_everflow_mcp_package",
                AsyncMock(return_value={"installed": True, "source": "existing"}),
            )
            write_guest = AsyncMock()
            monkeypatch.setattr(
                "app.everflow_mcp_inject.write_everflow_mcp_guest",
                write_guest,
            )

            from app.opencode_mgr import get_opencode_manager

            monkeypatch.setattr(
                get_opencode_manager(),
                "ensure_guest_via_exec",
                AsyncMock(
                    return_value={
                        "sandbox_name": "ef-mcp-tunnel",
                        "healthy": True,
                        "port": 4096,
                        "mode": "guest",
                    }
                ),
            )

            ensure = await ac.post(
                "/v1/sandboxes/ef-mcp-tunnel/opencode/ensure",
                headers=HEADERS,
                json={
                    "everflow_token": "ef_sbox_test",
                    "everflow_project_id": "11111111-1111-1111-1111-111111111111",
                    "everflow_api_url": "http://backend:8000",
                },
            )
            assert ensure.status_code == 200, ensure.text
            mcp = ensure.json().get("everflow_mcp") or {}
            assert mcp.get("configured") is False
            assert mcp.get("tunnel", {}).get("ok") is False
            assert "backend:8000" not in str(mcp.get("api_url", ""))
            write_guest.assert_not_awaited()

    get_settings.cache_clear()


def test_remember_volume_strategy() -> None:
    import app.msb as msb_mod

    prev = msb_mod._last_volume_strategy
    try:
        remember_volume_strategy("bind")
        ordered = volume_attempt_order("auto")
        assert ordered[0] == "bind"
    finally:
        msb_mod._last_volume_strategy = prev


@pytest.mark.asyncio
async def test_microsandbox_defers_bootstrap_and_cancels_on_remove() -> None:
    """Create must not await harness install; remove cancels the background task."""
    settings = Settings(sandbox_mock=False, volume_strategy="bind")
    backend = MicrosandboxBackend(settings)

    started = asyncio.Event()
    finished = asyncio.Event()

    async def slow_bootstrap(name: str, harnesses: list[str]):
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            finished.set()
            raise
        finished.set()
        return backend._meta[name]

    backend.bootstrap = slow_bootstrap  # type: ignore[method-assign]

    # Simulate post-VM-up path without calling real Sandbox.create
    from app.msb import SandboxRecord
    from datetime import datetime, timezone

    name = "ef-defer-test"
    backend._meta[name] = SandboxRecord(
        name=name,
        status="running",
        image="python",
        harnesses=["agent-claude-code"],
        created_at=datetime.now(timezone.utc),
    )
    backend._schedule_bootstrap(name, ["agent-claude-code"])

    await asyncio.wait_for(started.wait(), timeout=2.0)
    assert name in backend._bootstrap_tasks
    assert not backend._bootstrap_tasks[name].done()

    backend._cancel_bootstrap(name)
    # Allow cancellation to propagate
    await asyncio.sleep(0.05)
    assert name not in backend._bootstrap_tasks or backend._bootstrap_tasks[name].done()
    assert finished.is_set()


@pytest.mark.asyncio
async def test_msb_get_keeps_running_on_transient_sdk_error(monkeypatch) -> None:
    """Transient Sandbox.get failures must not poison status to error (chat false negative)."""
    import sys
    import types
    from datetime import datetime, timezone

    from app.msb import MicrosandboxBackend, SandboxRecord

    settings = Settings(sandbox_mock=False, workspace_root="/tmp/everflow-agent-test-ws")
    backend = MicrosandboxBackend(settings)
    name = "ef-transient"
    backend._meta[name] = SandboxRecord(
        name=name,
        status="running",
        image="python",
        created_at=datetime.now(timezone.utc),
    )

    class FakeSandbox:
        @staticmethod
        async def get(_name: str):
            raise TimeoutError("msb API timeout")

    fake_mod = types.ModuleType("microsandbox")
    fake_mod.Sandbox = FakeSandbox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "microsandbox", fake_mod)

    rec = await backend.get(name)
    assert rec is not None
    assert rec.status == "running"


def test_is_transient_guest_error() -> None:
    from app.msb import is_transient_guest_error

    assert is_transient_guest_error(RuntimeError("reader closed before response for id=1"))
    assert is_transient_guest_error(RuntimeError("exec session ended without exit event"))
    assert not is_transient_guest_error(RuntimeError("Sandbox not found"))


@pytest.mark.asyncio
async def test_msb_exec_retries_transient_once(monkeypatch) -> None:
    """One reconnect retry on reader-closed; second attempt succeeds."""
    from datetime import datetime, timezone

    from app.msb import MicrosandboxBackend, SandboxRecord

    settings = Settings(sandbox_mock=False, workspace_root="/tmp/everflow-agent-test-ws")
    backend = MicrosandboxBackend(settings)
    name = "ef-exec-retry"
    backend._meta[name] = SandboxRecord(
        name=name,
        status="running",
        image="python",
        created_at=datetime.now(timezone.utc),
    )

    calls = {"n": 0}

    class FakeSb:
        async def exec(self, cmd, args, **kwargs):  # noqa: ANN001
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("agent client error: reader closed before response for id=1")

            class Out:
                stdout_text = "ok"
                stderr_text = ""
                exit_code = 0

            return Out()

    async def fake_connect(_name: str):
        return FakeSb()

    monkeypatch.setattr(backend, "_connect", fake_connect)

    code, stdout, stderr = await backend.exec(name, "echo", ["hi"], timeout_seconds=5)
    assert code == 0
    assert stdout == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_msb_exec_serializes_per_sandbox(monkeypatch) -> None:
    """Concurrent execs for one sandbox must not overlap."""
    from datetime import datetime, timezone

    from app.msb import MicrosandboxBackend, SandboxRecord

    settings = Settings(sandbox_mock=False, workspace_root="/tmp/everflow-agent-test-ws")
    backend = MicrosandboxBackend(settings)
    name = "ef-exec-serial"
    backend._meta[name] = SandboxRecord(
        name=name,
        status="running",
        image="python",
        created_at=datetime.now(timezone.utc),
    )

    active = 0
    max_active = 0

    class FakeSb:
        async def exec(self, cmd, args, **kwargs):  # noqa: ANN001
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            active -= 1

            class Out:
                stdout_text = ""
                stderr_text = ""
                exit_code = 0

            return Out()

    async def fake_connect(_name: str):
        return FakeSb()

    monkeypatch.setattr(backend, "_connect", fake_connect)

    await asyncio.gather(
        backend.exec(name, "true", [], timeout_seconds=5),
        backend.exec(name, "true", [], timeout_seconds=5),
        backend.exec(name, "true", [], timeout_seconds=5),
    )
    assert max_active == 1


@pytest.mark.asyncio
async def test_msb_stream_exec_releases_lock_during_yield(monkeypatch) -> None:
    """Long-lived SSE must not hold the guest lock while streaming events.

    Chat opens /event (stream_exec) for the session life; prompt_async uses
    exec. Holding the lock during yield causes UI 45s busy timeouts.
    """
    from datetime import datetime, timezone

    from app.msb import MicrosandboxBackend, SandboxRecord

    settings = Settings(sandbox_mock=False, workspace_root="/tmp/everflow-agent-test-ws")
    backend = MicrosandboxBackend(settings)
    name = "ef-stream-lock"
    backend._meta[name] = SandboxRecord(
        name=name,
        status="running",
        image="python",
        created_at=datetime.now(timezone.utc),
    )

    stream_opened = asyncio.Event()
    stream_gate = asyncio.Event()

    class StreamEvent:
        def __init__(self, kind: str, data: bytes = b""):
            self.event_type = kind
            self.data = data

    class FakeHandle:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if not stream_opened.is_set():
                stream_opened.set()
                await stream_gate.wait()
                return StreamEvent("stdout", b"chunk")
            raise StopAsyncIteration

        async def kill(self) -> None:
            return None

    class FakeSb:
        async def exec_stream(self, cmd, args, **kwargs):  # noqa: ANN001
            return FakeHandle()

        async def exec(self, cmd, args, **kwargs):  # noqa: ANN001
            class Out:
                stdout_text = "ok"
                stderr_text = ""
                exit_code = 0

            return Out()

    async def fake_connect(_name: str):
        return FakeSb()

    monkeypatch.setattr(backend, "_connect", fake_connect)

    async def consume_stream() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in backend.stream_exec(name, "curl", ["-N", "http://x"]):
            chunks.append(chunk)
        return chunks

    stream_task = asyncio.create_task(consume_stream())
    await asyncio.wait_for(stream_opened.wait(), timeout=2.0)

    # While the stream is mid-yield, a short exec must complete (lock free).
    code, stdout, _ = await asyncio.wait_for(
        backend.exec(name, "true", [], timeout_seconds=5),
        timeout=1.0,
    )
    assert code == 0
    assert stdout == "ok"

    stream_gate.set()
    chunks = await asyncio.wait_for(stream_task, timeout=2.0)
    assert chunks == [b"chunk"]


@pytest.mark.asyncio
async def test_msb_get_marks_error_on_not_found(monkeypatch) -> None:
    import sys
    import types
    from datetime import datetime, timezone

    from app.msb import MicrosandboxBackend, SandboxRecord

    settings = Settings(sandbox_mock=False, workspace_root="/tmp/everflow-agent-test-ws")
    backend = MicrosandboxBackend(settings)
    name = "ef-gone"
    backend._meta[name] = SandboxRecord(
        name=name,
        status="running",
        image="python",
        created_at=datetime.now(timezone.utc),
    )

    class FakeSandbox:
        @staticmethod
        async def get(_name: str):
            raise RuntimeError("Sandbox not found")

    fake_mod = types.ModuleType("microsandbox")
    fake_mod.Sandbox = FakeSandbox  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "microsandbox", fake_mod)

    rec = await backend.get(name)
    assert rec is not None
    assert rec.status == "error"


def test_parse_ss_output_basic() -> None:
    from app.ports import parse_ss_output

    sample = """
LISTEN 0 4096 0.0.0.0:5173 0.0.0.0:* users:(("node",pid=42,fd=23))
LISTEN 0 128 127.0.0.1:4096 0.0.0.0:* users:(("opencode",pid=7,fd=3))
LISTEN 0 511 *:3000 *:* users:(("next-server",pid=99,fd=18))
LISTEN 0 128 [::]:8080 [::]:* users:(("python3",pid=11,fd=5))
"""
    ports = parse_ss_output(sample)
    by_port = {p.port: p for p in ports}
    assert 5173 in by_port
    assert by_port[5173].process == "node"
    assert by_port[5173].http_likely is True
    assert 3000 in by_port
    assert by_port[3000].http_likely is True
    assert 8080 in by_port
    assert by_port[8080].process == "python3"


def test_parse_proc_net_tcp_listen() -> None:
    """Guest images without ss still expose listeners via /proc/net/tcp."""
    from app.ports import parse_proc_net_tcp

    # 127.0.0.1:4096 LISTEN, 0.0.0.0:8765 LISTEN, established row ignored
    sample = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1000 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1127 1 0000000000182fe7 100 0 0 10 0
   1: 00000000:223D 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1788 1 000000000e1fce59 100 0 0 10 0
   2: 3E0010AC:BDD8 22031068:01BB 01 00000000:00000000 00:00000000 00000000     0        0 1285 1 00000000afce0590 20 4 12 10 -1
"""
    ports = parse_proc_net_tcp(sample)
    by_port = {p.port: p for p in ports}
    assert 4096 in by_port
    assert by_port[4096].address == "127.0.0.1"
    assert 8765 in by_port
    assert by_port[8765].address == "0.0.0.0"
    assert by_port[8765].http_likely is True
    # established connection must not appear
    assert all(p.port != 0xBDD8 for p in ports)


@pytest.mark.asyncio
async def test_list_ports_and_http_proxy(client: AsyncClient) -> None:
    """Start a tiny HTTP server, discover port, proxy through agent."""
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    create = await client.post(
        "/v1/sandboxes",
        headers=HEADERS,
        json={"name": "ef-preview", "harnesses": []},
    )
    assert create.status_code == 201, create.text

    # Bind ephemeral port on host (mock exec runs on host)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b'{"ok":true,"path":"' + self.path.encode() + b'"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A003
            return

    httpd = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        # Port list (ss may or may not show our port; still test proxy)
        ports_res = await client.get("/v1/sandboxes/ef-preview/ports", headers=HEADERS)
        assert ports_res.status_code == 200, ports_res.text
        assert ports_res.json()["sandbox_name"] == "ef-preview"
        assert "ports" in ports_res.json()

        proxied = await client.get(
            f"/v1/sandboxes/ef-preview/proxy/{port}/hello",
            headers=HEADERS,
        )
        assert proxied.status_code == 200, proxied.text
        assert proxied.json()["ok"] is True
        assert "/hello" in proxied.json()["path"]
        # Frame blockers stripped
        assert "x-frame-options" not in {k.lower() for k in proxied.headers.keys()}
    finally:
        httpd.shutdown()
        await client.post("/v1/sandboxes/ef-preview/remove", headers=HEADERS)
