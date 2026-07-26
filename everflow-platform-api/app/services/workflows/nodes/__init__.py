"""Node executors registry.

Dispatch reads from :data:`app.services.workflows.registry.REGISTRY`, which
is populated by :mod:`app.services.workflows.nodes.descriptors`. The
descriptor is the single source of truth — there is no hand-maintained
``{type: fn}`` table here.
"""

from __future__ import annotations

import importlib
from typing import Any, Awaitable, Callable

from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes import core, data_io, files, llm_agent  # noqa: F401  (registers descriptors on import)
from app.services.workflows.nodes import descriptors as _descriptors  # noqa: F401
from app.services.workflows.registry import REGISTRY, NodeDescriptor, get

# Executor returns multi-output: list of (output_index, items)
NodeResult = list[tuple[int, list[ExecutionItem]]]
Executor = Callable[..., Awaitable[NodeResult]]


def _resolve_executor(desc: NodeDescriptor) -> Executor:
    """Resolve a descriptor's executor import path to the live callable."""
    path = desc.executor
    if ":" not in path:
        raise RuntimeError(f"Bad executor path for {desc.n8n_type!r}: {path!r}")
    module_path, attr = path.split(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise RuntimeError(
            f"Cannot import executor module {module_path!r} for {desc.n8n_type!r}: {exc}"
        ) from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise RuntimeError(
            f"Executor attribute {attr!r} not found in {module_path!r} "
            f"for {desc.n8n_type!r}"
        ) from exc


async def dispatch(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: Any,
) -> NodeResult:
    """Route to the registered executor. ``ctx`` is :class:`EngineContext`."""
    desc = get(node.type)
    if desc is None:
        raise RuntimeError(
            f"Unsupported node type for execution: {node.type}. "
            "Add a descriptor in app.services.workflows.nodes.descriptors."
        )
    fn = _resolve_executor(desc)
    return await fn(node, items, ctx=ctx)


__all__ = ["dispatch", "NodeResult", "Executor", "REGISTRY"]
