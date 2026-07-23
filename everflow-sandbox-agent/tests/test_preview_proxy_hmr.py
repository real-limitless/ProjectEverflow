"""Vite HMR rewrite helpers used by the preview proxy (including guest-exec)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SANDBOX_MOCK", "true")
os.environ.setdefault("SANDBOX_AGENT_TOKEN", "test-token")

from app.preview_proxy import (  # noqa: E402
    DESKTOP_NOVNC_PORT,
    inject_ws_patch_html,
    rewrite_vite_client_js,
    should_inject_preview_html,
    should_rewrite_vite_client,
)


def test_rewrite_vite_client_js_rewrites_loopback_hosts() -> None:
    vite = (
        b'const serverHost = "127.0.0.1:5173";\n'
        b'const directSocketHost = "127.0.0.1:5173";\n'
        b"const hmrPort = 5173;\n"
    )
    out = rewrite_vite_client_js(vite).decode()
    assert "127.0.0.1:5173" not in out
    assert "importMetaUrl.host" in out
    assert "importMetaUrl.hostname" in out
    assert "hmrPort = null" in out


def test_inject_ws_patch_html_once() -> None:
    html = b"<html><head><title>x</title></head><body></body></html>"
    once = inject_ws_patch_html(html)
    twice = inject_ws_patch_html(once)
    text = twice.decode()
    assert text.count("data-everflow-ws-patch") == 1
    assert "location.hostname" in text


def test_preview_rewrite_skipped_for_desktop_and_errors() -> None:
    assert should_rewrite_vite_client(guest_port=5173, path="@vite/client", status_code=200)
    assert not should_rewrite_vite_client(
        guest_port=DESKTOP_NOVNC_PORT, path="@vite/client", status_code=200
    )
    assert should_inject_preview_html(
        guest_port=5173,
        path="index.html",
        content_type="text/html",
        status_code=200,
    )
    assert not should_inject_preview_html(
        guest_port=5173,
        path="vnc.html",
        content_type="application/json",
        status_code=502,
    )
    assert not should_inject_preview_html(
        guest_port=DESKTOP_NOVNC_PORT,
        path="vnc.html",
        content_type="text/html",
        status_code=200,
    )
