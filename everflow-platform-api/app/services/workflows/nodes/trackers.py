"""Project tracker executors (clean-room n8n-nodes-base.*).

Covers six project-tracker nodes:

- ``n8n-nodes-base.clickUp`` — ClickUp task operations
- ``n8n-nodes-base.trello`` — Trello card operations
- ``n8n-nodes-base.asana`` — Asana task operations
- ``n8n-nodes-base.mondayCom`` — Monday.com item operations
- ``n8n-nodes-base.todoist`` — Todoist task operations
- ``n8n-nodes-base.linear`` — Linear issue operations

Each executor honors ``parameters.operation`` (default ``create``) and
emits one item per input carrying the operation-specific fields and
``source: '<service>'``.

All API calls are mock-driven — no real network I/O is performed.

Mock precedence (per node):

1. ``ctx.mocks['<node>_response']`` — callable invoked as
   ``mock(operation, params, item, ctx)`` or dict used directly.
2. ``ctx.mocks['http_response']`` — generic fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response.
3. Offline synthetic response with deterministic-looking ids.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)


CLICKUP_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createList",
)
CLICKUP_DEFAULT_OPERATION: str = "create"

TRELLO_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createBoard",
    "createList",
)
TRELLO_DEFAULT_OPERATION: str = "create"

ASANA_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createProject",
)
ASANA_DEFAULT_OPERATION: str = "create"

MONDAY_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createBoard",
)
MONDAY_DEFAULT_OPERATION: str = "create"

TODOIST_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createProject",
)
TODOIST_DEFAULT_OPERATION: str = "create"

LINEAR_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createProject",
)
LINEAR_DEFAULT_OPERATION: str = "create"


def _ectx(item: ExecutionItem, ctx: "EngineContext") -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_coerce_str(v) for v in value if v is not None)
    if isinstance(value, dict):
        for key in ("value", "name", "id", "title", "content"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _random_id(source: str) -> str:
    return f"mock_{source}_{random.randint(10000, 99999)}"


def _resolve_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> Any:
    raw = params.get(key)
    if raw is not None:
        return evaluate(raw, ectx)
    for fk in json_fallbacks:
        if fk in item.json and item.json[fk] is not None:
            return item.json[fk]
    return None


def _resolve_str_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
    *,
    default: str = "",
) -> str:
    value = _resolve_param(params, key, item, ectx, json_fallbacks)
    s = _coerce_str(value).strip()
    return s or default


@dataclass(frozen=True)
class _Field:
    field: str
    param: str
    fallbacks: tuple[str, ...]
    default: str = ""
    role: str = "data"


@dataclass(frozen=True)
class _TrackerConfig:
    source: str
    mock_key: str
    operations: tuple[str, ...]
    default_operation: str
    default_name: str
    default_status: str
    fields: tuple[_Field, ...]


_CONFIGS: dict[str, _TrackerConfig] = {
    "clickup": _TrackerConfig(
        source="clickup",
        mock_key="clickup_response",
        operations=CLICKUP_OPERATIONS,
        default_operation=CLICKUP_DEFAULT_OPERATION,
        default_name="Mock Task",
        default_status="Open",
        fields=(
            _Field("taskId", "taskId", ("taskId", "id"), role="id"),
            _Field("name", "name", ("name", "title"), role="name"),
            _Field("status", "status", ("status",), role="status"),
        ),
    ),
    "trello": _TrackerConfig(
        source="trello",
        mock_key="trello_response",
        operations=TRELLO_OPERATIONS,
        default_operation=TRELLO_DEFAULT_OPERATION,
        default_name="Mock Card",
        default_status="Open",
        fields=(
            _Field("cardId", "cardId", ("cardId", "id"), role="id"),
            _Field("name", "name", ("name", "title"), role="name"),
            _Field("listId", "listId", ("listId",), role="container"),
        ),
    ),
    "asana": _TrackerConfig(
        source="asana",
        mock_key="asana_response",
        operations=ASANA_OPERATIONS,
        default_operation=ASANA_DEFAULT_OPERATION,
        default_name="Mock Task",
        default_status="Open",
        fields=(
            _Field("taskId", "taskId", ("taskId", "id"), role="id"),
            _Field("name", "name", ("name", "title"), role="name"),
            _Field("projectId", "projectId", ("projectId",), role="container"),
        ),
    ),
    "monday": _TrackerConfig(
        source="monday",
        mock_key="monday_response",
        operations=MONDAY_OPERATIONS,
        default_operation=MONDAY_DEFAULT_OPERATION,
        default_name="Mock Item",
        default_status="Open",
        fields=(
            _Field("itemId", "itemId", ("itemId", "id"), role="id"),
            _Field("itemName", "itemName", ("itemName", "name"), role="name"),
            _Field("boardId", "boardId", ("boardId",), role="container"),
        ),
    ),
    "todoist": _TrackerConfig(
        source="todoist",
        mock_key="todoist_response",
        operations=TODOIST_OPERATIONS,
        default_operation=TODOIST_DEFAULT_OPERATION,
        default_name="Mock Task",
        default_status="Open",
        fields=(
            _Field("taskId", "taskId", ("taskId", "id"), role="id"),
            _Field("content", "content", ("content", "name", "title"), role="name"),
            _Field("projectId", "projectId", ("projectId",), role="container"),
        ),
    ),
    "linear": _TrackerConfig(
        source="linear",
        mock_key="linear_response",
        operations=LINEAR_OPERATIONS,
        default_operation=LINEAR_DEFAULT_OPERATION,
        default_name="Mock Issue",
        default_status="Open",
        fields=(
            _Field("issueId", "issueId", ("issueId", "id"), role="id"),
            _Field("title", "title", ("title", "name"), role="name"),
            _Field("status", "status", ("status",), role="status"),
        ),
    ),
}


def _synthesize(
    config: _TrackerConfig,
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in config.fields:
        val = resolved.get(f.field, "")
        if f.role == "id":
            if operation in ("get", "update", "delete"):
                out[f.field] = val or _random_id(config.source)
            else:
                out[f.field] = _random_id(config.source)
        elif f.role == "name":
            out[f.field] = val or config.default_name
        elif f.role == "status":
            out[f.field] = val or config.default_status
        elif f.role == "container":
            out[f.field] = val or _random_id(config.source)
        else:
            out[f.field] = val or f.default
    return out


def _resolve_response(
    *,
    config: _TrackerConfig,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    ctx: "EngineContext",
    synth: Any,
) -> tuple[dict[str, Any], str]:
    mocks = ctx.mocks or {}
    nmock = mocks.get(config.mock_key)
    if nmock is not None:
        if callable(nmock):
            raw = nmock(operation, params, item, ctx)
        else:
            raw = nmock
        if isinstance(raw, dict):
            return raw, config.mock_key
        return synth(), config.mock_key

    hmock = mocks.get("http_response")
    if hmock is not None and isinstance(hmock, dict):
        body = hmock.get("body")
        if isinstance(body, dict):
            return body, "http_response"

    return synth(), "offline"


def _build_payload(
    config: _TrackerConfig,
    operation: str,
    response: dict[str, Any],
    resolved: dict[str, str],
    source: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for f in config.fields:
        val = response.get(f.field)
        if val in (None, ""):
            val = resolved.get(f.field, "")
        payload[f.field] = val
    for k, v in response.items():
        if k not in payload and k not in ("operation", "source", "mockSource"):
            payload[k] = v
    payload["operation"] = operation
    payload["source"] = config.source
    if source != config.mock_key:
        payload["mockSource"] = source
    return payload


async def _exec_tracker(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
    config: _TrackerConfig,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    op_raw = str(params.get("operation") or config.default_operation).strip()
    canonical = {o.lower(): o for o in config.operations}
    operation = canonical.get(op_raw.lower(), op_raw)
    if operation not in config.operations:
        raise ValueError(
            f"{config.source}: unsupported operation {op_raw!r}; "
            f"expected one of {config.operations}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        resolved: dict[str, str] = {}
        for f in config.fields:
            resolved[f.field] = _resolve_str_param(
                params, f.param, item, ectx, f.fallbacks, default=f.default
            )

        def _synth() -> dict[str, Any]:
            return _synthesize(config, operation, resolved)

        response, source = _resolve_response(
            config=config,
            operation=operation,
            params=params,
            item=item,
            ctx=ctx,
            synth=_synth,
        )

        payload = _build_payload(config, operation, response, resolved, source)
        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)

        logger.info(
            "%s %s source=%s",
            config.source,
            operation,
            source,
        )

    return [(0, out)]


async def exec_clickup(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """ClickUp node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["clickup"])


async def exec_trello(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Trello node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["trello"])


async def exec_asana(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Asana node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["asana"])


async def exec_monday(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Monday.com node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["monday"])


async def exec_todoist(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Todoist node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["todoist"])


async def exec_linear(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Linear node — routes on ``parameters.operation``."""
    return await _exec_tracker(node, items, ctx=ctx, config=_CONFIGS["linear"])


__all__ = [
    "exec_clickup",
    "exec_trello",
    "exec_asana",
    "exec_monday",
    "exec_todoist",
    "exec_linear",
    "CLICKUP_OPERATIONS",
    "CLICKUP_DEFAULT_OPERATION",
    "TRELLO_OPERATIONS",
    "TRELLO_DEFAULT_OPERATION",
    "ASANA_OPERATIONS",
    "ASANA_DEFAULT_OPERATION",
    "MONDAY_OPERATIONS",
    "MONDAY_DEFAULT_OPERATION",
    "TODOIST_OPERATIONS",
    "TODOIST_DEFAULT_OPERATION",
    "LINEAR_OPERATIONS",
    "LINEAR_DEFAULT_OPERATION",
]
