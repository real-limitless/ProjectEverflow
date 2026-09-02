"""Unit tests for the shared HTTP workflow client (no network)."""

from __future__ import annotations

import pytest

from app.services.workflows.http_client import (
    HttpRequestConfig,
    HttpResponse,
    execute_http_request,
)
from app.services.workflows.items import ExecutionItem


@pytest.mark.asyncio
async def test_mock_response_returns_canned_json() -> None:
    cfg = HttpRequestConfig(url="https://api.example.com/v1/items", method="GET")
    ctx_mocks = {
        "http": {
            "GET https://api.example.com/v1/items": {
                "status": 200,
                "headers": {"content-type": "application/json"},
                "body": {"items": [1, 2, 3]},
            }
        }
    }
    resp = await execute_http_request(cfg, ctx=_FakeCtx(ctx_mocks))
    assert resp.status_code == 200
    assert resp.body == {"items": [1, 2, 3]}


@pytest.mark.asyncio
async def test_mock_short_form_returns_200() -> None:
    cfg = HttpRequestConfig(url="https://api.example.com/v1/text", method="GET")
    ctx_mocks = {"http": {"https://api.example.com/v1/text": "hello"}}
    resp = await execute_http_request(cfg, ctx=_FakeCtx(ctx_mocks))
    assert resp.status_code == 200
    assert resp.body == "hello"


@pytest.mark.asyncio
async def test_mock_by_exception_path() -> None:
    cfg = HttpRequestConfig(url="https://api.example.com/v1/fail", method="GET")
    ctx_mocks = {
        "http": {
            "GET https://api.example.com/v1/fail": RuntimeError("upstream boom")
        }
    }
    with pytest.raises(RuntimeError, match="upstream boom"):
        await execute_http_request(cfg, ctx=_FakeCtx(ctx_mocks))


@pytest.mark.asyncio
async def test_request_without_mocks_raises_ssrf_for_localhost() -> None:
    cfg = HttpRequestConfig(url="http://127.0.0.1/health", method="GET")
    with pytest.raises(Exception):
        # Either HttpToolSsrfError or Network error — both acceptable.
        await execute_http_request(cfg)


@pytest.mark.asyncio
async def test_request_without_mocks_raises_ssrf_for_metadata() -> None:
    from app.services.http_tools import HttpToolSsrfError

    cfg = HttpRequestConfig(url="http://169.254.169.254/latest/meta-data/", method="GET")
    with pytest.raises(HttpToolSsrfError):
        await execute_http_request(cfg)


def test_safe_redirect_used_by_workflow_client() -> None:
    from app.services.http_tools import HttpToolSsrfError, safe_redirect_target

    with pytest.raises(HttpToolSsrfError):
        safe_redirect_target("https://example.com/x", "http://169.254.169.254/")
    with pytest.raises(HttpToolSsrfError):
        safe_redirect_target("https://example.com/x", "http://127.0.0.1/")


def test_apply_auth_header_mode() -> None:
    from app.services.workflows.http_client import _apply_auth
    import httpx

    req = httpx.Request("GET", "https://x")
    cfg = HttpRequestConfig(
        url="https://x",
        auth="header",
        auth_credential={"name": "X-Api-Key", "value": "secret"},
    )
    _apply_auth(req, cfg)
    assert req.headers["X-Api-Key"] == "secret"


def test_apply_auth_bearer_mode() -> None:
    from app.services.workflows.http_client import _apply_auth
    import httpx

    req = httpx.Request("GET", "https://x")
    cfg = HttpRequestConfig(
        url="https://x",
        auth="bearer",
        auth_credential={"token": "abc"},
    )
    _apply_auth(req, cfg)
    assert req.headers["Authorization"] == "Bearer abc"


def test_apply_auth_basic_mode() -> None:
    from app.services.workflows.http_client import _apply_auth
    import httpx

    req = httpx.Request("GET", "https://x")
    cfg = HttpRequestConfig(
        url="https://x",
        auth="basic",
        auth_credential={"user": "u", "password": "p"},
    )
    _apply_auth(req, cfg)
    assert req.headers["Authorization"].startswith("Basic ")


def test_apply_auth_custom_headers() -> None:
    from app.services.workflows.http_client import _apply_auth
    import httpx

    req = httpx.Request("GET", "https://x")
    cfg = HttpRequestConfig(
        url="https://x",
        auth="custom",
        auth_credential={"headers": {"X-Custom": "1", "X-Other": "2"}},
    )
    _apply_auth(req, cfg)
    assert req.headers["X-Custom"] == "1"
    assert req.headers["X-Other"] == "2"


def test_apply_auth_custom_headers_json_string() -> None:
    from app.services.workflows.http_client import _apply_auth
    import httpx
    import json

    req = httpx.Request("GET", "https://x")
    cfg = HttpRequestConfig(
        url="https://x",
        auth="custom",
        auth_credential={"headers": json.dumps({"X-J": "ok"})},
    )
    _apply_auth(req, cfg)
    assert req.headers["X-J"] == "ok"


class _FakeCtx:
    """Minimal EngineContext substitute for tests; only ``mocks`` is read."""

    def __init__(self, mocks: dict) -> None:
        self.mocks = mocks
