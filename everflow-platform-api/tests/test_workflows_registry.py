"""CI invariant: every supported n8n type has a registered descriptor.

This test is the guard rail for the top-200 implementation plan. It fails
fast if a new type is added to ``SUPPORTED_NODE_TYPES`` without a matching
executor wiring in :mod:`app.services.workflows.nodes.descriptors`.

The reverse check (registry has a type not in SUPPORTED_NODE_TYPES) is also
asserted to keep the two structures in lockstep — the registry populates
the supported map, so they should be identical sets.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from app.services.workflows import registry
from app.services.workflows.nodes import descriptors as _descriptors  # noqa: F401
from app.services.workflows.nodes import dispatch  # noqa: F401
from app.services.workflows.registry import REGISTRY, SUPPORTED_NODE_TYPES


def _load_descriptors() -> None:
    """Re-import the descriptors module to ensure registration has run."""
    importlib.reload(_descriptors)


def test_registry_import_side_effect_populates_supported_types() -> None:
    _load_descriptors()
    # All current descriptors are registered.
    assert REGISTRY, "REGISTRY is empty — descriptors module failed to import"
    # The descriptors module populates SUPPORTED_NODE_TYPES as a side effect.
    assert set(REGISTRY.keys()) == set(SUPPORTED_NODE_TYPES.keys()), (
        "REGISTRY and SUPPORTED_NODE_TYPES drifted out of sync:\n"
        f"  only in REGISTRY: {set(REGISTRY) - set(SUPPORTED_NODE_TYPES)}\n"
        f"  only in SUPPORTED: {set(SUPPORTED_NODE_TYPES) - set(REGISTRY)}"
    )


@pytest.mark.parametrize("n8n_type", sorted(REGISTRY.keys()))
def test_every_descriptor_resolves_to_a_callable(n8n_type: str) -> None:
    """Each registered descriptor's executor must be importable + callable."""
    _load_descriptors()
    desc = REGISTRY[n8n_type]
    path = desc.executor
    assert ":" in path, f"Bad executor path for {n8n_type!r}: {path!r}"
    module_path, attr = path.split(":", 1)
    module = importlib.import_module(module_path)
    fn = getattr(module, attr, None)
    assert fn is not None, (
        f"Executor for {n8n_type!r} not found: {path!r}"
    )
    assert callable(fn), f"Executor for {n8n_type!r} is not callable: {path!r}"


def test_no_descriptor_collisions() -> None:
    """Duplicate registrations with different executors must error."""
    from app.services.workflows.registry import NodeDescriptor, register

    with pytest.raises(ValueError, match="Duplicate descriptor"):
        register(
            NodeDescriptor(
                n8n_type="n8n-nodes-base.set",
                category="transform",
                executor="app.services.workflows.nodes.core:exec_filter",
            )
        )


def test_descriptors_wire_current_baseline() -> None:
    """Regression: keep the v1 Stock Agent Emailer acceptance set wired."""
    _load_descriptors()
    expected = {
        "n8n-nodes-base.manualTrigger",
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.executeWorkflowTrigger",
        "n8n-nodes-base.set",
        "n8n-nodes-base.code",
        "n8n-nodes-base.if",
        "n8n-nodes-base.filter",
        "n8n-nodes-base.aggregate",
        "n8n-nodes-base.splitOut",
        "n8n-nodes-base.splitInBatches",
        "n8n-nodes-base.ftp",
        "n8n-nodes-base.extractFromFile",
        "n8n-nodes-base.convertToFile",
        "n8n-nodes-base.dataTable",
        "n8n-nodes-base.emailSend",
        "@n8n/n8n-nodes-langchain.lmChatOpenAi",
        "@n8n/n8n-nodes-langchain.agent",
        "@n8n/n8n-nodes-langchain.mcpClientTool",
        "n8n-nodes-mcp.mcpClientTool",
    }
    missing = expected - set(REGISTRY.keys())
    assert not missing, f"v1 baseline type(s) lost from registry: {missing}"


def test_palette_export_is_deterministic() -> None:
    """The palette source helper should sort types for a stable UI list."""
    _load_descriptors()
    from app.services.workflows.registry import palette_entries

    entries = palette_entries()
    keys = [e["type"] for e in entries]
    assert keys == sorted(keys), "palette_entries() must be sorted"
    for entry in entries:
        assert {"type", "category", "description"} <= entry.keys()


def test_known_types_does_not_drop_after_reload() -> None:
    """Idempotency: reloading descriptors must keep the same registry size."""
    _load_descriptors()
    before = len(REGISTRY)
    importlib.reload(_descriptors)
    after = len(REGISTRY)
    assert before == after, f"Registry size changed on reload: {before} → {after}"
