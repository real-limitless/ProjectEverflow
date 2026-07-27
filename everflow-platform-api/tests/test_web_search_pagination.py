"""Unit tests for knowledge web-search pagination helper (mocked SearXNG)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.knowledge import _searxng_web_search


@pytest.mark.asyncio
async def test_searxng_forwards_pageno_and_slices() -> None:
    raw = {
        "results": [
            {"title": f"T{i}", "url": f"https://ex.com/{i}", "content": f"s{i}"}
            for i in range(15)
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = raw

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.api.v1.knowledge.httpx.AsyncClient", return_value=mock_client):
        out = await _searxng_web_search(
            "http://searx.local",
            "hello world",
            page=2,
            page_size=10,
        )

    assert out.query == "hello world"
    assert out.page == 2
    assert out.page_size == 10
    assert len(out.results) == 10
    assert out.has_more is True
    call_kwargs = mock_client.get.await_args
    params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
    assert params["pageno"] == 2
    assert params["q"] == "hello world"
    assert params["format"] == "json"


@pytest.mark.asyncio
async def test_searxng_empty_page_has_no_more() -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("app.api.v1.knowledge.httpx.AsyncClient", return_value=mock_client):
        out = await _searxng_web_search(
            "http://searx.local",
            "none",
            page=5,
            page_size=10,
        )

    assert out.results == []
    assert out.has_more is False
