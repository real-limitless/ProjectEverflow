"""Parse and validate n8n workflow export JSON into Everflow graph IR."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.workflows.registry import (
    KNOWN_CONNECTION_TYPES,
    MULTI_MAIN_OUTPUT_TYPES,
    SUPPORTED_CREDENTIAL_TYPES,
    categorize,
    is_supported,
)


@dataclass
class GraphNode:
    id: str
    name: str
    type: str
    type_version: float | int | None
    position: dict[str, float]
    parameters: dict[str, Any]
    credentials: dict[str, Any] | None
    category: str
    supported: bool
    disabled: bool = False
    retry_on_fail: bool = False
    max_tries: int | None = None
    continue_on_fail: bool = False
    notes: str | None = None
    webhook_id: str | None = None


@dataclass
class GraphEdge:
    id: str
    source: str  # node id
    target: str  # node id
    source_name: str
    target_name: str
    connection_type: str
    source_index: int = 0
    target_index: int = 0
    source_handle: str = "main:0"


@dataclass
class CredentialRequirement:
    credential_type: str
    n8n_id: str | None
    n8n_name: str | None
    used_by_nodes: list[str] = field(default_factory=list)


@dataclass
class ImportReport:
    node_count: int
    edge_count: int
    supported_types: list[str]
    unsupported_types: list[str]
    credential_requirements: list[dict[str, Any]]
    trigger_summary: str
    connection_type_counts: dict[str, int]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DerivedGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    name: str
    settings: dict[str, Any]
    pin_data: dict[str, Any]
    active: bool
    report: ImportReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
            "name": self.name,
            "settings": self.settings,
            "pin_data": self.pin_data,
            "active": self.active,
            "report": self.report.to_dict(),
        }


def _position(raw: Any, index: int) -> dict[str, float]:
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        return {"x": float(raw[0]), "y": float(raw[1])}
    if isinstance(raw, dict):
        return {"x": float(raw.get("x", index * 160)), "y": float(raw.get("y", 100))}
    return {"x": float(index * 160), "y": 100.0}


def _trigger_summary(types: list[str]) -> str:
    flags: set[str] = set()
    for t in types:
        if t.endswith("manualTrigger") or "manualTrigger" in t:
            flags.add("manual")
        elif t.endswith("scheduleTrigger") or "scheduleTrigger" in t:
            flags.add("schedule")
        elif t.endswith("executeWorkflowTrigger") or "executeWorkflowTrigger" in t:
            flags.add("executeWorkflow")
        elif "webhook" in t.lower():
            flags.add("webhook")
        elif "trigger" in t.lower():
            flags.add("other")
    if not flags:
        return "unknown"
    if len(flags) == 1:
        return next(iter(flags))
    return "mixed"


def _source_handle(connection_type: str, source_index: int, source_type: str) -> str:
    if connection_type == "main":
        labels = MULTI_MAIN_OUTPUT_TYPES.get(source_type)
        if labels and source_index < len(labels):
            return f"main:{source_index}:{labels[source_index]}"
        return f"main:{source_index}"
    return f"{connection_type}:{source_index}"


def derive_graph(document: dict[str, Any]) -> DerivedGraph:
    """Build canvas IR + import report from an n8n export document."""
    raw_nodes = document.get("nodes") or []
    if not isinstance(raw_nodes, list):
        raise ValueError("n8n document.nodes must be a list")

    nodes: list[GraphNode] = []
    name_to_id: dict[str, str] = {}
    type_by_name: dict[str, str] = {}
    supported_types: set[str] = set()
    unsupported_types: set[str] = set()
    cred_map: dict[tuple[str, str | None, str | None], CredentialRequirement] = {}
    warnings: list[str] = []

    for i, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            warnings.append(f"Skipping non-object node at index {i}")
            continue
        n_type = str(raw.get("type") or "unknown")
        n_id = str(raw.get("id") or f"node-{i}")
        n_name = str(raw.get("name") or f"Node {i + 1}")
        supported = is_supported(n_type)
        if supported:
            supported_types.add(n_type)
        else:
            unsupported_types.add(n_type)

        creds = raw.get("credentials") if isinstance(raw.get("credentials"), dict) else None
        if creds:
            for cred_type, meta in creds.items():
                meta_d = meta if isinstance(meta, dict) else {}
                n8n_id = str(meta_d["id"]) if meta_d.get("id") is not None else None
                n8n_name = str(meta_d["name"]) if meta_d.get("name") is not None else None
                key = (str(cred_type), n8n_id, n8n_name)
                if key not in cred_map:
                    cred_map[key] = CredentialRequirement(
                        credential_type=str(cred_type),
                        n8n_id=n8n_id,
                        n8n_name=n8n_name,
                        used_by_nodes=[n_name],
                    )
                else:
                    cred_map[key].used_by_nodes.append(n_name)
                if str(cred_type) not in SUPPORTED_CREDENTIAL_TYPES:
                    warnings.append(
                        f"Credential type '{cred_type}' on node '{n_name}' is not in v1 support set"
                    )

        params = raw.get("parameters") if isinstance(raw.get("parameters"), dict) else {}
        node = GraphNode(
            id=n_id,
            name=n_name,
            type=n_type,
            type_version=raw.get("typeVersion"),
            position=_position(raw.get("position"), i),
            parameters=params,
            credentials=creds,
            category=categorize(n_type),
            supported=supported,
            disabled=bool(raw.get("disabled")),
            retry_on_fail=bool(raw.get("retryOnFail")),
            max_tries=raw.get("maxTries") if isinstance(raw.get("maxTries"), int) else None,
            continue_on_fail=bool(raw.get("continueOnFail")),
            notes=str(raw["notes"]) if raw.get("notes") is not None else None,
            webhook_id=str(raw["webhookId"]) if raw.get("webhookId") is not None else None,
        )
        nodes.append(node)
        name_to_id[n_name] = n_id
        type_by_name[n_name] = n_type
        # Also index by id for robustness
        name_to_id.setdefault(n_id, n_id)

    edges: list[GraphEdge] = []
    conn_counts: dict[str, int] = {}
    connections = document.get("connections") or {}
    if not isinstance(connections, dict):
        raise ValueError("n8n document.connections must be an object")

    edge_i = 0
    for source_name, conn_block in connections.items():
        if not isinstance(conn_block, dict):
            continue
        source_id = name_to_id.get(str(source_name))
        if not source_id:
            warnings.append(f"Connection source '{source_name}' has no matching node")
            continue
        source_type = type_by_name.get(str(source_name), "unknown")

        for connection_type, groups in conn_block.items():
            ctype = str(connection_type)
            if ctype not in KNOWN_CONNECTION_TYPES:
                warnings.append(f"Unknown connection type '{ctype}' from '{source_name}'")
            if not isinstance(groups, list):
                continue
            for source_index, group in enumerate(groups):
                if not isinstance(group, list):
                    continue
                for link in group:
                    if not isinstance(link, dict):
                        continue
                    target_name = str(link.get("node") or "")
                    target_id = name_to_id.get(target_name)
                    if not target_id:
                        warnings.append(
                            f"Connection target '{target_name}' from '{source_name}' has no matching node"
                        )
                        continue
                    edge_type = str(link.get("type") or ctype)
                    target_index = int(link.get("index") or 0)
                    handle = _source_handle(ctype, source_index, source_type)
                    edges.append(
                        GraphEdge(
                            id=f"e-{edge_i}",
                            source=source_id,
                            target=target_id,
                            source_name=str(source_name),
                            target_name=target_name,
                            connection_type=edge_type if edge_type else ctype,
                            source_index=source_index,
                            target_index=target_index,
                            source_handle=handle,
                        )
                    )
                    edge_i += 1
                    key = ctype
                    conn_counts[key] = conn_counts.get(key, 0) + 1

    node_types = [n.type for n in nodes]
    report = ImportReport(
        node_count=len(nodes),
        edge_count=len(edges),
        supported_types=sorted(supported_types),
        unsupported_types=sorted(unsupported_types),
        credential_requirements=[asdict(c) for c in cred_map.values()],
        trigger_summary=_trigger_summary(node_types),
        connection_type_counts=conn_counts,
        warnings=warnings,
    )

    settings = document.get("settings") if isinstance(document.get("settings"), dict) else {}
    pin_data = document.get("pinData") if isinstance(document.get("pinData"), dict) else {}
    name = str(document.get("name") or "Imported n8n workflow")
    active = bool(document.get("active", False))

    return DerivedGraph(
        nodes=nodes,
        edges=edges,
        name=name,
        settings=settings,
        pin_data=pin_data,
        active=active,
        report=report,
    )


def import_n8n_document(document: Any) -> DerivedGraph:
    """Validate top-level shape and derive graph. Raises ValueError on bad input."""
    if not isinstance(document, dict):
        raise ValueError("n8n document must be a JSON object")
    if "nodes" not in document:
        raise ValueError("n8n document missing 'nodes'")
    return derive_graph(document)
