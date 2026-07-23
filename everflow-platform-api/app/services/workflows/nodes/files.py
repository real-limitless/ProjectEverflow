"""File extract / convert executors (binary <-> text/csv)."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, Any

from app.services.workflows.graph import ExecNode
from app.services.workflows.items import BinaryFile, ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext


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
