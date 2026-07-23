"""n8n-like execution items (json + optional binary)."""

from __future__ import annotations

import base64
import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BinaryFile:
    data_b64: str
    mime_type: str = "application/octet-stream"
    file_name: str = "file"
    file_extension: str = ""

    @classmethod
    def from_bytes(
        cls,
        raw: bytes,
        *,
        file_name: str = "file",
        mime_type: str = "application/octet-stream",
    ) -> BinaryFile:
        ext = ""
        if "." in file_name:
            ext = file_name.rsplit(".", 1)[-1]
        return cls(
            data_b64=base64.b64encode(raw).decode("ascii"),
            mime_type=mime_type,
            file_name=file_name,
            file_extension=ext,
        )

    def to_bytes(self) -> bytes:
        return base64.b64decode(self.data_b64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data_b64,
            "mimeType": self.mime_type,
            "fileName": self.file_name,
            "fileExtension": self.file_extension,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BinaryFile:
        return cls(
            data_b64=str(d.get("data") or ""),
            mime_type=str(d.get("mimeType") or "application/octet-stream"),
            file_name=str(d.get("fileName") or "file"),
            file_extension=str(d.get("fileExtension") or ""),
        )


@dataclass
class ExecutionItem:
    json: dict[str, Any] = field(default_factory=dict)
    binary: dict[str, BinaryFile] = field(default_factory=dict)
    paired_item: dict[str, Any] | None = None

    def clone(self) -> ExecutionItem:
        return ExecutionItem(
            json=copy.deepcopy(self.json),
            binary={k: BinaryFile(**v.__dict__) for k, v in self.binary.items()},
            paired_item=copy.deepcopy(self.paired_item) if self.paired_item else None,
        )

    def to_public_dict(self, *, max_binary: int = 256) -> dict[str, Any]:
        """Serialize for run logs (truncate large binary)."""
        out: dict[str, Any] = {"json": self.json}
        if self.binary:
            bins: dict[str, Any] = {}
            for k, b in self.binary.items():
                data = b.data_b64
                bins[k] = {
                    "fileName": b.file_name,
                    "mimeType": b.mime_type,
                    "size": len(b.to_bytes()) if data else 0,
                    "data": (data[:max_binary] + "…") if len(data) > max_binary else data,
                }
            out["binary"] = bins
        return out


def items_from_json_list(rows: list[dict[str, Any]]) -> list[ExecutionItem]:
    return [ExecutionItem(json=dict(r)) for r in rows]


def empty_item() -> ExecutionItem:
    return ExecutionItem(json={})
