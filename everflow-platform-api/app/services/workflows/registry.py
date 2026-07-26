"""Supported n8n node types and descriptor registry.

The descriptor registry is the single source of truth for n8n node types
in Everflow. Each descriptor carries:

- ``n8n_type``: the canonical n8n type string (e.g. ``n8n-nodes-base.set``)
- ``category``: a coarse UI category used by the canvas palette
- ``executor``: a dotted import path (``pkg.module:attr``) that resolves to
  the async coroutine implementing the node
- ``outputs``: stable names for non-zero main outputs (used by the canvas);
  the empty list means a single main output
- ``description``: human-readable summary shown in the UI palette

Descriptors are registered by importing the ``app.services.workflows.nodes.descriptors``
module, which lives in the node package. Tests assert that every type in
``SUPPORTED_NODE_TYPES`` has a matching descriptor — this is the CI invariant
that prevents "supported but unrouted" gaps.

Unknown types are still stored on import; execute will refuse them later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

NodeCategory = Literal[
    "trigger",
    "input",
    "transform",
    "logic",
    "ai",
    "output",
    "data",
    "unknown",
]


@dataclass(frozen=True)
class NodeDescriptor:
    n8n_type: str
    category: NodeCategory
    executor: str  # "pkg.module:attr"
    outputs: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""
    version: int = 1


# Categories used by the canvas — kept for backward compat.
SUPPORTED_NODE_TYPES: dict[str, NodeCategory] = {}


# Descriptor source of truth. Populated by ``nodes/descriptors.py``.
REGISTRY: dict[str, NodeDescriptor] = {}


def register(descriptor: NodeDescriptor, *, overwrite: bool = False) -> NodeDescriptor:
    """Register a node descriptor. Raises on duplicate unless ``overwrite``."""
    if not overwrite and descriptor.n8n_type in REGISTRY:
        existing = REGISTRY[descriptor.n8n_type]
        if existing == descriptor:
            return existing
        raise ValueError(
            f"Duplicate descriptor for {descriptor.n8n_type!r}: "
            f"existing={existing.executor!r} new={descriptor.executor!r}"
        )
    REGISTRY[descriptor.n8n_type] = descriptor
    SUPPORTED_NODE_TYPES[descriptor.n8n_type] = descriptor.category
    return descriptor


def get(n8n_type: str) -> Optional[NodeDescriptor]:
    return REGISTRY.get(n8n_type)


def categorize(n8n_type: str) -> NodeCategory:
    return SUPPORTED_NODE_TYPES.get(n8n_type, "unknown")


def is_supported(n8n_type: str) -> bool:
    return n8n_type in SUPPORTED_NODE_TYPES


def palette_entries() -> list[dict[str, str]]:
    """Return a UI-ready palette list, derived from REGISTRY (single source of truth).

    Output is deterministically sorted by ``n8n_type`` so the UI palette is
    stable across processes. Each entry has the keys ``type``, ``category``,
    and ``description``.
    """
    return [
        {
            "type": desc.n8n_type,
            "category": desc.category,
            "description": desc.description,
        }
        for desc in sorted(REGISTRY.values(), key=lambda d: d.n8n_type)
    ]


# Credential types referenced by Stock Agent Emailer
SUPPORTED_CREDENTIAL_TYPES: frozenset[str] = frozenset(
    {
        "openAiApi",
        "ftp",
        "smtp",
        "httpMultipleHeadersAuth",
        "mcpClientApi",
    }
)

# Connection types we preserve on import
KNOWN_CONNECTION_TYPES: frozenset[str] = frozenset(
    {
        "main",
        "ai_languageModel",
        "ai_tool",
        "ai_memory",
        "ai_outputParser",
        "ai_embedding",
        "ai_vectorStore",
        "ai_document",
        "ai_textSplitter",
        "ai_toolExecutor",
    }
)

# Multi-output main handles (for canvas)
MULTI_MAIN_OUTPUT_TYPES: dict[str, list[str]] = {
    "n8n-nodes-base.if": ["true", "false"],
    "n8n-nodes-base.splitInBatches": ["done", "loop"],
    "n8n-nodes-base.switch": [],  # dynamic
}
