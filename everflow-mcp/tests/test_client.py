"""Unit tests for EverflowClient with mocked HTTP."""

import json

import httpx
import pytest
import respx

from everflow_mcp.client import EverflowApiError, EverflowClient

BASE = "http://api.test"
PID = "11111111-1111-1111-1111-111111111111"
TOKEN = "ef_sbox_testtokenvalue00000000000000000000"


def _client() -> EverflowClient:
    return EverflowClient(base_url=BASE, token=TOKEN, project_id=PID)


@respx.mock
def test_whoami_and_create_canvas() -> None:
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
    who = c.whoami()
    assert who["project_slug"] == "demo"
    canvas = c.create_canvas(name="Arch", content_md="# hi")
    assert canvas["name"] == "Arch"


@respx.mock
def test_api_error() -> None:
    respx.get(f"{BASE}/api/v1/projects/{PID}/knowledge/canvases").mock(
        return_value=httpx.Response(403, json={"detail": "Missing scope"})
    )
    with pytest.raises(EverflowApiError) as ei:
        _client().list_canvases()
    assert ei.value.status_code == 403


def test_missing_env() -> None:
    with pytest.raises(EverflowApiError):
        EverflowClient(base_url="", token=TOKEN, project_id=PID)


@respx.mock
def test_list_and_call_http_tool() -> None:
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
    tools = c.list_http_tools()
    assert tools[0]["name"] == "status"
    result = c.call_http_tool(tool_id)
    assert result["ok"] is True
    assert result["status_code"] == 200
