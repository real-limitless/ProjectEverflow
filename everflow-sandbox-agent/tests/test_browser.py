"""Unit tests for Playwright browser harness helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.browser import (
    apply_browser_stamps_host,
    is_playwright_mcp_entry,
    normalize_mode,
    playwright_mcp_config,
    sync_browser_stamps_from_pack,
    validate_public_http_url,
)


def test_normalize_mode() -> None:
    assert normalize_mode(None) == "headless"
    assert normalize_mode("HEADLESS") == "headless"
    assert normalize_mode("headed") == "headed"
    assert normalize_mode("visible") == "headed"
    assert normalize_mode("headful") == "headed"


def test_playwright_mcp_config_shape() -> None:
    cfg = playwright_mcp_config()
    assert cfg["type"] == "local"
    assert cfg["command"] == ["everflow-playwright-mcp"]
    assert cfg["enabled"] is True
    assert cfg["environment"]["PLAYWRIGHT_BROWSERS_PATH"] == "/opt/everflow-browsers"
    assert cfg["environment"]["DISPLAY"] == ":99"


def test_is_playwright_mcp_entry() -> None:
    assert is_playwright_mcp_entry(playwright_mcp_config())
    assert is_playwright_mcp_entry(
        {"type": "local", "command": ["npx", "-y", "@playwright/mcp"], "enabled": True}
    )
    assert not is_playwright_mcp_entry({"enabled": False, "command": ["everflow-playwright-mcp"]})
    assert not is_playwright_mcp_entry({"command": ["python3", "-m", "everflow_mcp"]})


def test_sync_stamps_enable_disable(tmp_path: Path) -> None:
    pack_on = {"mcp": {"playwright": playwright_mcp_config()}}
    out = sync_browser_stamps_from_pack(tmp_path, pack_on)
    assert out["enabled"] is True
    assert (tmp_path / ".everflow" / "browser.enabled").read_text(encoding="utf-8").strip() == "1"
    assert (tmp_path / ".everflow" / "browser.mode").read_text(encoding="utf-8").strip() == "headless"

    pack_off = {"mcp": {"playwright": None}}
    out2 = sync_browser_stamps_from_pack(tmp_path, pack_off)
    assert out2["enabled"] is False
    assert not (tmp_path / ".everflow" / "browser.enabled").exists()


def test_apply_browser_stamps_preserves_mode(tmp_path: Path) -> None:
    apply_browser_stamps_host(tmp_path, enabled=True, mode="headed")
    apply_browser_stamps_host(tmp_path, enabled=True)  # should not clobber mode
    assert (tmp_path / ".everflow" / "browser.mode").read_text(encoding="utf-8").strip() == "headed"


def test_validate_public_http_url_blocks_private() -> None:
    try:
        assert validate_public_http_url("https://example.com/a") == "https://example.com/a"
    except ValueError as exc:
        if "Unable to resolve" not in str(exc):
            raise
    for bad in (
        "http://localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://[::ffff:169.254.169.254]/",
        "file:///etc/passwd",
    ):
        with pytest.raises(ValueError):
            validate_public_http_url(bad)
