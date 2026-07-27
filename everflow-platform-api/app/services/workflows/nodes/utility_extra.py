"""Utility extra executors (clean-room n8n-nodes-base.*).

v1 covers:

- ``debugHelper``       — pass-through with logging to ``ctx.debug_log``.
- ``executeCommand``    — run a shell command (mock-first, never executed).
- ``n8n``               — meta API for workflow/execution info.
- ``evaluation``        — evaluate LLM output against expected output.
- ``evaluationTrigger`` — trigger that emits evaluation test cases.
- ``activationTrigger`` — fires when workflow is activated.
- ``n8nTrigger``        — generic n8n system trigger.
- ``form``              — form page trigger.
- ``totp``              — generate/validate TOTP codes.
- ``ldap``              — LDAP search/add/modify/delete.
- ``iCalendar``         — parse iCalendar (.ics) data.
- ``quickChart``        — generate chart URLs/images.
- ``hackerNews``        — fetch Hacker News stories.

All API calls are mock-driven — no real network I/O is performed.

Behavior precedence (all nodes):

1. ``ctx.mocks['<node>_response']`` (or node-specific key) — callable
   invoked as ``mock(operation, params, item, ctx)`` or dict used directly.
2. ``ctx.mocks['http_response']`` — generic fallback
   (``{status_code, body, headers}``); a JSON ``body`` dict is used.
3. Offline synthetic response.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext
    from app.services.workflows.graph import ExecNode

logger = logging.getLogger(__name__)

N8N_META_OPERATIONS: tuple[str, ...] = (
    "getWorkflow",
    "getWorkflowTags",
    "getExecutions",
    "getExecution",
    "deleteExecution",
)
LDAP_OPERATIONS: tuple[str, ...] = ("search", "add", "modify", "delete")
TOTP_OPERATIONS: tuple[str, ...] = ("generate", "validate")
HN_OPERATIONS: tuple[str, ...] = ("get", "getAll", "search")
CHART_TYPES: tuple[str, ...] = ("bar", "line", "pie", "doughnut", "radar")


# ── Shared helpers ────────────────────────────────────────────────────


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
        for key in ("value", "name", "id", "text", "title"):
            if key in value and value[key] is not None:
                return _coerce_str(value[key])
    return str(value)


def _resolve_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> Any:
    """Return ``params[key]`` (evaluated) or the first present ``$json`` fallback."""
    raw = params.get(key)
    if raw is not None:
        return evaluate(raw, ectx)
    for fk in json_fallbacks:
        if fk in item.json:
            return item.json[fk]
    return None


def _resolve_str_param(
    params: dict[str, Any],
    key: str,
    item: ExecutionItem,
    ectx: ExpressionContext,
    json_fallbacks: tuple[str, ...] = (),
) -> str:
    return _coerce_str(_resolve_param(params, key, item, ectx, json_fallbacks))


def _iso(ctx: "EngineContext") -> str:
    now = ctx.now if ctx.now else datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _mock_item(items: list[ExecutionItem]) -> ExecutionItem:
    return items[0] if items else ExecutionItem(json={})


def _resolve_mock_response(
    ctx: "EngineContext",
    mock_key: str,
    operation: str,
    params: dict[str, Any],
    item: ExecutionItem,
) -> tuple[Any, str]:
    """Return ``(value, source)`` from ``ctx.mocks[mock_key]`` or http_response.

    A callable mock is invoked as ``mock(operation, params, item, ctx)``; a
    non-callable is used as-is.  If the callable returns ``None`` the call is
    treated as a miss and the http_response fallback is tried.
    """
    mocks = ctx.mocks if isinstance(ctx.mocks, dict) else {}
    mock = mocks.get(mock_key)
    if mock is not None:
        if callable(mock):
            val = mock(operation, params, item, ctx)
            if val is not None:
                return val, mock_key
        else:
            return mock, mock_key
    http = mocks.get("http_response")
    if http is not None:
        if isinstance(http, dict):
            body = http.get("body", http)
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except (ValueError, TypeError):
                    return http, "http_response"
            return body, "http_response"
        return http, "http_response"
    return None, ""


def _add_mock_source(payload: dict[str, Any], src: str, mock_key: str) -> None:
    if src and src != mock_key:
        payload["mockSource"] = src


def _as_payload_list(
    mock_val: Any,
    synthesize: Any,
) -> list[dict[str, Any]]:
    """Build a list of payload dicts from a mock value or offline synthesis."""
    if mock_val is None:
        return [synthesize()]
    if isinstance(mock_val, list):
        if not mock_val:
            return [synthesize()]
        return [v if isinstance(v, dict) else synthesize() for v in mock_val]
    if isinstance(mock_val, dict):
        return [mock_val]
    return [synthesize()]


# ── 1. Debug Helper ───────────────────────────────────────────────────


async def exec_debug_helper(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Debug Helper — pass-through with logging to ``ctx.debug_log``.

    Emits input items unchanged.  Appends a log entry to ``ctx.debug_log``
    (if that attribute is a list) for each item, using the mock value when
    available or the item JSON otherwise.
    """
    params = node.parameters or {}
    options = params.get("options") or {}
    if not isinstance(options, dict):
        options = {}
    log_level = _coerce_str(options.get("logLevel")).strip() or "info"
    prefix = _coerce_str(options.get("prefix"))

    debug_log = getattr(ctx, "debug_log", None)

    out: list[ExecutionItem] = []
    for item in items:
        mock_val, src = _resolve_mock_response(
            ctx, "debug_helper_response", "", params, item
        )
        if mock_val is None:
            log_data: Any = dict(item.json)
            src = "offline"
        else:
            log_data = mock_val

        entry: dict[str, Any] = {
            "level": log_level,
            "prefix": prefix,
            "nodeName": node.name,
            "data": log_data,
        }
        if src and src != "debug_helper_response":
            entry["mockSource"] = src

        if isinstance(debug_log, list):
            debug_log.append(entry)

        level_num = getattr(logging, log_level.upper(), logging.INFO)
        logger.log(
            level_num,
            "%s%s: %s",
            prefix,
            node.name,
            json.dumps(item.json, default=str),
        )

        out.append(item.clone())

    return [(0, out)]


# ── 2. Execute Command ────────────────────────────────────────────────


def _synthesize_execute_command(command: str) -> dict[str, Any]:
    return {
        "stdout": "",
        "stderr": "",
        "exitCode": 0,
        "command": command,
    }


async def exec_execute_command(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Execute Command — run a shell command (mock-first, never executed).

    Emits one item per input with ``{stdout, stderr, exitCode, command}``.
    When ``executeOnce`` is true the mock is resolved once and the same
    result is attached to every input item.
    """
    params = node.parameters or {}
    execute_once = bool(params.get("executeOnce", False))

    out: list[ExecutionItem] = []
    cached: dict[str, Any] | None = None
    cached_src = ""

    for item in items:
        ectx = _ectx(item, ctx)
        command = _coerce_str(evaluate(params.get("command", ""), ectx))

        if execute_once and cached is not None:
            result = dict(cached)
            src = cached_src
        else:
            mock_val, src = _resolve_mock_response(
                ctx, "execute_command_response", "", params, item
            )
            if mock_val is None:
                mock_val = _synthesize_execute_command(command)
                src = "offline"
            if isinstance(mock_val, dict):
                result = {
                    "stdout": mock_val.get("stdout", ""),
                    "stderr": mock_val.get("stderr", ""),
                    "exitCode": mock_val.get("exitCode", 0),
                    "command": mock_val.get("command", command),
                }
            else:
                result = _synthesize_execute_command(command)
                src = "offline"
            if execute_once:
                cached = dict(result)
                cached_src = src

        payload: dict[str, Any] = dict(result)
        _add_mock_source(payload, src, "execute_command_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "executeCommand exitCode=%s source=%s", result["exitCode"], src
        )

    return [(0, out)]


# ── 3. n8n (meta API) ────────────────────────────────────────────────


def _synthesize_n8n_meta(operation: str, ctx: "EngineContext") -> dict[str, Any]:
    iso = _iso(ctx)
    wf_id = "wf-mock-1"
    if operation == "getWorkflow":
        return {
            "id": wf_id,
            "name": "Mock Workflow",
            "active": True,
            "nodes": [],
            "connections": {},
            "createdAt": iso,
            "updatedAt": iso,
        }
    if operation == "getWorkflowTags":
        return {
            "tags": [{"id": "tag-1", "name": "mock-tag"}],
            "workflowId": wf_id,
        }
    if operation == "getExecutions":
        return {
            "data": [
                {
                    "id": "exec-1",
                    "status": "success",
                    "finished": True,
                    "mode": "manual",
                    "startedAt": iso,
                    "stoppedAt": iso,
                },
                {
                    "id": "exec-2",
                    "status": "success",
                    "finished": True,
                    "mode": "manual",
                    "startedAt": iso,
                    "stoppedAt": iso,
                },
            ],
            "nextCursor": "",
        }
    if operation == "getExecution":
        return {
            "id": "exec-1",
            "status": "success",
            "finished": True,
            "mode": "manual",
            "startedAt": iso,
            "stoppedAt": iso,
            "workflowId": wf_id,
        }
    if operation == "deleteExecution":
        return {
            "success": True,
            "id": "exec-1",
            "deletedAt": iso,
        }
    return {}


async def exec_n8n(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """n8n — meta API for workflow/execution info.

    Operations: ``getWorkflow``, ``getWorkflowTags``, ``getExecutions``,
    ``getExecution``, ``deleteExecution``.  Emits one item.
    """
    params = node.parameters or {}
    operation = _coerce_str(params.get("operation")).strip() or "getWorkflow"
    if operation not in N8N_META_OPERATIONS:
        raise ValueError(
            f"n8n: unsupported operation {operation!r}; "
            f"expected one of {N8N_META_OPERATIONS}"
        )

    item = _mock_item(items)
    mock_val, src = _resolve_mock_response(
        ctx, "n8n_meta_response", operation, params, item
    )
    if mock_val is None:
        mock_val = _synthesize_n8n_meta(operation, ctx)
        src = "offline"

    payload: dict[str, Any] = mock_val if isinstance(mock_val, dict) else {}
    _add_mock_source(payload, src, "n8n_meta_response")

    logger.info("n8n %s source=%s", operation, src)
    return [(0, [ExecutionItem(json=payload)])]


# ── 4. Evaluation ────────────────────────────────────────────────────


def _evaluate_score(metric: str, expected: str, actual: str) -> float:
    if metric == "exact_match":
        return 1.0 if expected == actual else 0.0
    return 1.0 if expected == actual else 0.0


async def exec_evaluation(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Evaluation — evaluate LLM output against expected output.

    Emits one item per input with ``{score, metric, expected, actual,
    passed}``.  Default metric is ``exact_match`` (score 1.0 on equality).
    """
    params = node.parameters or {}
    metric = _coerce_str(params.get("metric")).strip() or "exact_match"

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        expected = _resolve_str_param(
            params, "expectedOutput", item, ectx, ("expectedOutput", "expected")
        )
        actual = _resolve_str_param(
            params, "actualOutput", item, ectx, ("actualOutput", "actual")
        )

        mock_val, src = _resolve_mock_response(
            ctx, "evaluation_response", "", params, item
        )
        if mock_val is None:
            score = _evaluate_score(metric, expected, actual)
            mock_val = {
                "score": score,
                "metric": metric,
                "expected": expected,
                "actual": actual,
                "passed": score >= 1.0,
            }
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = {
                "score": mock_val.get("score", 0.0),
                "metric": mock_val.get("metric", metric),
                "expected": mock_val.get("expected", expected),
                "actual": mock_val.get("actual", actual),
                "passed": mock_val.get("passed", False),
            }
        else:
            payload = {
                "score": 0.0,
                "metric": metric,
                "expected": expected,
                "actual": actual,
                "passed": False,
            }
            src = "offline"

        _add_mock_source(payload, src, "evaluation_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info(
            "evaluation score=%s passed=%s source=%s",
            payload["score"],
            payload["passed"],
            src,
        )

    return [(0, out)]


# ── 5. Evaluation Trigger ─────────────────────────────────────────────


def _synthesize_evaluation_trigger() -> dict[str, Any]:
    return {
        "testId": "test-1",
        "input": "sample input",
        "expectedOutput": "expected output",
    }


async def exec_evaluation_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Evaluation Trigger — emit evaluation test cases.

    Emits one item with ``{testId, input, expectedOutput}`` (mockable via
    ``ctx.mocks['evaluation_trigger_payload']``).
    """
    del items
    params = node.parameters or {}
    item = ExecutionItem(json={})
    mock_val, src = _resolve_mock_response(
        ctx, "evaluation_trigger_payload", "", params, item
    )
    if mock_val is None:
        mock_val = _synthesize_evaluation_trigger()
        src = "offline"

    payloads = _as_payload_list(mock_val, _synthesize_evaluation_trigger)
    out: list[ExecutionItem] = []
    for p in payloads:
        payload = dict(p)
        _add_mock_source(payload, src, "evaluation_trigger_payload")
        out.append(ExecutionItem(json=payload))
    logger.info("evaluationTrigger emitted %d items source=%s", len(out), src)
    return [(0, out)]


# ── 6. Activation Trigger ─────────────────────────────────────────────


def _synthesize_activation_trigger(ctx: "EngineContext") -> dict[str, Any]:
    return {
        "activatedAt": _iso(ctx),
        "workflowId": "wf-mock-1",
    }


async def exec_activation_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Activation Trigger — fires when workflow is activated.

    Emits one item with ``{activatedAt, workflowId}`` (mockable via
    ``ctx.mocks['activation_payload']``).
    """
    del items
    params = node.parameters or {}
    item = ExecutionItem(json={})
    mock_val, src = _resolve_mock_response(
        ctx, "activation_payload", "", params, item
    )
    if mock_val is None:
        mock_val = _synthesize_activation_trigger(ctx)
        src = "offline"

    payloads = _as_payload_list(
        mock_val, lambda: _synthesize_activation_trigger(ctx)
    )
    out: list[ExecutionItem] = []
    for p in payloads:
        payload = dict(p)
        _add_mock_source(payload, src, "activation_payload")
        out.append(ExecutionItem(json=payload))
    logger.info("activationTrigger emitted %d items source=%s", len(out), src)
    return [(0, out)]


# ── 7. n8n Trigger ────────────────────────────────────────────────────


def _synthesize_n8n_trigger(ctx: "EngineContext") -> dict[str, Any]:
    return {
        "event": "manual",
        "timestamp": _iso(ctx),
        "workflowId": "wf-mock-1",
    }


async def exec_n8n_trigger(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """n8n Trigger — generic n8n system trigger.

    Emits one item with ``{event, timestamp, workflowId}`` (mockable via
    ``ctx.mocks['n8n_trigger_payload']``).
    """
    del items
    params = node.parameters or {}
    item = ExecutionItem(json={})
    mock_val, src = _resolve_mock_response(
        ctx, "n8n_trigger_payload", "", params, item
    )
    if mock_val is None:
        mock_val = _synthesize_n8n_trigger(ctx)
        src = "offline"

    payloads = _as_payload_list(mock_val, lambda: _synthesize_n8n_trigger(ctx))
    out: list[ExecutionItem] = []
    for p in payloads:
        payload = dict(p)
        _add_mock_source(payload, src, "n8n_trigger_payload")
        out.append(ExecutionItem(json=payload))
    logger.info("n8nTrigger emitted %d items source=%s", len(out), src)
    return [(0, out)]


# ── 8. n8n Form ───────────────────────────────────────────────────────


def _form_field_names(params: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for f in (params.get("formFields") or []):
        if isinstance(f, dict):
            name = f.get("fieldName") or f.get("name") or f.get("label") or ""
            if name:
                names.append(str(name))
    return names


def _synthesize_form(params: dict[str, Any], ctx: "EngineContext") -> dict[str, Any]:
    field_names = _form_field_names(params)
    fields = {name: f"mock_value_{i + 1}" for i, name in enumerate(field_names)}
    return {
        "formTitle": _coerce_str(params.get("formTitle")) or "Mock Form",
        "submittedAt": _iso(ctx),
        "fields": fields,
    }


async def exec_form(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """n8n Form — form page trigger.

    Emits one item per submission with ``{formTitle, submittedAt, fields}``
    (mockable via ``ctx.mocks['form_submission']``).
    """
    del items
    params = node.parameters or {}
    item = ExecutionItem(json={})
    mock_val, src = _resolve_mock_response(
        ctx, "form_submission", "", params, item
    )
    if mock_val is None:
        mock_val = _synthesize_form(params, ctx)
        src = "offline"

    payloads = _as_payload_list(mock_val, lambda: _synthesize_form(params, ctx))
    out: list[ExecutionItem] = []
    for p in payloads:
        payload = dict(p)
        _add_mock_source(payload, src, "form_submission")
        out.append(ExecutionItem(json=payload))
    logger.info("form emitted %d items source=%s", len(out), src)
    return [(0, out)]


# ── 9. TOTP ───────────────────────────────────────────────────────────


def _synthesize_totp(operation: str, secret: str, token: str) -> dict[str, Any]:
    if operation == "validate":
        return {
            "valid": True,
            "token": token or "123456",
            "secret": secret,
        }
    return {
        "token": "123456",
        "secret": secret or "mock_secret",
        "algorithm": "SHA1",
        "digits": 6,
        "period": 30,
    }


async def exec_totp(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """TOTP — generate/validate TOTP codes.

    Operations: ``generate`` (default), ``validate``.  Emits one item per
    input.  Offline generate returns ``{token, secret, algorithm, digits,
    period}``; offline validate returns ``{valid, token, secret}``.
    """
    params = node.parameters or {}
    operation = _coerce_str(params.get("operation")).strip() or "generate"
    if operation not in TOTP_OPERATIONS:
        raise ValueError(
            f"totp: unsupported operation {operation!r}; "
            f"expected one of {TOTP_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        secret = _resolve_str_param(params, "secret", item, ectx, ("secret",))
        token = _resolve_str_param(params, "token", item, ectx, ("token",))

        mock_val, src = _resolve_mock_response(
            ctx, "totp_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_totp(operation, secret, token)
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = dict(mock_val)
        else:
            payload = _synthesize_totp(operation, secret, token)
            src = "offline"

        _add_mock_source(payload, src, "totp_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("totp %s source=%s", operation, src)

    return [(0, out)]


# ── 10. LDAP ──────────────────────────────────────────────────────────


def _synthesize_ldap(
    operation: str, base_dn: str, ctx: "EngineContext"
) -> Any:
    if operation == "search":
        return [
            {
                "dn": f"cn=user{i + 1},{base_dn}",
                "attributes": {
                    "cn": f"user{i + 1}",
                    "mail": f"user{i + 1}@example.com",
                    "uid": str(i + 1),
                },
            }
            for i in range(3)
        ]
    return {
        "success": True,
        "dn": base_dn,
        "operation": operation,
        "updatedAt": _iso(ctx),
    }


async def exec_ldap(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """LDAP — search/add/modify/delete.

    Operations: ``search`` (default), ``add``, ``modify``, ``delete``.
    Search emits one item per entry; add/modify/delete emit one item.
    """
    params = node.parameters or {}
    operation = _coerce_str(params.get("operation")).strip() or "search"
    if operation not in LDAP_OPERATIONS:
        raise ValueError(
            f"ldap: unsupported operation {operation!r}; "
            f"expected one of {LDAP_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        base_dn = _resolve_str_param(
            params, "baseDn", item, ectx, ("baseDn", "dn")
        ) or "dc=example,dc=com"

        mock_val, src = _resolve_mock_response(
            ctx, "ldap_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_ldap(operation, base_dn, ctx)
            src = "offline"

        if operation == "search":
            entries = mock_val if isinstance(mock_val, list) else [mock_val]
        else:
            entries = [mock_val]

        for entry in entries:
            payload = dict(entry) if isinstance(entry, dict) else {}
            _add_mock_source(payload, src, "ldap_response")
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        logger.info("ldap %s source=%s", operation, src)

    return [(0, out)]


# ── 11. iCalendar ─────────────────────────────────────────────────────


def _parse_ics(ics_data: str) -> list[dict[str, Any]]:
    """Parse VEVENT blocks from iCalendar data."""
    events: list[dict[str, Any]] = []
    raw_lines = ics_data.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for line in raw_lines:
        if line.startswith(" ") or line.startswith("\t"):
            if lines:
                lines[-1] += line[1:]
        else:
            lines.append(line)

    in_event = False
    current: dict[str, str] = {}
    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            current = {}
        elif line == "END:VEVENT":
            if in_event:
                events.append(
                    {
                        "summary": current.get("SUMMARY", ""),
                        "start": current.get("DTSTART", ""),
                        "end": current.get("DTEND", ""),
                        "location": current.get("LOCATION", ""),
                        "description": current.get("DESCRIPTION", ""),
                        "uid": current.get("UID", ""),
                    }
                )
                in_event = False
        elif in_event and ":" in line:
            prop_part, _, value = line.partition(":")
            prop_name = prop_part.split(";")[0].upper()
            current[prop_name] = value
    return events


def _empty_event() -> dict[str, Any]:
    return {
        "summary": "",
        "start": "",
        "end": "",
        "location": "",
        "description": "",
        "uid": "",
    }


async def exec_icalendar(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """iCalendar — parse iCalendar (.ics) data.

    Reads ``icsData`` (string) or ``binaryPropertyName`` (binary field).
    Emits one item per VEVENT with ``{summary, start, end, location,
    description, uid}``.
    """
    params = node.parameters or {}
    bin_prop = _coerce_str(params.get("binaryPropertyName"))

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        ics_data = _coerce_str(evaluate(params.get("icsData", ""), ectx))
        if not ics_data and bin_prop and bin_prop in item.binary:
            ics_data = item.binary[bin_prop].to_bytes().decode(
                "utf-8", errors="replace"
            )

        mock_val, src = _resolve_mock_response(
            ctx, "icalendar_response", "", params, item
        )
        if mock_val is None:
            events = _parse_ics(ics_data)
            if not events:
                events = [_empty_event()]
            src = "offline"
        elif isinstance(mock_val, list):
            events = mock_val if mock_val else [_empty_event()]
        elif isinstance(mock_val, dict):
            events = [mock_val]
        else:
            events = [_empty_event()]

        for ev in events:
            payload = dict(ev) if isinstance(ev, dict) else _empty_event()
            _add_mock_source(payload, src, "icalendar_response")
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        logger.info("iCalendar parsed %d events source=%s", len(events), src)

    return [(0, out)]


# ── 12. Quick Chart ───────────────────────────────────────────────────


def _synthesize_quick_chart(
    chart_type: str,
    datasets: list[Any],
    labels: list[Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    config: dict[str, Any] = {
        "type": chart_type,
        "data": {
            "labels": labels,
            "datasets": datasets,
        },
        "options": options,
    }
    config_json = json.dumps(config, separators=(",", ":"), default=str)
    chart_url = f"https://quickchart.io/chart?c={quote(config_json)}"
    return {
        "chartUrl": chart_url,
        "type": chart_type,
        "config": config,
    }


async def exec_quick_chart(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Quick Chart — generate chart URLs/images.

    Params: ``type`` (bar/line/pie/doughnut/radar), ``datasets`` (list),
    ``labels`` (list), ``options`` (dict).  Emits one item per input with
    ``{chartUrl, type, config}``.
    """
    params = node.parameters or {}
    chart_type = _coerce_str(params.get("type")).strip() or "bar"
    if chart_type not in CHART_TYPES:
        chart_type = "bar"
    datasets = params.get("datasets") or []
    if not isinstance(datasets, list):
        datasets = []
    labels = params.get("labels") or []
    if not isinstance(labels, list):
        labels = []
    options = params.get("options") or {}
    if not isinstance(options, dict):
        options = {}

    out: list[ExecutionItem] = []
    for item in items:
        mock_val, src = _resolve_mock_response(
            ctx, "quick_chart_response", "", params, item
        )
        if mock_val is None:
            mock_val = _synthesize_quick_chart(chart_type, datasets, labels, options)
            src = "offline"

        if isinstance(mock_val, dict):
            payload: dict[str, Any] = dict(mock_val)
        else:
            payload = _synthesize_quick_chart(chart_type, datasets, labels, options)
            src = "offline"

        _add_mock_source(payload, src, "quick_chart_response")

        ni = item.clone()
        ni.json = {**item.json, **payload}
        out.append(ni)
        logger.info("quickChart type=%s source=%s", chart_type, src)

    return [(0, out)]


# ── 13. Hacker News ───────────────────────────────────────────────────


def _synthesize_hn_story(story_id: int) -> dict[str, Any]:
    return {
        "id": story_id,
        "title": f"Mock Story {story_id}",
        "url": f"https://example.com/story/{story_id}",
        "score": 100 + story_id,
        "by": "mock_user",
        "time": int(time.time()),
        "type": "story",
    }


def _synthesize_hn(operation: str, story_id: str, limit: int) -> Any:
    if operation == "get":
        sid = int(story_id) if story_id.isdigit() else 1
        return _synthesize_hn_story(sid)
    capped = min(max(limit, 1), 3)
    return [_synthesize_hn_story(i + 1) for i in range(capped)]


async def exec_hacker_news(
    node: "ExecNode",
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Hacker News — fetch Hacker News stories.

    Operations: ``get`` (default, get story by id), ``getAll`` (get top
    stories), ``search``.  ``limit`` defaults to 10, capped at 3 offline.
    Emits one item per story with ``{id, title, url, score, by, time,
    type}``.
    """
    params = node.parameters or {}
    operation = _coerce_str(params.get("operation")).strip() or "get"
    if operation not in HN_OPERATIONS:
        raise ValueError(
            f"hackerNews: unsupported operation {operation!r}; "
            f"expected one of {HN_OPERATIONS}"
        )

    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        story_id = _resolve_str_param(params, "storyId", item, ectx, ("storyId", "id"))
        limit_raw = _resolve_param(params, "limit", item, ectx, ("limit",))
        try:
            limit = int(limit_raw) if limit_raw is not None else 10
        except (ValueError, TypeError):
            limit = 10

        mock_val, src = _resolve_mock_response(
            ctx, "hacker_news_response", operation, params, item
        )
        if mock_val is None:
            mock_val = _synthesize_hn(operation, story_id, limit)
            src = "offline"

        if isinstance(mock_val, list):
            stories = mock_val
        elif isinstance(mock_val, dict):
            stories = [mock_val]
        else:
            synthesized = _synthesize_hn(operation, story_id, limit)
            src = "offline"
            if isinstance(synthesized, list):
                stories = synthesized
            elif isinstance(synthesized, dict):
                stories = [synthesized]
            else:
                stories = []

        for story in stories:
            payload = dict(story) if isinstance(story, dict) else {}
            _add_mock_source(payload, src, "hacker_news_response")
            ni = item.clone()
            ni.json = {**item.json, **payload}
            out.append(ni)

        logger.info(
            "hackerNews %s emitted %d source=%s", operation, len(stories), src
        )

    return [(0, out)]


__all__ = [
    "exec_debug_helper",
    "exec_execute_command",
    "exec_n8n",
    "exec_evaluation",
    "exec_evaluation_trigger",
    "exec_activation_trigger",
    "exec_n8n_trigger",
    "exec_form",
    "exec_totp",
    "exec_ldap",
    "exec_icalendar",
    "exec_quick_chart",
    "exec_hacker_news",
    "N8N_META_OPERATIONS",
    "LDAP_OPERATIONS",
    "TOTP_OPERATIONS",
    "HN_OPERATIONS",
    "CHART_TYPES",
]