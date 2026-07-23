"""Rewrite Vite HMR client assets for preview-proxy public hosts."""

from __future__ import annotations

import re

# Desktop panel (noVNC / websockify) — never apply Preview HMR rewrites.
DESKTOP_NOVNC_PORT = 6080

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

_NAV_BRIDGE_SCRIPT = (
    "<script data-everflow-nav-bridge>"
    "(function(){"
    "if(window.__efNavPatched)return;"
    "window.__efNavPatched=1;"
    "function report(){"
    "try{"
    "parent.postMessage("
    "{type:'everflow-preview-nav',path:location.pathname+location.search+location.hash},"
    "'*'"
    ");"
    "}catch(e){}"
    "}"
    "var _ps=history.pushState,_rs=history.replaceState;"
    "history.pushState=function(){"
    "var r=_ps.apply(this,arguments);report();return r;"
    "};"
    "history.replaceState=function(){"
    "var r=_rs.apply(this,arguments);report();return r;"
    "};"
    "addEventListener('popstate',report);"
    "addEventListener('hashchange',report);"
    "addEventListener('message',function(e){"
    "var d=e&&e.data;"
    "if(!d||d.type!=='everflow-preview-history')return;"
    "if(d.delta===-1)history.back();"
    "else if(d.delta===1)history.forward();"
    "});"
    "report();"
    "})();"
    "</script>"
)


def should_rewrite_vite_client(
    *,
    guest_port: int,
    path: str,
    status_code: int = 200,
) -> bool:
    """True when this response is a Vite dev client module (Preview tab only)."""
    if guest_port == DESKTOP_NOVNC_PORT:
        return False
    if status_code < 200 or status_code >= 300:
        return False
    path_l = (path or "").lstrip("/")
    return (
        path_l.endswith("@vite/client")
        or path_l == "@vite/client"
        or "/@vite/client" in f"/{path_l}"
        or "vite/dist/client" in path_l
    )


def should_inject_preview_html(
    *,
    guest_port: int,
    path: str,
    content_type: str = "",
    status_code: int = 200,
) -> bool:
    """True when HTML should get WS/nav patches (Preview tab only, not errors)."""
    if guest_port == DESKTOP_NOVNC_PORT:
        return False
    if status_code < 200 or status_code >= 300:
        return False
    media_l = (content_type or "").lower()
    if "application/json" in media_l:
        return False
    if "text/html" in media_l:
        return True
    path_l = (path or "").lstrip("/")
    return path_l == "" or path_l.endswith(".html")


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
    inject = ""
    if "data-everflow-ws-patch" not in text:
        inject += _WS_PATCH_SCRIPT
    if "data-everflow-nav-bridge" not in text:
        inject += _NAV_BRIDGE_SCRIPT
    if not inject:
        return content
    lower = text.lower()
    idx = lower.find("<head>")
    if idx >= 0:
        insert_at = idx + len("<head>")
        text = text[:insert_at] + inject + text[insert_at:]
        return text.encode("utf-8")
    return (inject + text).encode("utf-8")


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
