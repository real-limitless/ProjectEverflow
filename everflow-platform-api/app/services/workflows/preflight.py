"""Validate a workflow can run with current bindings / credentials."""

from __future__ import annotations

from typing import Any

from app.services.workflows.import_n8n import import_n8n_document
from app.services.workflows.registry import is_supported


def preflight_workflow(
    document: dict[str, Any],
    *,
    credential_bindings: dict[str, Any] | None,
    available_credential_keys: set[str],
    available_by_type: set[str],
) -> dict[str, Any]:
    """Return validation report for UI / execute gate."""
    derived = import_n8n_document(document)
    unsupported = [n.type for n in derived.nodes if not is_supported(n.type)]
    missing: list[dict[str, Any]] = []
    bindings = credential_bindings if isinstance(credential_bindings, dict) else {}

    for req in derived.report.credential_requirements:
        ctype = str(req.get("credential_type") or "")
        name = req.get("n8n_name")
        n8n_id = req.get("n8n_id")
        keys_to_try = [
            str(k)
            for k in (
                name,
                n8n_id,
                f"{ctype}:{name}" if name else None,
                f"{ctype}:{n8n_id}" if n8n_id else None,
                ctype,
            )
            if k
        ]
        bound = False
        for k in keys_to_try:
            if k in bindings and str(bindings[k]) in available_credential_keys:
                bound = True
                break
            if k in available_credential_keys:
                bound = True
                break
        if not bound and ctype in available_by_type:
            # project has some credential of this type
            bound = True
        if not bound:
            missing.append(
                {
                    "credential_type": ctype,
                    "n8n_name": name,
                    "n8n_id": n8n_id,
                    "used_by_nodes": req.get("used_by_nodes") or [],
                }
            )

    triggers = [
        {"name": n.name, "type": n.type}
        for n in derived.nodes
        if "trigger" in n.type.lower()
    ]
    schedule_nodes = [t for t in triggers if "scheduleTrigger" in t["type"]]

    return {
        "ok": not missing and not unsupported,
        "missing_credentials": missing,
        "unsupported_types": sorted(set(unsupported)),
        "triggers": triggers,
        "has_schedule": bool(schedule_nodes),
        "node_count": derived.report.node_count,
        "edge_count": derived.report.edge_count,
        "credential_requirements": derived.report.credential_requirements,
    }
