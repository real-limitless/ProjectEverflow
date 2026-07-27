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

When a service credential is attached and no mock is present, real calls
are made to the service REST API via :func:`execute_http_request`.
Otherwise the executor is mock-driven with an offline synthetic
fallback.

Resolution precedence for action nodes:

1. ``ctx.mocks['<node>_response']`` — callable invoked as
   ``mock(operation, params, item, ctx)`` or dict used directly.
2. ``ctx.mocks['http_response']`` — generic fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used as
   the response.
3. If a service credential resolves, a real API call is made via
   :func:`execute_http_request`; the response is converted to the
   internal envelope and ``source`` is set to ``'<service>_api'``.
4. Offline synthetic response with deterministic-looking ids.

Resolution precedence for trigger nodes:

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
from typing import TYPE_CHECKING, Any, Callable

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.http_client import HttpRequestConfig, execute_http_request
from app.services.workflows.items import ExecutionItem
from app.services.workflows.nodes._http_helpers import resolve_credential

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


# ── HTTP request helpers ─────────────────────────────────────────────


def _req(
    url: str,
    method: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any = None,
    auth: str = "none",
    auth_credential: dict[str, Any] | None = None,
) -> HttpRequestConfig:
    return HttpRequestConfig(
        url=url,
        method=method,
        headers=headers or {},
        body=body,
        body_mode="json" if body is not None else "none",
        auth=auth,  # type: ignore[arg-type]
        auth_credential=auth_credential or {},
        response_mode="json",
        timeout=30.0,
    )


def _build_gitlab_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    token = str(cred.get("accessToken") or "")
    base = str(cred.get("baseUrl") or "https://gitlab.com").rstrip("/")
    if not token:
        return None
    api = f"{base}/api/v4/"
    headers = {"Authorization": f"Bearer {token}"}
    issue_iid = resolved.get("issueIid", "")
    project_id = resolved.get("projectId", "")
    title = resolved.get("title", "")
    mr_iid = _coerce_str(params.get("mergeRequestIid"))
    if operation == "create":
        return _req(
            f"{api}projects/{project_id}/issues", "POST", headers=headers, body={"title": title}
        )
    if operation == "get":
        return _req(f"{api}projects/{project_id}/issues/{issue_iid}", "GET", headers=headers)
    if operation == "update":
        return _req(
            f"{api}projects/{project_id}/issues/{issue_iid}", "PUT", headers=headers, body={"title": title}
        )
    if operation == "delete":
        return _req(f"{api}projects/{project_id}/issues/{issue_iid}", "DELETE", headers=headers)
    if operation == "list":
        return _req(f"{api}projects/{project_id}/issues", "GET", headers=headers)
    if operation == "createMergeRequest":
        return _req(
            f"{api}projects/{project_id}/merge_requests", "POST", headers=headers, body={"title": title}
        )
    if operation == "getMergeRequest":
        return _req(
            f"{api}projects/{project_id}/merge_requests/{mr_iid}", "GET", headers=headers
        )
    return None


def _envelope_from_gitlab_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    if operation == "list" and isinstance(data, list):
        if not data:
            return {"issueIid": "", "title": "", "projectId": "", "items": []}
        first = data[0] if isinstance(data[0], dict) else {}
        return {
            "issueIid": str(first.get("iid") or ""),
            "title": first.get("title") or "",
            "projectId": str(first.get("project_id") or resolved.get("projectId", "")),
            "items": data,
        }
    return {
        "issueIid": str(data.get("iid") or resolved.get("issueIid", "")),
        "title": data.get("title") or resolved.get("title", ""),
        "projectId": str(data.get("project_id") or resolved.get("projectId", "")),
    }


def _build_jenkins_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    base = str(cred.get("baseUrl") or "").rstrip("/")
    username = str(cred.get("username") or "")
    api_token = str(cred.get("apiToken") or "")
    if not base or not username or not api_token:
        return None
    auth_cred = {"username": username, "password": api_token}
    job_name = resolved.get("jobName", "")
    build_id = resolved.get("buildId", "")
    if operation == "trigger":
        return _req(f"{base}/job/{job_name}/build", "POST", auth="basic", auth_credential=auth_cred)
    if operation == "getJob":
        return _req(f"{base}/job/{job_name}/api/json", "GET", auth="basic", auth_credential=auth_cred)
    if operation == "getBuild":
        return _req(
            f"{base}/job/{job_name}/{build_id}/api/json", "GET", auth="basic", auth_credential=auth_cred
        )
    if operation == "listJobs":
        return _req(
            f"{base}/api/json?tree=jobs[name]", "GET", auth="basic", auth_credential=auth_cred
        )
    return None


def _envelope_from_jenkins_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    if operation == "listJobs" and isinstance(data.get("jobs"), list):
        jobs = data["jobs"]
        if not jobs:
            return {"jobName": "", "buildId": "", "status": "", "items": []}
        first = jobs[0] if isinstance(jobs[0], dict) else {}
        return {
            "jobName": first.get("name") or "",
            "buildId": "",
            "status": "",
            "items": jobs,
        }
    return {
        "jobName": data.get("name") or resolved.get("jobName", ""),
        "buildId": str(data.get("number") or data.get("id") or resolved.get("buildId", "")),
        "status": data.get("result") or data.get("building") or resolved.get("status", ""),
    }


def _build_circleci_request(
    cred: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
    params: dict[str, Any],
) -> HttpRequestConfig | None:
    token = str(cred.get("apiToken") or "")
    if not token:
        return None
    base = "https://circleci.com/api/v2/"
    headers = {"Circle-Token": token}
    pipeline_id = resolved.get("pipelineId", "")
    project_slug = _coerce_str(params.get("projectSlug"))
    job_id = _coerce_str(params.get("jobId"))
    if operation == "trigger":
        body: dict[str, Any] = {}
        if project_slug:
            return _req(
                f"{base}project/{project_slug}/pipeline", "POST", headers=headers, body=body
            )
        return None
    if operation == "getPipeline":
        return _req(f"{base}pipeline/{pipeline_id}", "GET", headers=headers)
    if operation == "getWorkflow":
        return _req(f"{base}pipeline/{pipeline_id}/workflow", "GET", headers=headers)
    if operation == "getJob":
        if job_id:
            return _req(f"{base}job/{job_id}", "GET", headers=headers)
        return None
    return None


def _envelope_from_circleci_api(
    data: dict[str, Any],
    operation: str,
    resolved: dict[str, str],
) -> dict[str, Any]:
    if operation == "getWorkflow" and isinstance(data.get("items"), list):
        items = data["items"]
        if not items:
            return {"pipelineId": "", "status": "", "items": []}
        first = items[0] if isinstance(items[0], dict) else {}
        return {
            "pipelineId": str(first.get("pipeline_id") or resolved.get("pipelineId", "")),
            "status": first.get("status") or "",
            "items": items,
        }
    return {
        "pipelineId": str(data.get("id") or resolved.get("pipelineId", "")),
        "status": data.get("state") or data.get("status") or resolved.get("status", ""),
    }


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
    cred_type: str
    build_request: Callable[..., HttpRequestConfig | None]
    convert_response: Callable[..., dict[str, Any]]


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
        cred_type="gitlabApi",
        build_request=_build_gitlab_request,
        convert_response=_envelope_from_gitlab_api,
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
        cred_type="jenkinsApi",
        build_request=_build_jenkins_request,
        convert_response=_envelope_from_jenkins_api,
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
        cred_type="circleCiApi",
        build_request=_build_circleci_request,
        convert_response=_envelope_from_circleci_api,
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


async def _resolve_action_response(
    *,
    config: _ActionConfig,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
    node: "ExecNode",
    ctx: "EngineContext",
    resolved: dict[str, str],
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

    cred = resolve_credential(node, ctx, config.cred_type)
    if cred:
        cfg = config.build_request(cred, operation, resolved, params)
        if cfg is not None:
            logger.info(
                "%s real HTTP call operation=%s",
                config.source,
                operation,
            )
            try:
                resp = await execute_http_request(cfg, ctx=ctx)
                if isinstance(resp.body, dict):
                    return (
                        config.convert_response(resp.body, operation, resolved),
                        f"{config.source}_api",
                    )
            except Exception as exc:
                logger.warning("%s HTTP call failed: %s", config.source, exc)

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
    if source not in (config.mock_key, f"{config.source}_api"):
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

        response, source = await _resolve_action_response(
            config=config,
            operation=operation,
            params=params,
            item=item,
            node=node,
            ctx=ctx,
            resolved=resolved,
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