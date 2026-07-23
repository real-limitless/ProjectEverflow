"""Unit tests for HTTP tool SSRF guard (no network)."""

import pytest

from app.config import Settings
from app.services.http_tools import HttpToolSsrfError, assert_url_safe, render_url_template


def test_render_url_template() -> None:
    assert render_url_template("https://api.example.com/v1/{id}", {"id": "42"}) == (
        "https://api.example.com/v1/42"
    )
    with pytest.raises(ValueError, match="Missing"):
        render_url_template("https://api.example.com/{missing}", {})


def test_blocks_localhost_by_default() -> None:
    settings = Settings(http_tools_allow_sandbox_internal=False)
    with pytest.raises(HttpToolSsrfError, match="localhost|loopback"):
        assert_url_safe("http://127.0.0.1/health", settings=settings)
    with pytest.raises(HttpToolSsrfError, match="localhost|loopback"):
        assert_url_safe("http://localhost/health", settings=settings)


def test_blocks_private_and_metadata() -> None:
    settings = Settings(http_tools_allow_sandbox_internal=False)
    with pytest.raises(HttpToolSsrfError, match="private"):
        assert_url_safe("http://10.0.0.5/x", settings=settings)
    with pytest.raises(HttpToolSsrfError, match="link-local|metadata"):
        assert_url_safe("http://169.254.169.254/latest/meta-data/", settings=settings)
    with pytest.raises(HttpToolSsrfError, match="metadata"):
        assert_url_safe("http://metadata.google.internal/", settings=settings)


def test_allows_sandbox_internal_private_but_not_metadata() -> None:
    settings = Settings(http_tools_allow_sandbox_internal=True)
    assert assert_url_safe("http://10.0.0.5/x", settings=settings) == "http://10.0.0.5/x"
    assert assert_url_safe("http://127.0.0.1/health", settings=settings) == "http://127.0.0.1/health"
    with pytest.raises(HttpToolSsrfError, match="link-local|metadata"):
        assert_url_safe("http://169.254.169.254/latest/meta-data/", settings=settings)


def test_public_https_ok() -> None:
    settings = Settings(http_tools_allow_sandbox_internal=False)
    # example.com resolves publicly in most environments; skip if DNS unavailable
    try:
        url = assert_url_safe("https://example.com/", settings=settings)
    except HttpToolSsrfError as exc:
        if "Unable to resolve" in str(exc):
            pytest.skip("DNS unavailable")
        raise
    assert url == "https://example.com/"
