"""Workflow graph helpers for execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecNode:
    id: str
    name: str
    type: str
    type_version: float | int | None
    parameters: dict[str, Any]
    credentials: dict[str, Any] | None
    position: dict[str, float]
    retry_on_fail: bool = False
    max_tries: int | None = None
    continue_on_fail: bool = False
    disabled: bool = False


@dataclass
class ExecEdge:
    source_id: str
    target_id: str
    source_name: str
    target_name: str
    connection_type: str
    source_index: int = 0
    target_index: int = 0


@dataclass
class ExecGraph:
    nodes_by_id: dict[str, ExecNode]
    nodes_by_name: dict[str, ExecNode]
    # source_id -> connection_type -> source_index -> list of edges
    out_edges: dict[str, dict[str, dict[int, list[ExecEdge]]]] = field(default_factory=dict)
    # reverse main edges for feedback detection
    in_main: dict[str, list[ExecEdge]] = field(default_factory=dict)

    def main_successors(self, node_id: str, output_index: int = 0) -> list[ExecEdge]:
        return list(self.out_edges.get(node_id, {}).get("main", {}).get(output_index, []))

    def ai_inputs(self, node_id: str, connection_type: str) -> list[ExecNode]:
        """Find nodes that connect TO node_id via ai_* edges (sub-nodes)."""
        found: list[ExecNode] = []
        for src_id, by_type in self.out_edges.items():
            for ctype, by_idx in by_type.items():
                if ctype != connection_type:
                    continue
                for edges in by_idx.values():
                    for e in edges:
                        if e.target_id == node_id:
                            n = self.nodes_by_id.get(src_id)
                            if n:
                                found.append(n)
        return found

    def trigger_nodes(self, preferred: str | None = None) -> list[ExecNode]:
        triggers = [
            n
            for n in self.nodes_by_id.values()
            if "trigger" in n.type.lower() or n.type.endswith("Trigger")
        ]
        if preferred == "manual":
            manuals = [n for n in triggers if "manualTrigger" in n.type]
            if manuals:
                return manuals
        if preferred == "schedule":
            sched = [n for n in triggers if "scheduleTrigger" in n.type]
            if sched:
                return sched
        if preferred == "executeWorkflow":
            ex = [n for n in triggers if "executeWorkflowTrigger" in n.type]
            if ex:
                return ex
        # Prefer manual if present
        manuals = [n for n in triggers if "manualTrigger" in n.type]
        return manuals or triggers


def build_exec_graph(document: dict[str, Any]) -> ExecGraph:
    from app.services.workflows.import_n8n import derive_graph

    derived = derive_graph(document)
    nodes_by_id: dict[str, ExecNode] = {}
    nodes_by_name: dict[str, ExecNode] = {}
    for n in derived.nodes:
        en = ExecNode(
            id=n.id,
            name=n.name,
            type=n.type,
            type_version=n.type_version,
            parameters=dict(n.parameters or {}),
            credentials=n.credentials,
            position=n.position,
            retry_on_fail=n.retry_on_fail,
            max_tries=n.max_tries,
            continue_on_fail=n.continue_on_fail,
            disabled=n.disabled,
        )
        nodes_by_id[en.id] = en
        nodes_by_name[en.name] = en

    out_edges: dict[str, dict[str, dict[int, list[ExecEdge]]]] = {}
    in_main: dict[str, list[ExecEdge]] = {}
    for e in derived.edges:
        ee = ExecEdge(
            source_id=e.source,
            target_id=e.target,
            source_name=e.source_name,
            target_name=e.target_name,
            connection_type=e.connection_type,
            source_index=e.source_index,
            target_index=e.target_index,
        )
        out_edges.setdefault(ee.source_id, {}).setdefault(ee.connection_type, {}).setdefault(
            ee.source_index, []
        ).append(ee)
        if ee.connection_type == "main":
            in_main.setdefault(ee.target_id, []).append(ee)

    return ExecGraph(
        nodes_by_id=nodes_by_id,
        nodes_by_name=nodes_by_name,
        out_edges=out_edges,
        in_main=in_main,
    )
