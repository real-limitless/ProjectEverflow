"""Rewrite Vite HMR client assets for preview-proxy public hosts."""

from __future__ import annotations

import re

_WS_PATCH_SCRIPT = (
    "<script data-everflow-ws-patch>"
    "(function(){"
    "var N=window.WebSocket;"
    "if(!N||N.__efPatched)return;"
    "function P(u){"
    "try{"
    "var x=new URL(u,location.href);"
    "if(x.hostname==='127.0.0.1'||x.hostname==='localhost'){"
    "x.hostname=location.hostname;"
    "x.protocol=location.protocol==='https:'?'wss:':'ws:';"
    "if(location.port)x.port=location.port;else x.port='';"
    "return x.toString();"
    "}}catch(e){}"
    "return u;"
    "}"
    "function W(u,p){"
    "return p===undefined?new N(P(u)):new N(P(u),p);"
    "}"
    "W.prototype=N.prototype;"
    "W.CONNECTING=N.CONNECTING;W.OPEN=N.OPEN;W.CLOSING=N.CLOSING;W.CLOSED=N.CLOSED;"
    "W.__efPatched=1;window.WebSocket=W;"
    "})();"
    "</script>"
)


def rewrite_vite_client_js(content: bytes) -> bytes:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    if "directSocketHost" not in text and "setupWebSocket" not in text:
        return content
    text2 = re.sub(
        r'const serverHost = "[^"]*";',
        'const serverHost = importMetaUrl.host + "/";',
        text,
        count=1,
    )
    text2 = re.sub(
        r'const directSocketHost = "[^"]*";',
        "const directSocketHost = `${importMetaUrl.hostname}:${importMetaUrl.port}/`;",
        text2,
        count=1,
    )
    text2 = re.sub(r"const hmrPort = [^;]+;", "const hmrPort = null;", text2, count=1)
    return text2.encode("utf-8")


def inject_ws_patch_html(content: bytes) -> bytes:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    if "data-everflow-ws-patch" in text:
        return content
    lower = text.lower()
    idx = lower.find("<head>")
    if idx >= 0:
        insert_at = idx + len("<head>")
        text = text[:insert_at] + _WS_PATCH_SCRIPT + text[insert_at:]
        return text.encode("utf-8")
    return (_WS_PATCH_SCRIPT + text).encode("utf-8")


def preview_cache_headers(path: str, headers: dict[str, str]) -> dict[str, str]:
    out = dict(headers)
    pl = (path or "").lower()
    if (
        "@vite/client" in pl
        or pl.endswith(".html")
        or pl in ("", "/")
        or pl.endswith("/")
        or "vite/dist/client" in pl
    ):
        out["Cache-Control"] = "no-store, no-cache, must-revalidate"
        out["Pragma"] = "no-cache"
    return out
