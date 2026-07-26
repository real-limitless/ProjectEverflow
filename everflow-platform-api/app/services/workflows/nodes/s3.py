"""S3 executor (clean-room n8n ``n8n-nodes-base.s3``).

v1 supports the four operations most commonly used in n8n templates:

- ``upload``   — upload a file; emit one item per input with
  ``{key, bucket, etag, location, size, source: 's3'}``.
- ``download`` — download a file by key; emit one item per input with
  ``{key, bucket, body, contentType, contentLength, etag, source: 's3'}``
  (``body`` is base64-encoded).
- ``list``     — list objects in a bucket; emit one item per file (or one
  item with a ``contents`` array when ``parameters.dataMode == 'object'``).
- ``delete``   — delete a file by key; emit one item per input with
  ``{key, bucket, deleted, source: 's3'}``.

Parameters honored:

- ``operation`` (``"upload"`` / ``"download"`` / ``"list"`` / ``"delete"``;
  default ``"list"``)
- ``bucket``     (string; ``$json.bucket`` / ``$json.bucketName`` fallback;
  required for all operations — empty bucket skips the item)
- ``key``        (string; ``$json.key`` / ``$json.fileName`` fallback;
  required for download/delete — empty key skips the item)
- ``content``    (string base64 or bytes; ``$json.content`` / ``$json.data``
  fallback for upload)
- ``contentType``(string; default ``"application/octet-stream"``; upload only)
- ``prefix``     (string; default ``""``; list only)
- ``maxKeys``    (int; default 100; list only)
- ``delimiter``  (string; optional; list only; echoed)
- ``dataMode``   (``"array"`` / ``"object"``; default ``"array"``; list only)

Behavior precedence:

1. ``ctx.mocks['s3_response']`` — when present, the value drives the
   executor. A dict is used per operation (operation-specific shape); a
   callable is invoked as
   ``mock(operation, bucket, params, item, ctx)`` and may return a dict
   (used per operation) or a non-dict truthy value (wrapped as the
   operation's envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the operation envelope.
3. Offline synthetic response with deterministic-looking ETags and
   timestamps.

Items missing the data needed for the operation (empty ``bucket`` for all
operations; empty ``key`` for download/delete) are skipped (no item
emitted) — matching the behavior of the other output nodes in this
package.
"""

from __future__ import annotations

import base64
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


S3_OPERATIONS: tuple[str, ...] = ("upload", "download", "list", "delete")
S3_DEFAULT_OPERATION: str = "list"
S3_DEFAULT_CONTENT_TYPE: str = "application/octet-stream"
S3_DEFAULT_MAX_KEYS: int = 100
S3_OFFLINE_FILE_COUNT: int = 3
S3_OFFLINE_DOWNLOAD_BODY: bytes = b"mock s3 file content"


def _ectx(item: ExecutionItem, ctx: "EngineContext") -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_coerce_str(v) for v in value if v is not None)
    if isinstance(value, dict):
        for key in ("value", "name", "id", "key", "bucket"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _coerce_int(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                return default
    return default


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_etag() -> str:
    return f'"{uuid.uuid4().hex}"'


def _get_field(d: dict[str, Any], *keys: str) -> Any:
    """Return the first present non-None value among ``keys`` in ``d``."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _resolve_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> Any:
    """Return ``params[key]`` (evaluated) or the first present ``$json`` fallback."""
    raw = params.get(key)
    if raw is not None:
        return evaluate(raw, ectx)
    for fk in json_fallbacks:
        if fk in item.json:
            return item.json[fk]
    return None


def _resolve_str_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> str:
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    return _coerce_str(value)


def _resolve_content_bytes(
    params: dict[str, Any], item: ExecutionItem, ectx: ExpressionContext
) -> bytes:
    """Resolve upload ``content`` from params or ``$json.content``/``$json.data``.

    Accepts either a base64 string or raw bytes. Returns the raw bytes;
    the size of the produced upload envelope is derived from this.
    """
    raw: Any = None
    if params.get("content") is not None:
        raw = evaluate(params.get("content"), ectx)
    else:
        for fk in ("content", "data"):
            if fk in item.json:
                raw = item.json[fk]
                break
    if raw is None:
        return b""
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    if isinstance(raw, str):
        try:
            return base64.b64decode(raw, validate=True)
        except Exception:
            return raw.encode("utf-8")
    return _coerce_str(raw).encode("utf-8")


# ── Offline synthesis ─────────────────────────────────────────────────


def _synthesize_upload(key: str, bucket: str, content_bytes: bytes) -> dict[str, Any]:
    return {
        "ETag": _new_etag(),
        "LOCATION": f"https://{bucket}.s3.amazonaws.com/{key}",
        "key": key,
        "bucket": bucket,
        "size": len(content_bytes),
    }


def _synthesize_download(key: str, bucket: str) -> dict[str, Any]:
    return {
        "Body": base64.b64encode(S3_OFFLINE_DOWNLOAD_BODY).decode("ascii"),
        "ContentType": S3_DEFAULT_CONTENT_TYPE,
        "ContentLength": 22,
        "ETag": _new_etag(),
        "key": key,
        "bucket": bucket,
    }


def _synthesize_list(bucket: str, prefix: str, max_keys: int) -> dict[str, Any]:
    contents: list[dict[str, Any]] = []
    for i in range(1, S3_OFFLINE_FILE_COUNT + 1):
        contents.append(
            {
                "Key": f"mock_file_{i}.txt",
                "LastModified": _now_iso(),
                "ETag": _new_etag(),
                "Size": 1024 * i,
            }
        )
    return {
        "Contents": contents,
        "IsTruncated": False,
        "KeyCount": S3_OFFLINE_FILE_COUNT,
        "MaxKeys": max_keys,
        "Name": bucket,
        "Prefix": prefix,
    }


def _synthesize_delete(key: str, bucket: str) -> dict[str, Any]:
    return {
        "Deleted": [{"Key": key}],
        "key": key,
        "bucket": bucket,
    }


# ── Envelope coercion (normalize mock dicts) ──────────────────────────


def _coerce_upload_envelope(
    raw: dict[str, Any], *, key: str, bucket: str, content_bytes: bytes
) -> dict[str, Any]:
    etag = _coerce_str(_get_field(raw, "ETag", "etag")) or _new_etag()
    location = _coerce_str(_get_field(raw, "LOCATION", "Location", "location"))
    if not location:
        loc_key = _coerce_str(_get_field(raw, "key", "Key")) or key
        loc_bucket = _coerce_str(_get_field(raw, "bucket", "Bucket", "Name")) or bucket
        location = f"https://{loc_bucket}.s3.amazonaws.com/{loc_key}"
    size_raw = _get_field(raw, "size", "Size", "ContentLength")
    if isinstance(size_raw, (int, float)) and not isinstance(size_raw, bool):
        size = int(size_raw)
    else:
        size = len(content_bytes)
    return {
        "etag": etag,
        "location": location,
        "key": _coerce_str(_get_field(raw, "key", "Key")) or key,
        "bucket": _coerce_str(_get_field(raw, "bucket", "Bucket", "Name")) or bucket,
        "size": size,
    }


def _coerce_download_envelope(
    raw: dict[str, Any], *, key: str, bucket: str
) -> dict[str, Any]:
    body = _get_field(raw, "Body", "body", "content")
    if isinstance(body, (bytes, bytearray)):
        body_b64 = base64.b64encode(bytes(body)).decode("ascii")
    elif isinstance(body, str):
        body_b64 = body
    else:
        body_b64 = base64.b64encode(S3_OFFLINE_DOWNLOAD_BODY).decode("ascii")
    ct = _coerce_str(_get_field(raw, "ContentType", "contentType")) or S3_DEFAULT_CONTENT_TYPE
    cl_raw = _get_field(raw, "ContentLength", "contentLength", "size", "Size")
    if isinstance(cl_raw, (int, float)) and not isinstance(cl_raw, bool):
        content_length = int(cl_raw)
    else:
        try:
            content_length = len(base64.b64decode(body_b64)) if body_b64 else 0
        except Exception:
            content_length = 0
    return {
        "body": body_b64,
        "contentType": ct,
        "contentLength": content_length,
        "etag": _coerce_str(_get_field(raw, "ETag", "etag")) or _new_etag(),
        "key": _coerce_str(_get_field(raw, "key", "Key")) or key,
        "bucket": _coerce_str(_get_field(raw, "bucket", "Bucket", "Name")) or bucket,
    }


def _coerce_list_envelope(
    raw: dict[str, Any], *, bucket: str, prefix: str, max_keys: int
) -> dict[str, Any]:
    contents_raw = _get_field(raw, "Contents", "contents", "files")
    if not isinstance(contents_raw, list):
        contents_raw = []
    contents: list[dict[str, Any]] = []
    cap = max_keys if isinstance(max_keys, int) and max_keys > 0 else S3_DEFAULT_MAX_KEYS
    for i, entry in enumerate(contents_raw[:cap]):
        if not isinstance(entry, dict):
            continue
        size_raw = _get_field(entry, "Size", "size")
        if isinstance(size_raw, (int, float)) and not isinstance(size_raw, bool):
            size = int(size_raw)
        else:
            size = 0
        contents.append(
            {
                "key": _coerce_str(_get_field(entry, "Key", "key", "name")) or f"mock_file_{i}.txt",
                "lastModified": _coerce_str(_get_field(entry, "LastModified", "lastModified", "createdTime")) or _now_iso(),
                "etag": _coerce_str(_get_field(entry, "ETag", "etag")) or _new_etag(),
                "size": size,
            }
        )
    return {
        "contents": contents,
        "isTruncated": bool(_get_field(raw, "IsTruncated", "isTruncated") or False),
        "keyCount": _coerce_int(_get_field(raw, "KeyCount", "keyCount"), len(contents)),
        "maxKeys": _coerce_int(_get_field(raw, "MaxKeys", "maxKeys"), max_keys),
        "name": _coerce_str(_get_field(raw, "Name", "name", "bucket")) or bucket,
        "prefix": _coerce_str(_get_field(raw, "Prefix", "prefix")) if _get_field(raw, "Prefix", "prefix") is not None else prefix,
    }


def _coerce_delete_envelope(
    raw: dict[str, Any], *, key: str, bucket: str
) -> dict[str, Any]:
    deleted_raw = _get_field(raw, "Deleted", "deleted")
    deleted: list[dict[str, Any]] = []
    if isinstance(deleted_raw, list):
        for entry in deleted_raw:
            if isinstance(entry, dict):
                deleted.append(
                    {
                        "Key": _coerce_str(_get_field(entry, "Key", "key")) or key,
                    }
                )
            elif isinstance(entry, str):
                deleted.append({"Key": entry})
    if not deleted:
        deleted = [{"Key": key}]
    return {
        "deleted": deleted,
        "key": _coerce_str(_get_field(raw, "key", "Key")) or key,
        "bucket": _coerce_str(_get_field(raw, "bucket", "Bucket", "Name")) or bucket,
    }


# ── http_response fallback ────────────────────────────────────────────


def _s3_response_from_http_mock(
    mock: Any, *, operation: str, key: str, bucket: str, prefix: str, max_keys: int, content_bytes: bytes
) -> dict[str, Any] | None:
    """Extract an S3-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if not isinstance(body, dict):
        if isinstance(body, str) and body.strip():
            if operation == "list":
                return _coerce_list_envelope({"raw": body}, bucket=bucket, prefix=prefix, max_keys=max_keys)
            if operation == "delete":
                return _coerce_delete_envelope({"raw": body}, key=key, bucket=bucket)
            if operation == "download":
                return _coerce_download_envelope({"raw": body}, key=key, bucket=bucket)
            return _coerce_upload_envelope({"raw": body}, key=key, bucket=bucket, content_bytes=content_bytes)
        return None
    if operation == "upload":
        return _coerce_upload_envelope(body, key=key, bucket=bucket, content_bytes=content_bytes)
    if operation == "download":
        return _coerce_download_envelope(body, key=key, bucket=bucket)
    if operation == "list":
        return _coerce_list_envelope(body, bucket=bucket, prefix=prefix, max_keys=max_keys)
    return _coerce_delete_envelope(body, key=key, bucket=bucket)


# ── Response resolver ─────────────────────────────────────────────────


def _resolve_s3_response(
    *,
    operation: str,
    bucket: str,
    params: dict[str, Any],
    key: str,
    prefix: str,
    max_keys: int,
    content_bytes: bytes,
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"s3_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    smock = mocks.get("s3_response")
    if smock is not None:
        if callable(smock):
            raw = smock(operation, bucket, params, item, ctx)
        else:
            raw = smock
        if isinstance(raw, dict):
            if operation == "upload":
                return _coerce_upload_envelope(raw, key=key, bucket=bucket, content_bytes=content_bytes), "s3_response"
            if operation == "download":
                return _coerce_download_envelope(raw, key=key, bucket=bucket), "s3_response"
            if operation == "list":
                return _coerce_list_envelope(raw, bucket=bucket, prefix=prefix, max_keys=max_keys), "s3_response"
            return _coerce_delete_envelope(raw, key=key, bucket=bucket), "s3_response"
        # Non-dict truthy → wrap as a synthetic envelope
        if operation == "list":
            return (
                _coerce_list_envelope({"raw": raw}, bucket=bucket, prefix=prefix, max_keys=max_keys),
                "s3_response",
            )
        if operation == "delete":
            return (
                _coerce_delete_envelope({"raw": raw}, key=key, bucket=bucket),
                "s3_response",
            )
        if operation == "download":
            return (
                _coerce_download_envelope({"raw": raw}, key=key, bucket=bucket),
                "s3_response",
            )
        return (
            _coerce_upload_envelope({"raw": raw}, key=key, bucket=bucket, content_bytes=content_bytes),
            "s3_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _s3_response_from_http_mock(
            hmock,
            operation=operation,
            key=key,
            bucket=bucket,
            prefix=prefix,
            max_keys=max_keys,
            content_bytes=content_bytes,
        )
        if env is not None:
            return env, "http_response"

    if operation == "upload":
        return _coerce_upload_envelope(_synthesize_upload(key, bucket, content_bytes), key=key, bucket=bucket, content_bytes=content_bytes), "offline"
    if operation == "download":
        return _coerce_download_envelope(_synthesize_download(key, bucket), key=key, bucket=bucket), "offline"
    if operation == "list":
        return _coerce_list_envelope(_synthesize_list(bucket, prefix, max_keys), bucket=bucket, prefix=prefix, max_keys=max_keys), "offline"
    return _coerce_delete_envelope(_synthesize_delete(key, bucket), key=key, bucket=bucket), "offline"


# ── Executor ──────────────────────────────────────────────────────────


async def exec_s3(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """S3 node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(params.get("operation") or S3_DEFAULT_OPERATION)
    if operation not in S3_OPERATIONS:
        raise ValueError(
            f"s3: unsupported operation {operation!r}; "
            f"expected one of {S3_OPERATIONS}"
        )

    data_mode = str(params.get("dataMode") or "array").strip().lower()
    if data_mode not in ("array", "object"):
        data_mode = "array"

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        # Shared
        bucket = _resolve_str_param(
            params, "bucket", item, ectx, ("bucket", "bucketName")
        )
        if not bucket:
            logger.info("s3 %s skipped: no bucket on node %r", operation, node.name)
            continue

        key = _resolve_str_param(
            params, "key", item, ectx, ("key", "fileName")
        )
        prefix = _resolve_str_param(params, "prefix", item, ectx, ("prefix",))
        max_keys = _coerce_int(
            evaluate(params.get("maxKeys"), ectx) if params.get("maxKeys") is not None else item.json.get("maxKeys"),
            S3_DEFAULT_MAX_KEYS,
        )
        if max_keys < 1:
            max_keys = S3_DEFAULT_MAX_KEYS
        delimiter = _resolve_str_param(params, "delimiter", item, ectx, ("delimiter",))
        content_type = _resolve_str_param(
            params, "contentType", item, ectx, ("contentType", "content_type")
        ) or S3_DEFAULT_CONTENT_TYPE

        # Operation-specific gate
        content_bytes = b""
        if operation == "upload":
            content_bytes = _resolve_content_bytes(params, item, ectx)
        elif operation in ("download", "delete"):
            if not key:
                logger.info(
                    "s3 %s skipped: no key on node %r", operation, node.name
                )
                continue

        envelope, source = _resolve_s3_response(
            operation=operation,
            bucket=bucket,
            params=params,
            key=key,
            prefix=prefix,
            max_keys=max_keys,
            content_bytes=content_bytes,
            item=item,
            ctx=ctx,
        )

        if operation == "upload":
            payload: dict[str, Any] = {
                "key": envelope.get("key") or key,
                "bucket": envelope.get("bucket") or bucket,
                "etag": envelope.get("etag") or _new_etag(),
                "location": envelope.get("location")
                or f"https://{bucket}.s3.amazonaws.com/{key}",
                "size": envelope.get("size") if isinstance(envelope.get("size"), int) else len(content_bytes),
                "operation": operation,
                "ok": True,
                "source": "s3",
            }
            if source != "s3_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        elif operation == "download":
            payload = {
                "key": envelope.get("key") or key,
                "bucket": envelope.get("bucket") or bucket,
                "body": envelope.get("body") or "",
                "contentType": envelope.get("contentType") or content_type,
                "contentLength": envelope.get("contentLength") or 0,
                "etag": envelope.get("etag") or _new_etag(),
                "operation": operation,
                "ok": True,
                "source": "s3",
            }
            if source != "s3_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        elif operation == "list":
            contents = envelope.get("contents") or []
            if data_mode == "object":
                payload = {
                    "contents": list(contents),
                    "keyCount": envelope.get("keyCount", len(contents)),
                    "bucket": envelope.get("name") or bucket,
                    "prefix": envelope.get("prefix", prefix),
                    "maxKeys": envelope.get("maxKeys", max_keys),
                    "operation": operation,
                    "ok": True,
                    "source": "s3",
                }
                if delimiter:
                    payload["delimiter"] = delimiter
                if source != "s3_response":
                    payload["mockSource"] = source
                ni = item.clone()
                ni.json = {**item.json, **payload}
                out.append(ni)
            else:
                if not contents:
                    payload = {
                        "key": "",
                        "lastModified": "",
                        "etag": "",
                        "size": 0,
                        "contents": [],
                        "bucket": envelope.get("name") or bucket,
                        "prefix": envelope.get("prefix", prefix),
                        "operation": operation,
                        "ok": True,
                        "source": "s3",
                    }
                    if source != "s3_response":
                        payload["mockSource"] = source
                    ni = item.clone()
                    ni.json = {**item.json, **payload}
                    out.append(ni)
                else:
                    for entry in contents:
                        payload = {
                            "key": entry.get("key"),
                            "lastModified": entry.get("lastModified"),
                            "etag": entry.get("etag"),
                            "size": entry.get("size"),
                            "bucket": envelope.get("name") or bucket,
                            "operation": operation,
                            "ok": True,
                            "source": "s3",
                        }
                        if source != "s3_response":
                            payload["mockSource"] = source
                        ni = item.clone()
                        ni.json = {**item.json, **payload}
                        out.append(ni)

        else:  # delete
            payload = {
                "key": envelope.get("key") or key,
                "bucket": envelope.get("bucket") or bucket,
                "deleted": envelope.get("deleted") or [{"Key": key}],
                "operation": operation,
                "ok": True,
                "source": "s3",
            }
            if source != "s3_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        logger.info(
            "s3 %s key=%r bucket=%r prefix=%r maxKeys=%s source=%s",
            operation,
            key[:80],
            bucket[:80],
            prefix,
            max_keys,
            source,
        )
    return [(0, out)]


__all__ = [
    "exec_s3",
    "S3_OPERATIONS",
    "S3_DEFAULT_OPERATION",
    "S3_DEFAULT_CONTENT_TYPE",
    "S3_DEFAULT_MAX_KEYS",
]