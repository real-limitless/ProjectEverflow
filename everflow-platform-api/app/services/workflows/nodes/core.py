"""Core transform / control / trigger executors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.workflows.code_js import run_js_each_item
from app.services.workflows.expression import ExpressionContext, evaluate, evaluate_deep
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext


def _expr_ctx(item: ExecutionItem, ctx: EngineContext) -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


async def exec_trigger(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    del node, ctx
    if items:
        return [(0, items)]
    return [(0, [ExecutionItem(json={})])]


async def exec_set(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    assignments = (
        (params.get("assignments") or {}).get("assignments")
        if isinstance(params.get("assignments"), dict)
        else params.get("assignments")
    )
    if not isinstance(assignments, list):
        assignments = []
    include_other = bool(params.get("includeOtherFields", True))
    out: list[ExecutionItem] = []
    for item in items:
        ectx = _expr_ctx(item, ctx)
        base = dict(item.json) if include_other else {}
        for a in assignments:
            if not isinstance(a, dict):
                continue
            name = str(a.get("name") or "")
            if not name:
                continue
            val = evaluate(a.get("value"), ectx)
            base[name] = val
        ni = item.clone()
        ni.json = base
        out.append(ni)
    return [(0, out)]


def _eval_condition(cond: dict[str, Any], ectx: ExpressionContext) -> bool:
    left = evaluate(cond.get("leftValue"), ectx)
    right = evaluate(cond.get("rightValue"), ectx)
    op = cond.get("operator") or {}
    if isinstance(op, dict):
        operation = str(op.get("operation") or "equals")
        op_type = str(op.get("type") or "string")
    else:
        operation = str(op)
        op_type = "string"
    ls = "" if left is None else str(left)
    rs = "" if right is None else str(right)
    if operation in ("equals", "equal"):
        if op_type == "number":
            try:
                return float(ls) == float(rs)
            except ValueError:
                return ls == rs
        return ls == rs
    if operation == "notEquals":
        return ls != rs
    if operation == "contains":
        return rs in ls
    if operation == "notContains":
        return rs not in ls
    if operation == "startsWith":
        return ls.startswith(rs)
    if operation == "endsWith":
        return ls.endswith(rs)
    if operation == "isEmpty":
        return left is None or ls == ""
    if operation == "isNotEmpty":
        return left is not None and ls != ""
    if operation in ("gt", "larger"):
        try:
            return float(ls) > float(rs)
        except ValueError:
            return False
    if operation in ("lt", "smaller"):
        try:
            return float(ls) < float(rs)
        except ValueError:
            return False
    return False


def _conditions_pass(params: dict[str, Any], ectx: ExpressionContext) -> bool:
    conditions = params.get("conditions")
    combinator = "and"
    cond_list: list[dict[str, Any]] = []
    if isinstance(conditions, dict):
        combinator = str(conditions.get("combinator") or "and").lower()
        raw = conditions.get("conditions")
        if isinstance(raw, list):
            cond_list = [c for c in raw if isinstance(c, dict)]
        # filter node nests options separately
    elif isinstance(conditions, list):
        cond_list = [c for c in conditions if isinstance(c, dict)]
    # n8n filter v2 stores conditions at top with combinator
    if not cond_list and isinstance(params.get("conditions"), dict):
        # already handled
        pass
    # Filter node shape from Stock Agent: parameters.conditions is list + combinator sibling
    if not cond_list:
        # try direct
        raw = params.get("conditions")
        if isinstance(raw, list):
            cond_list = [c for c in raw if isinstance(c, dict)]
    # Stock Agent filter stores combinator inside conditions object OR as sibling
    if isinstance(params.get("conditions"), dict):
        cobj = params["conditions"]
        combinator = str(cobj.get("combinator") or combinator).lower()
        if isinstance(cobj.get("conditions"), list):
            cond_list = [c for c in cobj["conditions"] if isinstance(c, dict)]
    # Also top-level combinator used by some versions
    if params.get("combinator"):
        combinator = str(params["combinator"]).lower()
    # Stock Agent Filter: parameters has conditions list + combinator key
    # From analysis: "conditions": [...], "combinator": "or" — but also nested in object
    if not cond_list:
        # flattened from import: conditions may be the list with combinator in options
        maybe = params.get("conditions")
        if isinstance(maybe, list):
            cond_list = [c for c in maybe if isinstance(c, dict)]

    # Re-read Stock Agent structure: parameters.conditions is OBJECT with conditions array
    # We already handle that. Also handle when combinator is on same object.

    if not cond_list:
        return True
    results = [_eval_condition(c, ectx) for c in cond_list]
    if combinator == "or":
        return any(results)
    return all(results)


async def exec_filter(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    kept: list[ExecutionItem] = []
    for item in items:
        ectx = _expr_ctx(item, ctx)
        if _conditions_pass(params, ectx):
            kept.append(item)
    return [(0, kept)]


async def exec_if(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    true_items: list[ExecutionItem] = []
    false_items: list[ExecutionItem] = []
    for item in items:
        ectx = _expr_ctx(item, ctx)
        if _conditions_pass(params, ectx):
            true_items.append(item)
        else:
            false_items.append(item)
    return [(0, true_items), (1, false_items)]


async def exec_code(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    params = node.parameters or {}
    mode = str(params.get("mode") or "runOnceForAllItems")
    js = str(params.get("jsCode") or "")
    out: list[ExecutionItem] = []
    if mode == "runOnceForEachItem":
        for item in items:
            new_json = run_js_each_item(js, item.json)
            ni = item.clone()
            ni.json = new_json if isinstance(new_json, dict) else {"result": new_json}
            out.append(ni)
    else:
        # all items — expose as array in a single pass using first item only for simplicity
        if not items:
            return [(0, [])]
        # Provide $input-like by joining — for v1 run each and collect
        for item in items:
            new_json = run_js_each_item(js, item.json)
            ni = item.clone()
            ni.json = new_json if isinstance(new_json, dict) else {"result": new_json}
            out.append(ni)
    return [(0, out)]


async def exec_aggregate(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    params = node.parameters or {}
    mode = str(params.get("aggregate") or "")
    if mode == "aggregateAllItemData" or not mode:
        dest = str(params.get("destinationFieldName") or "data")
        rows = [dict(i.json) for i in items]
        # fieldsToAggregate empty → aggregate all items into one
        if params.get("fieldsToAggregate") and mode != "aggregateAllItemData":
            # default aggregate individual fields — treat as collect all json
            pass
        return [(0, [ExecutionItem(json={dest: rows})])]
    # fallback: single item with all jsons
    return [(0, [ExecutionItem(json={"data": [i.json for i in items]})])]


async def exec_split_out(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    del ctx
    params = node.parameters or {}
    field = str(params.get("fieldToSplitOut") or "data")
    include = str(params.get("include") or "noOtherFields")
    out: list[ExecutionItem] = []
    for item in items:
        val = item.json.get(field)
        if not isinstance(val, list):
            out.append(item)
            continue
        for el in val:
            if include == "allOtherFields":
                base = {k: v for k, v in item.json.items() if k != field}
            else:
                base = {}
            if isinstance(el, dict):
                base.update(el)
            else:
                base[field] = el
            ni = item.clone()
            ni.json = base
            out.append(ni)
    return [(0, out)]


async def exec_split_in_batches(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """n8n splitInBatches: output 0=done, 1=loop.

    Lifecycle:
    - First call (not loop return): load items into queue, emit first batch on loop.
    - Loop return (batch_loop_return): append processed items, emit next batch or done.
    """
    params = node.parameters or {}
    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    batch_size = int(options.get("batchSize") or params.get("batchSize") or 1)
    state = ctx.batch_state.setdefault(node.id, {"queue": [], "processed": [], "started": False})

    if ctx.batch_reset.get(node.id):
        state["queue"] = []
        state["processed"] = []
        state["started"] = False
        ctx.batch_reset[node.id] = False

    if ctx.batch_loop_return.get(node.id):
        # Completed one loop body iteration
        if items:
            state["processed"].extend(items)
        ctx.batch_loop_return[node.id] = False
    elif not state["started"]:
        state["queue"] = list(items)
        state["processed"] = []
        state["started"] = True
    elif items and not state["queue"]:
        # Fresh upstream while idle — restart
        state["queue"] = list(items)
        state["processed"] = []
        state["started"] = True

    queue: list[ExecutionItem] = state["queue"]
    if queue:
        batch = queue[:batch_size]
        state["queue"] = queue[batch_size:]
        return [(1, batch)]

    done_items = list(state["processed"])
    state["started"] = False
    state["processed"] = []
    state["queue"] = []
    return [(0, done_items)]
