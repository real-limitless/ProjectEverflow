"""Sandbox-agent mock-mode API tests."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Force mock before app import side effects
os.environ.setdefault("SANDBOX_MOCK", "true")
os.environ.setdefault("SANDBOX_AGENT_TOKEN", "test-token")
os.environ.setdefault("WORKSPACE_ROOT", "/tmp/everflow-agent-test-ws")

from app.config import get_settings
from app.main import create_app


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
    names = {e["name"] for e in listing.json()}
    assert "README.md" in names or "src" in names

    rm = await client.post("/v1/sandboxes/ef-test-proj/remove", headers=HEADERS)
    assert rm.status_code == 204
