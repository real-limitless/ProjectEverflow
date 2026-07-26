"""Clean-room n8n ``@n8n/n8n-nodes-langchain`` text-AI executors.

v1 supports the 80% ops used in templates: each tool receives an input text
and a connected language model, applies the LLM, and returns structured
output. All three follow the same pattern:

1. Read ``parameters.text`` (expression or JSON field name) and fall back
   to ``$json.text`` / ``$json.content`` / ``$json.input``.
2. Resolve the connected LM via ``ctx.graph.ai_inputs(node.id, "ai_languageModel")``
   and read its metadata from ``ctx.lm_configs[id]['parameters']['model']``.
3. Honor ``ctx.mocks['<tool>_output']`` first — callable
   ``(text, item, params, ctx)`` or static value.
4. Otherwise run a deterministic offline fallback per tool.
5. Emit one item per input, carrying the tool's structured payload plus
   ``source`` and ``model``.

The three tools in this module:

- :func:`exec_information_extraction` — structured field extraction.
- :func:`exec_text_classifier`        — single-label classification.
- :func:`exec_sentiment_analysis`     — sentiment label + confidence.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext

logger = logging.getLogger(__name__)


# ── Shared helpers ────────────────────────────────────────────────────


_POSITIVE_KEYWORDS: tuple[str, ...] = (
    "good",
    "great",
    "excellent",
    "love",
    "happy",
)
_NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "bad",
    "terrible",
    "hate",
    "sad",
    "awful",
)
_DEFAULT_SENTIMENT_CATEGORIES: tuple[str, ...] = (
    "positive",
    "negative",
    "neutral",
)


def _ectx(item: ExecutionItem, ctx: "EngineContext") -> ExpressionContext:
    return ExpressionContext(item=item, node_outputs=ctx.node_outputs, now=ctx.now)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        try:
            import json as _json

            return _json.dumps(value, default=str)
        except Exception:
            return str(value)
    return str(value)


def _resolve_input_text(
    raw_param: Any,
    item: ExecutionItem,
    ctx: "EngineContext",
) -> str:
    """Resolve the input text for a text-AI tool.

    Order:

    1. ``parameters.text`` — evaluated as an n8n expression when prefixed
       with ``=``; otherwise treated as a JSON field name on the item.
    2. ``item.json['text']`` (string).
    3. ``item.json['content']`` (string).
    4. ``item.json['input']`` (string).
    """
    ectx = _ectx(item, ctx)
    if raw_param is not None:
        if isinstance(raw_param, str) and raw_param.startswith("="):
            evaluated = evaluate(raw_param, ectx)
            text = _coerce_text(evaluated).strip()
            if text:
                return text
        else:
            key = _coerce_text(raw_param).strip()
            if key and key in item.json:
                val = item.json[key]
                text = _coerce_text(val).strip()
                if text:
                    return text
            text = _coerce_text(evaluate(raw_param, ectx)).strip()
            if text:
                return text

    for fallback_key in ("text", "content", "input"):
        val = item.json.get(fallback_key)
        if val is None:
            continue
        text = _coerce_text(val).strip()
        if text:
            return text
    return ""


def _resolve_model(
    ctx: "EngineContext",
    lm_nodes: list[ExecNode],
    *,
    default: str = "gpt-4o-mini",
) -> str:
    """Return the configured model name for the first connected LM."""
    for ln in lm_nodes:
        cfg = ctx.lm_configs.get(ln.id) or {}
        params = cfg.get("parameters") if isinstance(cfg.get("parameters"), dict) else {}
        raw = params.get("model")
        if raw is None:
            continue
        text = _coerce_text(raw).strip()
        if text:
            return text
        # Resource-locator wrappers ({__rl: true, value: ...})
        if isinstance(raw, dict):
            inner = raw.get("value") or raw.get("name")
            inner_text = _coerce_text(inner).strip()
            if inner_text:
                return inner_text
    return default


def _capture_lm_configs(
    ctx: "EngineContext",
    lm_nodes: list[ExecNode],
) -> None:
    """Ensure every connected LM has an entry in ``ctx.lm_configs``.

    Falls back to a minimal record when the upstream executor did not run
    (e.g. unit tests that pass ``ai_inputs`` but no real graph step).
    """
    for ln in lm_nodes:
        if ln.id in ctx.lm_configs:
            continue
        ctx.lm_configs[ln.id] = {
            "name": ln.name,
            "parameters": dict(ln.parameters or {}),
        }


def _keyword_label(text: str) -> str:
    """Default positive/negative/neutral heuristic used by offline fallbacks."""
    lowered = (text or "").lower()
    for kw in _POSITIVE_KEYWORDS:
        if kw in lowered:
            return "positive"
    for kw in _NEGATIVE_KEYWORDS:
        if kw in lowered:
            return "negative"
    return "neutral"


def _normalise_schema(raw: Any) -> dict[str, str]:
    """Coerce a schema parameter into ``{field_name: description}``."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        out: dict[str, str] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or not key:
                continue
            if isinstance(value, str):
                out[key] = value
            elif isinstance(value, dict):
                desc = value.get("description") or value.get("desc") or ""
                out[key] = _coerce_text(desc)
            else:
                out[key] = _coerce_text(value)
        return out
    if isinstance(raw, list):
        out_list: dict[str, str] = {}
        for entry in raw:
            if isinstance(entry, str) and entry.strip():
                out_list[entry.strip()] = entry.strip()
            elif isinstance(entry, dict):
                name = entry.get("name") or entry.get("field") or entry.get("key")
                if isinstance(name, str) and name:
                    out_list[name] = _coerce_text(
                        entry.get("description") or entry.get("desc") or name
                    )
        return out_list
    return {}


def _coerce_categories(raw: Any) -> list[str]:
    """Coerce a categories parameter into a clean list of strings."""
    if raw is None:
        return list(_DEFAULT_SENTIMENT_CATEGORIES)
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",")]
        return [p for p in parts if p] or list(_DEFAULT_SENTIMENT_CATEGORIES)
    if isinstance(raw, (list, tuple)):
        out: list[str] = []
        for entry in raw:
            text = _coerce_text(entry).strip()
            if text:
                out.append(text)
        return out or list(_DEFAULT_SENTIMENT_CATEGORIES)
    return list(_DEFAULT_SENTIMENT_CATEGORIES)


def _invoke_mock(mock: Any, args: tuple[Any, ...]) -> Any:
    if callable(mock):
        return mock(*args)
    return mock


def _mock_lookup(
    ctx: "EngineContext",
    keys: tuple[str, ...],
) -> tuple[bool, Any]:
    if not ctx.mocks:
        return False, None
    for key in keys:
        if key in ctx.mocks:
            return True, ctx.mocks[key]
    return False, None


# ── 1. informationExtraction ──────────────────────────────────────────


async def exec_information_extraction(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Extract structured fields from input text per ``parameters.schema``.

    Mock: ``ctx.mocks['extraction_output']`` (callable
    ``(text, item, params, ctx)`` or dict of ``{field: value}``).
    Offline: produce a stub dict with each schema field set to
    ``"extracted_<field>"`` (or ``"<field>"`` when the schema only carries
    a list of names).
    Output: ``{text, extracted, schema, model, source}``.
    """
    params = node.parameters or {}
    schema = _normalise_schema(params.get("schema"))
    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    _capture_lm_configs(ctx, lm_nodes)
    model = _resolve_model(ctx, lm_nodes)

    out: list[ExecutionItem] = []
    for item in items:
        text = _resolve_input_text(params.get("text"), item, ctx)
        present, mock = _mock_lookup(ctx, ("extraction_output",))
        if present:
            raw = _invoke_mock(mock, (text, item, params, ctx))
            if isinstance(raw, dict):
                extracted: dict[str, Any] = {str(k): v for k, v in raw.items()}
            else:
                extracted = {"output": raw}
            source = "mock"
        else:
            if schema:
                extracted = {
                    field_name: f"extracted_{field_name}" for field_name in schema
                }
            else:
                extracted = {}
            source = "offline"

        ni = item.clone()
        ni.json = {
            **item.json,
            "text": text,
            "extracted": extracted,
            "schema": schema,
            "model": model,
            "source": source,
        }
        out.append(ni)
    return [(0, out)]


# ── 2. textClassifier ─────────────────────────────────────────────────


async def exec_text_classifier(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Classify text into one of ``parameters.categories``.

    Mock: ``ctx.mocks['classification_output']`` (callable
    ``(text, item, params, ctx)`` or string category).
    Offline: keyword heuristic — ``positive`` for any of
    ``{good, great, excellent, love, happy}``, ``negative`` for any of
    ``{bad, terrible, hate, sad, awful}``, else ``neutral``.
    Output: ``{text, category, confidence, categories, model, source}``.
    """
    params = node.parameters or {}
    categories = _coerce_categories(params.get("categories"))
    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    _capture_lm_configs(ctx, lm_nodes)
    model = _resolve_model(ctx, lm_nodes)

    out: list[ExecutionItem] = []
    for item in items:
        text = _resolve_input_text(params.get("text"), item, ctx)
        present, mock = _mock_lookup(ctx, ("classification_output",))
        if present:
            raw = _invoke_mock(mock, (text, item, params, ctx))
            category = _coerce_text(raw).strip() or categories[0]
            source = "mock"
        else:
            category = _keyword_label(text)
            source = "offline"

        if category not in categories:
            categories.append(category)

        ni = item.clone()
        ni.json = {
            **item.json,
            "text": text,
            "category": category,
            "confidence": 0.8,
            "categories": list(categories),
            "model": model,
            "source": source,
        }
        out.append(ni)
    return [(0, out)]


# ── 3. sentimentAnalysis ──────────────────────────────────────────────


async def exec_sentiment_analysis(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Return a sentiment label + confidence for the input text.

    Mock: ``ctx.mocks['sentiment_output']`` — callable
    ``(text, item, params, ctx)`` returning either a ``{label, confidence}``
    dict, a bare string label, or a numeric confidence. A non-callable
    value follows the same shape rules.
    Offline: same positive/negative/neutral keyword heuristic as the
    text classifier, with confidence ``0.8`` for any keyword match and
    ``0.5`` for the neutral fallback.
    Output: ``{text, label, confidence, model, source}``.
    """
    params = node.parameters or {}
    categories = _coerce_categories(params.get("categories"))
    if categories == list(_DEFAULT_SENTIMENT_CATEGORIES):
        categories = list(_DEFAULT_SENTIMENT_CATEGORIES)

    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    _capture_lm_configs(ctx, lm_nodes)
    model = _resolve_model(ctx, lm_nodes)

    out: list[ExecutionItem] = []
    for item in items:
        text = _resolve_input_text(params.get("text"), item, ctx)
        present, mock = _mock_lookup(ctx, ("sentiment_output",))
        if present:
            raw = _invoke_mock(mock, (text, item, params, ctx))
            if isinstance(raw, dict):
                label = _coerce_text(raw.get("label") or raw.get("sentiment") or "").strip()
                conf_raw = raw.get("confidence") if "confidence" in raw else raw.get("score")
                try:
                    confidence: float = float(conf_raw) if conf_raw is not None else 0.8
                except (TypeError, ValueError):
                    confidence = 0.8
            else:
                label = _coerce_text(raw).strip()
                confidence = 0.8
            source = "mock"
        else:
            label = _keyword_label(text)
            lowered = (text or "").lower()
            if any(kw in lowered for kw in _POSITIVE_KEYWORDS + _NEGATIVE_KEYWORDS):
                confidence = 0.8
            else:
                confidence = 0.5
            source = "offline"

        if not label:
            label = "neutral"
        if categories and label not in categories:
            categories.append(label)

        ni = item.clone()
        ni.json = {
            **item.json,
            "text": text,
            "label": label,
            "confidence": confidence,
            "categories": list(categories),
            "model": model,
            "source": source,
        }
        out.append(ni)
    return [(0, out)]
