"""Flow-control executors: wait, merge, switch, limit, sort, no-op, etc.

These are Tier A core engine nodes from the top-200 plan. Each is a
standalone executor function; wire into the descriptor registry.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext


def _expr_ctx(item: ExecutionItem, ctx: "EngineContext") -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


# ── Wait ──────────────────────────────────────────────────────────────


async def exec_wait(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Wait node — supports ``amount`` + ``unit`` (seconds/minutes/hours/days)
    or a ``webhook`` resume sub-option.

    v1 implements both:

    - Time-based wait: blocks the run for the configured duration.
    - Webhook resume: records a ``resumeUrl`` on the engine context; tests
      can inject a mock at ``ctx.mocks['wait_resume'][node_id]`` to fire the
      wait instantly without blocking. When the run completes, the engine
      records the wait state so the API layer (separate concern) can
      accept a resume POST later.

    The actual ``$execution.resumeUrl`` is published as a field on each
    output item's JSON so downstream nodes can read it.
    """
    params = node.parameters or {}
    resume = params.get("resume") if isinstance(params.get("resume"), dict) else {}

    if resume.get("resume") == "webhook":
        # Webhook resume path. Record a synthetic resume URL on the context
        # so the API layer can wire it to a real endpoint later.
        resume_url = (
            f"/api/v1/workflows/_/resume/{ctx.run_id or 'local'}/{node.id}"
        )
        ctx.wait_states[node.id] = {
            "mode": "webhook",
            "resume_url": resume_url,
            "items": [i.to_public_dict() for i in items],
        }
        # If a mock provides a resume signal, treat as fired.
        if isinstance(ctx.mocks, dict) and isinstance(ctx.mocks.get("wait_resume"), dict):
            if ctx.mocks["wait_resume"].get(node.id) is True:
                ctx.wait_states.pop(node.id, None)
                return [(0, _with_resume_url(items, resume_url, fired=True))]
        # Otherwise emit items with the resume URL exposed; downstream
        # nodes can choose to use it. The run loop is responsible for
        # parking execution when a wait is unresolved.
        return [(0, _with_resume_url(items, resume_url, fired=False))]

    amount = float(params.get("amount") or 0)
    unit = str(params.get("unit") or "seconds").lower()
    multiplier = {
        "seconds": 1.0,
        "minutes": 60.0,
        "hours": 3600.0,
        "days": 86400.0,
    }.get(unit, 1.0)
    delay = amount * multiplier
    if delay > 0:
        await asyncio.sleep(delay)
    return [(0, items)]


def _with_resume_url(
    items: list[ExecutionItem],
    url: str,
    *,
    fired: bool,
) -> list[ExecutionItem]:
    out: list[ExecutionItem] = []
    for it in items:
        ni = it.clone()
        ni.json = {**it.json, "$execution": {**it.json.get("$execution", {}), "resumeUrl": url, "resumeFired": fired}}
        out.append(ni)
    return out


# ── Merge ─────────────────────────────────────────────────────────────


async def exec_merge(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Merge node — combine items from multiple incoming main edges.

    Modes:
    - ``append`` (default): concat all input items into one stream
    - ``combineByPosition``: zip inputs by position; merge per field with
      optional ``clashHandling`` (``preferInput2`` / ``addSuffix`` / ``override``)
    - ``chooseBranch``: pass through items from a specific input
      (``parameters.chooseBranch`` -> input index, default 0)
    - ``multiplex``: pass items through one at a time
    - ``passThrough``: behave like a no-op passthrough

    The engine buffers items per source; this executor receives the combined
    stream in execution order. When the source-aware view is needed (e.g. for
    ``chooseBranch``), ``ctx.pending_inputs_indexed`` is consulted.
    """
    params = node.parameters or {}
    mode = str(params.get("mode") or "append").lower()
    node_id = node.id

    if mode in ("passthrough", "passThrough", "pass_through"):
        return [(0, items)]

    if mode == "choosebranch" or mode == "chooseBranch":
        choose = int(params.get("chooseBranch") or 0)
        if node_id in ctx.pending_inputs_indexed:
            for idx, src_items in ctx.pending_inputs_indexed[node_id]:
                if idx == choose:
                    return [(0, src_items)]
        return [(0, items)]

    if mode == "multiplex":
        # Pass through combined items one at a time (engine will fan-out)
        return [(0, items)]

    if mode == "append":
        return [(0, items)]

    if mode in ("combinebyposition", "combineByPosition", "combineByFields"):
        # n8n combine merges by position; use clashHandling for duplicate fields
        clash = str(
            (params.get("options") or {}).get("clashHandling")
            or params.get("clashHandling")
            or "preferInput2"
        ).lower()
        if node_id not in ctx.pending_inputs_indexed:
            return [(0, items)]
        per_input = ctx.pending_inputs_indexed[node_id]
        if not per_input:
            return [(0, [])]
        max_len = max(len(it) for _, it in per_input) if per_input else 0
        out: list[ExecutionItem] = []
        # Sort inputs by source index for stable merge
        per_input_sorted = sorted(per_input, key=lambda x: x[0])
        for i in range(max_len):
            base: dict[str, Any] = {}
            for input_idx, src_items in per_input_sorted:
                if i >= len(src_items):
                    continue
                src = src_items[i]
                for k, v in src.json.items():
                    if k in base and clash in ("addsuffix", "addSuffix", "add_suffix"):
                        base[f"{k}_input{input_idx}"] = v
                    elif k in base and clash == "override":
                        base[k] = v
                    elif k in base and clash in ("preferinput1", "preferInput1"):
                        # Keep first
                        pass
                    else:
                        # default: prefer later input (preferInput2)
                        base[k] = v
                # Merge binary from first input that has it
                if not base.get("_has_binary") and src.binary:
                    base["_has_binary"] = True
            ni = ExecutionItem(json=base)
            if any(
                (i < len(src_items) and src_items[i].binary)
                for _, src_items in per_input_sorted
            ):
                # Carry first non-empty binary
                for _, src_items in per_input_sorted:
                    if i < len(src_items) and src_items[i].binary:
                        ni.binary = dict(src_items[i].binary)
                        break
            out.append(ni)
        return [(0, out)]

    # Default fallback: append
    return [(0, items)]


# ── Switch ────────────────────────────────────────────────────────────


async def exec_switch(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Switch node — multi-output routing by per-output rules.

    Each output is a rule list; an item goes to the first output whose rule
    matches. v1 supports ``stringOperation`` and a single per-output
    condition with ``leftValue`` / ``rightValue`` / ``operation``.
    """
    from app.services.workflows.nodes.core import _conditions_pass

    rules = node.parameters.get("rules") if isinstance(node.parameters.get("rules"), dict) else {}
    outputs: list[dict[str, Any]] = []
    if isinstance(rules, dict) and isinstance(rules.get("values"), list):
        outputs = [r for r in rules["values"] if isinstance(r, dict)]
    elif isinstance(rules, list):
        outputs = [r for r in rules if isinstance(r, dict)]

    # Initialise output buckets
    buckets: list[list[ExecutionItem]] = [[] for _ in outputs]
    fallback: list[ExecutionItem] = []

    for item in items:
        matched = False
        for i, out in enumerate(outputs):
            cond = out.get("conditions") if isinstance(out.get("conditions"), dict) else None
            if cond is None:
                continue
            ectx = _expr_ctx(item, ctx)
            if _conditions_pass(dict(cond), ectx):
                buckets[i].append(item)
                matched = True
                break
        if not matched:
            fallback.append(item)

    # Return as list of (index, items); include empty buckets so the engine
    # can still walk the corresponding successor edges.
    result: list[tuple[int, list[ExecutionItem]]] = []
    for i, bucket in enumerate(buckets):
        result.append((i, bucket))
    result.append((len(outputs), fallback))
    return result


# ── Limit ─────────────────────────────────────────────────────────────


async def exec_limit(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    params = node.parameters or {}
    max_items = int(params.get("maxItems") or 0)
    keep = str(params.get("keep") or "firstItems").lower()
    if max_items <= 0:
        return [(0, items)]
    if keep in ("firstitems", "firstItems"):
        return [(0, items[:max_items])]
    if keep in ("lastitems", "lastItems"):
        return [(0, items[-max_items:])]
    return [(0, items[:max_items])]


# ── Remove Duplicates ────────────────────────────────────────────────


async def exec_remove_duplicates(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    params = node.parameters or {}
    compare = params.get("compare") if isinstance(params.get("compare"), dict) else {}
    fields: list[str] = []
    if isinstance(compare.get("fields"), list):
        fields = [str(f) for f in compare["fields"] if isinstance(f, str)]
    elif isinstance(compare.get("by"), str):
        fields = [compare["by"]]
    elif params.get("by"):
        fields = [str(params["by"])]
    seen: set[tuple] = set()
    out: list[ExecutionItem] = []
    for it in items:
        if not fields:
            key = ("__all__", tuple(sorted(it.json.items(), key=lambda kv: str(kv[0]))))
        else:
            key = tuple(it.json.get(f) for f in fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return [(0, out)]


# ── Sort ──────────────────────────────────────────────────────────────


async def exec_sort(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    params = node.parameters or {}
    rules = params.get("sortFields") if isinstance(params.get("sortFields"), dict) else {}
    if not isinstance(rules, dict) or not isinstance(rules.get("fields"), list):
        rules_list: list[dict[str, Any]] = []
    else:
        rules_list = [f for f in rules["fields"] if isinstance(f, dict)]

    def _key(it: ExecutionItem) -> tuple:
        keys: list[Any] = []
        for r in rules_list:
            field = str(r.get("fieldName") or "")
            direction = str(r.get("order") or "ascending").lower()
            v = it.json.get(field)
            keys.append((v is None, v) if direction == "ascending" else (v is None, _neg(v)))
        return tuple(keys)

    sorted_items = sorted(items, key=_key)
    return [(0, sorted_items)]


def _neg(v: Any) -> Any:
    if isinstance(v, (int, float)):
        return -v
    if isinstance(v, str):
        return tuple(-ord(c) for c in v)
    return v


# ── NoOp / Stop and Error ────────────────────────────────────────────


async def exec_noop(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    return [(0, items)]


async def exec_stop_and_error(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    msg = str(params.get("errorMessage") or params.get("message") or "Stopped by Stop and Error node")
    raise RuntimeError(msg)


# ── Execute Sub-workflow ──────────────────────────────────────────────


async def exec_execute_workflow(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Run another workflow by id and return its primary output.

    v1: looks up the workflow doc on ``ctx`` via a callable supplied by the
    engine (``ctx.get_workflow``); the workflow document is then run with a
    fresh engine and the primary main output returned.
    """
    from app.services.workflows.engine import WorkflowEngine

    params = node.parameters or {}
    workflow_doc: dict[str, Any] | None = None
    if ctx.mocks and isinstance(ctx.mocks.get("subworkflows"), dict):
        sub = ctx.mocks["subworkflows"].get(params.get("workflowId"))
        if isinstance(sub, dict):
            workflow_doc = sub
    if workflow_doc is None:
        getter = getattr(ctx, "get_workflow", None)
        if callable(getter):
            try:
                workflow_doc = getter(params.get("workflowId"))
            except Exception:
                workflow_doc = None
    if not workflow_doc:
        raise RuntimeError(f"executeWorkflow: workflow {params.get('workflowId')!r} not found")

    out: list[ExecutionItem] = []

    async def _run_sub() -> list[dict[str, Any]]:
        sub_engine = WorkflowEngine(
            workflow_doc,
            credentials=ctx.credentials,
            credential_bindings=ctx.credential_bindings,
            mocks=ctx.mocks,
            data_tables=ctx.data_tables,
            max_steps=ctx.max_steps,
        )
        result = await sub_engine.run(trigger="executeWorkflow")
        if result.status != "success":
            raise RuntimeError(
                f"executeWorkflow: sub-workflow failed: {result.error_message}"
            )
        return result.final_items

    for item in items:
        final = await _run_sub()
        for row in final:
            inner = row.get("json") if isinstance(row, dict) else None
            base = inner if isinstance(inner, dict) else {}
            ni = item.clone()
            ni.json = {**item.json, **base}
            out.append(ni)
    if not items:
        final = await _run_sub()
        for row in final:
            inner = row.get("json") if isinstance(row, dict) else None
            base = inner if isinstance(inner, dict) else {}
            out.append(ExecutionItem(json=base))
    return [(0, out)]


# ── Webhook (v1: in-engine, mockable; real ingress is an API concern) ──


async def exec_webhook(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Webhook trigger — seed the run with the inbound request payload.

    v1 reads the request from ``ctx.mocks['webhook_request']``. The real
    ingress (an API route that POSTs to ``/api/v1/projects/{id}/workflows/
    {wf}/webhook/{path}``) is implemented in the platform-api routes; this
    executor only needs to expose the request data as a workflow item.

    The returned item's JSON contains: ``body``, ``headers``, ``query``,
    ``method``, ``path``. The first call always returns exactly one item.
    """
    req: dict[str, Any] = {}
    if isinstance(ctx.mocks, dict) and isinstance(ctx.mocks.get("webhook_request"), dict):
        req = dict(ctx.mocks["webhook_request"])
    body = req.get("body")
    headers = req.get("headers") or {}
    query = req.get("query") or {}
    method = req.get("method", "POST")
    path = req.get("path", "/")
    item = ExecutionItem(
        json={
            "body": body,
            "headers": dict(headers) if isinstance(headers, dict) else {},
            "query": dict(query) if isinstance(query, dict) else {},
            "method": str(method),
            "path": str(path),
            "webhook": True,
        }
    )
    # Record path on context so respondToWebhook can echo
    ctx.webhook_meta[node.id] = {
        "path": str(path),
        "method": str(method),
    }
    return [(0, [item])]


async def exec_respond_to_webhook(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Respond to Webhook — capture the response for the original HTTP call.

    Stores the chosen response on ``ctx.webhook_response`` so the platform
    API can return it on the open HTTP request. Per n8n semantics, the
    response can be JSON, text, or a binary file; v1 supports JSON and
    text via ``options.responseBody`` or by passing through the first
    item's JSON.
    """
    params = node.parameters or {}
    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    respond_with = str(options.get("responseMode") or params.get("responseMode") or "lastNode")
    status = int(options.get("responseCode") or 200)

    body: Any = None
    if respond_with == "allEntries":
        body = [i.to_public_dict() for i in items]
    elif respond_with == "binary":
        first = items[0] if items else None
        body = first.binary.get("data").to_dict() if first and first.binary and "data" in first.binary else None
    else:
        # default: lastNode / json
        if items:
            body = items[-1].json
        else:
            body = {}

    # Allow an explicit body override via parameters.responseBody
    if "responseBody" in params and params["responseBody"] is not None:
        body = params["responseBody"]

    ctx.webhook_response = {
        "status": status,
        "body": body,
        "headers": {"content-type": "application/json"},
    }
    return [(0, items)]


# ── Compare Datasets ──────────────────────────────────────────────────


def _split_inputs_by_target_index(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> dict[int, list[ExecutionItem]]:
    """Recover the per-input-item stream for a multi-input node.

    The engine buffers all incoming streams into ``items`` (concatenated in
    ``sorted(source_id)`` order) and clears ``pending_inputs_indexed`` before
    the executor runs. We use the connection graph + ``ctx.node_outputs`` to
    reconstruct which source contributed which slice.

    Falls back to treating the combined stream as input 0 when only one main
    edge is present, and to a single empty input 0 if no edges are found.
    """
    edges = list((ctx.graph.in_main.get(node.id) or []))
    main_edges = [e for e in edges if e.connection_type == "main"]
    if not main_edges:
        return {0: list(items)}

    by_index: dict[int, list[ExecutionItem]] = {}
    for e in main_edges:
        if e.target_index in by_index:
            continue
        src_node = ctx.graph.nodes_by_id.get(e.source_id)
        if src_node is None:
            continue
        src_items = ctx.node_outputs.get(src_node.name)
        if src_items is None:
            continue
        by_index[e.target_index] = list(src_items)

    # Fill missing input indices with empty streams so downstream logic
    # can rely on both being present.
    for idx in (0, 1):
        by_index.setdefault(idx, [])
    return by_index


def _match_key(item: ExecutionItem, fields: list[str]) -> tuple:
    if not fields:
        return ()
    return tuple(item.json.get(f) for f in fields)


def _fields_equal(a: ExecutionItem, b: ExecutionItem, fields: list[str]) -> bool:
    for f in fields:
        if a.json.get(f) != b.json.get(f):
            return False
    return True


async def exec_compare_datasets(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Compare two input streams and bucket items by match outcome.

    Reads two main input streams (input 1 → target_index 0, input 2 → target_index 1)
    from the engine's buffered items, then pairs items by ``parameters.fieldsToMatch``
    and routes them into up to four buckets:

    - ``equal_items``          — both items match on all ``fieldsToMatch`` AND on
                                 all ``parameters.skipOnEqual`` fields
    - ``different_items``      — items match on ``fieldsToMatch`` but differ on
                                 at least one ``skipOnEqual`` field
    - ``unique_to_input_1``    — items in input 1 with no match in input 2
    - ``unique_to_input_2``    — items in input 2 with no match in input 1

    Parameters shape (clean-room n8n compareDatasets v1):

    .. code-block:: json

        {
          "fieldsToMatch": ["id"],
          "skipOnEqual":   ["name"],
          "resolveBy":     "preferByField",
          "outputFormat":  "single"
        }

    - ``resolveBy = preferByField`` (default): each input-1 item is paired with
      the first matching input-2 item, which is then consumed (no double-pairing).
    - ``resolveBy = preferAll``: an input-1 item is paired with *all* matches in
      input 2; remaining input-2 items with no match still go to
      ``unique_to_input_2``.
    - ``outputFormat = single``: emit a single output (index 0) with every
      bucket item, tagged by a ``compareBucket`` field. Each bucket is also
      tagged with a ``compareOpposite`` field carrying the partner item
      (``null`` for unique buckets).
    - ``outputFormat = separate``: emit four separate outputs
      (0=equal, 1=different, 2=unique_to_input_1, 3=unique_to_input_2).
      Empty buckets are emitted as a single summary item so the engine
      still walks their successor edges.
    """
    params = node.parameters or {}
    fields_raw = params.get("fieldsToMatch")
    if isinstance(fields_raw, list):
        fields = [str(f) for f in fields_raw if isinstance(f, str) and f]
    else:
        fields = []
    skip_raw = params.get("skipOnEqual")
    if isinstance(skip_raw, list):
        skip_fields = [str(f) for f in skip_raw if isinstance(f, str) and f]
    else:
        skip_fields = []
    resolve_by = str(params.get("resolveBy") or "preferByField").lower()
    output_format = str(params.get("outputFormat") or "single").lower()

    streams = _split_inputs_by_target_index(node, items, ctx=ctx)
    input_1 = streams.get(0) or []
    input_2 = streams.get(1) or []

    consume = resolve_by not in ("preferall", "prefer_all")

    input_2_pool: list[ExecutionItem] = list(input_2)
    input_2_matched: set[int] = set()
    input_1_matched: set[int] = set()

    equal_items: list[ExecutionItem] = []
    different_items: list[ExecutionItem] = []
    unique_to_input_1: list[ExecutionItem] = []

    for i, a in enumerate(input_1):
        key = _match_key(a, fields)
        partner: ExecutionItem | None = None
        partner_j: int | None = None
        for j, b in enumerate(input_2_pool):
            if _match_key(b, fields) == key:
                partner = b
                partner_j = j
                break
        if partner is None:
            unique_to_input_1.append(a)
            continue
        input_1_matched.add(i)
        if consume:
            input_2_matched.add(partner_j)
        if skip_fields and _fields_equal(a, partner, skip_fields):
            ni = a.clone()
            ni.json = {**a.json, "compareBucket": "equal_items", "compareOpposite": partner.json}
            equal_items.append(ni)
        else:
            ni = a.clone()
            ni.json = {**a.json, "compareBucket": "different_items", "compareOpposite": partner.json}
            different_items.append(ni)

    unique_to_input_2: list[ExecutionItem] = []
    for j, b in enumerate(input_2_pool):
        if consume and j in input_2_matched:
            continue
        ni = b.clone()
        ni.json = {**b.json, "compareBucket": "unique_to_input_2", "compareOpposite": None}
        unique_to_input_2.append(ni)

    # Tag unique_to_input_1 with bucket name (partner is null)
    for k, it in enumerate(unique_to_input_1):
        if it.json.get("compareBucket") is None:
            it.json = {**it.json, "compareBucket": "unique_to_input_1", "compareOpposite": None}

    if output_format in ("single", "all_in_one"):
        combined: list[ExecutionItem] = []
        combined.extend(equal_items)
        combined.extend(different_items)
        combined.extend(unique_to_input_1)
        combined.extend(unique_to_input_2)
        return [(0, combined)]

    # separate outputs: 0=equal, 1=different, 2=unique_to_input_1, 3=unique_to_input_2
    def _bucket_summary(name: str, real: list[ExecutionItem]) -> list[ExecutionItem]:
        if real:
            return real
        # Emit a single summary item so the engine walks the successor edge
        # even when the bucket is empty.
        return [
            ExecutionItem(
                json={
                    "compareBucket": name,
                    "compareSummary": True,
                    "count": 0,
                }
            )
        ]

    return [
        (0, _bucket_summary("equal_items", equal_items)),
        (1, _bucket_summary("different_items", different_items)),
        (2, _bucket_summary("unique_to_input_1", unique_to_input_1)),
        (3, _bucket_summary("unique_to_input_2", unique_to_input_2)),
    ]


# ── Sticky Note (UI-only, no runtime side effects) ───────────────────


async def exec_sticky_note(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    del node, ctx
    return [(0, items)]
