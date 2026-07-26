"""Google Drive executor (clean-room n8n ``n8n-nodes-base.googleDrive``).

v1 supports the four operations most commonly used in n8n templates:

- ``upload``   — upload a file; emit one item per input with
  ``{id, name, mimeType, size, webViewLink, source: 'googleDrive'}``.
- ``download`` — download a file by id; emit one item per input with
  ``{id, name, mimeType, content, size, source: 'googleDrive'}``
  (``content`` is base64-encoded).
- ``list``     — list files in a folder; emit one item per file (or one
  item with a ``files`` array when ``parameters.dataMode == 'object'``).
- ``delete``   — delete a file by id; emit one item per input with
  ``{fileId, success, deletedAt, source: 'googleDrive'}``.

Parameters honored:

- ``operation`` (``"upload"`` / ``"download"`` / ``"list"`` / ``"delete"``;
  default ``"list"``)
- ``name``      (string; ``$json.name`` / ``$json.fileName`` fallback)
- ``mimeType``  (string; default ``"application/octet-stream"``)
- ``folderId``  (string; ``$json.folderId`` / ``$json.folder_id`` fallback;
  default ``"root"`` for list)
- ``content``   (string base64 or bytes; ``$json.content`` / ``$json.data``
  fallback for upload)
- ``fileId``    (string; ``$json.fileId`` / ``$json.id`` fallback for
  download/delete)
- ``pageSize``  (int; default 10; max 3 in offline mode)
- ``query``     (optional raw q-string; only echoed offline)
- ``dataMode``  (``"array"`` / ``"object"``; default ``"array"``; only
  meaningful for ``list``)

Behavior precedence:

1. ``ctx.mocks['drive_response']`` — when present, the value drives the
   executor. A dict is used per operation (or operation-specific shape);
   a callable is invoked as
   ``mock(operation, params, item, ctx)`` and may return a dict (used
   per operation) or a non-dict truthy value (wrapped as the
   operation's envelope).
2. ``ctx.mocks['http_response']`` — generic HTTP-response fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is unwrapped
   into the operation envelope.
3. Offline synthetic response with deterministic-looking ids and
   timestamps.

Items missing the data needed for the operation (``name`` + ``content``
for upload, ``fileId`` for download/delete) are skipped (no item
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


DRIVE_OPERATIONS: tuple[str, ...] = ("upload", "download", "list", "delete")
DRIVE_DEFAULT_OPERATION: str = "list"
DRIVE_DEFAULT_MIME_TYPE: str = "application/octet-stream"
DRIVE_DEFAULT_PAGE_SIZE: int = 10
DRIVE_OFFLINE_MAX_FILES: int = 3
DRIVE_OFFLINE_FILE_SIZE: int = 1024


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
        for key in ("value", "name", "id", "address", "email"):
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


def _new_file_id() -> str:
    return f"mock_file_{uuid.uuid4().hex[:16]}"


def _new_listing_id(index: int) -> str:
    return f"mock_{index}_{uuid.uuid4().hex[:8]}"


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
        # Try base64 first, fall back to utf-8
        try:
            return base64.b64decode(raw, validate=True)
        except Exception:
            return raw.encode("utf-8")
    return _coerce_str(raw).encode("utf-8")


def _encode_content_b64(content_bytes: bytes) -> str:
    if not content_bytes:
        return ""
    return base64.b64encode(content_bytes).decode("ascii")


def _synthesize_upload(name: str, mime_type: str, size: int) -> dict[str, Any]:
    file_id = _new_file_id()
    return {
        "id": file_id,
        "name": name,
        "mimeType": mime_type,
        "size": size,
        "createdTime": _now_iso(),
        "webViewLink": f"https://drive.google.com/file/d/{file_id}/view",
    }


def _synthesize_download(file_id: str) -> dict[str, Any]:
    raw = b"mock file content"
    return {
        "id": file_id,
        "name": "mock_file.txt",
        "mimeType": "text/plain",
        "content": base64.b64encode(raw).decode("ascii"),
        "size": len(raw),
    }


def _synthesize_listing(page_size: int) -> dict[str, Any]:
    count = min(page_size, DRIVE_OFFLINE_MAX_FILES)
    files: list[dict[str, Any]] = []
    for i in range(count):
        fid = _new_listing_id(i)
        files.append(
            {
                "id": fid,
                "name": f"mock_file_{i}.txt",
                "mimeType": "text/plain",
                "size": DRIVE_OFFLINE_FILE_SIZE,
                "createdTime": _now_iso(),
            }
        )
    return {"files": files, "nextPageToken": None}


def _synthesize_delete(file_id: str) -> dict[str, Any]:
    return {
        "success": True,
        "fileId": file_id,
        "deletedAt": _now_iso(),
    }


def _coerce_upload_envelope(raw: dict[str, Any], *, name: str, mime_type: str) -> dict[str, Any]:
    file_id = _coerce_str(raw.get("id")) or _new_file_id()
    return {
        "id": file_id,
        "name": _coerce_str(raw.get("name")) or name,
        "mimeType": _coerce_str(raw.get("mimeType")) or mime_type,
        "size": int(raw["size"]) if isinstance(raw.get("size"), (int, float)) and not isinstance(raw.get("size"), bool) else DRIVE_OFFLINE_FILE_SIZE,
        "createdTime": _coerce_str(raw.get("createdTime")) or _now_iso(),
        "webViewLink": _coerce_str(raw.get("webViewLink"))
        or f"https://drive.google.com/file/d/{file_id}/view",
    }


def _coerce_download_envelope(raw: dict[str, Any], *, file_id: str) -> dict[str, Any]:
    content = raw.get("content")
    if isinstance(content, (bytes, bytearray)):
        content_b64 = base64.b64encode(bytes(content)).decode("ascii")
    elif isinstance(content, str):
        content_b64 = content
    else:
        content_b64 = base64.b64encode(b"mock file content").decode("ascii")
    declared_size = raw.get("size")
    if isinstance(declared_size, (int, float)) and not isinstance(declared_size, bool):
        size = int(declared_size)
    else:
        try:
            size = len(base64.b64decode(content_b64)) if content_b64 else 0
        except Exception:
            size = 0
    return {
        "id": _coerce_str(raw.get("id")) or file_id,
        "name": _coerce_str(raw.get("name")) or "mock_file.txt",
        "mimeType": _coerce_str(raw.get("mimeType")) or "text/plain",
        "content": content_b64,
        "size": size,
    }


def _coerce_listing_envelope(raw: dict[str, Any], *, page_size: int) -> dict[str, Any]:
    files_raw = raw.get("files")
    if not isinstance(files_raw, list):
        files_raw = []
    files: list[dict[str, Any]] = []
    for i, entry in enumerate(files_raw[: max(page_size, 1)]):
        if not isinstance(entry, dict):
            continue
        fid = _coerce_str(entry.get("id")) or _new_listing_id(i)
        files.append(
            {
                "id": fid,
                "name": _coerce_str(entry.get("name")) or f"mock_file_{i}.txt",
                "mimeType": _coerce_str(entry.get("mimeType")) or "text/plain",
                "size": int(entry["size"])
                if isinstance(entry.get("size"), (int, float)) and not isinstance(entry.get("size"), bool)
                else DRIVE_OFFLINE_FILE_SIZE,
                "createdTime": _coerce_str(entry.get("createdTime")) or _now_iso(),
            }
        )
    return {
        "files": files,
        "nextPageToken": raw.get("nextPageToken") if raw.get("nextPageToken") is not None else None,
    }


def _coerce_delete_envelope(raw: dict[str, Any], *, file_id: str) -> dict[str, Any]:
    return {
        "success": bool(raw.get("success", True)),
        "fileId": _coerce_str(raw.get("fileId")) or file_id,
        "deletedAt": _coerce_str(raw.get("deletedAt")) or _now_iso(),
    }


def _drive_response_from_http_mock(
    mock: Any, *, operation: str
) -> dict[str, Any] | None:
    """Extract a Drive-style envelope from a generic ``http_response`` mock."""
    if not isinstance(mock, dict):
        return None
    body = mock.get("body")
    if not isinstance(body, dict):
        if isinstance(body, str) and body.strip():
            # Wrap a string body in a synthetic envelope
            if operation == "list":
                return {"files": [], "nextPageToken": None, "raw": body}
            if operation == "delete":
                return {"success": True, "fileId": "", "deletedAt": _now_iso(), "raw": body}
            return {"id": _new_file_id(), "name": "mock_file.txt", "mimeType": "text/plain", "raw": body}
        return None
    if operation == "list":
        return _coerce_listing_envelope(body, page_size=DRIVE_OFFLINE_MAX_FILES)
    if operation == "delete":
        return _coerce_delete_envelope(body, file_id="")
    if operation == "download":
        return _coerce_download_envelope(body, file_id="")
    return _coerce_upload_envelope(body, name="mock_file.txt", mime_type=DRIVE_DEFAULT_MIME_TYPE)


def _resolve_drive_response(
    *,
    operation: str,
    params: dict[str, Any],
    name: str,
    mime_type: str,
    file_id: str,
    page_size: int,
    item: ExecutionItem,
    ctx: "EngineContext",
) -> tuple[dict[str, Any], str]:
    """Return ``(envelope, source)`` for the current call.

    ``source`` is one of ``"drive_response"``, ``"http_response"``,
    ``"offline"`` so downstream observers can tell where the result came
    from.
    """
    mocks = ctx.mocks or {}
    dmock = mocks.get("drive_response")
    if dmock is not None:
        if callable(dmock):
            raw = dmock(operation, params, item, ctx)
        else:
            raw = dmock
        if isinstance(raw, dict):
            if operation == "upload":
                return _coerce_upload_envelope(raw, name=name, mime_type=mime_type), "drive_response"
            if operation == "download":
                return _coerce_download_envelope(raw, file_id=file_id), "drive_response"
            if operation == "list":
                return _coerce_listing_envelope(raw, page_size=page_size), "drive_response"
            return _coerce_delete_envelope(raw, file_id=file_id), "drive_response"
        # Non-dict truthy → wrap as a synthetic envelope
        if operation == "list":
            return (
                {"files": [], "nextPageToken": None, "raw": raw},
                "drive_response",
            )
        if operation == "delete":
            return (
                {"success": True, "fileId": file_id, "deletedAt": _now_iso(), "raw": raw},
                "drive_response",
            )
        if operation == "download":
            return (
                {
                    "id": file_id or _new_file_id(),
                    "name": "mock_file.txt",
                    "mimeType": "text/plain",
                    "content": base64.b64encode(b"mock file content").decode("ascii"),
                    "size": 17,
                    "raw": raw,
                },
                "drive_response",
            )
        return (
            {
                "id": _new_file_id(),
                "name": name,
                "mimeType": mime_type,
                "size": DRIVE_OFFLINE_FILE_SIZE,
                "createdTime": _now_iso(),
                "webViewLink": "https://drive.google.com/file/d/mock_id/view",
                "raw": raw,
            },
            "drive_response",
        )

    hmock = mocks.get("http_response")
    if hmock is not None:
        env = _drive_response_from_http_mock(hmock, operation=operation)
        if env is not None:
            if operation == "list":
                return env, "http_response"
            if operation == "delete":
                return env, "http_response"
            if operation == "download":
                return env, "http_response"
            return env, "http_response"

    if operation == "upload":
        return _synthesize_upload(name, mime_type, DRIVE_OFFLINE_FILE_SIZE), "offline"
    if operation == "download":
        return _synthesize_download(file_id or _new_file_id()), "offline"
    if operation == "list":
        return _synthesize_listing(page_size), "offline"
    return _synthesize_delete(file_id or _new_file_id()), "offline"


async def exec_google_drive(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Google Drive node — routes on ``parameters.operation``."""
    params = node.parameters or {}
    operation = str(params.get("operation") or DRIVE_DEFAULT_OPERATION)
    if operation not in DRIVE_OPERATIONS:
        raise ValueError(
            f"googleDrive: unsupported operation {operation!r}; "
            f"expected one of {DRIVE_OPERATIONS}"
        )

    data_mode = str(params.get("dataMode") or "array").strip().lower()
    if data_mode not in ("array", "object"):
        data_mode = "array"

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        # Shared
        name = _resolve_str_param(
            params, "name", item, ectx, ("name", "fileName")
        ) or "mock_file.txt"
        mime_type = _resolve_str_param(
            params, "mimeType", item, ectx, ("mimeType", "mime_type")
        ) or DRIVE_DEFAULT_MIME_TYPE
        folder_id = _resolve_str_param(
            params, "folderId", item, ectx, ("folderId", "folder_id")
        )
        file_id = _resolve_str_param(
            params, "fileId", item, ectx, ("fileId", "id")
        )
        page_size = _coerce_int(
            evaluate(params.get("pageSize"), ectx) if params.get("pageSize") is not None else item.json.get("pageSize"),
            DRIVE_DEFAULT_PAGE_SIZE,
        )
        if page_size < 1:
            page_size = DRIVE_DEFAULT_PAGE_SIZE

        # Operation-specific gate
        if operation == "upload":
            content_bytes = _resolve_content_bytes(params, item, ectx)
            if not name and not content_bytes:
                logger.info(
                    "googleDrive upload skipped: no name or content on node %r",
                    node.name,
                )
                continue
            size = len(content_bytes) if content_bytes else DRIVE_OFFLINE_FILE_SIZE
        elif operation in ("download", "delete"):
            if not file_id:
                logger.info(
                    "googleDrive %s skipped: no fileId on node %r",
                    operation,
                    node.name,
                )
                continue
        elif operation == "list":
            if not folder_id:
                folder_id = "root"

        envelope, source = _resolve_drive_response(
            operation=operation,
            params=params,
            name=name,
            mime_type=mime_type,
            file_id=file_id,
            page_size=page_size,
            item=item,
            ctx=ctx,
        )

        if operation == "upload":
            # Use the synthetic size when the envelope is the default 1024
            # and the caller provided actual content — override with real size.
            upload_size = envelope.get("size")
            if not isinstance(upload_size, int) or upload_size == DRIVE_OFFLINE_FILE_SIZE:
                if content_bytes:
                    upload_size = len(content_bytes)
                else:
                    upload_size = DRIVE_OFFLINE_FILE_SIZE
            payload: dict[str, Any] = {
                "id": envelope.get("id"),
                "name": envelope.get("name") or name,
                "mimeType": envelope.get("mimeType") or mime_type,
                "size": upload_size,
                "webViewLink": envelope.get("webViewLink")
                or f"https://drive.google.com/file/d/{envelope.get('id')}/view",
                "operation": operation,
                "ok": True,
                "source": "googleDrive",
            }
            if folder_id:
                payload["folderId"] = folder_id
            if source != "drive_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        elif operation == "download":
            payload = {
                "id": envelope.get("id") or file_id,
                "name": envelope.get("name") or "mock_file.txt",
                "mimeType": envelope.get("mimeType") or "text/plain",
                "content": envelope.get("content") or "",
                "size": envelope.get("size") or 0,
                "operation": operation,
                "ok": True,
                "source": "googleDrive",
            }
            if source != "drive_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        elif operation == "list":
            files = envelope.get("files") or []
            if data_mode == "object":
                payload = {
                    "files": list(files),
                    "folderId": folder_id,
                    "pageSize": page_size,
                    "nextPageToken": envelope.get("nextPageToken"),
                    "operation": operation,
                    "ok": True,
                    "source": "googleDrive",
                }
                if source != "drive_response":
                    payload["mockSource"] = source
                ni = item.clone()
                ni.json = {**item.json, **payload}
                out.append(ni)
            else:
                if not files:
                    # No files: still emit one item so downstream nodes see the run.
                    payload = {
                        "id": "",
                        "name": "",
                        "mimeType": "",
                        "size": 0,
                        "files": [],
                        "folderId": folder_id,
                        "operation": operation,
                        "ok": True,
                        "source": "googleDrive",
                    }
                    if source != "drive_response":
                        payload["mockSource"] = source
                    ni = item.clone()
                    ni.json = {**item.json, **payload}
                    out.append(ni)
                else:
                    for entry in files:
                        payload = {
                            "id": entry.get("id"),
                            "name": entry.get("name"),
                            "mimeType": entry.get("mimeType"),
                            "size": entry.get("size"),
                            "folderId": folder_id,
                            "operation": operation,
                            "ok": True,
                            "source": "googleDrive",
                        }
                        if source != "drive_response":
                            payload["mockSource"] = source
                        ni = item.clone()
                        ni.json = {**item.json, **payload}
                        out.append(ni)

        else:  # delete
            payload = {
                "fileId": envelope.get("fileId") or file_id,
                "success": bool(envelope.get("success", True)),
                "deletedAt": envelope.get("deletedAt") or _now_iso(),
                "operation": operation,
                "ok": bool(envelope.get("success", True)),
                "source": "googleDrive",
            }
            if source != "drive_response":
                payload["mockSource"] = source
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        logger.info(
            "googleDrive %s name=%r fileId=%r folderId=%r pageSize=%s source=%s",
            operation,
            name[:80],
            file_id[:80],
            folder_id,
            page_size,
            source,
        )
    return [(0, out)]


__all__ = [
    "exec_google_drive",
    "DRIVE_OPERATIONS",
    "DRIVE_DEFAULT_OPERATION",
    "DRIVE_DEFAULT_MIME_TYPE",
    "DRIVE_DEFAULT_PAGE_SIZE",
]
