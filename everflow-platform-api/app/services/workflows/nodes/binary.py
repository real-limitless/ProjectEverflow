"""Binary data executors (clean-room n8n-nodes-base.*).

Covers:

- ``itemLists``       — split / aggregate / flatten item collections.
- ``moveBinaryData``  — convert between JSON and binary representations.
- ``readBinaryFile``  — read a single file from disk into binary data.
- ``readBinaryFiles`` — read multiple files from a directory into binary data.
- ``writeBinaryFile`` — write binary data to a file on disk.
- ``spreadsheetFile`` — read / write CSV and XLSX spreadsheet files.
- ``readPDF``         — extract text from a PDF file.

Every executor follows the mock precedence:

1. ``ctx.mocks['<node_name>_response']`` — callable or dict.
   If callable, invoked as ``mock(operation, params, item, ctx)``.
   If dict, used directly.
2. ``ctx.mocks['http_response']`` — generic fallback
   ``{status_code, body, headers}``.
3. Offline synthetic response — deterministic-looking ids and ISO
   timestamps.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import logging
import mimetypes
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import BinaryFile, ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


ITEM_LISTS_OPERATIONS: tuple[str, ...] = ("splitOut", "aggregate", "flatten")
ITEM_LISTS_DEFAULT_OPERATION: str = "splitOut"

MOVE_BINARY_OPERATIONS: tuple[str, ...] = ("jsonToBinary", "binaryToJson")
MOVE_BINARY_DEFAULT_OPERATION: str = "jsonToBinary"

SPREADSHEET_OPERATIONS: tuple[str, ...] = ("read", "write")
SPREADSHEET_DEFAULT_OPERATION: str = "read"
SPREADSHEET_FORMATS: tuple[str, ...] = ("csv", "xlsx")

READ_PDF_OPERATIONS: tuple[str, ...] = ("pdfExtractText",)
READ_PDF_DEFAULT_OPERATION: str = "pdfExtractText"


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _new_id(prefix: str = "mock") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _basename(path: str) -> str:
    cleaned = path.rstrip("/\\")
    if not cleaned:
        return ""
    return cleaned.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


_MIME_BY_EXT: dict[str, str] = {
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
}


def _infer_mime(file_name: str) -> str:
    if not file_name:
        return "application/octet-stream"
    ext = ""
    if "." in file_name:
        ext = file_name.rsplit(".", 1)[-1].lower()
    if ext and ext in _MIME_BY_EXT:
        return _MIME_BY_EXT[ext]
    if ext:
        guess, _ = mimetypes.guess_type(file_name)
        if guess:
            return guess
    return "application/octet-stream"


def _ectx(item: ExecutionItem, ctx: "EngineContext") -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return str(value)


def _resolve_node_mock(
    key: str,
    *,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> Any | None:
    mocks = ctx.mocks or {}
    mock = mocks.get(key)
    if mock is None:
        return None
    if callable(mock):
        return mock(operation, params, item, ctx)
    return mock


def _resolve_http_body(ctx: "EngineContext") -> Any | None:
    mocks = ctx.mocks or {}
    hmock = mocks.get("http_response")
    if not isinstance(hmock, dict):
        return None
    body = hmock.get("body")
    if body is None:
        return hmock
    return body


def _mock_to_items(raw: Any, base: ExecutionItem) -> list[ExecutionItem]:
    if isinstance(raw, list):
        out: list[ExecutionItem] = []
        for entry in raw:
            if isinstance(entry, dict):
                ni = base.clone()
                ni.json = {**base.json, **entry}
                out.append(ni)
            else:
                ni = base.clone()
                ni.json = {**base.json, "value": entry}
                out.append(ni)
        return out
    if isinstance(raw, dict):
        ni = base.clone()
        ni.json = {**base.json, **raw}
        return [ni]
    ni = base.clone()
    ni.json = {**base.json, "value": raw}
    return [ni]


def _resolve_mock_or_http(
    mock_key: str,
    *,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
) -> list[ExecutionItem] | None:
    mock = _resolve_node_mock(
        mock_key,
        operation=operation,
        params=params,
        item=item,
        ctx=ctx,
    )
    if mock is not None:
        return _mock_to_items(mock, item)
    http_body = _resolve_http_body(ctx)
    if http_body is not None:
        return _mock_to_items(http_body, item)
    return None


async def exec_item_lists(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Item Lists (legacy) — split / aggregate / flatten item collections.

    Clean-room n8n ``n8n-nodes-base.itemLists`` v1.

    Operations:

    - ``splitOut``  — split a list field into separate items.
    - ``aggregate`` — combine items into a single item with a list field.
    - ``flatten``   — flatten nested arrays in a field.
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or ITEM_LISTS_DEFAULT_OPERATION)
    field = str(params.get("field") or "data")
    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    dest_field = str(options.get("destinationFieldName") or field)

    if operation == "aggregate":
        base = items[0] if items else ExecutionItem()
        mock_items = _resolve_mock_or_http(
            "itemLists_response",
            operation=operation,
            params=params,
            item=base,
            ctx=ctx,
        )
        if mock_items is not None:
            return [(0, mock_items)]
        collected: list[Any] = []
        for item in items:
            if field in item.json:
                collected.append(item.json[field])
        ni = base.clone()
        ni.json = {**base.json, dest_field: collected, "count": len(collected)}
        return [(0, [ni])]

    out: list[ExecutionItem] = []
    for item in items:
        mock_items = _resolve_mock_or_http(
            "itemLists_response",
            operation=operation,
            params=params,
            item=item,
            ctx=ctx,
        )
        if mock_items is not None:
            out.extend(mock_items)
            continue

        if operation == "splitOut":
            value = item.json.get(field)
            if isinstance(value, list):
                for element in value:
                    ni = item.clone()
                    if isinstance(element, dict):
                        ni.json = {**item.json, **element}
                    else:
                        ni.json = {**item.json, dest_field: element}
                    out.append(ni)
            else:
                out.append(item)
        elif operation == "flatten":
            value = item.json.get(field)
            if isinstance(value, list):
                flat: list[Any] = []
                for element in value:
                    if isinstance(element, list):
                        flat.extend(element)
                    else:
                        flat.append(element)
                ni = item.clone()
                ni.json = {**item.json, dest_field: flat}
                out.append(ni)
            else:
                out.append(item)
        else:
            out.append(item)

    return [(0, out)]


async def exec_move_binary_data(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Move Binary Data — convert between JSON and binary representations.

    Clean-room n8n ``n8n-nodes-base.moveBinaryData`` v1.

    Operations:

    - ``jsonToBinary``  — convert a JSON field to a binary property.
    - ``binaryToJson``  — convert a binary property to a JSON field.
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or MOVE_BINARY_DEFAULT_OPERATION)
    source = str(params.get("source") or "data")
    destination = str(params.get("destination") or "data")
    options = params.get("options") if isinstance(params.get("options"), dict) else {}

    out: list[ExecutionItem] = []
    for item in items:
        mock_items = _resolve_mock_or_http(
            "moveBinaryData_response",
            operation=operation,
            params=params,
            item=item,
            ctx=ctx,
        )
        if mock_items is not None:
            out.extend(mock_items)
            continue

        if operation == "jsonToBinary":
            raw_value = item.json.get(source)
            if raw_value is None:
                out.append(item)
                continue
            if isinstance(raw_value, (bytes, bytearray)):
                raw_bytes = bytes(raw_value)
            elif isinstance(raw_value, str):
                encoding = str(options.get("encoding") or "utf-8")
                try:
                    raw_bytes = base64.b64decode(raw_value, validate=True)
                except Exception:
                    raw_bytes = raw_value.encode(encoding)
            else:
                raw_bytes = json.dumps(raw_value).encode("utf-8")
            file_name = str(options.get("fileName") or destination)
            mime_type = str(options.get("mimeType") or _infer_mime(file_name))
            bf = BinaryFile.from_bytes(
                raw_bytes, file_name=file_name, mime_type=mime_type,
            )
            ni = item.clone()
            ni.binary = {**item.binary, destination: bf}
            out.append(ni)
        elif operation == "binaryToJson":
            bf = item.binary.get(source) if item.binary else None
            ni = item.clone()
            if bf is not None:
                raw_bytes = bf.to_bytes()
                encoding = str(options.get("encoding") or "utf-8")
                ni.json = {
                    **item.json,
                    destination: raw_bytes.decode(encoding, errors="replace"),
                }
            else:
                ni.json = {**item.json, destination: ""}
            out.append(ni)
        else:
            out.append(item)

    return [(0, out)]


async def exec_read_binary_file(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Read Binary File — read a single file from disk into binary data.

    Clean-room n8n ``n8n-nodes-base.readBinaryFile`` v1.

    Emits one item per input with ``{data, fileName, mimeType, fileSize,
    filePath}`` on the JSON and a ``BinaryFile`` under ``item.binary['data']``.
    """
    params = node.parameters or {}
    options = params.get("options") if isinstance(params.get("options"), dict) else {}

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        file_path = str(evaluate(params.get("filePath"), ectx) or "")
        file_name = str(options.get("fileName") or _basename(file_path) or "file")

        mock_items = _resolve_mock_or_http(
            "readBinaryFile_response",
            operation="read",
            params=params,
            item=item,
            ctx=ctx,
        )
        if mock_items is not None:
            out.extend(mock_items)
            continue

        raw = b"mock file content"
        data_b64 = base64.b64encode(raw).decode("ascii")
        mime = _infer_mime(file_name)
        ni = item.clone()
        ni.json = {
            **item.json,
            "data": data_b64,
            "fileName": file_name,
            "mimeType": mime,
            "fileSize": len(raw),
            "filePath": file_path,
        }
        ni.binary = {
            "data": BinaryFile.from_bytes(
                raw, file_name=file_name, mime_type=mime,
            )
        }
        out.append(ni)

    return [(0, out)]


async def exec_read_binary_files(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Read Binary Files — read multiple files from a directory into binary data.

    Clean-room n8n ``n8n-nodes-base.readBinaryFiles`` v1.

    Emits one item per file with ``{data, fileName, mimeType, fileSize,
    filePath}`` on the JSON and a ``BinaryFile`` under ``item.binary['data']``.
    """
    params = node.parameters or {}

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        folder = str(evaluate(params.get("fileFolderPath"), ectx) or "")

        mock_items = _resolve_mock_or_http(
            "readBinaryFiles_response",
            operation="read",
            params=params,
            item=item,
            ctx=ctx,
        )
        if mock_items is not None:
            out.extend(mock_items)
            continue

        for i in range(3):
            fname = f"mock_file_{i}.txt"
            raw = f"mock file content {i}".encode("utf-8")
            data_b64 = base64.b64encode(raw).decode("ascii")
            mime = _infer_mime(fname)
            ni = item.clone()
            ni.json = {
                **item.json,
                "data": data_b64,
                "fileName": fname,
                "mimeType": mime,
                "fileSize": len(raw),
                "filePath": f"{folder}/{fname}" if folder else fname,
            }
            ni.binary = {
                "data": BinaryFile.from_bytes(
                    raw, file_name=fname, mime_type=mime,
                )
            }
            out.append(ni)

    return [(0, out)]


async def exec_write_binary_file(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Write Binary File — write binary data to a file on disk.

    Clean-room n8n ``n8n-nodes-base.writeBinaryFile`` v1.

    Emits one item per input with ``{fileName, filePath, fileSize,
    success}``.
    """
    params = node.parameters or {}
    data_prop = str(params.get("dataPropertyName") or "data")
    options = params.get("options") if isinstance(params.get("options"), dict) else {}

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        file_path = str(evaluate(params.get("filePath"), ectx) or "")
        file_name = _basename(file_path) or str(options.get("fileName") or "file")

        mock_items = _resolve_mock_or_http(
            "writeBinaryFile_response",
            operation="write",
            params=params,
            item=item,
            ctx=ctx,
        )
        if mock_items is not None:
            out.extend(mock_items)
            continue

        bf = item.binary.get(data_prop) if item.binary else None
        if bf is not None:
            raw = bf.to_bytes()
            size = len(raw)
            file_name = bf.file_name or file_name
        else:
            raw_value = item.json.get(data_prop)
            if raw_value is None:
                size = 0
            elif isinstance(raw_value, (bytes, bytearray)):
                size = len(raw_value)
            else:
                size = len(str(raw_value).encode("utf-8"))

        ni = item.clone()
        ni.json = {
            **item.json,
            "fileName": file_name,
            "filePath": file_path,
            "fileSize": size,
            "success": True,
        }
        out.append(ni)

    return [(0, out)]


async def exec_spreadsheet_file(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Spreadsheet File — read / write CSV and XLSX spreadsheet files.

    Clean-room n8n ``n8n-nodes-base.spreadsheetFile`` v1.

    Operations:

    - ``read``  — parse CSV/XLSX into items (one per row).
    - ``write`` — write items to CSV/XLSX and emit one item with binary.
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or SPREADSHEET_DEFAULT_OPERATION)
    file_format = str(params.get("fileFormat") or "csv").lower()
    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    header_row = bool(options.get("headerRow", True))
    binary_prop = str(params.get("binaryPropertyName") or "data")

    if operation == "write":
        base = items[0] if items else ExecutionItem()
        mock_items = _resolve_mock_or_http(
            "spreadsheetFile_response",
            operation=operation,
            params=params,
            item=base,
            ctx=ctx,
        )
        if mock_items is not None:
            return [(0, mock_items)]

        buf = io.StringIO()
        writer = csv.writer(buf)
        keys: list[str] = []
        for ri in items:
            for k in ri.json.keys():
                if k not in keys:
                    keys.append(k)
        if header_row and keys:
            writer.writerow(keys)
        for ri in items:
            if header_row and keys:
                writer.writerow([_coerce_str(ri.json.get(k)) for k in keys])
            else:
                writer.writerow([_coerce_str(v) for v in ri.json.values()])
        raw = buf.getvalue().encode("utf-8")
        file_name = f"spreadsheet.{file_format}"
        mime = _infer_mime(file_name)
        ni = base.clone()
        ni.json = {
            **base.json,
            "fileName": file_name,
            "fileSize": len(raw),
            "format": file_format,
        }
        ni.binary = {
            binary_prop: BinaryFile.from_bytes(
                raw, file_name=file_name, mime_type=mime,
            )
        }
        return [(0, [ni])]

    out: list[ExecutionItem] = []
    for item in items:
        mock_items = _resolve_mock_or_http(
            "spreadsheetFile_response",
            operation=operation,
            params=params,
            item=item,
            ctx=ctx,
        )
        if mock_items is not None:
            out.extend(mock_items)
            continue

        bf = item.binary.get(binary_prop) if item.binary else None
        if bf is not None:
            raw_text = bf.to_bytes().decode("utf-8", errors="replace")
        else:
            raw_text = "col1,col2\nval1,val2\nval3,val4\n"

        if file_format in ("csv", "txt"):
            if header_row:
                reader = csv.DictReader(io.StringIO(raw_text))
                for row in reader:
                    ni = item.clone()
                    ni.json = {**item.json, **dict(row)}
                    out.append(ni)
            else:
                rdr = csv.reader(io.StringIO(raw_text))
                for row in rdr:
                    ni = item.clone()
                    ni.json = {**item.json, "row": row}
                    out.append(ni)
        else:
            for i in range(2):
                ni = item.clone()
                ni.json = {
                    **item.json,
                    "col1": f"val{i + 1}",
                    "col2": f"data{i + 1}",
                }
                out.append(ni)

    return [(0, out)]


async def exec_read_pdf(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Read PDF — extract text from a PDF file.

    Clean-room n8n ``n8n-nodes-base.readPDF`` v1.

    Emits one item per input with ``{text, pageCount, fileName}``.
    """
    params = node.parameters or {}
    operation = str(params.get("operation") or READ_PDF_DEFAULT_OPERATION)
    file_field = str(params.get("file") or "data")
    options = params.get("options") if isinstance(params.get("options"), dict) else {}

    out: list[ExecutionItem] = []
    for item in items:
        mock_items = _resolve_mock_or_http(
            "readPDF_response",
            operation=operation,
            params=params,
            item=item,
            ctx=ctx,
        )
        if mock_items is not None:
            out.extend(mock_items)
            continue

        bf = item.binary.get(file_field) if item.binary else None
        file_name = bf.file_name if bf else "document.pdf"

        text = "Mock PDF extracted text content."
        page_count = 1

        try:
            import pypdf  # type: ignore[import-not-found]

            if bf is not None:
                reader = pypdf.PdfReader(io.BytesIO(bf.to_bytes()))
                password = str(options.get("password") or "")
                if password:
                    reader.decrypt(password)
                pages = []
                for page in reader.pages:
                    pages.append(page.extract_text() or "")
                text = "\n".join(pages)
                page_count = len(reader.pages)
        except Exception:
            pass

        ni = item.clone()
        ni.json = {
            **item.json,
            "text": text,
            "pageCount": page_count,
            "fileName": file_name,
        }
        out.append(ni)

    return [(0, out)]