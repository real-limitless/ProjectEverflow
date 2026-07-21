"""Sandbox-agent mock-mode API tests."""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient

# Force mock before app import side effects
os.environ.setdefault("SANDBOX_MOCK", "true")
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
    """Guest mode has no host base_url — proxy uses in-guest HTTP via exec."""
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
