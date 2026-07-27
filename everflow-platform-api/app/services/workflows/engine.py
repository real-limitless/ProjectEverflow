"""Item-based workflow execution engine (n8n-compatible subset)."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.services.workflows.graph import ExecGraph, ExecNode, build_exec_graph
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes import dispatch

logger = logging.getLogger(__name__)

# Max serialized sample payload per step (chars of JSON-ish content)
MAX_SAMPLE_CHARS = 32_000

OnStep = Callable[["StepLog"], Awaitable[None] | None]
CancelCheck = Callable[[], bool]


@dataclass
class StepLog:
    node_id: str
    node_name: str
    n8n_type: str
    status: str  # success | error | skipped
    attempt: int = 1
    input_count: int = 0
    output_count: int = 0
    outputs_by_index: dict[int, int] = field(default_factory=dict)
    error: str | None = None
    sample_output: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        sample = self.sample_output
        # Hard truncate oversized samples for DB / API
        try:
            import json as _json

            raw = _json.dumps(sample, default=str)
            if len(raw) > MAX_SAMPLE_CHARS:
                sample = [{"_truncated": True, "chars": len(raw)}]
        except Exception:
            sample = []
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "n8n_type": self.n8n_type,
            "status": self.status,
            "attempt": self.attempt,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "outputs_by_index": {str(k): v for k, v in self.outputs_by_index.items()},
            "error": self.error,
            "sample_output": sample,
        }


@dataclass
class RunResult:
    status: str  # success | error
    trigger_type: str
    steps: list[StepLog] = field(default_factory=list)
    error_message: str | None = None
    final_items: list[dict[str, Any]] = field(default_factory=list)
    data_tables: dict[str, Any] = field(default_factory=dict)
    sent_emails: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trigger_type": self.trigger_type,
            "error_message": self.error_message,
            "steps": [s.to_dict() for s in self.steps],
            "final_items": self.final_items,
            "data_tables": {
                k: {"row_count": len(v.get("rows") or []), "rows": (v.get("rows") or [])[:20]}
                for k, v in self.data_tables.items()
            },
            "sent_emails": self.sent_emails,
        }


@dataclass
class EngineContext:
    graph: ExecGraph
    node_outputs: dict[str, list[ExecutionItem]] = field(default_factory=dict)
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    credentials: dict[str, dict[str, Any]] = field(default_factory=dict)
    credential_bindings: dict[str, str] = field(default_factory=dict)
    data_tables: dict[str, dict[str, Any]] = field(default_factory=dict)
    mocks: dict[str, Any] = field(default_factory=dict)
    batch_state: dict[str, Any] = field(default_factory=dict)
    batch_reset: dict[str, bool] = field(default_factory=dict)
    batch_loop_return: dict[str, bool] = field(default_factory=dict)
    lm_configs: dict[str, Any] = field(default_factory=dict)
    tool_configs: dict[str, Any] = field(default_factory=dict)
    steps: list[StepLog] = field(default_factory=list)
    step_count: int = 0
    max_steps: int = 500
    last_main_items: list[ExecutionItem] = field(default_factory=list)
    fatal_error: str | None = None
    on_step: OnStep | None = None
    cancel_check: CancelCheck | None = None
    # Multi-input merge buffering: target_id -> source_id -> items
    pending_inputs: dict[str, dict[str, list[ExecutionItem]]] = field(default_factory=dict)
    # source_id -> list of (input_index, items) for merge-aware executors
    pending_inputs_indexed: dict[str, list[tuple[int, list[ExecutionItem]]]] = field(
        default_factory=dict
    )
    # Wait-node bookkeeping: node_id -> {mode, resume_url, items}
    wait_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Run identifier used to mint resume URLs.
    run_id: str | None = None
    # Webhook bookkeeping
    webhook_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    webhook_response: dict[str, Any] | None = None
    # AI memory sub-nodes: node_id -> {type, contextWindowLength, sessionId}
    memory_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Mutable memory state shared across nodes in a run.
    memory_state: dict[str, Any] = field(default_factory=dict)
    # Output parser sub-nodes: node_id -> {type, schema}
    output_parsers: dict[str, dict[str, Any]] = field(default_factory=dict)

    def resolve_credential(self, node: ExecNode, cred_type: str) -> dict[str, Any] | None:
        if cred_type in self.credentials:
            return self.credentials[cred_type]
        creds = node.credentials or {}
        meta = creds.get(cred_type) if isinstance(creds, dict) else None
        if isinstance(meta, dict):
            name = meta.get("name")
            cid = meta.get("id")
            for key in (name, cid, f"{cred_type}:{name}", f"{cred_type}:{cid}"):
                if key and key in self.credentials:
                    return self.credentials[key]
            if name and name in self.credential_bindings:
                bid = self.credential_bindings[name]
                if bid in self.credentials:
                    return self.credentials[bid]
        for k, v in self.credentials.items():
            if k.startswith(f"{cred_type}:"):
                return v
        return None


class WorkflowEngine:
    def __init__(
        self,
        document: dict[str, Any],
        *,
        credentials: dict[str, dict[str, Any]] | None = None,
        credential_bindings: dict[str, str] | None = None,
        mocks: dict[str, Any] | None = None,
        data_tables: dict[str, dict[str, Any]] | None = None,
        max_steps: int = 2000,
        on_step: OnStep | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> None:
        self.document = document
        self.graph = build_exec_graph(document)
        self.credentials = credentials or {}
        self.credential_bindings = credential_bindings or {}
        self.mocks = mocks or {}
        self.data_tables = data_tables if data_tables is not None else {}
        self.max_steps = max_steps
        self.on_step = on_step
        self.cancel_check = cancel_check
        # Set by the respondToWebhook executor; read after run() for the
        # platform API to return on the inbound HTTP request.
        self.last_webhook_response: dict[str, Any] | None = None
        # Run identifier used to mint resume URLs.
        self.run_id: str | None = str(uuid4()) if hasattr(uuid4, "__call__") else None

    async def run(
        self,
        *,
        trigger: str = "manual",
        pin_data: dict[str, list[dict[str, Any]]] | None = None,
    ) -> RunResult:
        ctx = EngineContext(
            graph=self.graph,
            credentials=self.credentials,
            credential_bindings=self.credential_bindings,
            mocks=self.mocks,
            data_tables=self.data_tables,
            max_steps=self.max_steps,
            on_step=self.on_step,
            cancel_check=self.cancel_check,
            run_id=getattr(self, "run_id", None),
        )

        if pin_data:
            for name, rows in pin_data.items():
                ctx.node_outputs[name] = [ExecutionItem(json=dict(r)) for r in rows]
        doc_pin = self.document.get("pinData") if isinstance(self.document.get("pinData"), dict) else {}
        for name, rows in doc_pin.items():
            if name not in ctx.node_outputs and isinstance(rows, list):
                items = []
                for r in rows:
                    if isinstance(r, dict) and "json" in r:
                        items.append(ExecutionItem(json=dict(r["json"])))
                    elif isinstance(r, dict):
                        items.append(ExecutionItem(json=dict(r)))
                ctx.node_outputs[name] = items

        triggers = self.graph.trigger_nodes(preferred=trigger)
        if not triggers:
            triggers = [
                n
                for n in self.graph.nodes_by_id.values()
                if not self.graph.in_main.get(n.id) and not self._is_ai_subnode(n)
            ]

        if not triggers:
            return RunResult(
                status="error",
                trigger_type=trigger,
                error_message="No trigger or entry nodes found",
            )

        try:
            # Prefer a single manual trigger when multiple exist, but run all entry
            # triggers that share the same downstream (Stock Agent has 3). For
            # manual runs use manual only if present.
            entry = triggers
            for tnode in entry:
                seed = ctx.node_outputs.get(tnode.name) or [ExecutionItem(json={})]
                await self._run_node(ctx, tnode, seed, from_loop=False)
                if ctx.fatal_error:
                    break

            if ctx.fatal_error:
                return RunResult(
                    status="error",
                    trigger_type=trigger,
                    steps=ctx.steps,
                    error_message=ctx.fatal_error,
                    data_tables=ctx.data_tables,
                    sent_emails=list((ctx.mocks or {}).get("sent_emails") or []),
                )

            # Persist the webhook response (set by respondToWebhook) for the
            # platform API to return on the inbound HTTP request.
            if ctx.webhook_response is not None:
                self.last_webhook_response = dict(ctx.webhook_response)

            return RunResult(
                status="success",
                trigger_type=trigger,
                steps=ctx.steps,
                final_items=[i.to_public_dict() for i in ctx.last_main_items[:20]],
                data_tables=ctx.data_tables,
                sent_emails=list((ctx.mocks or {}).get("sent_emails") or []),
            )
        except Exception as exc:
            logger.exception("Workflow run failed")
            return RunResult(
                status="error",
                trigger_type=trigger,
                steps=ctx.steps,
                error_message=f"{exc}\n{traceback.format_exc()[-500:]}",
                data_tables=ctx.data_tables,
                sent_emails=list((ctx.mocks or {}).get("sent_emails") or []),
            )

    async def _run_node(
        self,
        ctx: EngineContext,
        node: ExecNode,
        items: list[ExecutionItem],
        *,
        from_loop: bool,
    ) -> list[ExecutionItem]:
        """Execute node and recursively follow main successors. Returns primary outputs."""
        if ctx.fatal_error:
            return []
        if node.disabled:
            return items
        if self._is_ai_subnode(node):
            return []

        if ctx.cancel_check and ctx.cancel_check():
            ctx.fatal_error = "cancelled"
            return []

        if ctx.step_count >= ctx.max_steps:
            ctx.fatal_error = f"Exceeded max_steps={ctx.max_steps}"
            return []

        ctx.step_count += 1
        if from_loop and "splitInBatches" in node.type:
            ctx.batch_loop_return[node.id] = True

        attempts = 1
        max_tries = node.max_tries if node.retry_on_fail else 1
        max_tries = max(1, max_tries or 1)
        last_err: Exception | None = None
        result: list[tuple[int, list[ExecutionItem]]] | None = None

        for attempt in range(1, max_tries + 1):
            attempts = attempt
            try:
                result = await dispatch(node, items, ctx=ctx)
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                logger.warning("Node %s failed attempt %s: %s", node.name, attempt, exc)
                if attempt >= max_tries:
                    break

        if last_err is not None:
            err_step = StepLog(
                node_id=node.id,
                node_name=node.name,
                n8n_type=node.type,
                status="error",
                attempt=attempts,
                input_count=len(items),
                error=str(last_err),
            )
            ctx.steps.append(err_step)
            await self._emit_step(ctx, err_step)
            if node.continue_on_fail:
                result = [(0, items)]
            else:
                ctx.fatal_error = f"{node.name}: {last_err}"
                return []

        assert result is not None
        by_idx: dict[int, int] = {}
        total_out = 0
        sample: list[dict[str, Any]] = []
        main_stored: list[ExecutionItem] = []
        for out_idx, out_items in result:
            by_idx[out_idx] = len(out_items)
            total_out += len(out_items)
            if out_items and not sample:
                sample = [i.to_public_dict() for i in out_items[:3]]
            if out_idx == 0 and out_items:
                main_stored = out_items
            elif not main_stored and out_items:
                main_stored = out_items

        ctx.node_outputs[node.name] = main_stored or (result[0][1] if result else [])
        if main_stored:
            ctx.last_main_items = main_stored

        ok_step = StepLog(
            node_id=node.id,
            node_name=node.name,
            n8n_type=node.type,
            status="success",
            attempt=attempts,
            input_count=len(items),
            output_count=total_out,
            outputs_by_index=by_idx,
            sample_output=sample,
        )
        ctx.steps.append(ok_step)
        await self._emit_step(ctx, ok_step)

        # splitInBatches: process loop branch fully, then re-enter until done
        if "splitInBatches" in node.type:
            return await self._finish_split_in_batches(ctx, node, result)

        # Fan-out all main outputs (if true/false, filter, etc.)
        for out_idx, out_items in result:
            if not out_items and out_idx != 0:
                continue
            successors = self._sorted_successors(node.id, out_idx)
            for edge in successors:
                target = self.graph.nodes_by_id.get(edge.target_id)
                if target is None:
                    continue
                is_return = "splitInBatches" in target.type and self._is_loop_body_return(
                    target.id, node.id
                )
                await self._enqueue_or_run(
                    ctx,
                    target,
                    source=node,
                    out_items=out_items,
                    source_out_index=out_idx,
                    from_loop=is_return,
                )
                if ctx.fatal_error:
                    return main_stored

        return main_stored

    def _sorted_successors(self, node_id: str, out_idx: int) -> list:
        """Prefer data-table setup nodes before long parallel branches (create before split)."""
        edges = list(self.graph.main_successors(node_id, out_idx))

        def rank(e) -> int:
            t = self.graph.nodes_by_id.get(e.target_id)
            if t is None:
                return 50
            if "dataTable" in t.type:
                op = str((t.parameters or {}).get("operation") or "")
                res = str((t.parameters or {}).get("resource") or "")
                if op == "create" or res == "table":
                    return 0
                if op == "delete":
                    return 1
                return 2
            if "splitOut" in t.type or "splitInBatches" in t.type:
                return 40
            return 20

        return sorted(edges, key=rank)

    def _expected_main_sources(self, target_id: str) -> set[str]:
        """Set of source node ids with a main edge into target_id.

        Cached on the graph object for the lifetime of the engine instance.
        """
        cache = getattr(self, "_expected_main_sources_cache", None)
        if cache is None:
            cache = {}
            for nid in self.graph.nodes_by_id:
                cache[nid] = {
                    e.source_id
                    for in_edges in self.graph.in_main.get(nid, [])
                    for e in [in_edges]
                }
                # Use a set comprehension for clarity
                cache[nid] = {e.source_id for e in self.graph.in_main.get(nid, [])}
            self._expected_main_sources_cache = cache
        return cache.get(target_id, set())

    async def _enqueue_or_run(
        self,
        ctx: EngineContext,
        target: ExecNode,
        source: ExecNode,
        out_items: list[ExecutionItem],
        *,
        source_out_index: int = 0,
        from_loop: bool = False,
    ) -> None:
        """Multi-input aware fan-out: buffer items until all sources arrive.

        If the target expects only one main input, this is equivalent to a
        direct :meth:`_run_node` call. If the target has multiple incoming
        main edges, items are buffered per source; the target runs only when
        every *expected non-trigger* source has delivered. Trigger sources
        run immediately (only one trigger fires per run in v1).
        """
        expected = self._expected_main_sources(target.id)
        source_is_trigger = (
            "trigger" in source.type.lower() or source.type.endswith("Trigger")
        )

        if len(expected) <= 1:
            # Common path: single-input target.
            await self._run_node(
                ctx,
                target,
                out_items,
                from_loop=from_loop,
            )
            return

        if source_is_trigger:
            # Triggers are the entry point: don't wait for other triggers.
            # Just run directly with this trigger's items.
            ctx.pending_inputs.pop(target.id, None)
            ctx.pending_inputs_indexed.pop(target.id, None)
            await self._run_node(
                ctx,
                target,
                out_items,
                from_loop=from_loop,
            )
            return

        # Skip buffering for back-edges (feedback in loops). An edge
        # source → target is a back-edge when the target can reach back
        # to source (i.e. they're in a cycle). For example, the loop body
        # of a splitInBatches node feeds its last node back to the batch
        # node — that final edge is a back-edge.
        if self._is_reachable_from(target.id, source.id):
            await self._run_node(
                ctx,
                target,
                out_items,
                from_loop=from_loop,
            )
            return

        # Multi-input, non-trigger source: buffer and dispatch when ready.
        pending = ctx.pending_inputs.setdefault(target.id, {})
        pending[source.id] = out_items
        indexed = ctx.pending_inputs_indexed.setdefault(target.id, [])
        indexed.append((source_out_index, out_items))

        # Non-trigger expected sources. If any expected source is reachable
        # from the target itself (i.e. part of a feedback loop), it cannot
        # fire until the target runs once. Treat that source as already
        # "self-supplied" — do not wait for it.
        non_trigger_expected = set()
        for src_id in expected:
            if self._is_trigger_node_id(src_id):
                continue
            if self._is_reachable_from(target.id, src_id):
                continue
            non_trigger_expected.add(src_id)

        if not non_trigger_expected.issubset(set(pending.keys())):
            # Not all non-trigger sources have arrived yet; wait.
            return

        # All non-trigger sources delivered. Combine and dispatch.
        combined: list[ExecutionItem] = []
        for src_id in sorted(pending.keys()):
            for it in pending[src_id]:
                combined.append(it)
        # Clear pending for this target so re-entry can start fresh.
        ctx.pending_inputs.pop(target.id, None)
        ctx.pending_inputs_indexed.pop(target.id, None)

        await self._run_node(
            ctx,
            target,
            combined,
            from_loop=from_loop,
        )

    def _is_trigger_node_id(self, node_id: str) -> bool:
        n = self.graph.nodes_by_id.get(node_id)
        if n is None:
            return False
        t = n.type.lower()
        return "trigger" in t or n.type.endswith("Trigger")

    def _is_reachable_from(
        self,
        start_id: str,
        goal_id: str,
        *,
        max_depth: int = 64,
    ) -> bool:
        """BFS from ``start_id`` over main edges; True if ``goal_id`` found.

        Used to detect feedback cycles: if any other expected source of a
        multi-input target is reachable from the target itself, that source
        cannot fire until the target runs at least once. We must not wait
        for it (would deadlock).
        """
        if start_id == goal_id:
            return True
        cache = getattr(self, "_reach_cache", None)
        if cache is None:
            cache = {}
            self._reach_cache = cache
        cache_key = (start_id, goal_id)
        if cache_key in cache:
            return cache[cache_key]
        seen = {start_id}
        stack = [(start_id, 0)]
        while stack:
            cur, depth = stack.pop()
            if depth >= max_depth:
                continue
            for idx in (0, 1, 2):
                for e in self.graph.main_successors(cur, idx):
                    if e.target_id == goal_id:
                        cache[cache_key] = True
                        return True
                    if e.target_id not in seen:
                        seen.add(e.target_id)
                        stack.append((e.target_id, depth + 1))
        cache[cache_key] = False
        return False

    def _has_explicit_feedback(self, batch_node_id: str) -> bool:
        """True if any node reachable from loop output has a main edge back to the batch node."""
        stack = [e.target_id for e in self.graph.main_successors(batch_node_id, 1)]
        seen = set(stack)
        while stack:
            nid = stack.pop()
            for idx in (0, 1, 2):
                for e in self.graph.main_successors(nid, idx):
                    if e.target_id == batch_node_id:
                        return True
                    if e.target_id not in seen:
                        seen.add(e.target_id)
                        stack.append(e.target_id)
        return False

    async def _finish_split_in_batches(
        self,
        ctx: EngineContext,
        node: ExecNode,
        result: list[tuple[int, list[ExecutionItem]]],
    ) -> list[ExecutionItem]:
        """Handle loop/done outputs.

        - If the loop body has an explicit edge back to this node (portfolio file loop),
          only fan-out; re-entry is driven by that edge with from_loop=True.
        - Otherwise (item research loop), re-enter automatically after the body finishes.
        """
        by_out = {idx: items for idx, items in result}
        loop_items = by_out.get(1) or []
        done_items = by_out.get(0) or []
        explicit = self._has_explicit_feedback(node.id)

        # Done branch (no more loop batches)
        if done_items and not loop_items:
            for edge in self.graph.main_successors(node.id, 0):
                target = self.graph.nodes_by_id.get(edge.target_id)
                if target is None:
                    continue
                await self._run_node(ctx, target, done_items, from_loop=False)
            return done_items

        if not loop_items:
            # empty done
            for edge in self.graph.main_successors(node.id, 0):
                target = self.graph.nodes_by_id.get(edge.target_id)
                if target is None:
                    continue
                await self._run_node(ctx, target, done_items, from_loop=False)
            return done_items

        if explicit:
            # Fan-out loop body only; feedback edge re-enters this node
            for edge in self.graph.main_successors(node.id, 1):
                target = self.graph.nodes_by_id.get(edge.target_id)
                if target is None:
                    continue
                await self._run_node(ctx, target, loop_items, from_loop=False)
                if ctx.fatal_error:
                    return []
            return loop_items

        # Auto re-enter: process body → redispatch until done
        while loop_items and not ctx.fatal_error:
            body_out: list[ExecutionItem] = []
            for edge in self.graph.main_successors(node.id, 1):
                target = self.graph.nodes_by_id.get(edge.target_id)
                if target is None:
                    continue
                body_out = await self._run_node(ctx, target, loop_items, from_loop=False)
                if ctx.fatal_error:
                    return body_out

            ctx.batch_loop_return[node.id] = True
            cont_result = await dispatch(node, body_out or loop_items, ctx=ctx)
            ctx.step_count += 1
            cont_by = {i: len(it) for i, it in cont_result}
            cont_sample: list[dict[str, Any]] = []
            for _, its in cont_result:
                if its:
                    cont_sample = [x.to_public_dict() for x in its[:3]]
                    break
            ctx.steps.append(
                StepLog(
                    node_id=node.id,
                    node_name=node.name,
                    n8n_type=node.type,
                    status="success",
                    input_count=len(body_out or loop_items),
                    output_count=sum(len(it) for _, it in cont_result),
                    outputs_by_index=cont_by,
                    sample_output=cont_sample,
                )
            )
            cont_map = {i: it for i, it in cont_result}
            loop_items = cont_map.get(1) or []
            done_items = cont_map.get(0) or []
            if done_items or not loop_items:
                if done_items:
                    ctx.node_outputs[node.name] = done_items
                    ctx.last_main_items = done_items
                for edge_d in self.graph.main_successors(node.id, 0):
                    target_d = self.graph.nodes_by_id.get(edge_d.target_id)
                    if target_d is None:
                        continue
                    await self._run_node(ctx, target_d, done_items, from_loop=False)
                return done_items

        return done_items or ctx.node_outputs.get(node.name) or []

    async def _emit_step(self, ctx: EngineContext, step: StepLog) -> None:
        if ctx.on_step is None:
            return
        try:
            maybe = ctx.on_step(step)
            if maybe is not None and hasattr(maybe, "__await__"):
                await maybe  # type: ignore[misc]
        except Exception:
            logger.exception("on_step callback failed for %s", step.node_name)

    def _is_ai_subnode(self, node: ExecNode) -> bool:
        t = node.type
        if "agent" in t and "langchain" in t:
            return False
        return "lmChat" in t or "mcpClientTool" in t or (
            "langchain" in t and "agent" not in t and "Tool" in t
        )

    def _is_loop_body_return(self, batch_node_id: str, source_id: str) -> bool:
        loop_targets = {e.target_id for e in self.graph.main_successors(batch_node_id, 1)}
        if source_id in loop_targets:
            return True
        seen = set(loop_targets)
        stack = list(loop_targets)
        while stack:
            nid = stack.pop()
            for idx in (0, 1, 2):
                for e in self.graph.main_successors(nid, idx):
                    if e.target_id == batch_node_id:
                        continue
                    if e.target_id not in seen:
                        seen.add(e.target_id)
                        stack.append(e.target_id)
        return source_id in seen
