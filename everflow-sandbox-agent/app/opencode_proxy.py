"""HTTP reverse proxy helpers for OpenCode server (including SSE)."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

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


def _filter_request_headers(headers: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP or lk == "authorization":
            # Drop agent Authorization — OpenCode uses its own auth if configured
            continue
        out[k] = v
    return out


def _filter_response_headers(
    headers: httpx.Headers,
    *,
    strip_encoding: bool = False,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP:
            continue
        # When we fully buffer/decode the body, drop encoding/length so clients
        # do not try to decompress again.
        if strip_encoding and lk in ("content-encoding", "content-length"):
            continue
        out[k] = v
    return out


async def proxy_to_opencode(
    request: Request,
    *,
    base_url: str,
    path: str,
    timeout: float | None = None,
) -> Response:
    """Forward request to OpenCode and return a FastAPI Response (streaming when needed)."""
    # path may be empty or start without leading slash
    rel = path.lstrip("/")
    url = urljoin(base_url.rstrip("/") + "/", rel)
    if request.url.query:
        url = f"{url}?{request.url.query}"

    method = request.method.upper()
    body = await request.body()
    headers = _filter_request_headers(request.headers)

    # Long timeout for SSE / long prompts; None → no read timeout
    if timeout is None:
        read_timeout = None if _wants_stream(request, path) else 300.0
    else:
        read_timeout = timeout

    client_timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=30.0, pool=10.0)

    client = httpx.AsyncClient(timeout=client_timeout, follow_redirects=False)
    req = client.build_request(method, url, headers=headers, content=body if body else None)

    try:
        upstream = await client.send(req, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        logger.warning("opencode proxy error url=%s: %s", url, exc)
        return Response(
            content=f'{{"detail":"OpenCode unreachable: {exc}"}}',
            status_code=502,
            media_type="application/json",
        )

    media = upstream.headers.get("content-type", "")
    is_sse = "text/event-stream" in media or path.rstrip("/").endswith("/event")

    if is_sse or _wants_stream(request, path):

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

    # Buffer non-streaming responses (decoded body via httpx)
    try:
        content = await upstream.aread()
    finally:
        await upstream.aclose()
        await client.aclose()

    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=_filter_response_headers(upstream.headers, strip_encoding=True),
        media_type=media or None,
    )


def _wants_stream(request: Request, path: str) -> bool:
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept:
        return True
    p = path.rstrip("/")
    return p.endswith("/event") or p.endswith("/global/event")


async def proxy_to_opencode_guest(
    request: Request,
    *,
    exec_fn: ExecFn,
    sandbox_name: str,
    path: str,
    port: int = 4096,
    cwd: str = "/workspace",
    stream_exec_fn: Any | None = None,
) -> Response:
    """
    Proxy HTTP to OpenCode listening on 127.0.0.1 inside the guest microVM.

    REST: python3 urllib via sandbox exec (buffered).
    SSE (/event): stream_exec curl -N so message.part deltas reach the browser.
    """
    rel = path.lstrip("/")
    url = f"http://127.0.0.1:{port}/{rel}" if rel else f"http://127.0.0.1:{port}/"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    method = request.method.upper()
    body = await request.body()

    # Real guest SSE stream — required for token streaming in the UI
    if _wants_stream(request, path) or rel.rstrip("/").endswith("event"):
        if stream_exec_fn is None:
            return Response(
                content='{"detail":"Guest SSE stream_exec not available"}',
                status_code=501,
                media_type="application/json",
            )

        async def sse() -> AsyncIterator[bytes]:
            # Announce bridge so UI knows stream is live
            yield b'data: {"type":"server.connected","properties":{"mode":"guest-sse"}}\n\n'
            try:
                # Prefer curl for low-latency SSE; fall back to python urllib reader
                args_curl = [
                    "-sN",
                    "--no-buffer",
                    "-H",
                    "Accept: text/event-stream",
                    url,
                ]
                try:
                    async for chunk in stream_exec_fn(
                        sandbox_name,
                        "curl",
                        args_curl,
                        cwd=cwd,
                        env=None,
                    ):
                        if chunk:
                            yield chunk
                    return
                except Exception as curl_exc:  # noqa: BLE001
                    logger.warning("guest SSE curl stream failed: %s — trying python", curl_exc)

                # Python fallback: line-buffer SSE from OpenCode
                py = (
                    "import sys,urllib.request\n"
                    f"req=urllib.request.Request({url!r},headers={{'Accept':'text/event-stream'}})\n"
                    "with urllib.request.urlopen(req,timeout=None) as r:\n"
                    "  while True:\n"
                    "    line=r.readline()\n"
                    "    if not line: break\n"
                    "    sys.stdout.buffer.write(line); sys.stdout.buffer.flush()\n"
                )
                async for chunk in stream_exec_fn(
                    sandbox_name,
                    "python3",
                    ["-u", "-c", py],
                    cwd=cwd,
                    env=None,
                ):
                    if chunk:
                        yield chunk
            except Exception as exc:  # noqa: BLE001
                logger.exception("guest SSE stream failed name=%s", sandbox_name)
                err = json.dumps({"type": "server.error", "properties": {"message": str(exc)}})
                yield f"data: {err}\n\n".encode()

        return StreamingResponse(
            sse(),
            status_code=200,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    body_b64 = base64.b64encode(body).decode("ascii") if body else ""
    # Keep script compact; print single JSON line with status + body
    script = (
        "import base64,json,urllib.error,urllib.request\n"
        f"url={url!r}\n"
        f"method={method!r}\n"
        f"raw=base64.b64decode({body_b64!r}) if {bool(body)!r} else None\n"
        "req=urllib.request.Request(url,data=raw,method=method)\n"
        "if raw is not None:\n"
        "  req.add_header('Content-Type','application/json')\n"
        "req.add_header('Accept','application/json, */*')\n"
        "try:\n"
        "  with urllib.request.urlopen(req,timeout=180) as r:\n"
        "    data=r.read(); status=getattr(r,'status',200) or 200; ctype=r.headers.get('Content-Type') or ''\n"
        "except urllib.error.HTTPError as e:\n"
        "  data=e.read(); status=e.code; ctype=e.headers.get('Content-Type') if e.headers else ''\n"
        "except Exception as e:\n"
        "  data=json.dumps({'detail':str(e)}).encode(); status=502; ctype='application/json'\n"
        "print(json.dumps({'status':int(status),'ctype':ctype or '','body_b64':base64.b64encode(data).decode()}))\n"
    )

    try:
        code, stdout, stderr = await exec_fn(
            sandbox_name,
            "python3",
            ["-c", script],
            cwd=cwd,
            env=None,
            timeout_seconds=200,
        )
    except KeyError:
        return Response(
            content='{"detail":"Sandbox not found"}',
            status_code=404,
            media_type="application/json",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest opencode proxy exec failed name=%s: %s", sandbox_name, exc)
        return Response(
            content=json.dumps({"detail": f"Guest OpenCode proxy failed: {exc}"}),
            status_code=502,
            media_type="application/json",
        )

    if code != 0 and not stdout.strip():
        logger.warning(
            "guest opencode proxy bad exit name=%s code=%s stderr=%s",
            sandbox_name,
            code,
            (stderr or "")[:400],
        )
        return Response(
            content=json.dumps(
                {
                    "detail": "Guest OpenCode proxy failed",
                    "exit_code": code,
                    "stderr": (stderr or "")[:500],
                }
            ),
            status_code=502,
            media_type="application/json",
        )

    line = (stdout or "").strip().splitlines()[-1] if stdout.strip() else ""
    try:
        payload = json.loads(line)
        status = int(payload.get("status") or 502)
        ctype = str(payload.get("ctype") or "application/json")
        content = base64.b64decode(payload.get("body_b64") or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("guest opencode proxy parse failed: %s out=%s", exc, (stdout or "")[:300])
        return Response(
            content=json.dumps(
                {"detail": "Invalid guest proxy response", "raw": (stdout or "")[:500]}
            ),
            status_code=502,
            media_type="application/json",
        )

    return Response(content=content, status_code=status, media_type=ctype or None)
