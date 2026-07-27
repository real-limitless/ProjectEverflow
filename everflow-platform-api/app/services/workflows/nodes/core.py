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


async def exec_error_trigger(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Error Trigger — emit a single item with the last run error.

    Clean-room n8n ``n8n-nodes-base.errorTrigger`` v1.

    Reads ``ctx.fatal_error`` (the engine stores the last fatal error
    here as ``"{node.name}: {exc}"``) and emits one item whose
    ``error`` field is a dict of:

    - ``message``  — the exception text (after stripping the leading
      ``nodeName: `` prefix)
    - ``nodeName`` — the name of the node that raised
    - ``n8n_type`` — the n8n type of that node, recovered from the
      last error step in ``ctx.steps`` or the graph
    - ``runId``    — ``ctx.run_id``

    When no error is set (``ctx.fatal_error`` is ``None``), emits one
    item with ``{"error": None}`` so downstream nodes can branch on
    presence/absence.

    ``ctx.last_error`` is also read as a fallback alias for parity
    with the engine's stated ``error_workflow`` plumbing.

    v1 does not subscribe to errors in real time — the engine's
    ``error_workflow`` / ``errors`` sub-context handling is what would
    invoke this node on a fatal failure. This executor only formats
    the payload given an already-set ``fatal_error``.
    """
    del items
    fatal = getattr(ctx, "fatal_error", None)
    if fatal is None:
        fatal = getattr(ctx, "last_error", None)

    run_id = getattr(ctx, "run_id", None)

    if not fatal:
        return [(0, [ExecutionItem(json={"error": None})])]

    message = str(fatal)
    node_name = ""
    if ":" in message:
        node_name, _, message = message.partition(":")
        message = message.lstrip()

    n8n_type = ""
    steps = getattr(ctx, "steps", None) or []
    for s in reversed(steps):
        if getattr(s, "status", None) != "error":
            continue
        if node_name and getattr(s, "node_name", None) != node_name:
            continue
        n8n_type = str(getattr(s, "n8n_type", "") or "")
        if n8n_type:
            break
    if not n8n_type and node_name:
        gnode = ctx.graph.nodes_by_name.get(node_name) if ctx.graph is not None else None
        if gnode is not None:
            n8n_type = str(getattr(gnode, "type", "") or "")

    return [
        (
            0,
            [
                ExecutionItem(
                    json={
                        "error": {
                            "message": message,
                            "nodeName": node_name,
                            "n8n_type": n8n_type,
                            "runId": run_id,
                        }
                    }
                )
            ],
        )
    ]


async def exec_chat_trigger(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Chat Trigger — emit one item per chat message.

    Clean-room n8n ``@n8n/n8n-nodes-langchain.chatTrigger`` v1.

    v1 is an in-engine stub: real chat hosting is a UI concern, so the
    executor just shapes the payload. When a chat message has been
    pinned via ``ctx.mocks['chat_input']`` (a dict like
    ``{"text": "hello", "sessionId": "abc"}``), emit one item whose
    JSON contains ``chatInput`` (the message text) and ``sessionId``.
    When no mock is set, emit one fallback item with
    ``{"chatInput": "", "sessionId": <params.sessionId or "default">}``.
    """
    del items
    params = node.parameters or {}
    default_session = str(params.get("sessionId") or "default")

    chat: dict[str, Any] = {}
    if isinstance(ctx.mocks, dict) and isinstance(ctx.mocks.get("chat_input"), dict):
        chat = dict(ctx.mocks["chat_input"])

    if not chat:
        return [
            (
                0,
                [
                    ExecutionItem(
                        json={
                            "chatInput": "",
                            "sessionId": default_session,
                        }
                    )
                ],
            )
        ]

    text = chat.get("text")
    if text is None:
        text = chat.get("chatInput")
    session_id = chat.get("sessionId")
    if session_id is None or session_id == "":
        session_id = default_session

    payload: dict[str, Any] = {
        "chatInput": str(text) if text is not None else "",
        "sessionId": str(session_id),
    }
    return [(0, [ExecutionItem(json=payload)])]


async def exec_sse_trigger(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """SSE Trigger — emit one item per Server-Sent Event.

    Clean-room n8n ``n8n-nodes-base.sseTrigger`` v1.

    v1 is an in-engine stub: real SSE connection handling is an API
    concern, so the executor just shapes the payload. When an SSE event
    has been pinned via ``ctx.mocks['sse_event']`` — either a single dict
    (``{"event": "name", "data": "...", "id": "..."}``) or a list of
    such dicts — emit one item per event. Each emitted item carries
    ``event``, ``data``, ``id`` plus any other fields present on the
    source event dict.

    When no mock is set, emit a single fallback item with
    ``{"event": "", "data": "", "id": ""}`` so downstream nodes can
    still branch on presence/absence.
    """
    del items
    mock = None
    if isinstance(ctx.mocks, dict):
        mock = ctx.mocks.get("sse_event")

    if mock is None:
        return [(0, [ExecutionItem(json={"event": "", "data": "", "id": ""})])]

    if isinstance(mock, dict):
        events: list[dict[str, Any]] = [mock]
    elif isinstance(mock, list):
        events = [e for e in mock if isinstance(e, dict)]
        if not events:
            return [(0, [ExecutionItem(json={"event": "", "data": "", "id": ""})])]
    else:
        return [(0, [ExecutionItem(json={"event": "", "data": "", "id": ""})])]

    out: list[ExecutionItem] = []
    for ev in events:
        payload: dict[str, Any] = dict(ev)
        payload.setdefault("event", "")
        payload.setdefault("data", "")
        payload.setdefault("id", "")
        out.append(ExecutionItem(json=payload))
    return [(0, out)]


async def exec_local_file_trigger(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Local File Trigger — emit one item per detected file change.

    Clean-room n8n ``n8n-nodes-base.localFileTrigger`` v1.

    v1 is an in-engine stub: real filesystem watching is an environment
    concern, so the executor just shapes the payload. When file changes
    have been pinned via ``ctx.mocks['file_change']`` — either a single
    dict (``{"path": "...", "event": "modified", "size": 123}``) or a
    list of such dicts — emit one item per change. Each emitted item
    carries ``path``, ``event``, ``size`` plus any other fields present
    on the source dict.

    When no mock is set, emit a single fallback item with
    ``{"path": "", "event": "", "size": 0}`` so downstream nodes can
    still branch on presence/absence.

    If ``node.parameters.path`` is set and the emitted item has an
    empty ``path`` field, default the path to the configured value.
    """
    del items
    params = node.parameters or {}
    default_path = str(params.get("path") or "")

    mock: object = None
    if isinstance(ctx.mocks, dict):
        mock = ctx.mocks.get("file_change")

    if mock is None:
        payload: dict[str, Any] = {"path": default_path, "event": "", "size": 0}
        return [(0, [ExecutionItem(json=payload)])]

    if isinstance(mock, dict):
        changes: list[dict[str, Any]] = [mock]
    elif isinstance(mock, list):
        changes = [c for c in mock if isinstance(c, dict)]
        if not changes:
            return [
                (
                    0,
                    [ExecutionItem(json={"path": default_path, "event": "", "size": 0})],
                )
            ]
    else:
        return [
            (
                0,
                [ExecutionItem(json={"path": default_path, "event": "", "size": 0})],
            )
        ]

    out: list[ExecutionItem] = []
    for ch in changes:
        payload = dict(ch)
        payload.setdefault("path", default_path)
        payload.setdefault("event", "")
        payload.setdefault("size", 0)
        out.append(ExecutionItem(json=payload))
    return [(0, out)]


async def exec_form_trigger(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Form Trigger — emit one item per form submission.

    Clean-room n8n ``n8n-nodes-base.formTrigger`` v1.

    v1 is in-engine only: real form hosting is a UI concern, so the executor
    just shapes the payload. When a submission has been pinned via
    ``ctx.mocks['form_submission']`` (a dict like
    ``{"submittedAt": "ISO8601", "formId": "...", "fields": {"name": "..."}}``),
    emit one item whose JSON contains ``submittedAt``, ``formId``, and each
    ``fields`` entry at the top level so downstream ``$json.name`` style
    expressions work. When no mock is set, emit one fallback item with
    ``{"formId": <param or "default">}`` and the rest empty.
    """
    del items
    params = node.parameters or {}
    default_form_id = str(params.get("formId") or "default")

    submission: dict[str, Any] = {}
    if isinstance(ctx.mocks, dict) and isinstance(ctx.mocks.get("form_submission"), dict):
        submission = dict(ctx.mocks["form_submission"])

    if not submission:
        return [(0, [ExecutionItem(json={"formId": default_form_id})])]

    fields_raw = submission.get("fields")
    fields: dict[str, Any] = dict(fields_raw) if isinstance(fields_raw, dict) else {}
    payload: dict[str, Any] = {
        "submittedAt": submission.get("submittedAt"),
        "formId": str(submission.get("formId") or default_form_id),
    }
    payload.update(fields)
    return [(0, [ExecutionItem(json=payload)])]


async def exec_workflow_trigger(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: EngineContext,
) -> list[tuple[int, list[ExecutionItem]]]:
    """Workflow Trigger — emit one item with the calling workflow's metadata.

    Clean-room n8n ``n8n-nodes-base.workflowTrigger`` v1.

    v1 is an in-engine stub: the legacy workflowTrigger fired when one
    workflow invoked another via the older non-typed n8n webhook style.
    Real cross-workflow routing is handled by the engine, so this executor
    just shapes the payload. When a call has been pinned via
    ``ctx.mocks['workflow_call']`` (a dict like
    ``{"workflowId": "...", "executionId": "...", "data": {...}}``), emit
    one item whose JSON contains ``workflowId``, ``executionId``, and
    every key from ``data`` promoted to the top level so downstream
    ``$json.*`` expressions see the input directly.

    When no mock is set, emit one fallback item with
    ``{"workflowId": "", "executionId": ""}`` so downstream nodes can
    still branch on presence/absence.
    """
    del items

    call: dict[str, Any] = {}
    if isinstance(ctx.mocks, dict) and isinstance(ctx.mocks.get("workflow_call"), dict):
        call = dict(ctx.mocks["workflow_call"])

    if not call:
        return [(0, [ExecutionItem(json={"workflowId": "", "executionId": ""})])]

    data_raw = call.get("data")
    data: dict[str, Any] = dict(data_raw) if isinstance(data_raw, dict) else {}

    payload: dict[str, Any] = {
        "workflowId": str(call.get("workflowId") or ""),
        "executionId": str(call.get("executionId") or ""),
    }
    payload.update(data)
    return [(0, [ExecutionItem(json=payload)])]


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
