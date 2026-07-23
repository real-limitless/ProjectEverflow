"""HTTP tool URL rendering, SSRF guard, and outbound execution."""

from __future__ import annotations

import ipaddress
import socket
import time
from string import Formatter
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.config import Settings, get_settings

# Always blocked (cloud metadata / link-local hosts), even when sandbox-internal is allowed.
_ALWAYS_BLOCKED_HOSTS = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "metadata",
        "kubernetes.default",
        "kubernetes.default.svc",
    }
)

_MAX_BODY_BYTES = 64 * 1024


class HttpToolSsrfError(ValueError):
    """Raised when a URL fails the SSRF guard."""


def render_url_template(template: str, path_params: dict[str, str] | None = None) -> str:
    """Replace ``{name}`` placeholders; unknown keys left as-is raise KeyError via format_map."""
    params = {str(k): str(v) for k, v in (path_params or {}).items()}
    # Only substitute named fields present in the template.
    names = {
        fn
        for _, fn, _, _ in Formatter().parse(template)
        if fn is not None and fn != ""
    }
    missing = names - set(params)
    if missing:
        raise ValueError(f"Missing path_params for template fields: {sorted(missing)}")
    return template.format(**{k: params[k] for k in names}) if names else template


def _host_is_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return None


def _ip_blocked(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_sandbox_internal: bool,
) -> str | None:
    """Return a reason string if blocked, else None."""
    # Link-local + metadata always blocked (AWS/GCP/Azure IMDS lives in 169.254.169.254).
    if ip.is_link_local:
        return "link-local addresses are not allowed"
    if ip == ipaddress.ip_address("169.254.169.254"):
        return "cloud metadata addresses are not allowed"
    # IPv6 unique-local / site-local treated as private unless sandbox-internal allowed
    if ip.is_multicast or ip.is_unspecified:
        return "multicast/unspecified addresses are not allowed"
    if ip.version == 6 and getattr(ip, "is_site_local", False):
        if not allow_sandbox_internal:
            return "site-local addresses are not allowed"
    if ip.is_loopback:
        if not allow_sandbox_internal:
            return "localhost/loopback is not allowed"
        return None
    if ip.is_private:
        if not allow_sandbox_internal:
            return "private IP addresses are not allowed"
        return None
    if ip.is_reserved:
        return "reserved addresses are not allowed"
    return None


def assert_url_safe(url: str, *, settings: Settings | None = None) -> str:
    """Validate URL scheme/host and resolve DNS; raise HttpToolSsrfError if unsafe.

    Returns the normalized URL string.
    """
    settings = settings or get_settings()
    allow_internal = bool(settings.http_tools_allow_sandbox_internal)

    raw = (url or "").strip()
    if not raw:
        raise HttpToolSsrfError("URL is empty")

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise HttpToolSsrfError("Only http and https URLs are allowed")
    if not parsed.hostname:
        raise HttpToolSsrfError("URL must include a hostname")
    if parsed.username or parsed.password:
        raise HttpToolSsrfError("URLs with embedded credentials are not allowed")

    host = parsed.hostname.lower()
    if host in _ALWAYS_BLOCKED_HOSTS or host.endswith(".metadata.google.internal"):
        raise HttpToolSsrfError("metadata hostnames are not allowed")

    as_ip = _host_is_ip(host)
    if as_ip is not None:
        reason = _ip_blocked(as_ip, allow_sandbox_internal=allow_internal)
        if reason:
            raise HttpToolSsrfError(reason)
        return raw

    # DNS resolve all A/AAAA — block if any address is unsafe (rebinding defense).
    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HttpToolSsrfError(f"Unable to resolve host: {host}") from exc

    if not infos:
        raise HttpToolSsrfError(f"Unable to resolve host: {host}")

    seen: set[str] = set()
    for info in infos:
        addr = info[4][0]
        if addr in seen:
            continue
        seen.add(addr)
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        reason = _ip_blocked(ip, allow_sandbox_internal=allow_internal)
        if reason:
            raise HttpToolSsrfError(f"{reason} (resolved {addr} for {host})")

    return raw


def merge_query(url: str, query: dict[str, str] | None) -> str:
    if not query:
        return url
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    existing.update({str(k): str(v) for k, v in query.items()})
    return urlunparse(parsed._replace(query=urlencode(existing)))


async def execute_http_tool(
    *,
    method: str,
    url_template: str,
    path_params: dict[str, str] | None = None,
    query: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    body: Any | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Render template, SSRF-check, and perform the HTTP request."""
    settings = settings or get_settings()
    method_u = method.strip().upper()
    try:
        rendered = render_url_template(url_template, path_params)
    except ValueError as exc:
        return {
            "ok": False,
            "status_code": None,
            "url": url_template,
            "method": method_u,
            "headers": {},
            "body": "",
            "truncated": False,
            "error": str(exc),
            "elapsed_ms": 0,
        }

    url = merge_query(rendered, query)
    try:
        assert_url_safe(url, settings=settings)
    except HttpToolSsrfError as exc:
        return {
            "ok": False,
            "status_code": None,
            "url": url,
            "method": method_u,
            "headers": {},
            "body": "",
            "truncated": False,
            "error": f"SSRF blocked: {exc}",
            "elapsed_ms": 0,
        }

    # Strip hop-by-hop / sensitive request headers callers might inject
    safe_headers: dict[str, str] = {}
    for k, v in (headers or {}).items():
        key = str(k).strip()
        if not key:
            continue
        low = key.lower()
        if low in {"host", "content-length", "connection", "transfer-encoding"}:
            continue
        safe_headers[key] = str(v)

    timeout = float(settings.http_tools_request_timeout_seconds)
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            req_kwargs: dict[str, Any] = {
                "method": method_u,
                "url": url,
                "headers": safe_headers or None,
            }
            if body is not None and method_u not in {"GET", "HEAD"}:
                if isinstance(body, (dict, list)):
                    req_kwargs["json"] = body
                else:
                    req_kwargs["content"] = str(body).encode("utf-8")
            res = await client.request(**req_kwargs)
    except httpx.HTTPError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status_code": None,
            "url": url,
            "method": method_u,
            "headers": {},
            "body": "",
            "truncated": False,
            "error": f"HTTP error: {exc}",
            "elapsed_ms": elapsed,
        }

    elapsed = int((time.perf_counter() - started) * 1000)
    raw = res.content or b""
    truncated = len(raw) > _MAX_BODY_BYTES
    snippet = raw[:_MAX_BODY_BYTES]
    try:
        text = snippet.decode("utf-8")
    except UnicodeDecodeError:
        text = snippet.decode("utf-8", errors="replace")

    out_headers = {k: v for k, v in list(res.headers.items())[:40]}
    return {
        "ok": 200 <= res.status_code < 400,
        "status_code": res.status_code,
        "url": url,
        "method": method_u,
        "headers": out_headers,
        "body": text,
        "truncated": truncated,
        "error": None if 200 <= res.status_code < 400 else f"HTTP {res.status_code}",
        "elapsed_ms": elapsed,
    }
