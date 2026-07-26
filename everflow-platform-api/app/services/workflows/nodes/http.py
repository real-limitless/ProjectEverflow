"""``n8n-nodes-base.httpRequest`` clean-room executor.

Wraps the shared :mod:`app.services.workflows.http_client` and converts
each input item to a single output item shaped for downstream ``$json``
access. v1 covers the 80% ops used in templates: single GET/POST/PUT/
PATCH/DELETE with auth + headers + body.

Output item shape per item::

    {
        "statusCode": 200,
        "headers": {...},
        "body": <parsed body — dict/str/bytes>,
        "url": "...",
        "elapsedMs": 123,
        "request": {  # echo of what was sent
            "method": "GET",
            "url": "...",
            "headers": {...},
            "body": <echoed body>,
        },
    }

On non-2xx, the executor honors ``node.continue_on_fail``:

- True: attach an ``error`` field to the output and continue.
- False: raise a ``RuntimeError`` so the engine halts the run.

``node.retry_on_fail`` and ``node.max_tries`` are forwarded via the
``retries`` field of :class:`HttpRequestConfig` so the shared client
implements the retry/backoff loop.
"""

from __future__ import annotations

import html as _html
import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Any

import httpx

from app.services.http_tools import HttpToolSsrfError, assert_url_safe
from app.services.workflows.graph import ExecNode
from app.services.workflows.http_client import (
    HttpRequestConfig,
    HttpResponse,
    build_config_from_node,
    execute_http_request,
    http_request as _shared_http_request,
)
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext

logger = logging.getLogger(__name__)


def _resolve_credentials(
    node: ExecNode,
    cfg: HttpRequestConfig,
    ctx: "EngineContext | None",
) -> None:
    """Populate ``cfg.auth`` and ``cfg.auth_credential`` from the context.

    The shared :func:`build_config_from_node` parses ``authentication`` and
    shape; here we resolve the actual credential payload from
    ``ctx.credentials`` and map the n8n credential type to our internal
    auth mode (header / bearer / basic / query / custom).
    """
    if ctx is None:
        return
    params = node.parameters or {}
    auth_type = str(params.get("authentication") or "none").lower()
    if not auth_type or auth_type == "none":
        cfg.auth = "none"
        return

    cred_type = (
        params.get("nodeCredentialType")
        or params.get("authType")
        or auth_type
    )
    cred = ctx.resolve_credential(node, str(cred_type)) or {}
    if cred:
        cfg.auth_credential = dict(cred)
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


def _retries_for(node: ExecNode) -> int:
    """Map ``retry_on_fail`` + ``max_tries`` to the shared ``retries`` field.

    ``retries=1`` means one attempt; the shared client uses
    ``max(1, retries)`` as its loop bound. ``retry_on_fail=True`` with no
    explicit ``max_tries`` defaults to 3 tries.
    """
    if node.retry_on_fail and node.max_tries:
        return max(1, int(node.max_tries))
    if node.retry_on_fail:
        return 3
    return 1


def _effective_request_headers(cfg: HttpRequestConfig) -> dict[str, str]:
    """Echo the headers as they would have been sent on the wire.

    The shared client applies auth on top of ``cfg.headers`` at send time;
    the response object only carries response headers, so we recompute
    here for the request echo.
    """
    out = dict(cfg.headers or {})
    cred = cfg.auth_credential or {}
    if cfg.auth == "header":
        name = cred.get("name") or cred.get("headerName") or "X-Api-Key"
        value = cred.get("value") or cred.get("apiKey") or cred.get("token") or ""
        if value:
            out[name] = str(value)
    elif cfg.auth == "bearer":
        token = cred.get("token") or cred.get("accessToken") or cred.get("apiKey") or ""
        if token:
            out["Authorization"] = f"Bearer {token}"
    elif cfg.auth == "basic":
        user = cred.get("user") or cred.get("username") or ""
        pw = cred.get("password") or cred.get("pass") or ""
        if user or pw:
            import base64

            raw = f"{user}:{pw}".encode("utf-8")
            out["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    elif cfg.auth == "custom":
        raw_headers = cred.get("headers") or cred.get("header") or {}
        if isinstance(raw_headers, str):
            try:
                raw_headers = json.loads(raw_headers)
            except Exception:
                raw_headers = {}
        if isinstance(raw_headers, dict):
            for k, v in raw_headers.items():
                out[str(k)] = str(v)
    return out


def _build_output(
    item: ExecutionItem,
    response: HttpResponse,
    cfg: HttpRequestConfig,
    *,
    error: str | None = None,
) -> ExecutionItem:
    """Convert a single ``HttpResponse`` to an ``ExecutionItem`` JSON shape.

    Always echoes back the request fields so downstream ``$json`` access
    works (e.g. ``$json.statusCode``).
    """
    body_out: Any = response.body
    # Keep binary bodies as a marker (raw bytes cannot live in JSON)
    if isinstance(body_out, (bytes, bytearray)):
        body_out = {"_binary": True, "bytes": len(body_out)}

    out: dict[str, Any] = {
        "statusCode": response.status_code,
        "headers": dict(response.headers or {}),
        "body": body_out,
        "url": response.url,
        "elapsedMs": response.elapsed_ms,
        "request": {
            "method": cfg.method,
            "url": cfg.url,
            "headers": _effective_request_headers(cfg),
            "body": cfg.body if not isinstance(cfg.body, (bytes, bytearray)) else None,
        },
    }
    if error is not None:
        out["error"] = error

    ni = item.clone()
    ni.json = {**item.json, **out}
    return ni


async def exec_http_request(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """``n8n-nodes-base.httpRequest`` executor — one output per input item.

    See module docstring for the output item shape and error semantics.
    """
    out: list[ExecutionItem] = []
    for item in items:
        cfg: HttpRequestConfig = build_config_from_node(node, item=item, ctx=ctx)
        _resolve_credentials(node, cfg, ctx)
        cfg.retries = _retries_for(node)
        if not cfg.url:
            raise RuntimeError(
                f"httpRequest: missing URL on node {node.name!r} "
                "(set parameters.url)"
            )

        try:
            response: HttpResponse = await execute_http_request(cfg, ctx=ctx)
        except Exception as exc:
            # Network / SSRF / protocol errors — honor continue_on_fail
            if node.continue_on_fail:
                logger.warning(
                    "httpRequest %s %s failed: %s (continue_on_fail=True)",
                    cfg.method,
                    cfg.url,
                    exc,
                )
                ni = item.clone()
                ni.json = {
                    **item.json,
                    "statusCode": 0,
                    "error": str(exc),
                    "request": {
                        "method": cfg.method,
                        "url": cfg.url,
                        "headers": dict(cfg.headers or {}),
                        "body": cfg.body,
                    },
                }
                out.append(ni)
                continue
            raise

        error_field: str | None = None
        if response.status_code >= 400:
            error_field = (
                f"HTTP {response.status_code} on {cfg.method} {cfg.url}"
            )
            if not node.continue_on_fail:
                raise RuntimeError(error_field)
            logger.info(
                "httpRequest %s %s -> %s (continue_on_fail=True)",
                cfg.method,
                cfg.url,
                response.status_code,
            )
        else:
            logger.info(
                "httpRequest %s %s -> %s in %sms",
                cfg.method,
                cfg.url,
                response.status_code,
                response.elapsed_ms,
            )

        out.append(_build_output(item, response, cfg, error=error_field))

    return [(0, out)]


__all__ = [
    "exec_http_request",
    "exec_graphql",
    "exec_rss_feed_read",
    "_shared_http_request",
]


def _resolve_param_text(
    raw: Any,
    item: ExecutionItem,
    ctx: "EngineContext | None",
) -> Any:
    """Run n8n expression evaluation on a parameter value if a ctx is provided.

    Strings are evaluated so ``{{ $json.foo }}`` style templates work.
    Non-strings are passed through unchanged. Returns the evaluated value
    (string, number, dict, list) as-is so callers can serialize it.
    """
    if ctx is None or not isinstance(raw, str):
        return raw
    from app.services.workflows.expression import ExpressionContext, evaluate

    ectx = ExpressionContext(
        item=item,
        node_outputs=ctx.node_outputs,
        now=ctx.now,
    )
    return evaluate(raw, ectx)


def _graphql_variables(params: dict[str, Any]) -> Any:
    """Best-effort normalize the ``variables`` parameter to a dict or None.

    Accepts a dict (pass through) or a JSON string (parse). Returns None
    when missing, empty, or unparseable — matches the 80% template shape.
    """
    raw = params.get("variables")
    if raw is None or raw == "":
        return None
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return None
        if isinstance(parsed, dict):
            return parsed
        return None
    return None


async def exec_graphql(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """``n8n-nodes-base.graphql`` executor — POST a query per input item.

    Reads:

    - ``parameters.endpoint`` (URL; ``{{...}}`` expressions allowed)
    - ``parameters.query`` (GraphQL document; ``{{...}}`` allowed)
    - ``parameters.variables`` (dict, or JSON string of a dict, optional)

    Always uses ``Content-Type: application/json`` with body
    ``{"query": ..., "variables": ...}``. Auth reuses the same resolution
    path as ``httpRequest`` (header / bearer / basic / custom / query)
    via the shared HTTP client.

    Output item shape per input item::

        {
            "data": <response body["data"]>,
            "query": <echoed query>,
            "variables": <echoed variables dict or None>,
            "statusCode": 200,
            "headers": {...},
        }

    On non-2xx OR when the GraphQL body contains an ``errors`` field, an
    ``error`` key is attached. ``continue_on_fail`` is honored: when False
    and the response is non-2xx, the run is halted.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []

    for item in items:
        endpoint = str(
            _resolve_param_text(
                params.get("endpoint") or params.get("url") or "", item, ctx
            )
            or ""
        )
        if not endpoint:
            raise RuntimeError(
                f"graphql: missing endpoint on node {node.name!r} "
                "(set parameters.endpoint)"
            )

        query_raw = params.get("query")
        if query_raw is None or query_raw == "":
            raise RuntimeError(
                f"graphql: missing query on node {node.name!r} "
                "(set parameters.query)"
            )
        query = str(_resolve_param_text(query_raw, item, ctx) or "").strip()
        if not query:
            raise RuntimeError(
                f"graphql: query evaluated to empty string on node {node.name!r}"
            )

        variables = _graphql_variables(params)
        # Also support templated variables string
        if isinstance(params.get("variables"), str) and variables is None:
            # If templating left a non-JSON result, skip silently
            pass

        body: dict[str, Any] = {"query": query}
        if variables is not None:
            body["variables"] = variables

        cfg = HttpRequestConfig(
            url=endpoint,
            method="POST",
            body=body,
            body_mode="json",
            headers={"Content-Type": "application/json"},
            response_mode="json",
        )
        _resolve_credentials(node, cfg, ctx)
        cfg.retries = _retries_for(node)

        try:
            response: HttpResponse = await execute_http_request(cfg, ctx=ctx)
        except Exception as exc:
            if node.continue_on_fail:
                logger.warning(
                    "graphql %s failed: %s (continue_on_fail=True)",
                    endpoint,
                    exc,
                )
                ni = item.clone()
                ni.json = {
                    **item.json,
                    "data": None,
                    "query": query,
                    "variables": variables,
                    "statusCode": 0,
                    "error": str(exc),
                }
                out.append(ni)
                continue
            raise

        resp_body: Any = response.body
        if isinstance(resp_body, (bytes, bytearray)):
            try:
                resp_body = resp_body.decode("utf-8", errors="replace")
            except Exception:
                resp_body = ""
        if isinstance(resp_body, str):
            try:
                resp_body = json.loads(resp_body)
            except (json.JSONDecodeError, ValueError):
                resp_body = {}
        if not isinstance(resp_body, dict):
            resp_body = {}

        data = resp_body.get("data")
        graphql_errors = resp_body.get("errors")

        out_payload: dict[str, Any] = {
            "data": data,
            "query": query,
            "variables": variables,
            "statusCode": response.status_code,
            "headers": dict(response.headers or {}),
        }

        if response.status_code >= 400:
            err_text = f"HTTP {response.status_code} on POST {endpoint}"
            if not node.continue_on_fail:
                raise RuntimeError(err_text)
            out_payload["error"] = err_text
            logger.info(
                "graphql %s -> %s (continue_on_fail=True)",
                endpoint,
                response.status_code,
            )
        elif graphql_errors:
            # GraphQL returns 200 with errors[] for partial / full failures.
            # Always surface an ``error`` field so downstream nodes can branch
            # on $json.error, but do not halt the run.
            out_payload["error"] = (
                json.dumps(graphql_errors, default=str)
                if not isinstance(graphql_errors, str)
                else graphql_errors
            )
            logger.info(
                "graphql %s -> 200 with errors: %s",
                endpoint,
                graphql_errors,
            )
        else:
            logger.info(
                "graphql %s -> %s in %sms",
                endpoint,
                response.status_code,
                response.elapsed_ms,
            )

        ni = item.clone()
        ni.json = {**item.json, **out_payload}
        out.append(ni)

    return [(0, out)]


# ── RSS Feed Read ────────────────────────────────────────────────────

_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_DC_NS = "{http://purl.org/dc/elements/1.1/}"
_CONTENT_SNIPPET_LIMIT = 280

# Pre-compiled patterns for stripping HTML / whitespace from feed text.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_BLOCK_TAGS = frozenset(
    {"p", "br", "div", "li", "tr", "td", "h1", "h2", "h3", "h4", "h5", "h6"}
)


def _snippet(html_or_text: str, *, limit: int = _CONTENT_SNIPPET_LIMIT) -> str:
    """Return a plain-text snippet of at most ``limit`` chars.

    Strips HTML tags, decodes entities, collapses whitespace, and trims to
    ``limit``. Newlines between block-level elements are preserved as a
    single space so the result reads as one continuous snippet.
    """
    if not html_or_text:
        return ""
    # Drop <script> / <style> content entirely.
    cleaned = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>",
        " ",
        html_or_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = _html.unescape(cleaned)
    # Collapse runs of whitespace (incl. newlines) to single spaces.
    cleaned = _WS_RE.sub(" ", cleaned).strip()
    if len(cleaned) > limit:
        return cleaned[:limit]
    return cleaned


def _find_text(elem: ET.Element, *paths: str) -> str:
    """Look up the first matching child text across a list of element paths.

    Path syntax is a ``/``-separated list of tag names; namespaces are
    expanded via the standard Clark notation (e.g. ``{ns}tag``) so callers
    can use ``atom:summary`` style or fully-qualified forms interchangeably.
    """
    for path in paths:
        node = elem.find(path)
        if node is not None and node.text is not None:
            return node.text
    return ""


def _parse_rss_item(item: ET.Element) -> dict[str, str]:
    """Return the cleaned fields for one RSS 2.0 ``<item>``."""
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()
    pub_date = (item.findtext("pubDate") or "").strip()
    # Dublin Core ``dc:creator`` is the canonical creator; n8n also accepts
    # bare ``author`` and ``creator`` elements.
    creator = (
        item.findtext(f"{_DC_NS}creator")
        or item.findtext("creator")
        or item.findtext("author")
        or ""
    ).strip()
    description = item.findtext("description") or ""
    return {
        "title": title,
        "link": link,
        "pubDate": pub_date,
        "contentSnippet": _snippet(description),
        "creator": creator,
    }


def _parse_rss(root: ET.Element) -> tuple[str, list[dict[str, str]]]:
    """Parse an RSS 2.0 document and return ``(channel_title, items)``."""
    channel = root.find("channel")
    if channel is None:
        # RSS 1.0 / RDF: items live directly under the root.
        feed_title = (root.findtext(f"{_DC_NS}title") or "").strip()
        items = [_parse_rss_item(it) for it in root.findall(".//item")]
        return feed_title, items
    feed_title = (channel.findtext("title") or "").strip()
    items = [_parse_rss_item(it) for it in channel.findall("item")]
    return feed_title, items


def _parse_atom_entry(entry: ET.Element) -> dict[str, str]:
    """Return the cleaned fields for one Atom ``<entry>``."""
    title = (entry.findtext(f"{_ATOM_NS}title") or "").strip()
    # Prefer rel="alternate"; fall back to the first link with no rel.
    link = ""
    for link_el in entry.findall(f"{_ATOM_NS}link"):
        rel = link_el.get("rel") or "alternate"
        href = link_el.get("href") or ""
        if rel == "alternate" and href:
            link = href
            break
        if not link and href:
            link = href
    pub_date = (
        entry.findtext(f"{_ATOM_NS}published")
        or entry.findtext(f"{_ATOM_NS}updated")
        or ""
    ).strip()
    author_name = entry.findtext(f"{_ATOM_NS}author/{_ATOM_NS}name") or ""
    summary = (
        entry.findtext(f"{_ATOM_NS}summary")
        or entry.findtext(f"{_ATOM_NS}content")
        or ""
    )
    return {
        "title": title,
        "link": link,
        "published": pub_date,
        "contentSnippet": _snippet(summary),
        "author": author_name.strip(),
    }


def _parse_atom(root: ET.Element) -> tuple[str, list[dict[str, str]]]:
    """Parse an Atom document and return ``(feed_title, entries)``."""
    feed_title = (root.findtext(f"{_ATOM_NS}title") or "").strip()
    items = [_parse_atom_entry(e) for e in root.findall(f"{_ATOM_NS}entry")]
    return feed_title, items


def _parse_feed(xml_text: str) -> tuple[str, list[dict[str, str]]]:
    """Detect the format and parse an RSS / Atom XML document.

    Returns ``(feed_title, items)`` where ``items`` is a list of dicts
    shaped per the per-format field names (``pubDate`` / ``creator`` for
    RSS, ``published`` / ``author`` for Atom).
    """
    if not isinstance(xml_text, str) or not xml_text.strip():
        raise ValueError("rssFeedRead: empty feed body")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"rssFeedRead: feed is not valid XML: {exc}") from exc
    tag = root.tag.lower()
    if tag == f"{_ATOM_NS.lower()}feed" or tag == "feed":
        return _parse_atom(root)
    if tag == "rss" or tag == f"{_DC_NS.lower()}rdf":
        return _parse_rss(root)
    # Some feeds use a namespaced root like <rdf:RDF xmlns:rdf=…> — try
    # matching the bare local name as a last resort.
    if tag.endswith("}rdf") or tag == "rdf":
        return _parse_rss(root)
    if tag.endswith("}feed"):
        return _parse_atom(root)
    raise ValueError(
        f"rssFeedRead: unsupported feed root element {root.tag!r}; "
        "expected RSS <rss> or Atom <feed>"
    )


def _lookup_mock(
    ctx: "EngineContext | None", url: str
) -> tuple[str | None, int | None]:
    """Return ``(body, status)`` from ``ctx.mocks['rss']`` or ``(None, None)``.

    Mock entries may be:

    - a plain string — treated as the raw feed body with status 200
    - a dict with ``status`` and ``body`` keys (or ``content`` as an
      alias for ``body``)
    """
    if ctx is None or not ctx.mocks:
        return None, None
    rss = ctx.mocks.get("rss")
    if not isinstance(rss, dict):
        return None, None
    canned = rss.get(url)
    if canned is None:
        return None, None
    if isinstance(canned, str):
        return canned, 200
    if isinstance(canned, dict):
        body = canned.get("body") or canned.get("content") or ""
        status = int(canned.get("status") or 200)
        return str(body), status
    return str(canned), 200


def _resolve_url(
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    node_name: str = "",
) -> str:
    """Read ``parameters.url`` (or ``feedUrl``) and evaluate any expression."""
    from app.services.workflows.expression import ExpressionContext, evaluate

    raw = params.get("url") or params.get("feedUrl") or ""
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError(
            f"rssFeedRead: missing url on node {node_name!r} "
            "(set parameters.url)"
        )
    ectx = ExpressionContext(
        item=item, node_outputs=ctx.node_outputs, now=ctx.now
    )
    evaluated = evaluate(raw, ectx)
    url = str(evaluated or "").strip()
    if not url:
        raise RuntimeError(
            f"rssFeedRead: evaluated url is empty on node {node_name!r}"
        )
    return url


async def _fetch_feed_body(
    url: str, ctx: "EngineContext", timeout: float = 30.0
) -> str:
    """Fetch the feed body, applying the SSRF guard unless mocking is active."""
    if ctx is None or not ctx.mocks:
        # The SSRF guard is bypassed when mocks are supplying responses, so
        # tests can use loopback URLs against fixture servers.
        assert_url_safe(url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"})
        if resp.status_code >= 400:
            raise RuntimeError(
                f"rssFeedRead: HTTP {resp.status_code} fetching {url}"
            )
        return resp.text


async def exec_rss_feed_read(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """``n8n-nodes-base.rssFeedRead`` executor — fetch an RSS / Atom feed.

    ``parameters`` shape (clean-room n8n rssFeedRead v1):

    .. code-block:: json

        {
          "url": "https://example.com/feed.xml"
        }

    Behavior:

    - Reads ``parameters.url`` (string or ``{{...}}`` expression).
    - Looks up ``ctx.mocks['rss'][url]`` first; falls back to a real GET
      via :mod:`httpx`. The :func:`assert_url_safe` SSRF guard is applied
      unless mocks are supplying the response.
    - Parses RSS 2.0 (``<rss><channel><item>``) and Atom
      (``<feed xmlns=…><entry>``) via the stdlib
      :mod:`xml.etree.ElementTree`.
    - Emits one output item per feed entry. Each item's JSON contains:

      - RSS: ``title``, ``link``, ``pubDate``, ``contentSnippet``,
        ``creator``
      - Atom: ``title``, ``link``, ``published``, ``contentSnippet``,
        ``author``

      ``contentSnippet`` is the description (RSS) or summary/content
      (Atom) stripped of HTML and clipped to 280 chars.

    - Per input item, the executor issues one fetch. When ``items`` is
      empty (e.g. wired straight to a trigger), a single synthetic item
      drives the fetch so the node produces a result.
    - Network / parse errors raise unless ``node.continue_on_fail`` is
      set, in which case a single item with an ``error`` field is
      emitted.
    """
    params = node.parameters or {}

    effective_items: list[ExecutionItem] = items or [ExecutionItem(json={})]
    out: list[ExecutionItem] = []
    for item in effective_items:
        url = _resolve_url(params, item, ctx, node_name=node.name)

        body: str | None = None
        try:
            body, _status = _lookup_mock(ctx, url)
            if body is None:
                body = await _fetch_feed_body(url, ctx)
        except (HttpToolSsrfError, RuntimeError) as exc:
            if not node.continue_on_fail:
                raise
            ni = item.clone()
            ni.json = {
                **item.json,
                "url": url,
                "error": str(exc),
            }
            out.append(ni)
            continue

        try:
            feed_title, entries = _parse_feed(body or "")
        except ValueError as exc:
            if not node.continue_on_fail:
                raise
            ni = item.clone()
            ni.json = {
                **item.json,
                "url": url,
                "error": str(exc),
            }
            out.append(ni)
            continue

        if not entries:
            # An empty feed still emits a single item summarizing the parse
            # so downstream Set / Filter nodes can see the feed title.
            ni = item.clone()
            ni.json = {**item.json, "url": url, "feedTitle": feed_title}
            out.append(ni)
            continue

        for entry in entries:
            ni = item.clone()
            ni.json = {**item.json, "url": url, "feedTitle": feed_title, **entry}
            out.append(ni)

    return [(0, out)]
