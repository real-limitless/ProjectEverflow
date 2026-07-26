"""Transform executors: summarize (aggregate numeric / distinct / count),
renameKeys (rename JSON keys on each item, with optional regex pre-pass),
dateTime (format / parse / add / subtract / toIso / fromUnix / toUnix),
crypto (hash / hmac / encrypt / decrypt / generateUuid), and
html (extractHtmlContent / htmlToText / extractHtmlLinkUrls /
convertMarkdownToHtml / extractHtmlAttribute) and
markdown (convertHtmlToMarkdown / convertMarkdownToHtml / convertToText), and
xml (xmlToJson / jsonToXml / modifyXml), and
compression (gzip / deflate / zip compress + decompress on a binary property), and
jwt (HS256 sign / verify with a per-item payload + secret).

The Summarize node collapses an input stream into a single item. Each
``fieldsToAggregate`` entry becomes a key on that item, computed by the
configured aggregation mode.

Supported modes (clean-room — matches the n8n Summarize v1 surface used in
the Stock Agent and most public templates):

- ``count``          — number of items in the input
- ``count_distinct`` — distinct count of a field
- ``sum``            — numeric sum of a field
- ``avg``            — numeric mean of a field
- ``min`` / ``max``  — numeric extrema of a field
- ``first`` / ``last`` — pick the first / last non-null value of a field

With no ``fieldsToAggregate`` entries the node still emits a single item
containing the total item ``count`` under the field name ``count``.

The Rename Keys node renames JSON keys on each item. It supports:

- a list of ``{oldKey, newKey}`` direct renames via ``parameters.keys``
- a list of ``{searchRegex, replaceRegex}`` (or ``{regex, replace}``)
  regex renames via ``parameters.regexReplacements``; applied first so
  direct renames can target the resulting keys
- a ``parameters.overwrite`` flag — when False (default) the rename is
  skipped if the new key already exists

The HTML node operates on an HTML / Markdown string carried on each
input item. Supported actions (``parameters.action``) mirror the 80%
surface used in n8n templates:

- ``extractHtmlContent``   — extract inner HTML/text of every element
  matching a CSS selector. Emits one output item per match under
  ``parameters.dataProperty`` (default ``"text"``).
- ``htmlToText``           — strip tags from the input HTML string, keeping
  whitespace. Emits one output item per input.
- ``extractHtmlLinkUrls``  — return every ``href`` from ``<a>`` tags in
  the input. Emits one output item per URL under ``parameters.dataProperty``
  (default ``"url"``).
- ``convertMarkdownToHtml`` — convert a Markdown string to HTML. Emits
  one output item per input.
- ``extractHtmlAttribute``  — return the value of a named attribute on
  every element matching a CSS selector. Emits one output item per match
  under ``parameters.dataProperty`` (default ``"attribute"``).

``cssQuery`` accepts a tiny subset of CSS: tag names (``a``),
id (``#main``), class (``.lead``), and tag.class combinations
(``p.lead``). Compound / descendant / attribute selectors are not
supported — the engine raises ``ValueError`` so callers know to migrate
their templates.

The DateTime node operates on a single value per item and produces a
single output key (default ``date``) per item. Supported actions
(``parameters.action``) mirror the 80% surface used in n8n templates:

- ``format``         — format a datetime with strftime (optionally in a tz)
- ``parse``          — parse a string with strftime to an ISO 8601 string
- ``addToDate``      — add a duration (seconds/minutes/hours/days/weeks/months/years)
- ``subtractFromDate`` — subtract a duration (same units as addToDate)
- ``toIso``          — format a datetime as ISO 8601
- ``fromUnix``       — convert integer seconds-since-epoch to ISO 8601
- ``toUnix``         — convert a datetime / ISO string to integer seconds
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import hmac
import html
import io
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.services.workflows.expression import ExpressionContext, evaluate, evaluate_deep
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext


def _coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _values_for_field(items: list[ExecutionItem], field: str) -> list[Any]:
    if not field:
        return [None] * len(items)
    out: list[Any] = []
    for it in items:
        out.append(it.json.get(field))
    return out


def _aggregate(values: list[Any], mode: str) -> Any:
    """Compute a single aggregated value from a list of field values."""
    if mode == "count":
        return len(values)
    if mode == "count_distinct":
        seen: set[Any] = set()
        for v in values:
            try:
                seen.add(v)
            except TypeError:
                seen.add(repr(v))
        return len(seen)
    if mode in ("sum", "avg", "min", "max"):
        nums: list[float] = []
        for v in values:
            n = _coerce_number(v)
            if n is not None:
                nums.append(n)
        if not nums:
            return 0 if mode == "sum" else None
        if mode == "sum":
            return sum(nums)
        if mode == "avg":
            return sum(nums) / len(nums)
        if mode == "min":
            return min(nums)
        return max(nums)
    if mode == "first":
        for v in values:
            if v is not None:
                return v
        return None
    if mode == "last":
        for v in reversed(values):
            if v is not None:
                return v
        return None
    return None


def _normalize_field_entry(entry: dict[str, Any]) -> tuple[str, str, str] | None:
    """Return ``(display_name, field_name, mode)`` or ``None`` if unusable."""
    name = str(entry.get("fieldDisplayName") or entry.get("displayName") or "").strip()
    fld = str(entry.get("fieldName") or "").strip()
    mode = str(entry.get("aggregation") or entry.get("type") or "").strip().lower()
    if not name or not mode:
        return None
    return name, fld, mode


async def exec_summarize(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Summarize node — collapse items into one summary item.

    ``parameters`` shape (clean-room n8n Summarize v1):

    .. code-block:: json

        {
          "fieldsToAggregate": [
            {
              "fieldDisplayName": "total",
              "fieldName": "amount",
              "aggregation": "sum"
            }
          ]
        }
    """
    del ctx
    params = node.parameters or {}
    raw = params.get("fieldsToAggregate")
    entries: list[dict[str, Any]] = []
    if isinstance(raw, list):
        entries = [e for e in raw if isinstance(e, dict)]
    elif isinstance(raw, dict):
        # Some shapes use a {values: [...]} wrapper
        nested = raw.get("values") if isinstance(raw.get("values"), list) else None
        if nested:
            entries = [e for e in nested if isinstance(e, dict)]

    if not items:
        return [(0, [])]

    summary: dict[str, Any] = {}
    if not entries:
        summary["count"] = len(items)
    else:
        for entry in entries:
            norm = _normalize_field_entry(entry)
            if norm is None:
                continue
            display, field, mode = norm
            values = _values_for_field(items, field)
            summary[display] = _aggregate(values, mode)

    return [(0, [ExecutionItem(json=summary)])]


# ── Rename Keys ───────────────────────────────────────────────────────


def _compile_regex_pattern(entry: dict[str, Any]) -> tuple[re.Pattern[str] | None, str] | None:
    """Return ``(compiled_pattern, replacement)`` or ``None`` if unusable."""
    pattern = entry.get("searchRegex") or entry.get("regex")
    replace = entry.get("replaceRegex") or entry.get("replace") or ""
    if not isinstance(pattern, str) or not pattern:
        return None
    if not isinstance(replace, str):
        replace = str(replace)
    try:
        compiled = re.compile(pattern)
    except re.error:
        return None
    return compiled, replace


def _apply_regex_renames(data: dict[str, Any], patterns: list[tuple[re.Pattern[str], str]]) -> dict[str, Any]:
    """Return a new dict whose keys have been renamed by the given regex patterns.

    Original keys are preserved (with their values) when no pattern matches.
    When multiple patterns match a key, each is applied in order.
    """
    if not patterns:
        return dict(data)
    out: dict[str, Any] = {}
    for key, value in data.items():
        new_key = str(key)
        for compiled, replace in patterns:
            new_key = compiled.sub(replace, new_key)
        out[new_key] = value
    return out


def _collect_direct_renames(params: dict[str, Any]) -> list[tuple[str, str]]:
    """Return ``[(oldKey, newKey), ...]`` from ``parameters.keys`` (and the
    ``{values: [...]}`` wrapper shape)."""
    raw = params.get("keys")
    pairs: list[tuple[str, str]] = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            old = entry.get("oldKey")
            new = entry.get("newKey")
            if not isinstance(old, str) or not isinstance(new, str):
                continue
            if not old or not new:
                continue
            pairs.append((old, new))
    elif isinstance(raw, dict):
        nested = raw.get("values")
        if isinstance(nested, list):
            for entry in nested:
                if not isinstance(entry, dict):
                    continue
                old = entry.get("oldKey")
                new = entry.get("newKey")
                if not isinstance(old, str) or not isinstance(new, str):
                    continue
                if not old or not new:
                    continue
                pairs.append((old, new))
    return pairs


def _collect_regex_renames(params: dict[str, Any]) -> list[tuple[re.Pattern[str], str]]:
    """Return ``[(compiled_pattern, replacement), ...]`` from
    ``parameters.regexReplacements``."""
    raw = params.get("regexReplacements")
    candidates: list[dict[str, Any]] = []
    if isinstance(raw, list):
        candidates = [e for e in raw if isinstance(e, dict)]
    elif isinstance(raw, dict):
        nested = raw.get("values")
        if isinstance(nested, list):
            candidates = [e for e in nested if isinstance(e, dict)]
    compiled_list: list[tuple[re.Pattern[str], str]] = []
    for entry in candidates:
        result = _compile_regex_pattern(entry)
        if result is None:
            continue
        compiled_list.append(result)
    return compiled_list


async def exec_rename_keys(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Rename Keys node — rename JSON keys on every item.

    ``parameters`` shape (clean-room n8n renameKeys v1):

    .. code-block:: json

        {
          "keys": [
            {"oldKey": "a", "newKey": "b"},
            {"oldKey": "firstName", "newKey": "given_name"}
          ],
          "regexReplacements": [
            {"searchRegex": "^prefix_", "replaceRegex": "x_"}
          ],
          "overwrite": false
        }

    Behavior:

    - Regex renames are applied first, then direct renames. This lets a
      direct rename target a key produced by a regex pass.
    - When ``parameters.overwrite`` is False (default), a rename is skipped
      if the new key already exists on the item.
    - Missing ``oldKey`` is a no-op (the entry is silently ignored).
    - Values are preserved by reference; only keys are mutated.
    """
    del ctx
    params = node.parameters or {}
    overwrite = bool(params.get("overwrite", False))
    regex_pairs = _collect_regex_renames(params)
    direct_pairs = _collect_direct_renames(params)

    out: list[ExecutionItem] = []
    for item in items:
        data = dict(item.json)
        if regex_pairs:
            data = _apply_regex_renames(data, regex_pairs)
        for old, new in direct_pairs:
            if old not in data:
                continue
            if old == new:
                continue
            if new in data and not overwrite:
                continue
            data[new] = data.pop(old)
        ni = item.clone()
        ni.json = data
        out.append(ni)
    return [(0, out)]


# ── DateTime ──────────────────────────────────────────────────────────


_TZ_OFFSET_RE = re.compile(r"^([+-])(\d{2}):?(\d{2})$")
_UNIT_TO_KWARG: dict[str, str] = {
    "seconds": "seconds",
    "second": "seconds",
    "minutes": "minutes",
    "minute": "minutes",
    "hours": "hours",
    "hour": "hours",
    "days": "days",
    "day": "days",
    "weeks": "weeks",
    "week": "weeks",
    "months": "months",
    "month": "months",
    "years": "years",
    "year": "years",
}


def _coerce_dt(value: Any) -> datetime:
    """Best-effort coerce a value to a tz-aware datetime (UTC if naive)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    # Expression evaluator's ``$now`` proxy — unwrap to the underlying datetime.
    if hasattr(value, "_dt") and isinstance(getattr(value, "_dt", None), datetime):
        return getattr(value, "_dt")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise ValueError("empty datetime string")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            try:
                dt = datetime.fromtimestamp(float(s), tz=timezone.utc)
            except ValueError as exc:
                raise ValueError(f"Cannot parse datetime from {value!r}") from exc
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    raise ValueError(f"Cannot coerce {value!r} to datetime")


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise ValueError("empty integer string")
        try:
            return int(s)
        except ValueError:
            return int(float(s))
    raise ValueError(f"Cannot coerce {value!r} to int")


def _resolve_tz(tz_name: Any) -> timezone | None:
    """Return a ``datetime.timezone`` for the given IANA name or ``+HH:MM``.

    ``None`` or empty string returns ``None`` (caller treats the value as
    already in the right zone). Unknown IANA names fall back to ``None``
    rather than raising so a single typo doesn't break the whole node.
    """
    if not tz_name:
        return None
    s = str(tz_name).strip()
    if not s:
        return None
    m = _TZ_OFFSET_RE.match(s)
    if m:
        sign = 1 if m.group(1) == "+" else -1
        hours = int(m.group(2))
        mins = int(m.group(3))
        return timezone(sign * timedelta(hours=hours, minutes=mins))
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(s)
    except Exception:
        return None


def _apply_tz(dt: datetime, tz: timezone | None) -> datetime:
    if tz is None:
        return dt
    if isinstance(tz, timezone) and not hasattr(tz, "key"):
        return dt.astimezone(tz)
    return dt.astimezone(tz)


def _shift(dt: datetime, amount: int, unit: str) -> datetime:
    key = _UNIT_TO_KWARG.get(str(unit).lower())
    if key is None:
        raise ValueError(f"Unknown timeUnit: {unit!r}")
    if key in ("months", "years"):
        years = amount // 12 if key == "months" else amount
        months_extra = amount % 12 if key == "months" else 0
        new_year = dt.year + years
        new_month = dt.month + months_extra
        while new_month > 12:
            new_month -= 12
            new_year += 1
        while new_month < 1:
            new_month += 12
            new_year -= 1
        day = min(dt.day, _days_in_month(new_year, new_month))
        return dt.replace(year=new_year, month=new_month, day=day)
    return dt + timedelta(**{key: amount})


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    next_month = datetime(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    return last_day.day


def _parse_with_format(value: str, fmt: str) -> datetime:
    """Parse a string with strftime, gracefully handling ``%z`` and ``%Z``."""
    s = value.strip()
    if not s:
        raise ValueError("empty parse input")
    try:
        return datetime.strptime(s, fmt)
    except ValueError:
        # Retry with ``-`` in numeric tz tokens made optional so e.g.
        # ``%z`` matches ``+0000`` / ``+00:00`` consistently.
        tokens = ("%z", "%Z")
        normalized = s
        for tok in tokens:
            if tok in fmt:
                normalized = normalized.replace(":", "")
        try:
            return datetime.strptime(normalized, fmt.replace(":%z", "%z"))
        except ValueError as exc:
            raise ValueError(
                f"Cannot parse {value!r} with format {fmt!r}"
            ) from exc


async def exec_date_time(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """DateTime node — format / parse / add / subtract / toIso / toUnix / fromUnix.

    ``parameters`` shape (clean-room n8n DateTime v1 surface used in templates):

    .. code-block:: json

        {
          "action": "format",
          "value": "={{ $json.created_at }}",
          "format": "%Y-%m-%d",
          "tz": "UTC",
          "outputFieldName": "date"
        }

    Behavior:

    - Each input item produces one output item. The result is written
      under ``parameters.outputFieldName`` (default ``"date"``). When
      ``outputFieldName`` is empty the result is not stored on the item
      (useful only for side-effect-free run).
    - ``value`` supports ``={{ $json.field }}`` expressions.
    - ``format`` is a standard strftime pattern. n8n's Luxon tokens are
      not interpreted here; templates that use them should be migrated.
    - ``tz`` accepts an IANA name (e.g. ``"America/New_York"``) or an
      offset string (``"+09:00"`` / ``"-0500"``). Unknown IANA names
      silently fall back to the input zone.
    - Supported ``timeUnit`` values for ``addToDate`` / ``subtractFromDate``:
      ``seconds``, ``minutes``, ``hours``, ``days``, ``weeks``, ``months``,
      ``years`` (singular forms accepted).
    """
    params = node.parameters or {}
    action = str(params.get("action") or "format").strip()
    fmt = params.get("format")
    tz_name = params.get("tz")
    output_field = params.get("outputFieldName", "date")
    if not isinstance(output_field, str) or not output_field:
        output_field = None
    duration = params.get("duration", 0)
    time_unit = params.get("timeUnit", "days")

    out: list[ExecutionItem] = []
    # When there are no input items (typical for `$now` / standalone use), still
    # emit one output item — n8n's DateTime v1 produces a single item here.
    effective_items: list[ExecutionItem] = items or [ExecutionItem(json={})]
    for item in effective_items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        raw_value = params.get("value")
        if "value" in params:
            raw_value = evaluate(raw_value, ectx)
        elif action in ("format", "parse", "toIso", "toUnix"):
            raw_value = None
        else:
            raw_value = None

        result: Any
        if action == "format":
            if fmt is None or not isinstance(fmt, str):
                raise ValueError("DateTime: 'format' action requires parameters.format")
            dt = _coerce_dt(raw_value if raw_value is not None else ctx.now)
            tz = _resolve_tz(tz_name)
            result = _apply_tz(dt, tz).strftime(fmt)
        elif action == "parse":
            if fmt is None or not isinstance(fmt, str):
                raise ValueError("DateTime: 'parse' action requires parameters.format")
            if not isinstance(raw_value, str):
                raise ValueError("DateTime: 'parse' requires a string value")
            dt = _parse_with_format(raw_value, fmt)
            tz = _resolve_tz(tz_name)
            if tz is not None:
                # ``tz`` names the zone the parsed wall-clock time lives in.
                # Attach the zone first; only then convert if needed.
                if dt.tzinfo is None:
                    if isinstance(tz, timezone) and not hasattr(tz, "key"):
                        dt = dt.replace(tzinfo=tz)
                    else:
                        dt = dt.replace(tzinfo=tz)
                else:
                    dt = dt.astimezone(tz)
            elif dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            result = dt.isoformat()
        elif action == "addToDate":
            amount = _coerce_int(duration)
            base = _coerce_dt(raw_value if raw_value is not None else ctx.now)
            result = _shift(base, amount, time_unit).isoformat()
        elif action == "subtractFromDate":
            amount = _coerce_int(duration)
            base = _coerce_dt(raw_value if raw_value is not None else ctx.now)
            result = _shift(base, -amount, time_unit).isoformat()
        elif action == "toIso":
            dt = _coerce_dt(raw_value if raw_value is not None else ctx.now)
            result = dt.isoformat()
        elif action == "fromUnix":
            seconds = _coerce_int(raw_value)
            result = datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
        elif action == "toUnix":
            dt = _coerce_dt(raw_value if raw_value is not None else ctx.now)
            result = int(dt.timestamp())
        else:
            raise ValueError(f"DateTime: unsupported action {action!r}")

        ni = item.clone()
        if output_field is not None:
            ni.json = dict(ni.json)
            ni.json[output_field] = result
        out.append(ni)
    return [(0, out)]


# ── Crypto ────────────────────────────────────────────────────────────


# Cipher configuration for encrypt / decrypt. AES-256-CBC with a fixed salt
# gives us a deterministic 32-byte key derived from the user-supplied
# passphrase via PBKDF2-HMAC-SHA256. The IV is generated fresh per call and
# prepended to the ciphertext so the same key can decrypt any blob produced
# by this node.
_CRYPTO_CIPHER = "aes-256-cbc"
_CRYPTO_KEY_LEN = 32
_CRYPTO_IV_LEN = 16
_CRYPTO_PBKDF2_ITERS = 100_000
_CRYPTO_PBKDF2_SALT = b"everflow-crypto-node-v1"

_HASH_ALGOS: dict[str, str] = {
    "md5": "md5",
    "sha1": "sha1",
    "sha256": "sha256",
    "sha512": "sha512",
}


def _coerce_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None:
        return ""
    return str(value)


def _coerce_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return _coerce_str(value).encode("utf-8")


def _resolve_param_value(
    item: ExecutionItem,
    raw_value: Any,
    node_outputs: dict[str, list[ExecutionItem]],
    now: datetime,
) -> Any:
    """Evaluate an ``={{ ... }}`` expression against an item; pass through otherwise."""
    ectx = ExpressionContext(item=item, node_outputs=node_outputs, now=now)
    return evaluate(raw_value, ectx)


def _derive_key(passphrase: str) -> bytes:
    """Derive a fixed-length AES key from a passphrase using PBKDF2-HMAC-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        _CRYPTO_PBKDF2_SALT,
        _CRYPTO_PBKDF2_ITERS,
        dklen=_CRYPTO_KEY_LEN,
    )


def _aes_encrypt_bytes(plaintext: bytes, key: bytes) -> bytes:
    iv = os.urandom(_CRYPTO_IV_LEN)
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as _padding

        padder = _padding.PKCS7(128).padder()
        padded = padder.update(plaintext) + padder.finalize()
        enc = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
        ct = enc.update(padded) + enc.finalize()
        return iv + ct
    except ImportError:
        # Fall back to ``pycryptodome`` if present.
        from Crypto.Cipher import AES  # type: ignore[import-not-found]
        from Crypto.Util import Padding  # type: ignore[import-not-found]

        padded = Padding.pad(plaintext, AES.block_size, style="pkcs7")
        ct = AES.new(key, AES.MODE_CBC, iv).encrypt(padded)
        return iv + ct


def _aes_decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    if len(blob) < _CRYPTO_IV_LEN:
        raise ValueError("crypto: ciphertext too short to contain an IV")
    iv = blob[:_CRYPTO_IV_LEN]
    ct = blob[_CRYPTO_IV_LEN:]
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as _padding

        dec = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = dec.update(ct) + dec.finalize()
        unpadder = _padding.PKCS7(128).unpadder()
        return unpadder.update(padded) + unpadder.finalize()
    except ImportError:
        from Crypto.Cipher import AES  # type: ignore[import-not-found]
        from Crypto.Util import Padding  # type: ignore[import-not-found]

        plain = AES.new(key, AES.MODE_CBC, iv).decrypt(ct)
        return Padding.unpad(plain, AES.block_size, style="pkcs7")


async def exec_crypto(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Crypto node — hash / hmac / encrypt / decrypt / generateUuid.

    ``parameters`` shape (clean-room n8n Crypto v1 surface used in templates):

    .. code-block:: json

        {
          "action": "hash",
          "value": "={{ $json.message }}",
          "algorithm": "sha256",
          "outputFieldName": "hash"
        }

    Supported actions:

    - ``hash``         — one-way digest of ``value`` with ``algorithm``
      (md5 / sha1 / sha256 / sha512). Output is a lower-case hex string.
    - ``hmac``         — keyed digest. Adds ``key`` (string or ``={{ ... }}``
      expression). Output is a lower-case hex string.
    - ``encrypt``      — AES-256-CBC with a PBKDF2-derived key. ``key`` is
      the passphrase. Output is base64 of ``iv ‖ ciphertext``.
    - ``decrypt``      — inverse of ``encrypt``. ``key`` is the passphrase,
      ``value`` is the base64 blob produced by ``encrypt``.
    - ``generateUuid`` — emit a UUID4 per item under ``outputFieldName``
      (default ``"uuid"``). No ``value`` / ``key`` required.

    The result is written under ``parameters.outputFieldName``
    (default ``"data"``). When ``outputFieldName`` is empty the original
    item is passed through unchanged.
    """
    params = node.parameters or {}
    action = str(params.get("action") or "hash").strip()
    algorithm = str(params.get("algorithm") or "sha256").strip().lower()
    output_field = params.get("outputFieldName", "data")
    if not isinstance(output_field, str) or not output_field:
        output_field = None

    out: list[ExecutionItem] = []
    # n8n's crypto node produces one output item per input item. With no
    # input, all actions except ``generateUuid`` return an empty stream
    # (no upstream data → nothing to operate on).
    effective_items: list[ExecutionItem] = items
    if not items and action == "generateUuid":
        effective_items = [ExecutionItem(json={})]
    for item in effective_items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)

        raw_value = params.get("value")
        if raw_value is not None:
            raw_value = evaluate(raw_value, ectx)
        raw_key = params.get("key")
        if raw_key is not None:
            raw_key = evaluate(raw_key, ectx)

        result: Any
        if action == "generateUuid":
            result = str(uuid4())
        elif action == "hash":
            if algorithm not in _HASH_ALGOS:
                raise ValueError(
                    f"crypto: unsupported hash algorithm {algorithm!r}; "
                    f"expected one of {sorted(_HASH_ALGOS)}"
                )
            payload = _coerce_bytes(raw_value if raw_value is not None else item.json.get("value", ""))
            result = hashlib.new(_HASH_ALGOS[algorithm], payload).hexdigest()
        elif action == "hmac":
            if algorithm not in _HASH_ALGOS:
                raise ValueError(
                    f"crypto: unsupported hmac algorithm {algorithm!r}; "
                    f"expected one of {sorted(_HASH_ALGOS)}"
                )
            if raw_key is None:
                raise ValueError("crypto: 'hmac' action requires parameters.key")
            payload = _coerce_bytes(raw_value if raw_value is not None else item.json.get("value", ""))
            key_bytes = _coerce_bytes(raw_key)
            result = hmac.new(key_bytes, payload, _HASH_ALGOS[algorithm]).hexdigest()
        elif action == "encrypt":
            if raw_key is None:
                raise ValueError("crypto: 'encrypt' action requires parameters.key")
            plaintext = _coerce_bytes(raw_value if raw_value is not None else "")
            key = _derive_key(_coerce_str(raw_key))
            blob = _aes_encrypt_bytes(plaintext, key)
            result = base64.b64encode(blob).decode("ascii")
        elif action == "decrypt":
            if raw_key is None:
                raise ValueError("crypto: 'decrypt' action requires parameters.key")
            if raw_value is None:
                raise ValueError("crypto: 'decrypt' action requires parameters.value")
            try:
                blob = base64.b64decode(_coerce_str(raw_value), validate=False)
            except Exception as exc:
                raise ValueError(f"crypto: cannot base64-decode ciphertext: {exc}") from exc
            key = _derive_key(_coerce_str(raw_key))
            try:
                plaintext = _aes_decrypt_bytes(blob, key)
            except Exception as exc:
                raise ValueError(f"crypto: decryption failed: {exc}") from exc
            result = plaintext.decode("utf-8", errors="replace")
        else:
            raise ValueError(f"crypto: unsupported action {action!r}")

        ni = item.clone()
        if output_field is not None:
            ni.json = dict(ni.json)
            ni.json[output_field] = result
        out.append(ni)
    return [(0, out)]



# ── HTML ──────────────────────────────────────────────────────────────


# Pre-compiled patterns used to compile a tiny CSS selector subset. We
# don't pull in a full selector engine (the rest of the project favors
# small deps); the supported grammar is:
#
#     element       — a tag name (a, div, p, …)
#     #identifier   — id selector
#     .identifier   — class selector
#     element.class — tag-qualified class selector
#
# Compound / descendant / attribute selectors raise.
_CSS_SELECTOR_RE = re.compile(
    r"^\s*"
    r"(?:(?P<tag>[A-Za-z][A-Za-z0-9]*)?)"
    r"(?P<rest>(?:\.[A-Za-z_][A-Za-z0-9_\-]*|#[A-Za-z_][A-Za-z0-9_\-]*)+)"
    r"\s*$"
)
_CSS_ID_ONLY_RE = re.compile(r"^\s*#(?P<id>[A-Za-z_][A-Za-z0-9_\-]*)\s*$")
_CSS_CLASS_ONLY_RE = re.compile(r"^\s*\.(?P<cls>[A-Za-z_][A-Za-z0-9_\-]*)\s*$")
_CSS_TAG_ONLY_RE = re.compile(r"^\s*(?P<tag>[A-Za-z][A-Za-z0-9]*)\s*$")


class _CompiledSelector:
    """A tiny tag/class/id matcher produced from ``_compile_selector``."""

    __slots__ = ("tag", "id_", "classes")

    def __init__(self, tag: str | None, id_: str | None, classes: tuple[str, ...]) -> None:
        self.tag = tag
        self.id_ = id_
        self.classes = classes

    def matches(self, tag: str, attrs: dict[str, str]) -> bool:
        if self.tag is not None and tag.lower() != self.tag.lower():
            return False
        if self.id_ is not None and attrs.get("id") != self.id_:
            return False
        if self.classes:
            cls_attr = attrs.get("class", "")
            tokens = cls_attr.split()
            for required in self.classes:
                if required not in tokens:
                    return False
        return True


def _compile_selector(selector: str) -> _CompiledSelector:
    """Parse a tiny CSS selector subset into a ``_CompiledSelector``.

    Raises ``ValueError`` for unsupported compound syntax so callers get
    a clear error rather than a silent zero-match result.
    """
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("html: cssQuery must be a non-empty string")
    text = selector.strip()

    m = _CSS_ID_ONLY_RE.match(text)
    if m:
        return _CompiledSelector(tag=None, id_=m.group("id"), classes=())
    m = _CSS_CLASS_ONLY_RE.match(text)
    if m:
        return _CompiledSelector(tag=None, id_=None, classes=(m.group("cls"),))
    m = _CSS_TAG_ONLY_RE.match(text)
    if m and m.group("tag"):
        return _CompiledSelector(tag=m.group("tag"), id_=None, classes=())
    m = _CSS_SELECTOR_RE.match(text)
    if m and m.group("tag") and m.group("rest"):
        rest = m.group("rest")
        classes: list[str] = []
        id_: str | None = None
        for piece in re.findall(r"[.#][A-Za-z_][A-Za-z0-9_\-]*", rest):
            if piece.startswith("."):
                classes.append(piece[1:])
            elif id_ is None:
                id_ = piece[1:]
            else:
                raise ValueError(
                    f"html: unsupported CSS selector {selector!r}: multiple id tokens"
                )
        return _CompiledSelector(tag=m.group("tag"), id_=id_, classes=tuple(classes))
    raise ValueError(
        f"html: unsupported CSS selector {selector!r}; "
        "supported: tag, #id, .class, tag.class"
    )


class _HtmlNode:
    """Lightweight DOM node used by the HTML executor.

    Holds the tag name, attribute dict, text fragments, and children. The
    builder (``_HtmlTreeBuilder``) walks the SAX stream from
    ``html.parser.HTMLParser`` and builds a tree so we can both match
    selectors and serialize inner HTML / text.
    """

    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.children: list[Any] = []  # _HtmlNode | str
        self.parent: _HtmlNode | None = None

    def append_child(self, child: Any) -> None:
        if isinstance(child, _HtmlNode):
            child.parent = self
        self.children.append(child)


class _HtmlTreeBuilder(HTMLParser):
    """Builds a tree of ``_HtmlNode`` from a SAX-style HTMLParser stream."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = _HtmlNode(tag="__root__")
        self._stack: list[_HtmlNode] = [self.root]
        # ``<script>`` and ``<style>`` contents should not surface in
        # text extraction or inner HTML.
        self._skip_depth = 0
        # Tracks raw text for the currently-open element (excludes tags).
        self._text: list[str] = []
        self._raw_text = False

    @property
    def _current(self) -> _HtmlNode:
        return self._stack[-1]

    def _flush_text(self) -> None:
        if self._skip_depth > 0 or not self._text:
            self._text = []
            return
        text = "".join(self._text)
        if text:
            self._current.append_child(text)
        self._text = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._flush_text()
        normalized = {
            (k.lower() if k else k): (v if v is not None else "")
            for k, v in attrs
        }
        node = _HtmlNode(tag=tag, attrs=normalized)
        self._current.append_child(node)
        if tag.lower() in ("script", "style"):
            self._skip_depth += 1
            self._raw_text = True
        # HTMLParser emits non-void start tags as both starttag and
        # startendtag — we let the tree accept them and rely on the
        # standard "void elements don't need explicit close" semantics.
        # Void elements (e.g. ``<br>``, ``<hr>``, ``<img>``) are reported
        # by HTMLParser as plain start tags — we must not push them onto
        # the stack or any following text gets attached to the void
        # element instead of its real parent.
        if tag.lower() in _VOID_ELEMENTS:
            return
        self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._flush_text()
        normalized = {
            (k.lower() if k else k): (v if v is not None else "")
            for k, v in attrs
        }
        node = _HtmlNode(tag=tag, attrs=normalized)
        self._current.append_child(node)
        # Self-closing → do not push onto stack.

    def handle_endtag(self, tag: str) -> None:
        self._flush_text()
        tag_lower = tag.lower()
        if tag_lower in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1
            self._raw_text = self._skip_depth > 0
        # Pop until we find a matching open tag. Malformed HTML may
        # close elements that were never opened — be tolerant.
        for idx in range(len(self._stack) - 1, 0, -1):
            if self._stack[idx].tag.lower() == tag_lower:
                del self._stack[idx:]
                return
        # No match: ignore (defensive against malformed input).

    def handle_data(self, data: str) -> None:
        if self._raw_text:
            # We still record the text inside the element so the tree
            # faithfully round-trips the input; text extraction below
            # simply skips script/style subtrees.
            self._current.append_child(data)
            return
        self._text.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._raw_text:
            self._current.append_child(f"&{name};")
            return
        self._text.append(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        if self._raw_text:
            self._current.append_child(f"&#{name};")
            return
        self._text.append(html.unescape(f"&#{name};"))

    def handle_comment(self, data: str) -> None:  # noqa: ARG002 — accepted by base
        # Comments don't affect selectors or text extraction.
        return

    def close(self) -> None:
        super().close()
        self._flush_text()


# Void elements that never receive a close tag in well-formed HTML.
_VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)


def _render_html(node: _HtmlNode) -> str:
    """Serialize a subtree back to HTML (tags + children)."""

    if not node.children:
        if node.tag.lower() in _VOID_ELEMENTS:
            return _render_void(node)
        return ""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(html.escape(child, quote=False))
            continue
        parts.append(_render_element(child))
    return "".join(parts)


def _render_void(node: _HtmlNode) -> str:
    attrs = _render_attrs(node.attrs)
    return f"<{node.tag}{attrs}/>" if attrs else f"<{node.tag}/>"


def _render_attrs(attrs: dict[str, str]) -> str:
    if not attrs:
        return ""
    parts: list[str] = []
    for key, value in attrs.items():
        parts.append(f' {key}="{html.escape(value, quote=True)}"')
    return "".join(parts)


def _render_element(node: _HtmlNode) -> str:
    attrs = _render_attrs(node.attrs)
    if node.tag.lower() in _VOID_ELEMENTS and not node.children:
        return f"<{node.tag}{attrs}/>" if attrs else f"<{node.tag}/>"
    inner = _render_html(node)
    return f"<{node.tag}{attrs}>{inner}</{node.tag}>"


def _inner_text(node: _HtmlNode) -> str:
    """Collect text from a subtree, preserving whitespace."""
    out: list[str] = []
    _collect_text(node, out, in_skip=False)
    return "".join(out)


def _collect_text(node: _HtmlNode, out: list[str], *, in_skip: bool) -> None:
    skip = in_skip or node.tag.lower() in ("script", "style")
    if skip:
        return
    for child in node.children:
        if isinstance(child, str):
            out.append(child)
        else:
            _collect_text(child, out, in_skip=skip)


def _parse_html(source: str) -> _HtmlNode:
    """Parse an HTML fragment into a tree rooted at ``_HtmlNode('__root__')``."""
    builder = _HtmlTreeBuilder()
    builder.feed(source or "")
    builder.close()
    return builder.root


def _walk(root: _HtmlNode):
    """Yield every ``_HtmlNode`` in document order (depth-first)."""
    stack: list[_HtmlNode] = [root]
    while stack:
        node = stack.pop()
        if node is root:
            # Surface the root's children but not the synthetic root itself
            # — selectors should not match it.
            stack.extend(reversed(node.children))
            continue
        yield node
        # Reverse so we visit left-to-right.
        children_nodes = [c for c in node.children if isinstance(c, _HtmlNode)]
        stack.extend(reversed(children_nodes))


def _strip_tags(html_source: str) -> str:
    """Remove HTML tags, decode entities, collapse runs of whitespace per line.

    We use the DOM tree (not a regex on the raw text) so adjacent text and
    inline tags like ``<b>world</b>!`` keep their tight attachment in the
    output. Block-level elements contribute a single separating space
    where the source had a clear gap; per-line whitespace is then
    collapsed to one space. Newlines are preserved between block
    elements so the output hints at the original structure.
    """
    root = _parse_html(html_source)
    parts: list[str] = []
    _collect_plain_text(root, parts)
    text = "".join(parts)
    text = html.unescape(text)
    lines = text.splitlines() or [text]
    normalized = [" ".join(line.split()) for line in lines]
    return "\n".join(line for line in normalized if line)


# Block-level tags that introduce a line break in the plain-text output.
_BLOCK_TAGS = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl",
        "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
        "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol",
        "p", "pre", "section", "table", "tbody", "td", "tfoot", "th", "thead",
        "tr", "ul",
    }
)


def _collect_plain_text(node: _HtmlNode, out: list[str], *, in_skip: bool = False) -> None:
    """Append plain-text fragments from ``node`` into ``out``.

    Inline children get concatenated without a separator; block-level
    children get a newline. Whitespace inside text nodes is preserved so
    the caller can decide how aggressively to collapse.
    """
    if node.tag == "__root__":
        for child in node.children:
            if isinstance(child, str):
                out.append(child)
            else:
                _collect_plain_text(child, out, in_skip=in_skip)
        return
    skip = in_skip or node.tag.lower() in ("script", "style")
    if skip:
        return
    for child in node.children:
        if isinstance(child, str):
            out.append(child)
            continue
        if child.tag.lower() in _BLOCK_TAGS:
            out.append("\n")
            _collect_plain_text(child, out, in_skip=False)
            out.append("\n")
        else:
            _collect_plain_text(child, out, in_skip=False)


def _convert_markdown_to_html(source: str) -> str:
    """Convert a small Markdown subset to HTML.

    Block-level constructs (headings, lists, blockquotes, code fences) are
    processed line-by-line; inline (bold, italic, code, links) is then
    applied to the surviving text. The supported subset is intentionally
    small: headings (#..######), fenced code, unordered + ordered lists,
    blockquotes, bold (** / __), italic (* / _), inline code, and links.

    The output is a single string of complete HTML elements separated by
    single newlines, so the result is both readable in source form and
    safe to round-trip through an HTML parser without stray whitespace
    ending up inside list items or other inline constructs.
    """
    text = source or ""
    lines = text.splitlines()
    out: list[str] = []
    in_code = False
    code_buffer: list[str] = []
    list_stack: list[tuple[str, int]] = []  # (kind, indent)
    # The most recent <li> body is buffered as a string and only appended
    # to ``out`` when the next item, list close, or block break forces a
    # flush. This keeps each list element atomic for the top-level join.
    pending_li: list[str] = []

    def _flush_li() -> None:
        if pending_li:
            out.append(f"<li>{''.join(pending_li)}</li>")
            pending_li.clear()

    def _flush_list() -> None:
        _flush_li()
        while list_stack:
            kind, _indent = list_stack.pop()
            out.append("</ul>" if kind == "ul" else "</ol>")

    def _close_para() -> None:
        if out and out[-1].startswith("<p>") and not out[-1].endswith("</p>"):
            out[-1] = out[-1] + "</p>"

    def _emit_para(content: str) -> None:
        out.append(f"<p>{_render_inline(content)}</p>")

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code blocks (``` ... ```).
        if stripped.startswith("```"):
            in_code = not in_code
            if in_code:
                _close_para()
                out.append("<pre><code>")
            else:
                out.append(html.escape("\n".join(code_buffer)))
                code_buffer = []
                out.append("</code></pre>")
            i += 1
            continue
        if in_code:
            code_buffer.append(line)
            i += 1
            continue

        # Blank line — paragraph break.
        if not stripped:
            _flush_list()
            _close_para()
            i += 1
            continue

        # Headings (# .. ######).
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            _flush_list()
            _close_para()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_render_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        # Blockquote (> …).
        if stripped.startswith(">"):
            _flush_list()
            _close_para()
            buf: list[str] = [stripped.lstrip(">").lstrip()]
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith(">"):
                buf.append(lines[j].lstrip().lstrip(">").lstrip())
                j += 1
            out.append(f"<blockquote>{_render_inline(' '.join(buf))}</blockquote>")
            i = j
            continue

        # Unordered list (- or * or +).
        ul = re.match(r"^([-*+])\s+(.*)$", stripped)
        if ul:
            _close_para()
            if not list_stack or list_stack[-1][0] != "ul":
                _flush_list()
                out.append("<ul>")
                list_stack.append(("ul", 0))
            else:
                _flush_li()
            pending_li.append(_render_inline(ul.group(2)))
            i += 1
            continue

        # Ordered list (1. 2. …).
        ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ol:
            _close_para()
            if not list_stack or list_stack[-1][0] != "ol":
                _flush_list()
                out.append("<ol>")
                list_stack.append(("ol", 0))
            else:
                _flush_li()
            pending_li.append(_render_inline(ol.group(1)))
            i += 1
            continue

        # Default: paragraph line. Accumulate contiguous non-empty,
        # non-block lines into one paragraph.
        para_lines = [stripped]
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt:
                break
            if nxt.startswith("```") or nxt.startswith("#") or nxt.startswith(">"):
                break
            if re.match(r"^([-*+])\s+", nxt) or re.match(r"^\d+\.\s+", nxt):
                break
            para_lines.append(nxt)
            j += 1
        _flush_list()
        _emit_para(" ".join(para_lines))
        i = j

    if in_code:
        out.append(html.escape("\n".join(code_buffer)))
        out.append("</code></pre>")
    _flush_list()
    return "\n".join(out)


def _render_inline(text: str) -> str:
    """Apply inline markdown transformations to a single line / paragraph.

    Order matters: extract code spans first so their contents don't get
    re-interpreted as markdown.
    """
    if not text:
        return ""

    # Inline code (`foo`).
    code_spans: list[str] = []

    def _stash(match: "re.Match[str]") -> str:
        code_spans.append(html.escape(match.group(1), quote=False))
        return f"\x00{len(code_spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash, text)

    text = html.escape(text, quote=False)

    # Links: [text](href).
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        text,
    )

    # Bold (**text** or __text__).
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)

    # Italic (*text* or _text_). Run after bold so `**x**` isn't halved.
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", text)

    # Restore code spans.
    text = re.sub(
        r"\x00(\d+)\x00",
        lambda m: f"<code>{code_spans[int(m.group(1))]}</code>",
        text,
    )
    return text


def _output_field_name(params: dict[str, Any], default: str) -> str | None:
    name = params.get("dataProperty", default)
    if not isinstance(name, str):
        return default
    name = name.strip()
    return name or None


async def exec_html(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """HTML node — extract, convert, and query HTML / Markdown content.

    ``parameters`` shape (clean-room n8n HTML v1 surface used in templates):

    .. code-block:: json

        {
          "action": "extractHtmlContent",
          "cssQuery": "p.lead",
          "dataProperty": "text"
        }

    Supported actions:

    - ``extractHtmlContent``   — read ``parameters.dataProperty`` from each
      input item (default ``"html"``), parse as HTML, and emit one output
      item per element matching ``parameters.cssQuery``. Each output item
      carries the matched element's inner HTML under
      ``parameters.dataProperty`` (default ``"text"``).
    - ``htmlToText``           — read the HTML string from
      ``parameters.dataProperty`` (default ``"html"``) and emit one output
      item whose ``dataProperty`` (default ``"text"``) holds the stripped
      plain text.
    - ``extractHtmlLinkUrls``  — emit one output item per ``<a href>`` on
      the input. The output field (``dataProperty``, default ``"url"``)
      carries the URL.
    - ``convertMarkdownToHtml`` — read a Markdown string from
      ``parameters.dataProperty`` (default ``"markdown"``) and emit one
      output item with the rendered HTML under
      ``dataProperty`` (default ``"html"``).
    - ``extractHtmlAttribute``  — emit one output item per element
      matching ``parameters.cssQuery`` whose ``parameters.attribute``
      value is written to ``parameters.dataProperty`` (default
      ``"attribute"``). Elements missing the attribute are skipped.

    The ``cssQuery`` grammar is intentionally tiny: tag, ``#id``,
    ``.class``, and ``tag.class``. Compound selectors raise ``ValueError``.

    Actions that produce zero matches (no element found) emit no items —
    matching n8n's "no input → no output" semantics for extract actions.
    """
    del ctx
    params = node.parameters or {}
    action = str(params.get("action") or "extractHtmlContent").strip()
    output_field_default = {
        "extractHtmlContent": "text",
        "htmlToText": "text",
        "extractHtmlLinkUrls": "url",
        "convertMarkdownToHtml": "html",
        "extractHtmlAttribute": "attribute",
    }.get(action, "text")
    output_field = _output_field_name(params, output_field_default)
    selector_text = params.get("cssQuery")
    if isinstance(selector_text, str):
        selector_text = selector_text.strip() or None

    def _read_property(item: ExecutionItem, default: str) -> str:
        prop = params.get("dataProperty", default)
        if not isinstance(prop, str) or not prop:
            prop = default
        value = item.json.get(prop)
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    def _emit_item(base: ExecutionItem, primary_value: Any, **aux: Any) -> ExecutionItem:
        ni = base.clone()
        ni.json = dict(ni.json)
        if output_field is not None:
            ni.json[output_field] = primary_value
        # Carry auxiliary fields too so callers can attach context
        # without losing the default channel.
        for k, v in aux.items():
            if k == output_field or k in ni.json:
                continue
            ni.json[k] = v
        return ni

    out: list[ExecutionItem] = []
    if action == "extractHtmlContent":
        if not selector_text:
            raise ValueError("html: extractHtmlContent requires parameters.cssQuery")
        compiled = _compile_selector(selector_text)
        for item in items:
            source = _read_property(item, "html")
            if not source:
                continue
            root = _parse_html(source)
            for node in _walk(root):
                if compiled.matches(node.tag, node.attrs):
                    inner = _render_html(node)
                    text = _inner_text(node).strip()
                    ni = _emit_item(item, primary_value=inner, inner=inner, text=text)
                    out.append(ni)
        return [(0, out)]

    if action == "htmlToText":
        for item in items:
            source = _read_property(item, "html")
            text = _strip_tags(source)
            ni = _emit_item(item, primary_value=text)
            out.append(ni)
        return [(0, out)]

    if action == "extractHtmlLinkUrls":
        for item in items:
            source = _read_property(item, "html")
            if not source:
                continue
            root = _parse_html(source)
            for node in _walk(root):
                if node.tag.lower() != "a":
                    continue
                href = node.attrs.get("href")
                if not href:
                    continue
                ni = _emit_item(item, primary_value=href)
                out.append(ni)
        return [(0, out)]

    if action == "convertMarkdownToHtml":
        for item in items:
            source = _read_property(item, "markdown")
            rendered = _convert_markdown_to_html(source)
            ni = _emit_item(item, primary_value=rendered)
            out.append(ni)
        return [(0, out)]

    if action == "extractHtmlAttribute":
        if not selector_text:
            raise ValueError("html: extractHtmlAttribute requires parameters.cssQuery")
        attribute = params.get("attribute")
        if not isinstance(attribute, str) or not attribute:
            raise ValueError("html: extractHtmlAttribute requires parameters.attribute")
        attr_lower = attribute.lower()
        compiled = _compile_selector(selector_text)
        for item in items:
            source = _read_property(item, "html")
            if not source:
                continue
            root = _parse_html(source)
            for node in _walk(root):
                if not compiled.matches(node.tag, node.attrs):
                    continue
                value = node.attrs.get(attr_lower)
                if value is None:
                    continue
                ni = _emit_item(item, primary_value=value)
                out.append(ni)
        return [(0, out)]

    raise ValueError(f"html: unsupported action {action!r}")


# ── Markdown ──────────────────────────────────────────────────────────


# Headings rendered as ``# Heading`` — capture the level once so the
# converter can map ``h1`` → 1 ``#`` etc.
_HEADING_TAGS = {f"h{i}": i for i in range(1, 7)}


def _inline_text(node: _HtmlNode) -> str:
    """Collect the raw text content of a subtree (used for inline rendering)."""
    out: list[str] = []
    _collect_text(node, out, in_skip=False)
    return "".join(out)


def _convert_html_to_markdown(source: str) -> str:
    """Convert a small HTML subset to Markdown.

    The supported grammar mirrors the 80% surface used in n8n templates:

    - ``<h1>``..``<h6>`` → ``# … ###### …``
    - ``<p>``           → paragraph (blank-line separated)
    - ``<strong>``/``<b>``  → ``**text**``
    - ``<em>``/``<i>``      → ``*text*``
    - ``<a href>``         → ``[text](href)`` (drops anchor with no href)
    - ``<code>``           → `` `text` ``
    - ``<pre>``            → fenced ```` ``` ```` code block
    - ``<ul>``/``<ol>``/``<li>`` → ``- item`` / ``1. item``
    - ``<blockquote>``     → ``> …`` (one ``>`` prefix per line)
    - ``<br>``             → hard line break (two trailing spaces + ``\n``)
    - other inline content → text as-is

    The output is a single string of complete Markdown elements separated by
    blank lines so the result is both readable in source form and safe to
    round-trip through a Markdown parser.
    """
    root = _parse_html(source)
    blocks: list[str] = []
    _render_html_blocks(root, blocks, list_stack=None, ordered_index=None)
    # Join top-level blocks with a blank line so Markdown parsers (and our
    # own ``_convert_markdown_to_text``) recognize them as separate
    # paragraphs / lists rather than a single wrapped line. Trim trailing
    # whitespace so callers don't have to.
    cleaned: list[str] = []
    for b in blocks:
        text = b.strip("\n")
        if not text:
            continue
        cleaned.append(text)
    return "\n\n".join(cleaned)


def _render_html_blocks(
    node: _HtmlNode,
    out: list[str],
    *,
    list_stack: list[tuple[str, int]] | None,
    ordered_index: list[int] | None,
) -> None:
    """Top-level / nested block rendering for HTML → Markdown.

    ``list_stack`` is a stack of ``(kind, depth)`` so we can choose between
    ``- item`` and ``1. item`` and bump the ordered-list index only when
    we're actually inside an ``<ol>``. ``None`` means we're at the document
    root and any list element triggers a fresh stack.
    """
    for child in node.children:
        if isinstance(child, str):
            text = child.strip()
            if not text:
                continue
            # Loose text at the document root → treat as a paragraph.
            out.append(_format_paragraph(text))
            continue
        tag = child.tag.lower()
        if tag in _HEADING_TAGS:
            level = _HEADING_TAGS[tag]
            content = _render_inline_html(child).strip()
            if not content:
                continue
            out.append(f"{'#' * level} {content}")
            continue
        if tag == "p":
            content = _render_inline_html(child).strip()
            if not content:
                continue
            out.append(_format_paragraph(content))
            continue
        if tag == "br":
            out.append("  \n")
            continue
        if tag == "hr":
            out.append("---")
            continue
        if tag == "blockquote":
            inner = _render_inline_html(child).strip()
            if not inner:
                continue
            quoted = "\n".join(f"> {line}" if line else ">" for line in inner.splitlines())
            out.append(quoted)
            continue
        if tag in ("ul", "ol"):
            new_stack = (list_stack or []) + [(tag, len(list_stack) if list_stack else 0)]
            new_index = ordered_index if tag != "ol" else None
            _render_list(child, out, list_stack=new_stack, ordered_index=new_index)
            continue
        if tag == "pre":
            code_text = _collect_pre_text(child)
            if not code_text:
                continue
            out.append(f"```\n{code_text}\n```")
            continue
        # Fallback: recurse so we can still find nested lists/headings.
        _render_html_blocks(child, out, list_stack=list_stack, ordered_index=ordered_index)


def _format_paragraph(text: str) -> str:
    """Normalize whitespace inside a paragraph."""
    return " ".join(text.split())


def _collect_pre_text(node: _HtmlNode) -> str:
    """Return the text of a ``<pre>`` subtree, preserving structure."""
    parts: list[str] = []
    _collect_pre(node, parts)
    raw = "".join(parts)
    return html.unescape(raw).rstrip("\n")


def _collect_pre(node: _HtmlNode, out: list[str]) -> None:
    if node.tag.lower() in ("script", "style"):
        return
    for child in node.children:
        if isinstance(child, str):
            out.append(child)
        else:
            _collect_pre(child, out)


def _render_list(
    node: _HtmlNode,
    out: list[str],
    *,
    list_stack: list[tuple[str, int]],
    ordered_index: list[int] | None,
) -> None:
    """Render a ``<ul>``/``<ol>`` subtree as a single Markdown block.

    All list items (and any nested blocks they contain) are concatenated
    into one block string and appended to ``out`` so the top-level join
    only adds a single blank line after the whole list, not between
    items. Nested lists are inlined under their parent item as
    2-space-indented blocks so the output round-trips through a
    Markdown parser.
    """
    kind = node.tag.lower()
    index = 1
    item_lines: list[str] = []
    for child in node.children:
        # Skip whitespace text nodes between ``<li>`` elements — the
        # HTMLParser preserves the source newlines and they would
        # otherwise be surfaced as blank lines between items.
        if isinstance(child, str):
            continue
        if child.tag.lower() != "li":
            continue
        # ``list_stack[-1]`` is the kind of the enclosing list.
        depth = len(list_stack) - 1
        indent = "  " * depth
        if kind == "ul":
            bullet = f"{indent}- "
        else:
            bullet = f"{indent}{index}. "
            index += 1
        # Split direct children of ``<li>`` into "primary" inline content
        # and any nested list(s). Inline content is rendered first; nested
        # lists are appended as their own blocks under the same prefix.
        inline_parts: list[str] = []
        nested_blocks: list[str] = []
        for li_child in child.children:
            if isinstance(li_child, str):
                inline_parts.append(li_child)
                continue
            tag = li_child.tag.lower()
            if tag in ("ul", "ol"):
                # Recurse with a deeper stack so nested list bullets get
                # the right indent.
                inner_index = ordered_index if tag == "ol" else None
                _render_list(
                    li_child,
                    nested_blocks,
                    list_stack=list_stack + [(tag, len(list_stack))],
                    ordered_index=inner_index,
                )
            else:
                # For block-level elements inside an ``<li>`` (e.g. a
                # paragraph), render them as additional block(s) under the
                # same bullet.
                _render_html_blocks(
                    li_child,
                    nested_blocks,
                    list_stack=list_stack,
                    ordered_index=ordered_index,
                )
        primary = " ".join(part.strip() for part in inline_parts if part.strip())
        primary_inline = _render_inline_html_for_listitem(child).strip()
        # Prefer the structured inline render (handles ``<strong>``/``<a>``)
        # when there are no nested blocks; otherwise fall back to the
        # plain text + structured nested blocks combo.
        rendered_inline = primary_inline or primary
        if rendered_inline:
            item_lines.append(f"{bullet}{rendered_inline}")
        if nested_blocks:
            # Re-indent nested blocks by the current depth so the Markdown
            # parser sees them as children of this ``<li>``.
            for nb in nested_blocks:
                item_lines.append(nb)
    if item_lines:
        out.append("\n".join(item_lines))


def _render_inline_html_for_listitem(li: _HtmlNode) -> str:
    """Inline render of an ``<li>``'s non-list descendants.

    Returns a single string with ``<strong>`` → ``**…**``, ``<a>`` →
    ``[text](href)``, etc. Nested ``<ul>``/``<ol>`` are skipped here (the
    caller renders them as separate blocks).
    """
    parts: list[str] = []
    _render_inline_walk(li, parts, skip_lists=True)
    text = "".join(parts)
    return " ".join(text.split())


def _render_inline_html(node: _HtmlNode) -> str:
    """Render a block element's inline descendants as Markdown."""
    parts: list[str] = []
    _render_inline_walk(node, parts, skip_lists=False)
    text = "".join(parts)
    return text


def _render_inline_walk(
    node: _HtmlNode,
    parts: list[str],
    *,
    skip_lists: bool,
) -> None:
    tag = node.tag.lower()
    if tag in ("script", "style"):
        return
    if skip_lists and tag in ("ul", "ol"):
        return
    if tag in ("strong", "b"):
        inner = _inline_text(node).strip()
        if inner:
            parts.append(f"**{inner}**")
        return
    if tag in ("em", "i"):
        inner = _inline_text(node).strip()
        if inner:
            parts.append(f"*{inner}*")
        return
    if tag == "code":
        inner = _inline_text(node)
        if inner:
            parts.append(f"`{inner}`")
        return
    if tag == "a":
        text = _inline_text(node).strip()
        href = node.attrs.get("href", "").strip()
        if not text:
            return
        if not href:
            parts.append(text)
        else:
            parts.append(f"[{text}]({href})")
        return
    if tag == "br":
        parts.append("  \n")
        return
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        else:
            _render_inline_walk(child, parts, skip_lists=skip_lists)


def _convert_markdown_to_text(source: str) -> str:
    """Strip Markdown to plain text.

    Behavior (intentionally simple, matches the 80% n8n Markdown v1 surface):

    - Fenced code blocks (```` ``` ````) → content kept verbatim
    - ATX headings (``# …``) → text after the marker
    - Blockquotes (``> …``) → text after ``>``
    - Unordered list items (``- x`` / ``* x`` / ``+ x``) → ``- x``
    - Ordered list items (``1. x``) → ``x`` (numbering dropped)
    - Links ``[text](url)`` → ``text (url)``
    - Bold ``**x**`` / ``__x__`` → ``x``
    - Italic ``*x*`` / ``_x_`` → ``x``
    - Inline code `` `x` `` → ``x``
    - Horizontal rule ``---`` → blank
    - Paragraphs are joined with single newlines; consecutive blank lines
      are collapsed.
    """
    text = source or ""
    lines = text.splitlines()
    out: list[str] = []
    in_code = False
    code_buf: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        # Fenced code block toggle.
        if stripped.startswith("```"):
            if in_code:
                out.append("\n".join(code_buf))
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(raw_line)
            continue

        if not stripped:
            out.append("")
            continue

        # Horizontal rule.
        if re.fullmatch(r"[-*_]{3,}", stripped):
            out.append("")
            continue

        # Heading.
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            out.append(_strip_inline_markdown(heading.group(2)))
            continue

        # Blockquote (possibly multi-prefixed: ``> > x``).
        if stripped.startswith(">"):
            content = re.sub(r"^>+\s?", "", stripped)
            out.append(_strip_inline_markdown(content))
            continue

        # Unordered list.
        ul = re.match(r"^[-*+]\s+(.*)$", stripped)
        if ul:
            out.append(f"- {_strip_inline_markdown(ul.group(1))}")
            continue

        # Ordered list.
        ol = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ol:
            out.append(_strip_inline_markdown(ol.group(1)))
            continue

        out.append(_strip_inline_markdown(stripped))

    if in_code and code_buf:
        out.append("\n".join(code_buf))

    # Collapse runs of blank lines and trim trailing whitespace.
    collapsed: list[str] = []
    blank = False
    for line in out:
        if not line:
            if not blank:
                collapsed.append("")
            blank = True
            continue
        collapsed.append(line)
        blank = False
    return "\n".join(collapsed).strip("\n")


def _strip_inline_markdown(text: str) -> str:
    """Strip inline Markdown syntax from a single line."""
    if not text:
        return ""

    # Pull out inline code first so we don't re-interpret its contents.
    code_spans: list[str] = []

    def _stash(match: "re.Match[str]") -> str:
        code_spans.append(match.group(1))
        return f"\x00{len(code_spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash, text)

    # Links: ``[text](url)`` → ``text (url)``; bare ``[text]`` → ``text``.
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f"{m.group(1)} ({m.group(2)})",
        text,
    )
    text = re.sub(r"\[([^\]]+)\]", r"\1", text)

    # Images: ``![alt](url)`` → ``alt``.
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # Bold / italic — order matters; bold first so ``**x**`` doesn't
    # leave a stray ``*x*`` italic behind.
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"\1", text)

    # Restore code spans.
    text = re.sub(
        r"\x00(\d+)\x00",
        lambda m: code_spans[int(m.group(1))],
        text,
    )
    return text


async def exec_markdown(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Markdown node — convert between HTML, Markdown, and plain text.

    ``parameters`` shape (clean-room n8n Markdown v1 surface used in
    templates):

    .. code-block:: json

        {
          "action": "convertHtmlToMarkdown",
          "dataProperty": "markdown"
        }

    Supported actions:

    - ``convertHtmlToMarkdown`` — read an HTML string from
      ``parameters.dataProperty`` (default ``"html"``) and emit one output
      item with the Markdown under the same field
      (default ``"markdown"``).
    - ``convertMarkdownToHtml`` — read a Markdown string from
      ``parameters.dataProperty`` (default ``"markdown"``) and emit one
      output item with the HTML under the same field (default ``"html"``).
      Implemented by re-using the HTML node's
      ``_convert_markdown_to_html`` helper so the round-trip is symmetric
      with the HTML node's action of the same name.
    - ``convertToText``        — strip Markdown to plain text. Emits one
      output item per input with the result under
      ``parameters.dataProperty`` (default ``"text"``).

    The ``dataProperty`` is the single channel the user wires up: it names
    both the input field and the output field. Per the clean-room
    convention used by the HTML node, the same name is read on input and
    written on output, so the chain ``Manual → Markdown → Set`` works
    with a single field.
    """
    del ctx
    params = node.parameters or {}
    action = str(params.get("action") or "convertHtmlToMarkdown").strip()
    input_field_default = {
        "convertHtmlToMarkdown": "html",
        "convertMarkdownToHtml": "markdown",
        "convertToText": "markdown",
    }.get(action, "markdown")
    output_field_default = {
        "convertHtmlToMarkdown": "markdown",
        "convertMarkdownToHtml": "html",
        "convertToText": "text",
    }.get(action, "markdown")
    output_field = _output_field_name(params, output_field_default)
    input_field = _output_field_name(params, input_field_default)

    def _read_property(item: ExecutionItem) -> str:
        if not input_field:
            return ""
        value = item.json.get(input_field)
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    def _emit_item(base: ExecutionItem, result: str) -> ExecutionItem:
        ni = base.clone()
        ni.json = dict(ni.json)
        if output_field is not None:
            ni.json[output_field] = result
        return ni

    out: list[ExecutionItem] = []
    if action == "convertHtmlToMarkdown":
        for item in items:
            source = _read_property(item)
            rendered = _convert_html_to_markdown(source)
            out.append(_emit_item(item, rendered))
        return [(0, out)]

    if action == "convertMarkdownToHtml":
        for item in items:
            source = _read_property(item)
            rendered = _convert_markdown_to_html(source)
            out.append(_emit_item(item, rendered))
        return [(0, out)]

    if action == "convertToText":
        for item in items:
            source = _read_property(item)
            rendered = _convert_markdown_to_text(source)
            out.append(_emit_item(item, rendered))
        return [(0, out)]

    raise ValueError(f"markdown: unsupported action {action!r}")


# ── XML ────────────────────────────────────────────────────────────────


# A leading ``<?xml … ?>`` declaration is legal but the clean-room
# convention here is to drop it on the way in (and never emit it on the
# way out) so callers can treat the result as a plain string without
# fighting the parser.
_XML_DECL_RE = re.compile(r"^\s*<\?xml\b[^?]*\?>\s*")

# ``elementToModify`` accepts a tiny "XPath-lite" subset: a bare tag name
# (``a``) or ``tag[index]`` with a 1-based index. Compound syntax
# (``/a/b``, predicates, wildcards) raises so callers get a clear
# migration signal.
_XML_SELECTOR_RE = re.compile(
    r"^\s*(?P<tag>[A-Za-z_][A-Za-z0-9_.\-]*)(?:\[(?P<index>\d+)\])?\s*$"
)


def _strip_xml_declaration(source: str) -> str:
    """Drop a leading XML declaration and BOM so the parser sees bare XML."""
    text = source or ""
    if text.startswith("﻿"):
        text = text[1:]
    return _XML_DECL_RE.sub("", text, count=1)


def _element_to_value(element: ET.Element) -> dict[str, Any]:
    """Convert an ``Element`` to a ``dict``.

    The result always uses the same key vocabulary so callers can rely
    on the shape regardless of leaf / branch position:

    - ``@attributes``  — the element's attribute map (omitted if none)
    - ``#text``        — the element's text content, preserved verbatim
      (an empty string is omitted; an element with only whitespace is
      still surfaced so the round-trip stays lossless)
    - child tag → nested value; multiple children sharing the same tag
      are surfaced as a list, preserving source order.

    Even a self-closed element like ``<a/>`` returns ``{"a": {}}`` so
    callers can use ``element.tag`` keys uniformly.
    """
    out: dict[str, Any] = {}
    if element.attrib:
        out["@attributes"] = dict(element.attrib)
    raw_text = element.text or ""
    if raw_text:
        out["#text"] = raw_text
    for child in element:
        if not isinstance(child.tag, str):
            # Skip comments / processing instructions — the surface API
            # only exposes element children.
            continue
        tag = child.tag
        value = _element_to_value(child)
        if tag in out:
            existing = out[tag]
            if isinstance(existing, list):
                existing.append(value)
            else:
                out[tag] = [existing, value]
        else:
            out[tag] = value
    return out


def _value_to_element(tag: str, value: Any) -> ET.Element:
    """Build an ``Element`` from a tag name and a Python value.

    Accepts:

    - ``str`` / ``int`` / ``float`` / ``bool`` / ``None`` → text content
      (``None`` becomes the empty string; ``bool`` follows Python truth)
    - ``dict`` → a structured element. Keys ``@attributes`` and ``#text``
      are interpreted as attribute map and text content respectively;
      any other key becomes a child element. List values become
      repeated child elements sharing the same tag.
    """
    element = ET.Element(tag)
    if isinstance(value, dict):
        for key, sub in value.items():
            if key == "@attributes":
                if isinstance(sub, dict):
                    for attr_name, attr_val in sub.items():
                        element.set(
                            str(attr_name),
                            "" if attr_val is None else str(attr_val),
                        )
                continue
            if key == "#text":
                element.text = "" if sub is None else str(sub)
                continue
            child_tag = str(key)
            if isinstance(sub, list):
                for item in sub:
                    element.append(_value_to_element(child_tag, item))
            else:
                element.append(_value_to_element(child_tag, sub))
        return element
    if value is None:
        element.text = ""
    elif isinstance(value, bool):
        element.text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        element.text = str(value)
    else:
        element.text = str(value)
    return element


def _parse_element_selector(selector: Any) -> tuple[str, int]:
    """Return ``(tag, 1-based-index)`` from a ``tag`` or ``tag[index]`` string."""
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("xml: elementToModify must be a non-empty string")
    text = selector.strip()
    match = _XML_SELECTOR_RE.match(text)
    if not match:
        raise ValueError(
            f"xml: unsupported elementToModify {selector!r}; "
            "supported forms: 'tag' or 'tag[index]'"
        )
    tag = match.group("tag")
    index_str = match.group("index")
    index = int(index_str) if index_str else 1
    if index < 1:
        raise ValueError("xml: elementToModify index must be >= 1")
    return tag, index


def _find_element(root: ET.Element, tag: str, index: int) -> ET.Element:
    """Return the ``index``-th (1-based) descendant ``Element`` whose tag matches.

    Document order is used (depth-first). Raises ``ValueError`` if the
    request falls outside the available matches.
    """
    matches = [el for el in root.iter(tag) if isinstance(el.tag, str)]
    if index > len(matches):
        raise ValueError(
            f"xml: elementToModify matched {len(matches)} element(s) for tag "
            f"{tag!r}; requested index {index}"
        )
    return matches[index - 1]


def _set_or_append_attribute(
    element: ET.Element,
    name: str,
    value: str,
    *,
    append: bool,
) -> None:
    """Apply ``set`` or ``append`` semantics to an element attribute.

    Append joins the new value to the existing attribute with a single
    space, mirroring the n8n modifyXml v1 behavior. An empty existing
    value is replaced directly so the output never starts with a stray
    space.
    """
    if append and name in element.attrib:
        existing = element.attrib[name]
        if existing:
            element.set(name, f"{existing} {value}")
        else:
            element.set(name, value)
    else:
        element.set(name, value)


def _read_string_property(item: ExecutionItem, params: dict[str, Any], default: str) -> str:
    """Read ``parameters.dataProperty`` (default ``default``) as a string."""
    name = params.get("dataProperty", default)
    if not isinstance(name, str) or not name:
        name = default
    raw = item.json.get(name)
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return str(raw)


def _read_data_property(item: ExecutionItem, params: dict[str, Any], default: str) -> Any:
    """Read ``parameters.dataProperty`` (default ``default``) as raw JSON.

    Returns the underlying value (dict, list, scalar) so callers can do
    their own type coercion.
    """
    name = params.get("dataProperty", default)
    if not isinstance(name, str) or not name:
        name = default
    return item.json.get(name)


async def exec_xml(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """XML node — parse, serialize, and lightly edit XML strings.

    ``parameters`` shape (clean-room n8n XML v1 surface used in templates):

    .. code-block:: json

        {
          "action": "xmlToJson",
          "dataProperty": "data"
        }

    Supported actions:

    - ``xmlToJson``  — read the XML string from
      ``parameters.dataProperty`` (default ``"data"``) and emit one output
      item per input. The result is a dict of the form
      ``{rootTag: <nested dict>}`` written to the same ``dataProperty``.
      Any leading ``<?xml ?>`` declaration and XML comments are stripped
      before parsing. An empty / whitespace-only input produces an empty
      ``{}`` so the downstream Set node sees a well-defined value.

    - ``jsonToXml``  — read a Python value (typically a dict) from
      ``parameters.dataProperty`` (default ``"data"``) and emit one
      output item per input whose ``dataProperty`` carries the rendered
      XML string. ``parameters.rootName`` (default ``"root"``) names the
      outer element. Attribute keys starting with ``@`` become XML
      attributes; ``#text`` becomes the text content; nested dicts
      become child elements; lists become repeated children sharing the
      same tag.

    - ``modifyXml``  — read the XML string from
      ``parameters.dataProperty`` (default ``"data"``) and set or append
      a single attribute on the matching element. The selector
      ``parameters.elementToModify`` accepts a tiny XPath-lite grammar:
      ``tag`` (first match) or ``tag[index]`` (1-based nth match,
      document order). ``parameters.attributeName`` is the attribute
      key; ``parameters.attributeValue`` is the value (no expression
      evaluation in v1). ``parameters.append`` (default ``False``) joins
      the new value to the existing attribute with a single space when
      ``True``; otherwise the value overwrites the existing one.

    Unknown actions raise ``ValueError`` so the engine surfaces a clear
    error to the user.
    """
    del ctx
    params = node.parameters or {}
    action = str(params.get("action") or "xmlToJson").strip()
    output_field = _output_field_name(params, "data")

    def _emit(base: ExecutionItem, value: Any) -> ExecutionItem:
        ni = base.clone()
        ni.json = dict(ni.json)
        if output_field is not None:
            ni.json[output_field] = value
        return ni

    out: list[ExecutionItem] = []

    if action == "xmlToJson":
        for item in items:
            source = _read_string_property(item, params, "data")
            cleaned = _strip_xml_declaration(source)
            result: dict[str, Any] = {}
            if cleaned.strip():
                try:
                    root = ET.fromstring(cleaned)
                except ET.ParseError as exc:
                    raise ValueError(f"xml: cannot parse input as XML: {exc}") from exc
                result = {root.tag: _element_to_value(root)}
            out.append(_emit(item, result))
        return [(0, out)]

    if action == "jsonToXml":
        root_name = params.get("rootName", "root")
        if not isinstance(root_name, str) or not root_name.strip():
            root_name = "root"
        else:
            root_name = root_name.strip()
        for item in items:
            data = _read_data_property(item, params, "data")
            if data is None:
                payload: Any = ""
            elif isinstance(data, dict):
                payload = data
            elif isinstance(data, list):
                # Wrap lists in a synthetic child tag so the output is a
                # well-formed single-root document. The most natural name
                # is the existing rootName; we surface each list item as
                # a child of the root with a generic ``item`` tag.
                payload = {"item": data}
            else:
                payload = data
            element = _value_to_element(root_name, payload)
            try:
                rendered = ET.tostring(element, encoding="unicode")
            except ET.ParseError as exc:  # pragma: no cover — guarded upstream
                raise ValueError(f"xml: cannot serialize output XML: {exc}") from exc
            out.append(_emit(item, rendered))
        return [(0, out)]

    if action == "modifyXml":
        attr_name = params.get("attributeName")
        if not isinstance(attr_name, str) or not attr_name:
            raise ValueError("xml: modifyXml requires parameters.attributeName")
        attr_value = params.get("attributeValue", "")
        if attr_value is None:
            attr_value = ""
        attr_value_str = str(attr_value)
        selector = params.get("elementToModify")
        append = bool(params.get("append", False))
        for item in items:
            source = _read_string_property(item, params, "data")
            cleaned = _strip_xml_declaration(source)
            if not cleaned.strip():
                raise ValueError("xml: modifyXml input is empty")
            try:
                root = ET.fromstring(cleaned)
            except ET.ParseError as exc:
                raise ValueError(f"xml: cannot parse input as XML: {exc}") from exc
            tag, index = _parse_element_selector(selector)
            target = _find_element(root, tag, index)
            _set_or_append_attribute(target, attr_name, attr_value_str, append=append)
            try:
                rendered = ET.tostring(root, encoding="unicode")
            except ET.ParseError as exc:  # pragma: no cover — guarded upstream
                raise ValueError(f"xml: cannot serialize output XML: {exc}") from exc
            out.append(_emit(item, rendered))
        return [(0, out)]

    raise ValueError(f"xml: unsupported action {action!r}")


# ── Compression ───────────────────────────────────────────────────────


# Operations supported by the clean-room Compression v1 surface. The map
# stores the human-readable operation string and a hint about which codec
# family it belongs to. The actual encode / decode steps are split per
# action so the dispatch is easy to read.
_COMPRESSION_OPERATIONS: frozenset[str] = frozenset({"gzip", "deflate", "zip"})

# Default file names + mime types for the output BinaryFile per operation.
# We pick sensible n8n-ish defaults so downstream nodes (e.g. extractFromFile)
# see realistic metadata even when the user does not specify a name.
_COMPRESSION_OUTPUT_DEFAULTS: dict[str, tuple[str, str]] = {
    "gzip": ("file.gz", "application/gzip"),
    "deflate": ("file.deflate", "application/octet-stream"),
    "zip": ("file.zip", "application/zip"),
}


def _compress_bytes(data: bytes, operation: str) -> bytes:
    """Encode ``data`` with the requested operation. Raises ``ValueError``."""
    if operation == "gzip":
        return gzip.compress(data)
    if operation == "deflate":
        # zlib (with header) — matches n8n's deflate operation which is
        # interoperable with HTTP ``Content-Encoding: deflate`` clients that
        # expect a zlib wrapper.
        return zlib.compress(data)
    if operation == "zip":
        # Single-file zip envelope. n8n's compression node is similarly
        # limited to one entry per archive in v1; the entry is named after
        # the input file_name when available, otherwise ``file``.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("file", data)
        return buf.getvalue()
    raise ValueError(
        f"compression: unsupported operation {operation!r}; "
        f"expected one of {sorted(_COMPRESSION_OPERATIONS)}"
    )


def _decompress_bytes(data: bytes, operation: str) -> bytes:
    """Decode ``data`` with the requested operation. Raises ``ValueError``."""
    if operation == "gzip":
        try:
            return gzip.decompress(data)
        except (OSError, EOFError) as exc:
            raise ValueError(f"compression: gzip decode failed: {exc}") from exc
    if operation == "deflate":
        try:
            return zlib.decompress(data)
        except zlib.error as exc:
            raise ValueError(f"compression: deflate decode failed: {exc}") from exc
    if operation == "zip":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                entries = zf.namelist()
                if not entries:
                    raise ValueError("compression: zip archive is empty")
                # v1: always pick the first entry. n8n's clean-room surface
                # does not pick a particular name; downstream nodes that
                # need a specific file can rename the entry upstream.
                with zf.open(entries[0]) as fp:
                    return fp.read()
        except zipfile.BadZipFile as exc:
            raise ValueError(f"compression: zip decode failed: {exc}") from exc
    raise ValueError(
        f"compression: unsupported operation {operation!r}; "
        f"expected one of {sorted(_COMPRESSION_OPERATIONS)}"
    )


def _binary_property_name(params: dict[str, Any], key: str, default: str) -> str:
    """Read a binary property name from parameters, falling back to ``default``."""
    raw = params.get(key, default)
    if not isinstance(raw, str) or not raw.strip():
        return default
    return raw


async def exec_compression(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Compression node — gzip / deflate / zip compress or decompress.

    ``parameters`` shape (clean-room n8n Compression v1 surface used in
    templates):

    .. code-block:: json

        {
          "action": "compress",
          "operation": "gzip",
          "binaryPropertyName": "data",
          "outputBinaryPropertyName": "data"
        }

    Supported actions:

    - ``compress``   — read the input binary named by
      ``parameters.binaryPropertyName`` (default ``"data"``) and write the
      compressed payload to ``parameters.outputBinaryPropertyName`` (default
      ``"data"``). Compression uses the codec named by
      ``parameters.operation`` (``gzip`` / ``deflate`` / ``zip``). The zip
      operation wraps a single file named ``file`` inside the archive.

    - ``decompress`` — inverse of ``compress``. Reads the input binary and
      writes the decompressed payload to the output property. For ``zip``,
      the first entry of the archive is returned.

    Items with no input binary for the requested action are passed through
    unchanged so the node behaves like a no-op on optional streams. An
    empty operation string defaults to ``gzip`` (matches n8n defaults).
    """
    del ctx
    params = node.parameters or {}
    action = str(params.get("action") or "compress").strip().lower()
    operation = str(params.get("operation") or "gzip").strip().lower()
    input_key = _binary_property_name(params, "binaryPropertyName", "data")
    output_key = _binary_property_name(params, "outputBinaryPropertyName", "data")

    if action not in ("compress", "decompress"):
        raise ValueError(
            f"compression: unsupported action {action!r}; "
            "expected 'compress' or 'decompress'"
        )
    if operation not in _COMPRESSION_OPERATIONS:
        raise ValueError(
            f"compression: unsupported operation {operation!r}; "
            f"expected one of {sorted(_COMPRESSION_OPERATIONS)}"
        )

    default_name, default_mime = _COMPRESSION_OUTPUT_DEFAULTS[operation]
    out: list[ExecutionItem] = []

    for item in items:
        bf = item.binary.get(input_key)
        if bf is None:
            # No input binary → pass-through. Keeps the node safe in flows
            # where the upstream is optional.
            out.append(item)
            continue

        raw = bf.to_bytes()
        if action == "compress":
            try:
                payload = _compress_bytes(raw, operation)
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(
                    f"compression: {operation} compress failed: {exc}"
                ) from exc
        else:
            try:
                payload = _decompress_bytes(raw, operation)
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(
                    f"compression: {operation} decompress failed: {exc}"
                ) from exc

        # Preserve the user-visible name on the output binary when it looks
        # like a file. For zip output, the downstream consumer expects an
        # archive; for gzip, we tack on ``.gz`` so a Set + file pipeline
        # round-trips sensibly.
        in_name = bf.file_name or "file"
        if action == "compress":
            if operation == "gzip" and not in_name.endswith(".gz"):
                out_name = f"{in_name}.gz"
            elif operation == "zip":
                out_name = in_name
                if not out_name.lower().endswith(".zip"):
                    out_name = f"{out_name}.zip"
            else:
                out_name = in_name
        else:
            # Decompress: try to strip a known suffix so the name on the
            # recovered file looks natural.
            out_name = in_name
            if operation == "gzip" and out_name.endswith(".gz"):
                out_name = out_name[: -len(".gz")]
            elif operation == "zip" and out_name.lower().endswith(".zip"):
                out_name = out_name[: -len(".zip")]

        if not out_name:
            out_name = default_name

        ni = item.clone()
        ni.binary = dict(ni.binary)
        ni.binary[output_key] = BinaryFile.from_bytes(
            payload,
            file_name=out_name,
            mime_type=default_mime,
        )
        out.append(ni)

    return [(0, out)]


# ── JWT ────────────────────────────────────────────────────────────────


# JWT HS256 is HMAC-SHA256 over ``header_b64.payload_b64`` with the secret
# as the HMAC key. We hand-roll the encoding (RFC 7519) so the executor has
# no extra runtime dependency beyond the Python stdlib.
_JWT_ALGOS: dict[str, str] = {
    "HS256": "sha256",
    "HS384": "sha384",
    "HS512": "sha512",
}


def _b64url_encode(data: bytes) -> str:
    """RFC 7515 base64url: standard base64 with ``+``→``-`` and ``/``→``_``,
    trailing ``=`` padding stripped."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    """Inverse of :func:`_b64url_encode`; re-adds stripped padding."""
    if not isinstance(text, str):
        raise ValueError("jwt: token segment is not a string")
    pad = (-len(text)) % 4
    padded = text + ("=" * pad)
    try:
        return base64.urlsafe_b64decode(padded)
    except Exception as exc:
        raise ValueError(f"jwt: cannot base64url-decode segment: {exc}") from exc


def _jwt_hmac_sign(signing_input: bytes, secret: bytes, algorithm: str) -> bytes:
    algo = _JWT_ALGOS[algorithm]
    return hmac.new(secret, signing_input, algo).digest()


def _jwt_hmac_verify(
    signing_input: bytes, signature: bytes, secret: bytes, algorithm: str
) -> bool:
    expected = _jwt_hmac_sign(signing_input, secret, algorithm)
    return hmac.compare_digest(expected, signature)


def _coerce_payload(raw: Any) -> dict[str, Any]:
    """Coerce a ``payload`` parameter into a JSON-serializable dict.

    Accepts: dict (used as-is), JSON string (parsed), expression-evaluated
    ``_JsonProxy`` (unwrapped), ``None`` → ``{}``. Anything else is stringified
    and wrapped under a ``value`` key so the result is always a dict.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if hasattr(raw, "unwrap") and callable(getattr(raw, "unwrap", None)):
        try:
            value = raw.unwrap()
        except Exception:
            value = None
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except Exception:
                return {"value": value}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        if value is None:
            return {}
        return {"value": value}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {"value": raw}
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    if isinstance(raw, (int, float, bool)):
        return {"value": raw}
    if isinstance(raw, list):
        return {"value": list(raw)}
    return {"value": str(raw)}


def _jwt_sign(payload: dict[str, Any], secret: str, algorithm: str) -> str:
    if algorithm not in _JWT_ALGOS:
        raise ValueError(
            f"jwt: unsupported algorithm {algorithm!r}; "
            f"expected one of {sorted(_JWT_ALGOS)}"
        )
    if not isinstance(secret, str) or not secret:
        raise ValueError("jwt: 'sign' action requires a non-empty parameters.secret")
    header = {"alg": algorithm, "typ": "JWT"}
    header_b64 = _b64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    payload_b64 = _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = _jwt_hmac_sign(signing_input, secret.encode("utf-8"), algorithm)
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def _jwt_decode_unverified(token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Parse a JWT and return ``(header, payload)`` without verifying the
    signature. Raises ``ValueError`` on any structural problem."""
    if not isinstance(token, str) or not token:
        raise ValueError("jwt: token is empty")
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("jwt: token must have three dot-separated segments")
    try:
        header_raw = _b64url_decode(parts[0])
        payload_raw = _b64url_decode(parts[1])
    except ValueError:
        raise
    try:
        header = json.loads(header_raw.decode("utf-8"))
        payload = json.loads(payload_raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"jwt: cannot parse token JSON: {exc}") from exc
    if not isinstance(header, dict):
        raise ValueError("jwt: header is not a JSON object")
    if not isinstance(payload, dict):
        raise ValueError("jwt: payload is not a JSON object")
    return header, payload


def _jwt_verify(token: str, secret: str) -> dict[str, Any]:
    """Return ``{valid, payload, error}`` for the given token/secret pair.

    A failed decode or signature mismatch yields ``valid=False``; the
    ``error`` string names the failure. ``payload`` is still surfaced
    (unverified) so callers can introspect the claims when validation
    fails — this mirrors the n8n behavior used in templates.
    """
    result: dict[str, Any] = {"valid": False, "payload": {}, "error": ""}
    if not isinstance(secret, str) or not secret:
        result["error"] = "missing or empty secret"
        return result
    try:
        header, payload = _jwt_decode_unverified(token)
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    result["payload"] = payload
    alg = header.get("alg")
    if not isinstance(alg, str) or alg not in _JWT_ALGOS:
        result["error"] = f"unsupported algorithm {alg!r}"
        return result
    parts = token.split(".")
    if len(parts) != 3:
        result["error"] = "token must have three dot-separated segments"
        return result
    try:
        signature = _b64url_decode(parts[2])
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    if not _jwt_hmac_verify(signing_input, signature, secret.encode("utf-8"), alg):
        result["error"] = "signature mismatch"
        return result
    result["valid"] = True
    return result


async def exec_jwt(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """JWT node — sign (HS256) and verify a JSON Web Token per item.

    ``parameters`` shape (clean-room n8n JWT v1 surface used in templates):

    .. code-block:: json

        {
          "action": "sign",
          "payload": { "sub": "user-1" },
          "secret": "shhh",
          "algorithm": "HS256"
        }

    Supported actions:

    - ``sign``   — build a JWT from ``parameters.payload`` (object, JSON
      string, or ``={{ ... }}`` expression) signed with ``parameters.secret``
      under ``parameters.algorithm`` (default ``"HS256"``; ``HS384`` /
      ``HS512`` also accepted). Emits one output item per input with the
      flat shape ``{jwt: <token>, header: {...}, payload: {...}}``
      merged into the item's JSON. The token field can be renamed via
      ``parameters.tokenField`` (default ``"jwt"``); the other two
      fields are always named ``header`` and ``payload``.

    - ``verify`` — validate a ``parameters.token`` string against
      ``parameters.secret`` and emit one output item per input with the
      flat shape ``{valid: <bool>, payload: {...}, error: "..."}`` merged
      into the item's JSON. The payload is surfaced (unverified) even on
      failure so callers can introspect the claims; ``error`` is the empty
      string on success.

    An empty input stream with no upstream items produces no output.
    """
    params = node.parameters or {}
    action = str(params.get("action") or "sign").strip()
    algorithm = str(params.get("algorithm") or "HS256").strip()
    token_field = params.get("tokenField", "jwt")
    if not isinstance(token_field, str) or not token_field:
        token_field = "jwt"

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)

        raw_payload = params.get("payload")
        if raw_payload is not None:
            raw_payload = evaluate_deep(raw_payload, ectx)
        raw_secret = params.get("secret")
        if raw_secret is not None:
            raw_secret = evaluate(raw_secret, ectx)
        raw_token = params.get("token")
        if raw_token is not None:
            raw_token = evaluate(raw_token, ectx)

        ni = item.clone()
        ni.json = dict(ni.json)
        if action == "sign":
            payload_obj = _coerce_payload(raw_payload)
            secret_str = "" if raw_secret is None else str(raw_secret)
            try:
                token = _jwt_sign(payload_obj, secret_str, algorithm)
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f"jwt: sign failed: {exc}") from exc
            header, decoded_payload = _jwt_decode_unverified(token)
            ni.json[token_field] = token
            ni.json["header"] = header
            ni.json["payload"] = decoded_payload
        elif action == "verify":
            token_str = "" if raw_token is None else str(raw_token)
            secret_str = "" if raw_secret is None else str(raw_secret)
            verify_result = _jwt_verify(token_str, secret_str)
            ni.json["valid"] = verify_result["valid"]
            ni.json["payload"] = verify_result["payload"]
            ni.json["error"] = verify_result["error"]
        else:
            raise ValueError(f"jwt: unsupported action {action!r}")
        out.append(ni)
    return [(0, out)]


# ── Execution Data ────────────────────────────────────────────────────


def _infer_trigger_type(ctx: "EngineContext") -> str:
    """Return the n8n trigger type that started this run, or ``"unknown"``.

    The engine records the requested trigger string on ``RunResult`` but
    executors only see ``EngineContext``. We fall back to inspecting the
    step log — the first step whose ``n8n_type`` is a trigger is the
    entry point. ``"manual"`` is the conventional lower-case label n8n
    exposes; we mirror it from the trailing ``"Trigger"`` token.
    """
    for step in ctx.steps:
        n8n_type = (getattr(step, "n8n_type", "") or "").lower()
        if not n8n_type:
            continue
        if "trigger" in n8n_type or n8n_type.endswith("trigger"):
            # Strip the ``n8n-nodes-base.`` prefix and the ``Trigger`` tail
            # so the label matches the value users wire in templates.
            short = n8n_type.rsplit(".", 1)[-1]
            if short.endswith("trigger"):
                short = short[: -len("trigger")]
            return short or "unknown"
    return "unknown"


async def exec_execution_data(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Execution Data node — emit one item with run-level metadata.

    ``parameters`` shape (clean-room n8n Execution Data v1):

    .. code-block:: json

        {}

    The node is parameterless in v1; it surfaces run-level facts that
    other nodes (typically a downstream ``Set`` or ``Code``) can wire into
    audit trails and notification messages. The output item carries:

    - ``runId``       — the run id from ``ctx.run_id``. The engine stores
      it on ``last_webhook_response`` as a platform-API fallback, but
      executors only see ``EngineContext`` so we read it from there.
    - ``workflowId``  — ``getattr(ctx.graph, "workflow_id", None)``. The
      graph does not currently carry a workflow id, so this is ``None``
      unless a future descriptor wires one in. Surfacing ``None`` keeps
      the schema stable.
    - ``triggerType`` — the n8n trigger that fired this run, inferred
      from ``ctx.steps`` (the first trigger-typed step is the entry).
      Falls back to ``"unknown"`` when no trigger step has been logged
      yet (e.g. unit tests with a bare context).
    - ``now``         — ``ctx.now`` formatted as an ISO 8601 string.
    - ``stepCount``   — ``ctx.step_count`` at the time the node runs.
    - ``nodeName``    — the executor's own ``node.name``.

    The input ``items`` are passed through unchanged after the metadata
    item so downstream nodes see both the metadata snapshot and the
    original payload in execution order.
    """
    node_name = str(getattr(node, "name", "") or "")
    graph = ctx.graph
    workflow_id = getattr(graph, "workflow_id", None) if graph is not None else None
    run_id = getattr(ctx, "run_id", None)
    now = getattr(ctx, "now", None)
    step_count = int(getattr(ctx, "step_count", 0) or 0)
    trigger_type = _infer_trigger_type(ctx)

    metadata: dict[str, Any] = {
        "runId": run_id,
        "workflowId": workflow_id,
        "triggerType": trigger_type,
        "now": now.isoformat() if isinstance(now, datetime) else None,
        "stepCount": step_count,
        "nodeName": node_name,
    }
    out: list[ExecutionItem] = [ExecutionItem(json=metadata)]
    for item in items:
        out.append(item.clone())
    return [(0, out)]

