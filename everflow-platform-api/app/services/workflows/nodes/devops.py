"""DevOps integration executors (clean-room n8n-nodes-base.*).

Covers six DevOps nodes:

- ``n8n-nodes-base.gitlab`` — GitLab issue/MR operations
- ``n8n-nodes-base.gitlabTrigger`` — GitLab webhook trigger
- ``n8n-nodes-base.githubTrigger`` — GitHub webhook trigger
- ``n8n-nodes-base.bitbucketTrigger`` — Bitbucket webhook trigger
- ``n8n-nodes-base.jenkins`` — Jenkins job/build operations
- ``n8n-nodes-base.circleCi`` — CircleCI pipeline/workflow/job operations

Each action executor honors ``parameters.operation`` and emits one item
per input carrying the operation-specific fields and
``source: '<service>'``.

Each trigger executor emits one item per received webhook event.

All API calls are mock-driven — no real network I/O is performed.

Mock precedence for action nodes:

1. ``ctx.mocks['<node>_response']`` — callable invoked as
   ``mock(operation, params, item, ctx)`` or dict used directly.
2. ``ctx.mocks['http_response']`` — generic fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response.
3. Offline synthetic response with deterministic-looking ids.

Mock precedence for trigger nodes:

1. ``ctx.mocks['<node>_trigger_payload']`` — dict used directly or
   callable invoked as ``mock(node, ctx)``.
2. ``ctx.mocks['trigger_payload']`` — generic trigger-payload fallback.
3. Offline synthetic webhook payload.
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


GITLAB_OPERATIONS: tuple[str, ...] = (
    "create",
    "get",
    "update",
    "delete",
    "list",
    "createMergeRequest",
    "getMergeRequest",
)
GITLAB_DEFAULT_OPERATION: str = "create"

JENKINS_OPERATIONS: tuple[str, ...] = (
    "trigger",
    "getJob",
    "getBuild",
    "listJobs",
)
JENKINS_DEFAULT_OPERATION: str = "trigger"

CIRCLECI_OPERATIONS: tuple[str, ...] = (
    "trigger",
    "getPipeline",
    "getWorkflow",
    "getJob",
)
CIRCLECI_DEFAULT_OPERATION: str = "trigger"


# ── Helpers ───────────────────────────────────────────────────────────


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


# ── Action node config ────────────────────────────────────────────────


@dataclass(frozen=True)
class _Field:
    field: str
    param: str
    fallbacks: tuple[str, ...]
    default: str = ""
    role: str = "data"


@dataclass(frozen=True)
class _ActionConfig:
    source: str
    mock_key: str
    operations: tuple[str, ...]
    default_operation: str
    fields: tuple[_Field, ...]


_ACTION_CONFIGS: dict[str, _ActionConfig] = {
    "gitlab": _ActionConfig(
        source="gitlab",
        mock_key="gitlab_response",
        operations=GITLAB_OPERATIONS,
        default_operation=GITLAB_DEFAULT_OPERATION,
        fields=(
            _Field("issueIid", "issueIid", ("issueIid", "iid"), role="id"),
            _Field(
                "title",
                "title",
                ("title", "name"),
                role="name",
                default="Mock Issue",
            ),
            _Field(
                "projectId",
                "projectId",
                ("projectId", "project_id"),
                role="id",
            ),
        ),
    ),
    "jenkins": _ActionConfig(
        source="jenkins",
        mock_key="jenkins_response",
        operations=JENKINS_OPERATIONS,
        default_operation=JENKINS_DEFAULT_OPERATION,
        fields=(
            _Field(
                "jobName",
                "jobName",
                ("jobName", "job"),
                role="name",
                default="Mock Job",
            ),
            _Field("buildId", "buildId", ("buildId", "build"), role="id"),
            _Field(
                "status",
                "status",
                ("status",),
                role="constant",
                default="queued",
            ),
        ),
    ),
    "circleci": _ActionConfig(
        source="circleci",
        mock_key="circleci_response",
        operations=CIRCLECI_OPERATIONS,
        default_operation=CIRCLECI_DEFAULT_OPERATION,
        fields=(
            _Field(
                "pipelineId",
                "pipelineId",
                ("pipelineId", "pipeline_id"),
                role="id",
            ),
            _Field(
                "status",
                "status",
                ("status",),
                role="constant",
                default="queued",
            ),
        ),
    ),
}


def _synthesize_action(
    config: _ActionConfig,
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in config.fields:
        val = resolved.get(f.field, "")
        if f.role == "id":
            out[f.field] = val or _random_id(config.source)
        elif f.role == "name":
            out[f.field] = val or f.default
        elif f.role == "constant":
            out[f.field] = f.default
        else:
            out[f.field] = val or f.default
    return out


def _resolve_action_response(
    *,
    config: _ActionConfig,
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


def _build_action_payload(
    config: _ActionConfig,
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


async def _exec_action(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
    config: _ActionConfig,
) -> list[tuple[int, list[ExecutionItem]]]:
    params = node.parameters or {}
    operation = str(
        params.get("operation") or config.default_operation
    ).strip()
    if operation not in config.operations:
        raise ValueError(
            f"{config.source}: unsupported operation {operation!r}; "
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
            return _synthesize_action(config, operation, resolved)

        response, source = _resolve_action_response(
            config=config,
            operation=operation,
            params=params,
            item=item,
            ctx=ctx,
            synth=_synth,
        )

        payload = _build_action_payload(
            config, operation, response, resolved, source
        )
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


async def exec_gitlab(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """GitLab node — routes on ``parameters.operation``."""
    return await _exec_action(
        node, items, ctx=ctx, config=_ACTION_CONFIGS["gitlab"]
    )


async def exec_jenkins(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Jenkins node — routes on ``parameters.operation``."""
    return await _exec_action(
        node, items, ctx=ctx, config=_ACTION_CONFIGS["jenkins"]
    )


async def exec_circleci(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """CircleCI node — routes on ``parameters.operation``."""
    return await _exec_action(
        node, items, ctx=ctx, config=_ACTION_CONFIGS["circleci"]
    )


# ── Trigger config ────────────────────────────────────────────────────


@dataclass(frozen=True)
class _TriggerField:
    field: str
    fallbacks: tuple[str, ...] = ()
    default: Any = None


@dataclass(frozen=True)
class _TriggerConfig:
    source: str
    mock_key: str
    fields: tuple[_TriggerField, ...]


_TRIGGER_CONFIGS: dict[str, _TriggerConfig] = {
    "gitlab": _TriggerConfig(
        source="gitlab",
        mock_key="gitlab_trigger_payload",
        fields=(
            _TriggerField(
                "event", fallbacks=("object_kind",), default="push"
            ),
            _TriggerField(
                "projectId", fallbacks=("project_id",), default=12345
            ),
            _TriggerField(
                "objectKind", fallbacks=("object_kind",), default="push"
            ),
        ),
    ),
    "github": _TriggerConfig(
        source="github",
        mock_key="github_trigger_payload",
        fields=(
            _TriggerField("event", default="push"),
            _TriggerField("action", default="opened"),
            _TriggerField(
                "repository",
                default={
                    "name": "mock-repo",
                    "full_name": "mock-owner/mock-repo",
                    "html_url": "https://github.com/mock-owner/mock-repo",
                },
            ),
            _TriggerField(
                "sender", default={"login": "mock-user", "id": 12345}
            ),
        ),
    ),
    "bitbucket": _TriggerConfig(
        source="bitbucket",
        mock_key="bitbucket_trigger_payload",
        fields=(
            _TriggerField("event", default="repo:push"),
            _TriggerField(
                "repository",
                default={
                    "name": "mock-repo",
                    "full_name": "mock-owner/mock-repo",
                },
            ),
            _TriggerField(
                "actor",
                default={
                    "display_name": "mock-user",
                    "nickname": "mockuser",
                    "uuid": "{12345678-1234-1234-1234-123456789012}",
                },
            ),
        ),
    ),
}


def _synthesize_trigger(config: _TriggerConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in config.fields:
        out[f.field] = f.default
    return out


def _extract_trigger_field(
    payload: dict[str, Any], field: _TriggerField
) -> Any:
    if field.field in payload and payload[field.field] is not None:
        return payload[field.field]
    for fb in field.fallbacks:
        if fb in payload and payload[fb] is not None:
            return payload[fb]
    return field.default


def _resolve_trigger_payload(
    node: "ExecNode",
    ctx: "EngineContext",
    config: _TriggerConfig,
    synth: Any,
) -> tuple[dict[str, Any], str]:
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    tmock = mocks.get(config.mock_key)
    if tmock is not None:
        if callable(tmock):
            raw = tmock(node, ctx)
        else:
            raw = tmock
        if isinstance(raw, dict):
            return raw, config.mock_key
        return synth(), config.mock_key

    gmock = mocks.get("trigger_payload")
    if gmock is not None:
        if callable(gmock):
            raw = gmock(node, ctx)
        else:
            raw = gmock
        if isinstance(raw, dict):
            return raw, "trigger_payload"
        return synth(), "trigger_payload"

    return synth(), "offline"


async def _exec_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
    config: _TriggerConfig,
) -> list[tuple[int, list[ExecutionItem]]]:
    seed_item = items[0] if items else ExecutionItem()

    def _synth() -> dict[str, Any]:
        return _synthesize_trigger(config)

    payload, source = _resolve_trigger_payload(node, ctx, config, _synth)

    base: dict[str, Any] = {}
    for f in config.fields:
        base[f.field] = _extract_trigger_field(payload, f)
    base["source"] = config.source
    if source not in ("offline", config.mock_key):
        base["mockSource"] = source

    if items:
        out: list[ExecutionItem] = []
        for item in items:
            merged = dict(item.json)
            for key, value in base.items():
                merged.setdefault(key, value)
            ni = item.clone()
            ni.json = merged
            out.append(ni)
        return [(0, out)]

    logger.info(
        "%s trigger event=%s source=%s",
        config.source,
        base.get("event"),
        source,
    )
    return [(0, [ExecutionItem(json=base)])]


async def exec_gitlab_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """GitLab Trigger — emit one item per received GitLab webhook event."""
    return await _exec_trigger(
        node, items, ctx=ctx, config=_TRIGGER_CONFIGS["gitlab"]
    )


async def exec_github_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """GitHub Trigger — emit one item per received GitHub webhook event."""
    return await _exec_trigger(
        node, items, ctx=ctx, config=_TRIGGER_CONFIGS["github"]
    )


async def exec_bitbucket_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Bitbucket Trigger — emit one item per received Bitbucket webhook event."""
    return await _exec_trigger(
        node, items, ctx=ctx, config=_TRIGGER_CONFIGS["bitbucket"]
    )


__all__ = [
    "exec_gitlab",
    "exec_gitlab_trigger",
    "exec_github_trigger",
    "exec_bitbucket_trigger",
    "exec_jenkins",
    "exec_circleci",
    "GITLAB_OPERATIONS",
    "GITLAB_DEFAULT_OPERATION",
    "JENKINS_OPERATIONS",
    "JENKINS_DEFAULT_OPERATION",
    "CIRCLECI_OPERATIONS",
    "CIRCLECI_DEFAULT_OPERATION",
]