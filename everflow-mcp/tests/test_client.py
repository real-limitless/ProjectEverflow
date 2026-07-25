"""Unit tests for EverflowClient with mocked HTTP."""

import httpx
import pytest
import respx

from everflow_mcp.client import DEFAULT_TIMEOUT, EverflowApiError, EverflowClient

BASE = "http://api.test"
PID = "11111111-1111-1111-1111-111111111111"
TOKEN = "ef_sbox_testtokenvalue00000000000000000000"


def _client() -> EverflowClient:
    return EverflowClient(base_url=BASE, token=TOKEN, project_id=PID)


@pytest.mark.asyncio
@respx.mock
async def test_whoami_and_create_canvas() -> None:
    respx.get(f"{BASE}/api/v1/projects/{PID}/mcp/context").mock(
        return_value=httpx.Response(
            200,
            json={
                "via": "sandbox_token",
                "user_id": "22222222-2222-2222-2222-222222222222",
                "project_id": PID,
                "project_name": "Demo",
                "project_slug": "demo",
                "organization_id": "33333333-3333-3333-3333-333333333333",
                "sandbox_status": "running",
                "scopes": ["knowledge:rw", "agents:rw", "project:read"],
            },
        )
    )
    respx.post(f"{BASE}/api/v1/projects/{PID}/knowledge/canvases").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": "44444444-4444-4444-4444-444444444444",
                "project_id": PID,
                "name": "Arch",
                "content_md": "# hi",
                "origin": "created",
                "status": "ready",
            },
        )
    )

    c = _client()
    who = await c.whoami()
    assert who["project_slug"] == "demo"
    canvas = await c.create_canvas(name="Arch", content_md="# hi")
    assert canvas["name"] == "Arch"


@pytest.mark.asyncio
@respx.mock
async def test_api_error() -> None:
    respx.get(f"{BASE}/api/v1/projects/{PID}/knowledge/canvases").mock(
        return_value=httpx.Response(403, json={"detail": "Missing scope"})
    )
    with pytest.raises(EverflowApiError) as ei:
        await _client().list_canvases()
    assert ei.value.status_code == 403


def test_missing_env() -> None:
    with pytest.raises(EverflowApiError):
        EverflowClient(base_url="", token=TOKEN, project_id=PID)


def test_default_timeout_is_split() -> None:
    c = _client()
    assert isinstance(c._timeout, httpx.Timeout)
    assert c._timeout.connect == DEFAULT_TIMEOUT.connect
    assert c._timeout.read == DEFAULT_TIMEOUT.read


@pytest.mark.asyncio
@respx.mock
async def test_list_projects() -> None:
    respx.get(f"{BASE}/api/v1/projects/{PID}").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": PID,
                "name": "Demo",
                "slug": "demo",
                "organization_id": "33333333-3333-3333-3333-333333333333",
                "sandbox_status": "running",
            },
        )
    )
    projects = await _client().list_projects()
    assert len(projects) == 1
    assert projects[0]["slug"] == "demo"


@pytest.mark.asyncio
async def test_connect_error_surfaces_quickly() -> None:
    """Unreachable base URL should raise EverflowApiError (not hang indefinitely)."""
    c = EverflowClient(
        base_url="http://127.0.0.1:1",
        token=TOKEN,
        project_id=PID,
        timeout=httpx.Timeout(connect=0.2, read=0.5, write=0.5, pool=0.2),
    )
    with pytest.raises(EverflowApiError, match="HTTP error"):
        await c.get_project()


@pytest.mark.asyncio
@respx.mock
async def test_list_and_call_http_tool() -> None:
    tool_id = "55555555-5555-5555-5555-555555555555"
    respx.get(f"{BASE}/api/v1/projects/{PID}/http-tools").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": tool_id,
                    "project_id": PID,
                    "name": "status",
                    "method": "GET",
                    "url_template": "https://example.com/health",
                    "enabled": True,
                }
            ],
        )
    )
    respx.post(f"{BASE}/api/v1/projects/{PID}/http-tools/{tool_id}/execute").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "status_code": 200,
                "url": "https://example.com/health",
                "method": "GET",
                "headers": {},
                "body": "ok",
                "truncated": False,
                "error": None,
                "elapsed_ms": 12,
            },
        )
    )
    c = _client()
    tools = await c.list_http_tools()
    assert tools[0]["name"] == "status"
    result = await c.call_http_tool(tool_id)
    assert result["ok"] is True
    assert result["status_code"] == 200


@pytest.mark.asyncio
@respx.mock
async def test_create_list_and_job_logs() -> None:
    job_id = "66666666-6666-6666-6666-666666666666"
    job = {
        "id": job_id,
        "title": "Dev server",
        "command": "npm run dev",
        "cwd": None,
        "pid": 4242,
        "status": "running",
        "log_path": f"/workspace/.everflow/jobs/{job_id}.log",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "exit_code": None,
    }
    respx.post(f"{BASE}/api/v1/projects/{PID}/jobs").mock(
        return_value=httpx.Response(201, json=job)
    )
    respx.get(f"{BASE}/api/v1/projects/{PID}/jobs").mock(
        return_value=httpx.Response(200, json=[job])
    )
    respx.get(url__regex=rf"{BASE}/api/v1/projects/{PID}/jobs/{job_id}/logs(\?.*)?").mock(
        return_value=httpx.Response(
            200,
            json={
                "job_id": job_id,
                "status": "running",
                "tail": 200,
                "content": "ready on http://0.0.0.0:3000\n",
            },
        )
    )
    respx.post(f"{BASE}/api/v1/projects/{PID}/jobs/{job_id}/stop").mock(
        return_value=httpx.Response(200, json={**job, "status": "exited", "pid": None})
    )

    c = _client()
    created = await c.create_job(title="Dev server", command="npm run dev")
    assert created["id"] == job_id
    assert created["status"] == "running"

    jobs = await c.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["command"] == "npm run dev"

    logs = await c.get_job_logs(job_id, tail=200)
    assert "ready on" in logs["content"]

    stopped = await c.stop_job(job_id)
    assert stopped["status"] == "exited"
