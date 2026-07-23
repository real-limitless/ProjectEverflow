"""Generic HTTP + WebSocket reverse proxy to a sandbox-local TCP port.

Host/mock mode dials http://127.0.0.1:{port}. Guest microVMs use a local
tunnel port (see guest_tunnel.py) so HTTP and WebSockets (Vite HMR) work.
Optional in-guest urllib remains as a last-resort HTTP-only fallback.

Vite HMR notes:
- Client connects with Sec-WebSocket-Protocol: vite-hmr (must be accepted/forwarded)
- Bundled @vite/client hardcodes directSocketHost to the guest address; we rewrite
  that so the browser stays on the preview host instead of 127.0.0.1:5173.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

# Desktop panel (noVNC / websockify) — never apply Preview HMR rewrites.
DESKTOP_NOVNC_PORT = 6080

ExecFn = Callable[..., Awaitable[tuple[int, str, str]]]

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

# Headers that would prevent framing the app in Everflow Preview.
FRAME_BLOCKERS = {
    "x-frame-options",
    "content-security-policy",
    "content-security-policy-report-only",
}


def resolve_upstream_base(port: int, *, host: str = "127.0.0.1") -> str:
    """Return base URL for a listening process reachable from the agent host."""
    if port < 1 or port > 65535:
        raise ValueError(f"invalid port: {port}")
    return f"http://{host}:{port}"


def should_rewrite_vite_client(
    *,
    guest_port: int | None,
    path: str,
    status_code: int = 200,
) -> bool:
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
    guest_port: int | None,
    path: str,
    content_type: str = "",
    status_code: int = 200,
) -> bool:
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
    """Point Vite HMR at the browser's current host (preview proxy), not guest loopback."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    if "directSocketHost" not in text and "setupWebSocket" not in text:
        return content
    # serverHost / directSocketHost are injected as the guest listen address
    text2 = re.sub(
        r'const serverHost = "[^"]*";',
        "const serverHost = importMetaUrl.host + \"/\";",
        text,
        count=1,
    )
    text2 = re.sub(
        r'const directSocketHost = "[^"]*";',
        "const directSocketHost = `${importMetaUrl.hostname}:${importMetaUrl.port}/`;",
        text2,
        count=1,
    )
    # Force hmrPort null so client uses location.port (preview public port)
    text2 = re.sub(
        r'const hmrPort = [^;]+;',
        "const hmrPort = null;",
        text2,
        count=1,
    )
    if text2 != text:
        logger.info("rewrote Vite client HMR hosts for preview proxy")
    return text2.encode("utf-8")


# Injected into HTML so any code that still opens ws://127.0.0.1:5173 is redirected
# to the preview public host (iframe origin). Covers cached clients & Vite fallbacks.
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
    "var w=p===undefined?new N(P(u)):new N(P(u),p);"
    "return w;"
    "}"
    "W.prototype=N.prototype;"
    "W.CONNECTING=N.CONNECTING;W.OPEN=N.OPEN;W.CLOSING=N.CLOSING;W.CLOSED=N.CLOSED;"
    "W.__efPatched=1;window.WebSocket=W;"
    "})();"
    "</script>"
)


def inject_ws_patch_html(content: bytes) -> bytes:
    """Inject WebSocket host rewrite into HTML documents."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    if "data-everflow-ws-patch" in text:
        return content
    lower = text.lower()
    # Prefer <head>
    idx = lower.find("<head>")
    if idx >= 0:
        insert_at = idx + len("<head>")
        text = text[:insert_at] + _WS_PATCH_SCRIPT + text[insert_at:]
        return text.encode("utf-8")
    idx = lower.find("<!doctype")
    if idx >= 0:
        # after first line
        nl = text.find("\n", idx)
        if nl > 0:
            text = text[: nl + 1] + _WS_PATCH_SCRIPT + "\n" + text[nl + 1 :]
            return text.encode("utf-8")
    text = _WS_PATCH_SCRIPT + text
    return text.encode("utf-8")


def preview_cache_headers(path: str, headers: dict[str, str]) -> dict[str, str]:
    """Prevent browsers from caching pre-rewrite Vite client / HTML."""
    out = dict(headers)
    pl = (path or "").lower()
    if (
        "@vite/client" in pl
        or pl.endswith(".html")
        or pl == ""
        or pl.endswith("/")
        or "vite/dist/client" in pl
    ):
        out["Cache-Control"] = "no-store, no-cache, must-revalidate"
        out["Pragma"] = "no-cache"
    return out


def ws_requested_subprotocol(websocket: WebSocket) -> str | None:
    """Pick a subprotocol to accept (prefer vite-hmr)."""
    subs = list(websocket.scope.get("subprotocols") or [])
    if "vite-hmr" in subs:
        return "vite-hmr"
    if subs:
        return str(subs[0])
    return None


def _filter_request_headers(headers: Any, *, upstream_host: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP or lk == "authorization":
            continue
        out[k] = v
    out["Host"] = upstream_host
    return out


def _filter_response_headers(
    headers: httpx.Headers | dict[str, str],
    *,
    strip_encoding: bool = False,
    strip_frame_blockers: bool = True,
) -> dict[str, str]:
    out: dict[str, str] = {}
    items = headers.items() if hasattr(headers, "items") else []
    for k, v in items:
        lk = k.lower()
        if lk in HOP_BY_HOP:
            continue
        if strip_frame_blockers and lk in FRAME_BLOCKERS:
            continue
        if strip_encoding and lk in ("content-encoding", "content-length"):
            continue
        out[k] = v
    return out


async def proxy_http_to_port(
    request: Request,
    *,
    port: int,
    path: str,
    host: str = "127.0.0.1",
    timeout: float | None = None,
    exec_fn: ExecFn | None = None,
    sandbox_name: str | None = None,
    host_header: str | None = None,
    guest_port: int | None = None,
) -> Response:
    """Forward an HTTP request to host:{port}/{path}, with optional guest exec fallback.

    host_header: value for the Host header sent upstream (defaults to host:port).
    For tunnels, pass the guest's 127.0.0.1:{guest_port} so Vite host checks pass.

    guest_port: sandbox listen port (6080, 5173, …). When set, used for HMR rewrite
    gating and clearer upstream error messages (dial port may be an ephemeral tunnel).
    """
    app_port = guest_port if guest_port is not None else port
    base = resolve_upstream_base(port, host=host)
    rel = path.lstrip("/") if path else ""
    url = urljoin(base.rstrip("/") + "/", rel) if rel else base.rstrip("/") + "/"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    method = request.method.upper()
    body = await request.body()
    upstream_host = host_header or f"{host}:{port}"
    headers = _filter_request_headers(request.headers, upstream_host=upstream_host)

    # Preserve forwarded info for apps that care
    headers.setdefault("X-Forwarded-Proto", request.url.scheme or "http")
    if request.headers.get("host"):
        headers.setdefault("X-Forwarded-Host", request.headers["host"])
    client_host = request.client.host if request.client else None
    if client_host:
        headers.setdefault("X-Forwarded-For", client_host)

    read_timeout = timeout if timeout is not None else 300.0
    # Short connect timeout so microVM guest fallback is snappy
    client_timeout = httpx.Timeout(connect=1.5, read=read_timeout, write=30.0, pool=10.0)
    client = httpx.AsyncClient(timeout=client_timeout, follow_redirects=False)
    req = client.build_request(method, url, headers=headers, content=body if body else None)

    try:
        upstream = await client.send(req, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        if exec_fn is not None and sandbox_name:
            logger.info(
                "dial failed app_port=%s dial_port=%s (%s); trying guest exec proxy name=%s",
                app_port,
                port,
                exc,
                sandbox_name,
            )
            return await proxy_http_via_guest_exec(
                request,
                exec_fn=exec_fn,
                sandbox_name=sandbox_name,
                port=app_port,
                path=path,
                body=body,
                method=method,
                guest_port=guest_port,
            )
        logger.warning(
            "preview proxy error dial_port=%s app_port=%s url=%s: %s",
            port,
            app_port,
            url,
            exc,
        )
        return Response(
            content=f'{{"detail":"Upstream unreachable on port {app_port}: {exc}"}}',
            status_code=502,
            media_type="application/json",
        )

    media = upstream.headers.get("content-type", "")
    is_stream = (
        "text/event-stream" in media
        or "application/octet-stream" in media
        or request.headers.get("accept", "").find("text/event-stream") >= 0
    )

    if is_stream:

        async def stream() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_raw():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        return StreamingResponse(
            stream(),
            status_code=upstream.status_code,
            headers=_filter_response_headers(upstream.headers),
            media_type=media or None,
        )

    try:
        content = await upstream.aread()
    finally:
        await upstream.aclose()
        await client.aclose()

    # Rewrite Vite client + inject HTML WebSocket patch for HMR through preview host
    path_l = (path or "").lstrip("/")
    if should_rewrite_vite_client(
        guest_port=guest_port,
        path=path_l,
        status_code=upstream.status_code,
    ):
        content = rewrite_vite_client_js(content)
    if should_inject_preview_html(
        guest_port=guest_port,
        path=path_l,
        content_type=media or "",
        status_code=upstream.status_code,
    ):
        content = inject_ws_patch_html(content)

    headers = _filter_response_headers(upstream.headers, strip_encoding=True)
    headers = {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("content-length", "content-encoding")
    }
    headers = preview_cache_headers(path_l, headers)

    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=headers,
        media_type=media or None,
    )


async def proxy_http_via_guest_exec(
    request: Request,
    *,
    exec_fn: ExecFn,
    sandbox_name: str,
    port: int,
    path: str,
    body: bytes,
    method: str,
    guest_port: int | None = None,
) -> Response:
    """One-shot HTTP proxy via in-guest python3 urllib (no WebSocket / SSE)."""
    rel = path.lstrip("/") if path else ""
    url = f"http://127.0.0.1:{port}/{rel}" if rel else f"http://127.0.0.1:{port}/"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    body_b64 = base64.b64encode(body).decode("ascii") if body else ""
    # Forward a small subset of request headers
    hdr_pairs: list[tuple[str, str]] = []
    for k, v in request.headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP or lk in ("authorization", "cookie", "host", "content-length"):
            continue
        if lk.startswith("x-forwarded"):
            continue
        hdr_pairs.append((k, v))

    script = (
        "import base64,json,urllib.error,urllib.request\n"
        f"url={url!r}\n"
        f"method={method!r}\n"
        f"raw=base64.b64decode({body_b64!r}) if {bool(body)!r} else None\n"
        f"headers={hdr_pairs!r}\n"
        "req=urllib.request.Request(url,data=raw,method=method)\n"
        "for hk,hv in headers:\n"
        "  try:\n"
        "    req.add_header(hk,hv)\n"
        "  except Exception:\n"
        "    pass\n"
        "if raw is not None and not any(h[0].lower()=='content-type' for h in headers):\n"
        "  req.add_header('Content-Type','application/octet-stream')\n"
        "try:\n"
        "  with urllib.request.urlopen(req,timeout=60) as r:\n"
        "    data=r.read(); status=getattr(r,'status',200) or 200\n"
        "    ctype=r.headers.get('Content-Type') or ''\n"
        "except urllib.error.HTTPError as e:\n"
        "  data=e.read(); status=e.code; ctype=(e.headers.get('Content-Type') if e.headers else '') or ''\n"
        "except Exception as e:\n"
        "  data=json.dumps({'detail':str(e)}).encode(); status=502; ctype='application/json'\n"
        "print(json.dumps({'status':int(status),'ctype':ctype or '','body_b64':base64.b64encode(data).decode()}))\n"
    )

    try:
        code, stdout, stderr = await exec_fn(
            sandbox_name,
            "python3",
            ["-c", script],
            cwd="/workspace",
            env=None,
            timeout_seconds=90,
        )
    except KeyError:
        return Response(
            content='{"detail":"Sandbox not found"}',
            status_code=404,
            media_type="application/json",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest preview proxy exec failed name=%s: %s", sandbox_name, exc)
        return Response(
            content=json.dumps({"detail": f"Guest proxy failed: {exc}"}),
            status_code=502,
            media_type="application/json",
        )

    if code != 0 and not (stdout or "").strip():
        return Response(
            content=json.dumps(
                {
                    "detail": "Guest proxy failed",
                    "exit_code": code,
                    "stderr": (stderr or "")[:500],
                }
            ),
            status_code=502,
            media_type="application/json",
        )

    line = (stdout or "").strip().splitlines()[-1] if (stdout or "").strip() else ""
    try:
        payload = json.loads(line)
        status = int(payload.get("status") or 502)
        ctype = str(payload.get("ctype") or "application/json")
        content = base64.b64decode(payload.get("body_b64") or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest preview proxy parse failed: %s out=%s", exc, (stdout or "")[:300])
        return Response(
            content=json.dumps({"detail": "Invalid guest proxy response", "raw": (stdout or "")[:500]}),
            status_code=502,
            media_type="application/json",
        )

    # Same Vite HMR rewrites as the host-dial path so WS targets the preview host
    # even when we could only fetch HTML/JS via guest-exec (WS still needs tunnel).
    app_port = guest_port if guest_port is not None else port
    path_l = (path or "").lstrip("/")
    if should_rewrite_vite_client(
        guest_port=app_port,
        path=path_l,
        status_code=status,
    ):
        content = rewrite_vite_client_js(content)
    if should_inject_preview_html(
        guest_port=app_port,
        path=path_l,
        content_type=ctype or "",
        status_code=status,
    ):
        content = inject_ws_patch_html(content)
    headers = preview_cache_headers(
        path_l,
        {"X-Everflow-Preview-Via": "guest-exec"},
    )

    return Response(
        content=content,
        status_code=status,
        media_type=ctype or None,
        headers=headers,
    )


async def _reject_websocket(websocket: WebSocket, code: int = 1011) -> None:
    """Reject or close a client WebSocket without leaving a half-open HMR socket."""
    try:
        if websocket.client_state == WebSocketState.CONNECTING:
            await websocket.close(code=code)
        elif websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=code)
    except Exception:
        pass


async def proxy_websocket_to_port(
    websocket: WebSocket,
    *,
    port: int,
    path: str,
    query: str = "",
    host: str = "127.0.0.1",
    guest_port: int | None = None,
) -> None:
    """Bridge browser WebSocket to ws://host:port/path (Vite HMR safe).

    Connects to upstream Vite first, then accepts the client — so failed dials
    reject cleanly instead of accepting then closing 1011.

    guest_port: original sandbox listen port for Host/Origin headers when
    ``port`` is a local tunnel port (not the app's real port).
    """
    sub = ws_requested_subprotocol(websocket)

    rel = path.lstrip("/") if path else ""
    qs = f"?{query}" if query else ""
    if rel:
        url = f"ws://{host}:{port}/{rel}{qs}"
    else:
        # Root path — Vite HMR uses ws://host/?token=...
        url = f"ws://{host}:{port}/{qs}" if qs else f"ws://{host}:{port}/"

    try:
        import websockets
        from websockets.exceptions import ConnectionClosed
    except ImportError:
        await _reject_websocket(websocket, 1011)
        return

    # Vite validates Host / Origin against the dev server port, not the tunnel port.
    app_port = guest_port if guest_port is not None else port
    extra_headers = {
        "Host": f"127.0.0.1:{app_port}",
        "Origin": f"http://127.0.0.1:{app_port}",
    }
    # Prefer client-requested protocol; default to vite-hmr for Vite HMR token URLs
    upstream_subs: list[str]
    if sub:
        upstream_subs = [sub]
    elif "token=" in (query or ""):
        upstream_subs = ["vite-hmr"]
    else:
        upstream_subs = []

    connect_kwargs: dict[str, Any] = {
        "open_timeout": 45,
        "max_size": 8 * 1024 * 1024,
        "additional_headers": extra_headers,
        "compression": None,
    }
    if upstream_subs:
        connect_kwargs["subprotocols"] = upstream_subs

    upstream = None
    try:
        upstream = await websockets.connect(url, **connect_kwargs)
    except TypeError:
        # Older websockets: no compression= kw
        connect_kwargs.pop("compression", None)
        try:
            upstream = await websockets.connect(url, **connect_kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("preview ws connect failed port=%s url=%s: %s", port, url, exc)
            await _reject_websocket(websocket, 1011)
            return
    except Exception as exc:  # noqa: BLE001
        # Retry without subprotocol for non-Vite apps
        if upstream_subs:
            try:
                connect_kwargs.pop("subprotocols", None)
                upstream = await websockets.connect(url, **connect_kwargs)
            except Exception as exc2:  # noqa: BLE001
                logger.warning(
                    "preview ws connect failed port=%s url=%s: %s / %s",
                    port,
                    url,
                    exc,
                    exc2,
                )
                await _reject_websocket(websocket, 1011)
                return
        else:
            logger.warning("preview ws connect failed port=%s url=%s: %s", port, url, exc)
            await _reject_websocket(websocket, 1011)
            return

    # Upstream ready — accept browser with vite-hmr (or requested) subprotocol
    if websocket.client_state == WebSocketState.CONNECTING:
        try:
            await websocket.accept(subprotocol=sub)
        except Exception as exc:  # noqa: BLE001
            logger.warning("preview ws accept failed port=%s: %s", port, exc)
            try:
                await upstream.close()
            except Exception:
                pass
            return

    stop = asyncio.Event()

    async def client_to_upstream() -> None:
        try:
            while not stop.is_set():
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if "text" in msg and msg["text"] is not None:
                    await upstream.send(msg["text"])
                elif "bytes" in msg and msg["bytes"] is not None:
                    await upstream.send(msg["bytes"])
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("preview ws client→up: %s", exc)
        finally:
            stop.set()

    async def upstream_to_client() -> None:
        try:
            async for message in upstream:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)
        except ConnectionClosed:
            pass
        except Exception as exc:  # noqa: BLE001
            logger.debug("preview ws up→client: %s", exc)
        finally:
            stop.set()

    t1 = asyncio.create_task(client_to_upstream())
    t2 = asyncio.create_task(upstream_to_client())
    await stop.wait()
    for t in (t1, t2):
        t.cancel()
    try:
        await upstream.close()
    except Exception:
        pass
    try:
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
    except Exception:
        pass
