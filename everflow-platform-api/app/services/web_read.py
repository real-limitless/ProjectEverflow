"""Fetch a public URL and extract readable article Markdown for knowledge Reader mode."""

from __future__ import annotations

import ipaddress
import logging
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

_MAX_BYTES = 2_500_000
_FETCH_TIMEOUT = 25.0
_USER_AGENT = (
    "Mozilla/5.0 (compatible; EverflowReader/1.0; +https://everflow.local) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
}


class WebReadError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _host_blocked(hostname: str) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host in _BLOCKED_HOSTS:
        return True
    if host.endswith(".localhost") or host.endswith(".local"):
        return True
    # Literal IPs
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_http_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw or len(raw) > 2048:
        raise WebReadError("Invalid URL")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise WebReadError("Only http(s) URLs are allowed")
    if not parsed.netloc or parsed.username or parsed.password:
        raise WebReadError("Invalid URL host")
    if _host_blocked(parsed.hostname or ""):
        raise WebReadError("URL host is not allowed")
    return raw


class _ArticleHTMLParser(HTMLParser):
    """Best-effort main-content extractor → Markdown (no external deps)."""

    SKIP_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "button",
        "template",
    }
    BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "main",
        "li",
        "tr",
        "blockquote",
        "pre",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "br",
        "hr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._parts: list[str] = []
        self._buf = ""
        self._in_pre = False
        self._list_depth = 0
        self._href: str | None = None
        self._heading: str | None = None
        self._prefer_main = False
        self._main_parts: list[str] = []
        self._main_depth = 0
        self._capturing_main = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        attr = {k.lower(): (v or "") for k, v in attrs}
        if t == "title":
            self._in_title = True
            return
        if self._skip_depth or t in self.SKIP_TAGS:
            if t in self.SKIP_TAGS:
                self._skip_depth += 1
            return

        role = attr.get("role", "").lower()
        classes = f" {attr.get('class', '').lower()} "
        is_main = (
            t in ("article", "main")
            or role == "main"
            or "article-body" in classes
            or "post-content" in classes
            or "entry-content" in classes
            or "story-body" in classes
        )
        if is_main and not self._capturing_main:
            self._flush()
            self._capturing_main = True
            self._main_depth = 1
            self._prefer_main = True
            return
        if self._capturing_main:
            self._main_depth += 1

        if t in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self._heading = t
        elif t == "br":
            self._buf += "\n"
        elif t == "hr":
            self._flush()
            self._emit("\n---\n")
        elif t == "li":
            self._flush()
            indent = "  " * max(0, self._list_depth - 1)
            self._buf += f"{indent}- "
        elif t in ("ul", "ol"):
            self._flush()
            self._list_depth += 1
        elif t == "pre" or t == "code":
            if t == "pre":
                self._flush()
                self._in_pre = True
                self._buf += "```\n"
        elif t == "a":
            href = attr.get("href") or ""
            if href and not href.startswith(("#", "javascript:")):
                # Keep preceding plain text outside the markdown link
                if self._buf and not self._heading:
                    self._emit_raw(self._buf)
                    self._buf = ""
                self._href = href
        elif t in self.BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "title":
            self._in_title = False
            return
        if self._skip_depth:
            if t in self.SKIP_TAGS:
                self._skip_depth = max(0, self._skip_depth - 1)
            return

        if self._capturing_main:
            self._main_depth -= 1
            if self._main_depth <= 0:
                self._flush()
                self._capturing_main = False
                return

        if t in ("h1", "h2", "h3", "h4", "h5", "h6") and self._heading:
            level = int(t[1])
            text = self._buf.strip()
            self._buf = ""
            if text:
                self._emit(f"\n{'#' * level} {text}\n")
            self._heading = None
        elif t == "a" and self._href is not None:
            text = self._buf.strip() or self._href
            href = self._href
            self._buf = ""
            self._href = None
            self._buf += f"[{text}]({href})"
        elif t == "pre":
            self._buf += "\n```\n"
            self._flush()
            self._in_pre = False
        elif t in ("ul", "ol"):
            self._flush()
            self._list_depth = max(0, self._list_depth - 1)
        elif t in ("p", "div", "section", "li", "blockquote", "tr"):
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        if self._in_pre:
            self._buf += data
            return
        text = re.sub(r"[ \t]+", " ", data)
        if text:
            self._buf += text

    def _emit_raw(self, chunk: str) -> None:
        if not chunk:
            return
        if self._capturing_main or self._prefer_main:
            if self._capturing_main:
                self._main_parts.append(chunk)
            return
        self._parts.append(chunk)

    def _emit(self, chunk: str) -> None:
        self._emit_raw(chunk)

    def _flush(self) -> None:
        text = self._buf.strip()
        self._buf = ""
        if not text:
            return
        if self._href is not None:
            # Unclosed link text
            text = f"[{text}]({self._href})"
            self._href = None
        self._emit(text + "\n\n")

    def markdown(self) -> str:
        self._flush()
        parts = self._main_parts if self._prefer_main and self._main_parts else self._parts
        md = "".join(parts)
        md = re.sub(r"\n{3,}", "\n\n", md).strip()
        return md


def html_to_reader_markdown(html: str, *, base_url: str = "") -> tuple[str, str]:
    """Return (title, markdown) from HTML."""
    parser = _ArticleHTMLParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("html parse failed: %s", exc)

    title = re.sub(r"\s+", " ", parser.title).strip()
    md = parser.markdown()

    # Rewrite relative links when possible
    if base_url and md:

        def _abs(match: re.Match[str]) -> str:
            label, href = match.group(1), match.group(2)
            if href.startswith(("http://", "https://", "mailto:", "#")):
                return match.group(0)
            return f"[{label}]({urljoin(base_url, href)})"

        md = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _abs, md)

    if not md:
        # Last resort: strip tags coarsely
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        md = text[:120_000]

    return title, md[:200_000]


async def fetch_reader_content(url: str) -> dict[str, Any]:
    """Fetch URL and return reader payload dict."""
    safe_url = validate_public_http_url(url)

    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            max_redirects=5,
        ) as client:
            resp = await client.get(safe_url)
    except httpx.RequestError as exc:
        raise WebReadError(f"Failed to fetch URL: {exc}", status_code=502) from exc

    final_url = str(resp.url)
    try:
        validate_public_http_url(final_url)
    except WebReadError as exc:
        raise WebReadError("Redirect target is not allowed", status_code=400) from exc

    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    raw = resp.content[: _MAX_BYTES + 1]
    if len(raw) > _MAX_BYTES:
        raise WebReadError("Page is too large to load in Reader", status_code=413)

    if resp.status_code >= 400:
        raise WebReadError(
            f"Upstream returned HTTP {resp.status_code}",
            status_code=502,
        )

    # Non-HTML: return a short note (PDF/images would need OCR elsewhere)
    if ctype and ctype not in ("text/html", "application/xhtml+xml", "text/plain") and not ctype.startswith("text/"):
        raise WebReadError(
            f"Unsupported content type for Reader ({ctype or 'unknown'}). "
            "Open the Website tab or original URL instead.",
            status_code=415,
        )

    try:
        text = raw.decode(resp.encoding or "utf-8", errors="replace")
    except Exception:
        text = raw.decode("utf-8", errors="replace")

    if ctype == "text/plain":
        title = urlparse(final_url).path.rsplit("/", 1)[-1] or final_url
        md = text.strip()[:200_000]
    else:
        title, md = html_to_reader_markdown(text, base_url=final_url)

    if not title:
        title = urlparse(final_url).hostname or final_url

    if not md.strip():
        raise WebReadError(
            "Could not extract readable text from this page. Try the Website tab.",
            status_code=422,
        )

    return {
        "url": final_url,
        "title": title,
        "markdown": md,
        "content_type": ctype or "text/html",
    }
