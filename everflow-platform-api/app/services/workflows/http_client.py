"""Shared HTTP client primitive for workflow nodes.

Used by ``n8n-nodes-base.httpRequest``, agent tools, and most declarative
app nodes. Centralises:

- Auth modes (none, header, bearer, basic, query, custom generic)
- Body formats (json / form / raw / binary)
- Response parsing (json / text / binary)
- Retries with backoff
- SSRF guard (reuses ``app.services.http_tools.assert_url_safe``)
- Dry-run mock via ``ctx.mocks['http']`` keyed by URL → canned response

Clean-room: no n8n source. Public n8n documentation parameter shapes only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

import httpx

from app.services.http_tools import HttpToolSsrfError, assert_url_safe

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode
    from app.services.workflows.items import ExecutionItem

logger = logging.getLogger(__name__)


AuthMode = Literal["none", "header", "bearer", "basic", "query", "custom", "genericCredential"]
BodyMode = Literal["none", "json", "form", "raw", "binary"]
ResponseMode = Literal["auto", "json", "text", "binary"]


@dataclass
class HttpRequestConfig:
    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    body_mode: BodyMode = "none"
    auth: AuthMode = "none"
    auth_credential: dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0
    response_mode: ResponseMode = "auto"
    binary_property: str = "data"
    json_property: str = "json"
    follow_redirects: bool = True
    verify_ssl: bool = True
    retries: int = 0  # 0 means use node.max_tries / 3 default
    backoff_seconds: float = 0.5


@dataclass
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    body: Any  # dict / str / bytes depending on response_mode
    url: str
    elapsed_ms: int


def _apply_auth(req: httpx.Request, cfg: HttpRequestConfig) -> None:
    cred = cfg.auth_credential or {}
    if cfg.auth == "header":
        # httpHeaderAuth — single named header
        name = cred.get("name") or cred.get("headerName") or "X-Api-Key"
        value = cred.get("value") or cred.get("apiKey") or cred.get("token") or ""
        if value:
            req.headers[name] = str(value)
    elif cfg.auth == "bearer":
        token = cred.get("token") or cred.get("accessToken") or cred.get("apiKey") or ""
        if token:
            req.headers["Authorization"] = f"Bearer {token}"
    elif cfg.auth == "basic":
        user = cred.get("user") or cred.get("username") or ""
        pw = cred.get("password") or cred.get("pass") or ""
        if user or pw:
            # httpx Basic auth is set via auth= param; we mimic by header here
            import base64

            raw = f"{user}:{pw}".encode("utf-8")
            req.headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    elif cfg.auth == "query":
        # query-string token (e.g. RapidAPI legacy)
        # url already contains the placeholders; we don't rewrite
        pass
    elif cfg.auth == "custom":
        # httpCustomAuth — raw header list
        raw_headers = cred.get("headers") or cred.get("header") or {}
        if isinstance(raw_headers, str):
            try:
                raw_headers = json.loads(raw_headers)
            except json.JSONDecodeError:
                raw_headers = {}
        if isinstance(raw_headers, dict):
            for k, v in raw_headers.items():
                req.headers[str(k)] = str(v)
    elif cfg.auth == "genericCredential":
        # Maps to known credential types via resolve_credential in caller
        pass


def _encode_body(cfg: HttpRequestConfig) -> dict[str, Any] | str | bytes | None:
    if cfg.body_mode == "none" or cfg.body is None:
        return None
    if cfg.body_mode == "json":
        return json.dumps(cfg.body, default=str)
    if cfg.body_mode == "form":
        if isinstance(cfg.body, dict):
            return cfg.body  # httpx handles form-encoded
        return str(cfg.body)
    if cfg.body_mode == "raw":
        return str(cfg.body)
    if cfg.body_mode == "binary":
        if isinstance(cfg.body, (bytes, bytearray)):
            return bytes(cfg.body)
        return str(cfg.body).encode("utf-8")
    return None


def _parse_response(resp: httpx.Response, cfg: HttpRequestConfig) -> Any:
    ctype = (resp.headers.get("content-type") or "").lower()
    if cfg.response_mode == "json" or (
        cfg.response_mode == "auto" and "application/json" in ctype
    ):
        try:
            return resp.json()
        except (json.JSONDecodeError, ValueError):
            return resp.text
    if cfg.response_mode == "binary":
        return resp.content
    return resp.text


def _maybe_mock(
    cfg: HttpRequestConfig,
    ctx: "EngineContext | None",
) -> HttpResponse | None:
    if ctx is None or not ctx.mocks:
        return None
    fake = ctx.mocks.get("http")
    if not isinstance(fake, dict):
        return None
    key = f"{cfg.method.upper()} {cfg.url}"
    canned = fake.get(key) or fake.get(cfg.url)
    if canned is None:
        return None
    if isinstance(canned, BaseException):
        raise canned
    if isinstance(canned, dict) and "status" in canned:
        return HttpResponse(
            status_code=int(canned.get("status") or 200),
            headers=dict(canned.get("headers") or {}),
            body=canned.get("body", ""),
            url=cfg.url,
            elapsed_ms=0,
        )
    return HttpResponse(
        status_code=200,
        headers={"content-type": "application/json" if isinstance(canned, (dict, list)) else "text/plain"},
        body=canned,
        url=cfg.url,
        elapsed_ms=0,
    )


async def execute_http_request(
    cfg: HttpRequestConfig,
    *,
    ctx: "EngineContext | None" = None,
) -> HttpResponse:
    """Run a single HTTP request with retries and SSRF guard.

    The SSRF guard is bypassed when ``ctx.mocks`` is supplying the response
    (so tests can use loopback fixture URLs).
    """
    if ctx is None or not ctx.mocks:
        try:
            assert_url_safe(cfg.url)
        except HttpToolSsrfError:
            if ctx is not None and ctx.mocks:
                # Allowed when mock-only mode
                pass
            else:
                raise

    mock = _maybe_mock(cfg, ctx)
    if mock is not None:
        return mock

    max_tries = max(1, cfg.retries or 3)
    backoff = max(0.05, cfg.backoff_seconds)
    last_exc: Exception | None = None

    for attempt in range(1, max_tries + 1):
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=cfg.timeout,
                follow_redirects=cfg.follow_redirects,
                verify=cfg.verify_ssl,
            ) as client:
                body = _encode_body(cfg)
                method = cfg.method.upper()
                req = client.build_request(
                    method,
                    cfg.url,
                    headers=cfg.headers or None,
                    content=body,
                )
                _apply_auth(req, cfg)
                resp = await client.send(req)
            elapsed = int((time.monotonic() - t0) * 1000)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_tries:
                logger.info(
                    "httpRequest retryable %s %s status=%s attempt=%s",
                    method,
                    cfg.url,
                    resp.status_code,
                    attempt,
                )
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                continue
            return HttpResponse(
                status_code=resp.status_code,
                headers={k: v for k, v in resp.headers.items()},
                body=_parse_response(resp, cfg),
                url=str(resp.url),
                elapsed_ms=elapsed,
            )
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            logger.info(
                "httpRequest transient %s %s attempt=%s exc=%s",
                cfg.method,
                cfg.url,
                attempt,
                exc,
            )
            if attempt < max_tries:
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                continue
            raise

    if last_exc:
        raise last_exc
    raise RuntimeError(f"httpRequest exhausted retries: {cfg.method} {cfg.url}")


# ── Parameter parsing helpers (n8n-shaped) ──────────────────────────


def _params_get(params: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in params and params[k] is not None:
            return params[k]
    return default


def build_config_from_node(
    node: "ExecNode",
    *,
    item: "ExecutionItem | None" = None,
    ctx: "EngineContext | None" = None,
) -> HttpRequestConfig:
    """Build a config from a node's parameters + a single input item.

    Supports the n8n httpRequest v1/v2/v3 shapes commonly found in
    templates. Falls back to plain ``requestOptions`` fields.
    """
    from app.services.workflows.expression import ExpressionContext, evaluate

    params = node.parameters or {}
    raw_url = _params_get(params, "url")
    if item is not None and ctx is not None and raw_url is not None:
        ectx = ExpressionContext(
            item=item,
            node_outputs=ctx.node_outputs,
            now=ctx.now,
        )
        url = str(evaluate(raw_url, ectx) or "")
    else:
        url = str(raw_url or "")

    method = str(_params_get(params, "method", "httpMethod", default="GET")).upper()

    headers: dict[str, str] = {}
    raw_headers = _params_get(params, "headers", "headerParameters")
    if isinstance(raw_headers, dict):
        params_list = raw_headers.get("parameters") or raw_headers.get("values") or []
        if isinstance(params_list, list):
            for p in params_list:
                if isinstance(p, dict):
                    name = str(p.get("name") or p.get("key") or "").strip()
                    val = str(p.get("value") or "")
                    if name:
                        headers[name] = val
    elif isinstance(raw_headers, list):
        for p in raw_headers:
            if isinstance(p, dict):
                name = str(p.get("name") or p.get("key") or "").strip()
                val = str(p.get("value") or "")
                if name:
                    headers[name] = val

    auth_mode = str(_params_get(params, "authentication", default="none")).lower()
    auth_cred: dict[str, Any] = {}
    if auth_mode in ("genericcredentialtype", "credential"):
        # cred type is in the node.credentials and resolved by caller
        pass

    send_body = bool(_params_get(params, "sendBody", "send body", default=False))
    body_mode: BodyMode = "none"
    body: Any = None
    if send_body:
        btype = str(_params_get(params, "bodyContentType", "specifyBody", default="json")).lower()
        if "json" in btype:
            body_mode = "json"
            body = _params_get(params, "jsonBody", "body", default={})
        elif "form" in btype:
            body_mode = "form"
            body = _params_get(params, "bodyParameters", default={})
        elif "binary" in btype:
            body_mode = "binary"
            body = item.binary.get("data") if item is not None and item.binary else None
        else:
            body_mode = "raw"
            body = _params_get(params, "body", default="")

    timeout = float(_params_get(params, "timeout", default=30) or 30) / 1000.0
    if timeout <= 0:
        timeout = 30.0

    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    response = str(options.get("response", {}) if isinstance(options.get("response"), dict) else {}).lower()
    if "response" in options and isinstance(options["response"], dict):
        rm = options["response"].get("responseMode")
        if rm:
            response = str(rm).lower()
    if "json" in response:
        response_mode: ResponseMode = "json"
    elif "binary" in response:
        response_mode = "binary"
    else:
        response_mode = "auto"

    return HttpRequestConfig(
        url=url,
        method=method,
        headers=headers,
        body=body,
        body_mode=body_mode,
        auth="none" if auth_mode in ("none", "", "genericcredentialtype") else "header",  # refined by caller
        auth_credential=auth_cred,
        timeout=timeout,
        response_mode=response_mode,
        retries=int(node.max_tries or 3),
    )


async def http_request(
    node: "ExecNode",
    item: "ExecutionItem",
    *,
    ctx: "EngineContext",
) -> HttpResponse:
    """Convenience: build config from a node + item and run the request."""
    cfg = build_config_from_node(node, item=item, ctx=ctx)
    # Resolve credentials if an auth type is set
    params = node.parameters or {}
    auth_type = str(params.get("authentication") or "none").lower()
    if auth_type and auth_type not in ("none", "genericcredentialtype"):
        # n8n stores the credential type name in the parameter "nodeCredentialType"
        # OR inside parameters.<authType>; resolve generically.
        cred_type = (
            params.get("nodeCredentialType")
            or auth_type
            or params.get("authType")
        )
        cred = ctx.resolve_credential(node, str(cred_type)) or {}
        cfg.auth_credential = dict(cred)
        # Map to the right auth mode
        if cred_type in ("httpHeaderAuth", "httpHeader"):
            cfg.auth = "header"
        elif cred_type in ("httpBearerAuth", "httpBearer"):
            cfg.auth = "bearer"
        elif cred_type in ("httpBasicAuth", "httpBasic"):
            cfg.auth = "basic"
        elif cred_type in ("httpQueryAuth",):
            cfg.auth = "query"
        elif cred_type in ("httpCustomAuth", "httpCustom"):
            cfg.auth = "custom"
        else:
            cfg.auth = "header"
    return await execute_http_request(cfg, ctx=ctx)


__all__ = [
    "HttpRequestConfig",
    "HttpResponse",
    "execute_http_request",
    "build_config_from_node",
    "http_request",
]
