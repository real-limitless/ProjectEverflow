"""File extract / convert executors (binary <-> text/csv)."""

from __future__ import annotations

import csv
import io
import mimetypes
import os
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext


_MIME_BY_EXT: dict[str, str] = {
    "txt": "text/plain",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "json": "application/json",
    "xml": "application/xml",
    "html": "text/html",
    "htm": "text/html",
    "md": "text/markdown",
    "yaml": "application/x-yaml",
    "yml": "application/x-yaml",
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "svg": "image/svg+xml",
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


def _basename(path: str) -> str:
    cleaned = path.rstrip("/\\")
    if not cleaned:
        return ""
    return cleaned.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _join_path(directory: str, file_name: str) -> str:
    if not directory:
        return file_name
    if not file_name:
        return directory
    sep = "/" if "/" in directory or not directory.endswith("\\") else "\\"
    if directory.endswith("/") or directory.endswith("\\"):
        return f"{directory}{file_name}"
    return f"{directory}{sep}{file_name}"


def _filesystem_mock(ctx: EngineContext) -> dict[str, Any] | None:
    """Return the live filesystem mock dict (or None).

    The returned reference is the same object stored on ``ctx.mocks`` so
    writes from this executor are visible to subsequent calls within
    the same run.
    """
    if not isinstance(ctx.mocks, dict):
        return None
    raw = ctx.mocks.get("filesystem")
    if not isinstance(raw, dict):
        return None
    return raw


def _coerce_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    return str(value).encode("utf-8")


def _base_dir(ctx: EngineContext, node: ExecNode) -> str | None:
    raw = ctx.mocks.get("baseDir") if isinstance(ctx.mocks, dict) else None
    if isinstance(raw, str) and raw:
        return raw
    params = node.parameters or {}
    p = params.get("baseDir")
    if isinstance(p, str) and p:
        return p
    env = os.environ.get("EVERFLOW_DEV_BASEDIR")
    if env:
        return env
    return None


def _exec_read_write_file_item(  # noqa: PLR0915
    item: ExecutionItem,
    node: ExecNode,
    *,
    ctx: EngineContext,
    ectx: ExpressionContext,
    mock_fs: dict[str, Any] | None,
    base_dir: str | None,
    base_name: str,
) -> ExecutionItem:
    params = node.parameters or {}
    operation = str(params.get("operation") or "read")
    data_property = str(params.get("dataPropertyName") or "data")

    if operation == "read":
        raw_path = params.get("filePath")
        path = evaluate(raw_path, ectx)
        if path is None or path == "":
            path = evaluate(params.get("fileSelector"), ectx) or ""
        path = str(path or "")
        if not path:
            raise ValueError(
                f"{base_name}: filePath is required for read operation",
            )
        if not os.path.isabs(path) and base_dir:
            path = os.path.join(base_dir, path)

        bytes_data: bytes | None = None
        if mock_fs is not None:
            if path in mock_fs:
                bytes_data = _coerce_bytes(mock_fs[path])
            else:
                # try basename fallback for tests
                bn = _basename(path)
                for k, v in mock_fs.items():
                    if _basename(k) == bn and bn:
                        bytes_data = _coerce_bytes(v)
                        break
            if bytes_data is None:
                raise FileNotFoundError(
                    f"{base_name}: mock file not found: {path}",
                )
        else:
            if not base_dir:
                raise RuntimeError(
                    f"{base_name}: no ctx.mocks['filesystem'] and no baseDir configured; "
                    "this executor is a thin local fallback and must not touch real disk in production. "
                    "Production should route through the sandbox-agent.",
                )
            if not os.path.exists(path):
                raise FileNotFoundError(f"{base_name}: file not found: {path}")
            with open(path, "rb") as f:
                bytes_data = f.read()

        file_name = _basename(path) or "file"
        mime = _infer_mime(file_name)
        bf = BinaryFile.from_bytes(bytes_data, file_name=file_name, mime_type=mime)
        ni = item.clone()
        ni.binary = {data_property: bf}
        ni.json = {**item.json, "fileName": file_name, "mimeType": mime, "filePath": path}
        return ni

    if operation == "write":
        # Decide target path
        raw_path = params.get("filePath")
        evaluated_path = evaluate(raw_path, ectx) if raw_path is not None else None
        if evaluated_path:
            path = str(evaluated_path)
        else:
            directory = str(evaluate(params.get("directory"), ectx) or "")
            file_name = ""
            configured = evaluate(params.get("fileName"), ectx)
            if isinstance(configured, str) and configured:
                file_name = configured
            elif isinstance(item.json.get("fileName"), str) and item.json.get("fileName"):
                file_name = item.json["fileName"]
            elif data_property in item.binary and item.binary[data_property].file_name:
                file_name = item.binary[data_property].file_name
            if not file_name and not directory:
                raise ValueError(
                    f"{base_name}: write requires filePath or (directory + fileName) or item.binary['{data_property}']",
                )
            path = _join_path(directory, file_name) if directory else file_name

        if not os.path.isabs(path) and base_dir:
            path = os.path.join(base_dir, path)

        # Resolve payload bytes
        bf = item.binary.get(data_property) if data_property in item.binary else None
        if bf is not None:
            bytes_data = bf.to_bytes()
            file_name_out = bf.file_name or _basename(path) or "file"
            mime = bf.mime_type or _infer_mime(file_name_out)
        else:
            raw_value = item.json.get(data_property)
            if raw_value is None:
                raise ValueError(
                    f"{base_name}: write requires item.json['{data_property}'] or item.binary['{data_property}']",
                )
            if isinstance(raw_value, (bytes, bytearray)):
                bytes_data = bytes(raw_value)
            else:
                bytes_data = str(raw_value).encode("utf-8")
            file_name_out = _basename(path) or "file"
            mime = _infer_mime(file_name_out)

        if mock_fs is not None:
            mock_fs[path] = bytes_data
        else:
            if not base_dir:
                raise RuntimeError(
                    f"{base_name}: no ctx.mocks['filesystem'] and no baseDir configured; "
                    "this executor is a thin local fallback and must not touch real disk in production. "
                    "Production should route through the sandbox-agent.",
                )
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "wb") as f:
                f.write(bytes_data)

        ni = item.clone()
        ni.json = {
            **item.json,
            "filePath": path,
            "fileName": file_name_out,
            "mimeType": mime,
            "size": len(bytes_data),
        }
        return ni

    raise ValueError(f"{base_name}: unsupported operation {operation!r}")


async def exec_read_write_file(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Read/Write File — read filesystem paths into item binary, or write item
    data out to filesystem paths.

    Clean-room n8n ``n8n-nodes-base.readWriteFile`` v1.

    Operations:

    - ``read`` — read ``parameters.filePath`` (string or ``={{...}}`` expression)
      and put the bytes into ``item.binary[parameters.dataPropertyName]``
      (default ``"data"``) as a ``BinaryFile``. The basename and inferred mime
      type are also surfaced on the item JSON as ``fileName``/``mimeType``.
    - ``write`` — read ``parameters.dataPropertyName`` (default ``"data"``)
      on each input item. If the property is on ``item.binary`` the bytes
      are used as-is, otherwise the JSON value is UTF-8 encoded. Output goes
      to ``parameters.filePath``, or to ``parameters.directory +
      parameters.fileName`` when ``filePath`` is absent (e.g. when writing
      per-item filenames). ``item.json.fileName`` and
      ``item.binary[data].file_name`` are also consulted for the per-item
      name when ``filePath`` is not configured.

    Routing:

    - In production the platform API should always proxy file IO to the
      sandbox-agent; this executor is a thin local fallback.
    - When ``ctx.mocks['filesystem']`` is a dict of path → bytes, all reads
      and writes hit that dict and the real filesystem is never touched.
    - When no mock is set, a developer-only ``baseDir`` (from
      ``ctx.mocks['baseDir']``, ``parameters.baseDir``, or
      ``$EVERFLOW_DEV_BASEDIR``) is required; otherwise a clear ``RuntimeError``
      is raised. Tests must always go through ``ctx.mocks['filesystem']``.
    """
    mock_fs = _filesystem_mock(ctx)
    base_dir = _base_dir(ctx, node)
    base_name = node.name or node.id or "ReadWriteFile"

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)
        ni = _exec_read_write_file_item(
            item,
            node,
            ctx=ctx,
            ectx=ectx,
            mock_fs=mock_fs,
            base_dir=base_dir,
            base_name=base_name,
        )
        out.append(ni)
    return [(0, out)]


def _primary_binary(item: ExecutionItem) -> tuple[str, BinaryFile] | None:
    if not item.binary:
        return None
    if "data" in item.binary:
        return "data", item.binary["data"]
    key = next(iter(item.binary))
    return key, item.binary[key]


async def exec_extract_from_file(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    params = node.parameters or {}
    operation = str(params.get("operation") or "csv")
    dest_key = str(params.get("destinationKey") or "data")
    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    out: list[ExecutionItem] = []

    for item in items:
        pair = _primary_binary(item)
        if pair is None:
            # maybe text already on json
            out.append(item)
            continue
        _, bf = pair
        raw = bf.to_bytes()
        text = raw.decode("utf-8", errors="replace")

        if operation == "text":
            ni = item.clone()
            ni.json = {**item.json, dest_key: text}
            out.append(ni)
            continue

        # CSV parse (default)
        header_row = bool(options.get("headerRow", True))
        skip_err = options.get("skipRecordsWithErrors")
        # n8n nests skipRecordsWithErrors oddly
        reader = csv.DictReader(io.StringIO(text)) if header_row else None
        if header_row and reader is not None:
            for row in reader:
                try:
                    ni = item.clone()
                    ni.json = {**item.json, **dict(row)}
                    # drop binary after parse (optional)
                    ni.binary = {}
                    out.append(ni)
                except Exception:
                    if skip_err:
                        continue
                    raise
        else:
            rdr = csv.reader(io.StringIO(text))
            for row in rdr:
                ni = item.clone()
                ni.json = {**item.json, "row": row}
                ni.binary = {}
                out.append(ni)
    return [(0, out)]


async def exec_convert_to_file(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    params = node.parameters or {}
    operation = str(params.get("operation") or "toText")
    source_prop = str(params.get("sourceProperty") or "data")
    out: list[ExecutionItem] = []
    for item in items:
        if operation in ("toText", "text"):
            text = str(item.json.get(source_prop) or "")
            bf = BinaryFile.from_bytes(
                text.encode("utf-8"),
                file_name="file.txt",
                mime_type="text/plain",
            )
            ni = item.clone()
            ni.binary = {"data": bf}
            out.append(ni)
        else:
            out.append(item)
    return [(0, out)]
