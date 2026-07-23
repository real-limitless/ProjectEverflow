"""Safe-ish n8n expression evaluator for ={{ ... }} and bare expressions.

Supports the subset used by Stock Agent Emailer:
  $json, $json.field, nested access
  $('Node Name').item.json...
  $json.rows.toJsonString()
  $now / $now.toFormat(...)
  string concat with +
  simple property access and method calls on known helpers
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.workflows.items import ExecutionItem


class ExpressionError(ValueError):
    pass


@dataclass
class ExpressionContext:
    item: ExecutionItem
    # node_name -> last output items
    node_outputs: dict[str, list[ExecutionItem]] = field(default_factory=dict)
    now: datetime | None = None

    def get_now(self) -> datetime:
        return self.now or datetime.now(timezone.utc)


class _JsonProxy:
    """Attribute/item access over a dict, with toJsonString()."""

    def __init__(self, data: Any) -> None:
        self._data = data

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name == "toJsonString":
            return lambda: json.dumps(self._data, default=str)
        if isinstance(self._data, dict):
            if name not in self._data:
                return _JsonProxy(None)
            return _wrap(self._data[name])
        return _JsonProxy(None)

    def __getitem__(self, key: Any) -> Any:
        if isinstance(self._data, dict):
            return _wrap(self._data.get(key))
        if isinstance(self._data, (list, tuple)) and isinstance(key, int):
            if 0 <= key < len(self._data):
                return _wrap(self._data[key])
            return _JsonProxy(None)
        return _JsonProxy(None)

    def __str__(self) -> str:
        if self._data is None:
            return ""
        return str(self._data)

    def __bool__(self) -> bool:
        return bool(self._data)

    def __add__(self, other: Any) -> Any:
        return str(self) + str(other)

    def __radd__(self, other: Any) -> Any:
        return str(other) + str(self)

    def unwrap(self) -> Any:
        return self._data


class _NowProxy:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def toFormat(self, fmt: str) -> str:  # noqa: N802 — n8n Luxon-style
        # Map a few Luxon tokens to strftime
        mapping = [
            ("yyyy", "%Y"),
            ("MMMM", "%B"),
            ("MMM", "%b"),
            ("MM", "%m"),
            ("dd", "%d"),
            ("d", "%-d" if True else "%d"),
            ("HH", "%H"),
            ("mm", "%M"),
            ("ss", "%S"),
        ]
        py = fmt
        for lux, st in mapping:
            py = py.replace(lux, st)
        try:
            return self._dt.strftime(py)
        except Exception:
            return self._dt.isoformat()

    def toISO(self) -> str:  # noqa: N802
        return self._dt.isoformat()

    def __str__(self) -> str:
        return self._dt.isoformat()


class _ItemProxy:
    def __init__(self, item: ExecutionItem) -> None:
        self.json = _JsonProxy(item.json)
        self.binary = item.binary


class _NodeRef:
    def __init__(self, items: list[ExecutionItem]) -> None:
        self._items = items

    @property
    def item(self) -> _ItemProxy:
        if not self._items:
            return _ItemProxy(ExecutionItem())
        return _ItemProxy(self._items[0])

    @property
    def first(self) -> _ItemProxy:
        return self.item

    @property
    def all(self) -> list[_ItemProxy]:
        return [_ItemProxy(i) for i in self._items]


def _wrap(val: Any) -> Any:
    if isinstance(val, (dict, list, type(None))):
        return _JsonProxy(val)
    return val


def _node_lookup(ctx: ExpressionContext, name: str) -> _NodeRef:
    items = ctx.node_outputs.get(name) or []
    return _NodeRef(items)


_EXPR_RE = re.compile(r"^=\{\{(.*)\}\}$", re.DOTALL)
_BARE_EQ = re.compile(r"^=(?!\{)(.*)$", re.DOTALL)


def is_expression(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip()
    return s.startswith("={{") or (s.startswith("=") and not s.startswith("=="))


def evaluate(value: Any, ctx: ExpressionContext) -> Any:
    """Evaluate a parameter value; non-expression strings pass through."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    m = _EXPR_RE.match(s)
    if m:
        return _eval_jsish(m.group(1).strip(), ctx)
    # n8n also uses =literal with embedded {{ }} in subjects e.g. =Portfolio ... {{ $now... }}
    if s.startswith("=") and "{{" in s:
        return _eval_interpolated(s[1:], ctx)
    m2 = _BARE_EQ.match(s)
    if m2 and ("$json" in s or "$(" in s or "$now" in s):
        return _eval_jsish(m2.group(1).strip(), ctx)
    return value


def evaluate_deep(obj: Any, ctx: ExpressionContext) -> Any:
    """Walk dict/list and evaluate string expressions."""
    if isinstance(obj, dict):
        return {k: evaluate_deep(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [evaluate_deep(v, ctx) for v in obj]
    if isinstance(obj, str) and is_expression(obj):
        return evaluate(obj, ctx)
    if isinstance(obj, str) and "={{ " in obj or (isinstance(obj, str) and "={{$" in obj):
        # mixed strings rare; try full evaluate
        if "{{" in obj and obj.startswith("="):
            return evaluate(obj, ctx)
    return obj


def _eval_interpolated(template: str, ctx: ExpressionContext) -> str:
    """Evaluate =...{{ expr }}... templates."""
    parts: list[str] = []
    i = 0
    while i < len(template):
        start = template.find("{{", i)
        if start < 0:
            parts.append(template[i:])
            break
        parts.append(template[i:start])
        end = template.find("}}", start)
        if end < 0:
            parts.append(template[start:])
            break
        expr = template[start + 2 : end].strip()
        val = _eval_jsish(expr, ctx)
        parts.append("" if val is None else str(_unwrap(val)))
        i = end + 2
    return "".join(parts)


def _unwrap(val: Any) -> Any:
    if isinstance(val, _JsonProxy):
        return val.unwrap()
    return val


def _rewrite_n8n_expr(expr: str) -> str:
    """Rewrite n8n `$json` / `$now` / `$('Node')` into valid Python identifiers."""
    # $('Name') or $("Name") → __node('Name')
    expr = re.sub(
        r"\$\(\s*(['\"])(.*?)\1\s*\)",
        r"__node(\1\2\1)",
        expr,
    )
    # $json → __json  (word boundary after so $jsonX not partially matched wrongly)
    expr = re.sub(r"\$json\b", "__json", expr)
    expr = re.sub(r"\$now\b", "__now", expr)
    # leftover bare $ not allowed
    return expr


def _eval_jsish(expr: str, ctx: ExpressionContext) -> Any:
    """Evaluate a limited expression language via Python eval with safe globals."""
    py_expr = _rewrite_n8n_expr(expr)
    env: dict[str, Any] = {
        "__json": _JsonProxy(ctx.item.json),
        "__now": _NowProxy(ctx.get_now()),
        "__node": lambda name: _node_lookup(ctx, str(name)),
        "true": True,
        "false": False,
        "null": None,
        "JSON": json,
    }

    try:
        result = eval(py_expr, {"__builtins__": {}}, env)  # noqa: S307 — restricted env
    except Exception as exc:
        raise ExpressionError(f"Failed to evaluate expression: {expr!r}: {exc}") from exc
    return _unwrap(result)


def resolve_param(params: dict[str, Any], key: str, ctx: ExpressionContext, default: Any = None) -> Any:
    if key not in params:
        return default
    return evaluate(params[key], ctx)
