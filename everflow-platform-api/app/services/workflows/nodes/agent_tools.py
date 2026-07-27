"""Clean-room n8n ``@n8n/n8n-nodes-langchain`` agent sub-tool executors.

v1 supports the 80% ops used in templates: each tool receives a
``tool_call``-shaped input from a connected agent and returns a
``tool_result``. Every executor follows the same shape:

1. Read ``parameters.<relevant_field>`` (or ``$json.<field>`` expression).
2. Use ``ctx.mocks['<tool>_output']`` first (callable or static value).
3. Offline fallback per tool (see below).
4. Emit one item per input with ``{tool, input, output, source}``.

All real network/subprocess calls are intentionally stubbed — tests drive
these executors entirely through ``ctx.mocks``.

The seven tools in this module:

- :func:`exec_agent_think`        — passthrough "thinking" step
- :func:`exec_agent_calculator`   — safe-evaluated arithmetic expression
- :func:`exec_agent_code`         — code snippet preview (no execution)
- :func:`exec_agent_http`         — HTTP request (mock-first)
- :func:`exec_agent_wikipedia`    — Wikipedia search (offline stub)
- :func:`exec_agent_workflow`     — invoke another workflow (offline stub)
- :func:`exec_agent_serpapi`      — SerpAPI search (offline stub)
"""

from __future__ import annotations

import ast
import logging
import uuid
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import (
    ExpressionContext,
    evaluate,
    evaluate_deep,
)
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext

logger = logging.getLogger(__name__)


# ── Shared helpers ────────────────────────────────────────────────────


def _ectx(item: ExecutionItem, ctx: "EngineContext") -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            import json as _json

            return _json.dumps(value, default=str)
        except Exception:
            return str(value)
    return str(value)


def _eval_param_text(
    raw: Any,
    item: ExecutionItem,
    ctx: "EngineContext",
    *,
    json_fallback_keys: tuple[str, ...] = (),
) -> str:
    """Evaluate a parameter as text, falling back to ``$json.<keys>`` order."""
    ectx = _ectx(item, ctx)
    if raw is not None:
        evaluated = evaluate(raw, ectx)
        text = _coerce_text(evaluated).strip()
        if text:
            return text
    for key in json_fallback_keys:
        val = item.json.get(key)
        if val is None:
            continue
        text = _coerce_text(val).strip()
        if text:
            return text
    return ""


def _eval_param_value(
    raw: Any,
    item: ExecutionItem,
    ctx: "EngineContext",
    *,
    json_fallback_keys: tuple[str, ...] = (),
) -> Any:
    """Evaluate a parameter (any type) with ``$json.<key>`` fallback."""
    ectx = _ectx(item, ctx)
    if raw is not None:
        evaluated = evaluate(raw, ectx)
        if evaluated not in (None, ""):
            return evaluated
    for key in json_fallback_keys:
        val = item.json.get(key)
        if val is not None and val != "":
            return val
    return None


def _mock_lookup(
    ctx: "EngineContext",
    keys: tuple[str, ...],
) -> tuple[bool, Any]:
    """Return ``(present, value)`` for the first matching mock key."""
    if not ctx.mocks:
        return False, None
    for key in keys:
        if key in ctx.mocks:
            return True, ctx.mocks[key]
    return False, None


def _invoke_mock(
    mock: Any,
    args: tuple[Any, ...],
) -> Any:
    """Call a callable mock or return the static value."""
    if callable(mock):
        return mock(*args)
    return mock


# ── 1. agentThink ─────────────────────────────────────────────────────


async def exec_agent_think(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Passthrough "thinking" step — echoes the thought back.

    Mock: ``ctx.mocks['think_output']``. Offline: echo the thought text.
    Output: ``{tool, input, output}`` where ``output`` is the thought.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        raw = params.get("thought")
        if raw is None:
            raw = item.json.get("thought")
        if raw is None:
            raw = item.json.get("text")
        thought_text = ""
        if raw is not None:
            thought_text = _coerce_text(evaluate(raw, ectx))

        input_text = thought_text

        present, mock = _mock_lookup(ctx, ("think_output",))
        if present:
            output_text = _coerce_text(_invoke_mock(mock, (input_text, item, params, ctx)))
            source = "mock"
        else:
            output_text = thought_text
            source = "offline"

        ni = item.clone()
        ni.json = {
            **item.json,
            "tool": "agentThink",
            "input": input_text,
            "output": output_text,
            "source": source,
        }
        out.append(ni)
    return [(0, out)]


# ── 2. agentCalculator ────────────────────────────────────────────────


_CALC_FUNCS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
}


def _safe_eval_expression(expr: str) -> Any:
    """Evaluate a math expression using a tiny AST walker.

    Permits:
      - Numeric literals (``ast.Constant`` with int/float).
      - Names ``True``/``False`` and ``pi``/``e`` as numeric constants.
      - Binary ops: ``+``, ``-``, ``*``, ``/``, ``**``, ``%``, floor div.
      - Unary ``-``/``+``.
      - Tuple literals (for ``min``/``max``/``sum`` of inline lists).
      - Function calls limited to :data:`_CALC_FUNCS`.

    Anything else (attribute access, subscripts, comprehensions, names not
    in the whitelist, ``import``) raises :class:`ValueError`.
    """
    tree = ast.parse(expr, mode="eval")

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
                return node.value
            raise ValueError(f"calculator: disallowed constant: {node.value!r}")
        if isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            op = node.op
            if isinstance(op, ast.Add):
                return left + right
            if isinstance(op, ast.Sub):
                return left - right
            if isinstance(op, ast.Mult):
                return left * right
            if isinstance(op, ast.Div):
                return left / right
            if isinstance(op, ast.FloorDiv):
                return left // right
            if isinstance(op, ast.Mod):
                return left % right
            if isinstance(op, ast.Pow):
                return left ** right
            raise ValueError(f"calculator: unsupported binary op: {type(op).__name__}")
        if isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            raise ValueError(f"calculator: unsupported unary op: {type(node.op).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("calculator: only direct function calls are allowed")
            fname = node.func.id
            if fname not in _CALC_FUNCS:
                raise ValueError(f"calculator: function not allowed: {fname!r}")
            if node.keywords:
                raise ValueError(
                    f"calculator: keyword args not allowed for {fname!r}"
                )
            args = [_eval(a) for a in node.args]
            return _CALC_FUNCS[fname](*args)
        if isinstance(node, ast.Name):
            if node.id in ("True", "False"):
                return 1 if node.id == "True" else 0
            if node.id == "pi":
                import math as _math

                return _math.pi
            if node.id == "e":
                import math as _math

                return _math.e
            raise ValueError(f"calculator: name not allowed: {node.id!r}")
        if isinstance(node, ast.Tuple):
            return tuple(_eval(elt) for elt in node.elts)
        if isinstance(node, ast.List):
            return [_eval(elt) for elt in node.elts]
        raise ValueError(f"calculator: unsupported node: {type(node).__name__}")

    return _eval(tree)


async def exec_agent_calculator(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Evaluate a math expression; safe AST walker — no imports/attribute access.

    Mock: ``ctx.mocks['calculator_output']`` (callable
    ``(expression, item, params, ctx)`` or static value).
    Offline: :func:`_safe_eval_expression` (see whitelist).
    Output: ``{tool, input: {expression}, output: <numeric>, source}``.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        expression = _eval_param_text(
            params.get("expression"),
            item,
            ctx,
            json_fallback_keys=("expression",),
        )

        present, mock = _mock_lookup(ctx, ("calculator_output",))
        if present:
            raw = _invoke_mock(mock, (expression, item, params, ctx))
            try:
                result: Any = float(raw) if not isinstance(raw, (int, float)) else raw
            except (TypeError, ValueError):
                result = raw
            source = "mock"
        else:
            result = _safe_eval_expression(expression)
            source = "offline"

        ni = item.clone()
        ni.json = {
            **item.json,
            "tool": "agentCalculator",
            "input": {"expression": expression},
            "output": result,
            "source": source,
        }
        out.append(ni)
    return [(0, out)]


# ── 3. agentCode ──────────────────────────────────────────────────────


def _code_preview(language: str, code: str) -> str:
    lang = (language or "python").strip().lower()
    fence_lang = "python" if lang in ("python", "py") else "js" if lang in ("javascript", "js", "node") else lang or "python"
    return f"```{fence_lang}\n{code}\n```\n(mocks are required to execute)"


async def exec_agent_code(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Code tool — preview only; never actually run.

    Mock: ``ctx.mocks['code_output']`` (callable
    ``(code, language, item, params, ctx)`` or static value).
    Offline: produce a fenced code-block preview.
    Output: ``{tool, input: {code, language}, output: <preview>, source, language}``.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        raw_code = params.get("code")
        if raw_code is None:
            raw_code = item.json.get("code")
        code_text = _coerce_text(evaluate(raw_code, ectx)) if raw_code is not None else ""

        raw_lang = params.get("language")
        if raw_lang is None:
            raw_lang = params.get("languageName")
        if raw_lang is None:
            raw_lang = item.json.get("language")
        language = _coerce_text(evaluate(raw_lang, ectx)) if raw_lang is not None else ""
        if not language:
            language = "python"

        present, mock = _mock_lookup(ctx, ("code_output",))
        if present:
            output_text = _coerce_text(
                _invoke_mock(mock, (code_text, language, item, params, ctx))
            )
            source = "mock"
        else:
            output_text = _code_preview(language, code_text)
            source = "offline"

        ni = item.clone()
        ni.json = {
            **item.json,
            "tool": "agentCode",
            "input": {"code": code_text, "language": language},
            "output": output_text,
            "source": source,
            "language": language,
        }
        out.append(ni)
    return [(0, out)]


# ── 4. agentHttp ──────────────────────────────────────────────────────


def _coerce_headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            import json as _json

            value = _json.loads(value)
        except Exception:
            return {}
    if isinstance(value, dict):
        return {str(k): _coerce_text(v) for k, v in value.items()}
    if isinstance(value, list):
        out: dict[str, str] = {}
        for entry in value:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("key")
                val = entry.get("value") or entry.get("val")
                if name is not None and val is not None:
                    out[str(name)] = _coerce_text(val)
        return out
    return {}


def _coerce_body(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.startswith(("{", "[", '"')):
            try:
                import json as _json

                return _json.loads(s)
            except Exception:
                return s
        return s
    return value


async def exec_agent_http(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """HTTP request tool — mock-first; never hits the network without a mock.

    Mock: ``ctx.mocks['http_response']`` (or ``ctx.mocks['agent_http_response']``)
    — callable ``(url, method, headers, body, item, params, ctx)`` or dict
    with ``status_code``/``body``/``headers`` or ``status``/``body``/``headers``.
    Offline: synthetic 200 with body containing the URL/method.
    Output: ``{tool, input, output: {status_code, body, headers}, request}``.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)

        raw_url = params.get("url")
        url = _coerce_text(evaluate(raw_url, ectx)) if raw_url is not None else ""

        raw_method = params.get("method")
        method_text = _coerce_text(evaluate(raw_method, ectx)) if raw_method is not None else ""
        method = method_text.upper() or "GET"

        headers_raw = params.get("headers")
        if isinstance(headers_raw, (dict, list)):
            headers = _coerce_headers(evaluate_deep(headers_raw, ectx))
        else:
            headers = _coerce_headers(evaluate(headers_raw, ectx) if headers_raw is not None else None)

        body_raw = params.get("body")
        body = _coerce_body(evaluate(body_raw, ectx)) if body_raw is not None else None

        present, mock = _mock_lookup(
            ctx, ("http_response", "agent_http_response")
        )
        if present:
            raw = _invoke_mock(mock, (url, method, headers, body, item, params, ctx))
            if isinstance(raw, dict):
                status_code = int(
                    raw.get("status_code", raw.get("status", 200)) or 200
                )
                resp_headers = _coerce_headers(raw.get("headers") or {})
                resp_body = raw.get("body", "")
            else:
                status_code = 200
                resp_headers = {}
                resp_body = raw
            source = "mock"
        else:
            status_code = 200
            resp_headers = {"content-type": "text/plain"}
            resp_body = f"Mock HTTP response from {method} {url}"
            source = "offline"

        ni = item.clone()
        ni.json = {
            **item.json,
            "tool": "agentHttp",
            "input": {"url": url, "method": method, "headers": headers, "body": body},
            "output": {
                "status_code": status_code,
                "body": resp_body,
                "headers": resp_headers,
            },
            "request": {"url": url, "method": method},
            "source": source,
        }
        out.append(ni)
    return [(0, out)]


# ── 5. agentWikipedia ─────────────────────────────────────────────────


async def exec_agent_wikipedia(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Wikipedia search — offline stub returning one result per query.

    Mock: ``ctx.mocks['wikipedia_output']`` (callable
    ``(query, item, params, ctx)`` or list of ``{title, snippet, url}``).
    Offline: one result titled ``Wikipedia: {query}``.
    Output: ``{tool, input, output: <list>}``.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        query = _eval_param_text(
            params.get("query"),
            item,
            ctx,
            json_fallback_keys=("query", "text"),
        )

        present, mock = _mock_lookup(ctx, ("wikipedia_output",))
        if present:
            results = _invoke_mock(mock, (query, item, params, ctx))
            if isinstance(results, dict):
                results = [results]
            results = list(results) if results is not None else []
            source = "mock"
        else:
            slug = query.replace(" ", "_") or "search"
            results = [
                {
                    "title": f"Wikipedia: {query}" if query else "Wikipedia: search",
                    "snippet": f"Mock summary for {query}" if query else "Mock summary",
                    "url": f"https://en.wikipedia.org/wiki/{slug}",
                }
            ]
            source = "offline"

        ni = item.clone()
        ni.json = {
            **item.json,
            "tool": "agentWikipedia",
            "input": {"query": query},
            "output": results,
            "source": source,
        }
        out.append(ni)
    return [(0, out)]


# ── 6. agentWorkflow ──────────────────────────────────────────────────


async def exec_agent_workflow(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Sub-workflow invocation — synthetic record (no real engine call).

    Mock: ``ctx.mocks['workflow_output']`` (callable
    ``(workflowId, data, item, params, ctx)`` or dict).
    Offline: ``{workflowId, runId: 'sub-XXXXXXXX', status: 'completed', inputData}``.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        ectx = _ectx(item, ctx)
        raw_wf = params.get("workflowId")
        if raw_wf is None:
            raw_wf = params.get("workflow")
        if raw_wf is None:
            raw_wf = item.json.get("workflowId")
        workflow_id = _coerce_text(evaluate(raw_wf, ectx)) if raw_wf is not None else ""

        raw_data = params.get("data")
        if raw_data is None:
            raw_data = item.json.get("data")
        if isinstance(raw_data, (dict, list)):
            data = evaluate_deep(raw_data, ectx)
        elif raw_data is not None:
            data = evaluate(raw_data, ectx)
        else:
            data = {}

        present, mock = _mock_lookup(ctx, ("workflow_output",))
        if present:
            result = _invoke_mock(mock, (workflow_id, data, item, params, ctx))
            if not isinstance(result, dict):
                result = {"output": result}
            payload = {
                "workflowId": workflow_id,
                "runId": str(result.get("runId") or f"sub-{uuid.uuid4().hex[:8]}"),
                "status": str(result.get("status") or "completed"),
                "inputData": result.get("inputData", data),
            }
            source = "mock"
        else:
            payload = {
                "workflowId": workflow_id,
                "runId": f"sub-{uuid.uuid4().hex[:8]}",
                "status": "completed",
                "inputData": data,
            }
            source = "offline"

        ni = item.clone()
        ni.json = {
            **item.json,
            "tool": "agentWorkflow",
            "input": {"workflowId": workflow_id, "data": data},
            "output": payload,
            "source": source,
        }
        out.append(ni)
    return [(0, out)]


# ── 7. agentSerpApi ───────────────────────────────────────────────────


async def exec_agent_serpapi(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """SerpAPI search — offline stub returning five mock results per query.

    Mock: ``ctx.mocks['serp_output']`` or ``ctx.mocks['serpapi_output']``
    (callable ``(query, item, params, ctx)`` or list of
    ``{title, link, snippet}``).
    Offline: 5 results titled ``Result N for {query}``.
    Output: ``{tool, input, output: <list>}``.
    """
    params = node.parameters or {}
    out: list[ExecutionItem] = []
    for item in items:
        query = _eval_param_text(
            params.get("query"),
            item,
            ctx,
            json_fallback_keys=("query", "text"),
        )

        present, mock = _mock_lookup(
            ctx, ("serp_output", "serpapi_output")
        )
        if present:
            results = _invoke_mock(mock, (query, item, params, ctx))
            if isinstance(results, dict):
                results = [results]
            results = list(results) if results is not None else []
            source = "mock"
        else:
            results = [
                {
                    "title": f"Result {i + 1} for {query}" if query else f"Result {i + 1}",
                    "link": f"https://example.com/{i + 1}",
                    "snippet": f"Mock snippet {i + 1}",
                }
                for i in range(5)
            ]
            source = "offline"

        ni = item.clone()
        ni.json = {
            **item.json,
            "tool": "agentSerpApi",
            "input": {"query": query},
            "output": results,
            "source": source,
        }
        out.append(ni)
    return [(0, out)]
