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


_THIN_MIN_CHARS = 400
_SOFT_BLOCK_PHRASES = (
    "enable javascript",
    "enable js",
    "please enable cookies",
    "captcha",
    "access denied",
    "attention required",
    "checking your browser",
    "cf-browser-verification",
    "just a moment",
    "verify you are human",
    "bot detection",
    "cloudflare",
)


def is_thin_markdown(md: str) -> bool:
    """True when extracted text is too short or looks like a soft block page."""
    text = re.sub(r"\s+", " ", (md or "").strip()).lower()
    if len(text) < _THIN_MIN_CHARS:
        return True
    return any(p in text for p in _SOFT_BLOCK_PHRASES)


async def fetch_reader_content(url: str) -> dict[str, Any]:
    """Fetch URL via HTTP and return reader payload dict (method=http)."""
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

    # Non-HTML: escalate to browser/OCR rather than hard-fail in cascade callers
    if ctype and ctype not in ("text/html", "application/xhtml+xml", "text/plain") and not ctype.startswith("text/"):
        raise WebReadError(
            f"Unsupported content type for Reader ({ctype or 'unknown'}). "
            "Try browser extract or open the original URL.",
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
            "Could not extract readable text from this page. Try browser extract.",
            status_code=422,
        )

    return {
        "url": final_url,
        "title": title,
        "markdown": md,
        "content_type": ctype or "text/html",
        "method": "http",
        "warnings": [],
    }


def _payload_from_browser(data: dict[str, Any], *, method: str = "browser") -> dict[str, Any]:
    final_url = str(data.get("final_url") or data.get("url") or "").strip()
    title = str(data.get("title") or "").strip()
    text = str(data.get("text") or "").strip()
    html = str(data.get("html") or data.get("html_or_text") or "").strip()
    md = ""
    if html and ("<" in html and ">" in html):
        t2, md = html_to_reader_markdown(html, base_url=final_url or "")
        if not title and t2:
            title = t2
    if not md.strip() and text:
        md = text[:200_000]
    if not title:
        title = urlparse(final_url).hostname or final_url or "Page"
    if not final_url:
        final_url = str(data.get("url") or "")
    return {
        "url": final_url,
        "title": title,
        "markdown": md[:200_000],
        "content_type": "text/html",
        "method": method,
        "warnings": list(data.get("warnings") or []),
        "screenshot_b64": data.get("screenshot_b64"),
    }


async def _browser_read_via_sandbox(
    url: str,
    *,
    project: Any,
    settings: Any,
    include_screenshot: bool = False,
) -> dict[str, Any]:
    from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

    name = getattr(project, "sandbox_name", None)
    if not name:
        raise WebReadError(
            "Browser extract needs a project sandbox. Start the project sandbox first.",
            status_code=503,
        )
    if not getattr(settings, "sandbox_enabled", True):
        raise WebReadError("Sandbox is disabled on this deployment.", status_code=503)

    client = SandboxAgentClient(settings)
    try:
        data = await client.browser_read(
            name,
            url=url,
            include_screenshot=include_screenshot,
        )
    except SandboxAgentError as exc:
        msg = str(exc) or "Browser extract failed"
        code = 503 if (exc.status_code in (404, 409, 503) or "not provisioned" in msg.lower()) else 502
        raise WebReadError(msg, status_code=code) from exc
    if not isinstance(data, dict):
        raise WebReadError("Browser extract returned invalid payload", status_code=502)
    return data


async def fetch_reader_content_cascade(
    url: str,
    *,
    mode: str = "auto",
    max_ocr_pages: int = 3,
    project: Any = None,
    session: Any = None,
    principal: Any = None,
    settings: Any = None,
) -> dict[str, Any]:
    """HTTP → sandbox Playwright DOM → vision OCR cascade.

    ``mode``: auto | http | browser | ocr
    """
    mode_norm = (mode or "auto").strip().lower()
    if mode_norm not in ("auto", "http", "browser", "ocr"):
        mode_norm = "auto"

    warnings: list[str] = []
    http_payload: dict[str, Any] | None = None
    http_error: WebReadError | None = None

    if mode_norm in ("auto", "http"):
        try:
            http_payload = await fetch_reader_content(url)
        except WebReadError as exc:
            http_error = exc
            if mode_norm == "http":
                raise
            warnings.append(f"HTTP extract: {exc}")

        if http_payload and mode_norm == "http":
            return http_payload

        if http_payload and mode_norm == "auto" and not is_thin_markdown(http_payload.get("markdown") or ""):
            return http_payload

        if http_payload and is_thin_markdown(http_payload.get("markdown") or ""):
            warnings.append("HTTP extract looked thin or blocked; trying browser…")

    # Browser step
    browser_payload: dict[str, Any] | None = None
    browser_error: WebReadError | None = None
    need_browser = mode_norm in ("auto", "browser", "ocr")
    if need_browser and mode_norm != "http":
        want_shot = mode_norm == "ocr" or mode_norm == "auto"
        try:
            raw_browser = await _browser_read_via_sandbox(
                url,
                project=project,
                settings=settings,
                include_screenshot=want_shot,
            )
            browser_payload = _payload_from_browser(raw_browser, method="browser")
            browser_payload["warnings"] = warnings + list(browser_payload.get("warnings") or [])
        except WebReadError as exc:
            browser_error = exc
            warnings.append(f"Browser extract: {exc}")
            if mode_norm == "browser":
                raise

    if browser_payload and mode_norm == "browser":
        if not (browser_payload.get("markdown") or "").strip():
            raise WebReadError(
                "Browser extract returned no readable text.",
                status_code=422,
            )
        browser_payload["warnings"] = warnings
        browser_payload.pop("screenshot_b64", None)
        return browser_payload

    if (
        browser_payload
        and mode_norm == "auto"
        and not is_thin_markdown(browser_payload.get("markdown") or "")
    ):
        browser_payload["warnings"] = warnings
        browser_payload.pop("screenshot_b64", None)
        return browser_payload

    # OCR step
    need_ocr = mode_norm in ("auto", "ocr")
    if need_ocr:
        shot = None
        if browser_payload:
            shot = browser_payload.get("screenshot_b64")
        if not shot and project is not None and settings is not None:
            try:
                raw_browser = await _browser_read_via_sandbox(
                    url,
                    project=project,
                    settings=settings,
                    include_screenshot=True,
                )
                if not browser_payload:
                    browser_payload = _payload_from_browser(raw_browser, method="browser")
                shot = raw_browser.get("screenshot_b64")
            except WebReadError as exc:
                warnings.append(f"Browser screenshot: {exc}")
                if mode_norm == "ocr":
                    raise

        if shot and session is not None and principal is not None and settings is not None and project is not None:
            try:
                from app.services.web_ocr import ocr_screenshot_to_markdown

                title = (browser_payload or http_payload or {}).get("title") or ""
                final_url = (browser_payload or http_payload or {}).get("url") or url
                md = await ocr_screenshot_to_markdown(
                    session,
                    project_id=project.id,
                    user_id=principal.user.id,
                    settings=settings,
                    image_b64=str(shot),
                    page_url=str(final_url),
                    title=str(title),
                    max_pages=max_ocr_pages,
                )
                if md and md.strip():
                    return {
                        "url": final_url,
                        "title": title or urlparse(str(final_url)).hostname or "Page",
                        "markdown": md[:200_000],
                        "content_type": "text/html",
                        "method": "ocr",
                        "warnings": warnings + ["Used vision OCR on browser screenshot"],
                    }
                warnings.append("OCR returned empty text")
            except WebReadError as exc:
                warnings.append(f"OCR: {exc}")
                if mode_norm == "ocr":
                    raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("OCR cascade failed: %s", exc)
                warnings.append(f"OCR failed: {exc}")
                if mode_norm == "ocr":
                    raise WebReadError(f"OCR failed: {exc}", status_code=502) from exc
        elif mode_norm == "ocr":
            raise WebReadError(
                "OCR needs a running project sandbox (for screenshots) and an OCR-capable provider key.",
                status_code=503,
            )

    # Fallbacks: return best available thin content rather than hard fail in auto
    for candidate in (browser_payload, http_payload):
        if candidate and (candidate.get("markdown") or "").strip():
            candidate = {**candidate, "warnings": warnings}
            candidate.pop("screenshot_b64", None)
            return candidate

    if browser_error:
        raise browser_error
    if http_error:
        raise http_error
    raise WebReadError(
        "Could not extract readable text (HTTP, browser, and OCR all failed).",
        status_code=422,
    )
