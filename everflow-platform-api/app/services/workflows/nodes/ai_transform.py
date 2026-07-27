"""AI Transform node executor.

Clean-room n8n ``@n8n/n8n-nodes-langchain.aiTransform`` v1.

The n8n AI Transform node takes a prompt template plus an optional system
instruction and, per input item, asks the connected language model to
"transform" the item. The clean-room implementation reuses the same mock
surface as the rest of the LangChain family (``ctx.mocks['chain_output']``
with ``ctx.mocks['agent_output']`` as a fallback) and falls back to an
offline echo of the resolved prompt so test runs and templates still
complete without a real LLM call.

Parameter surface:

- ``parameters.prompt`` (required) — string template. ``{{ $json.field }}``
  expressions are evaluated per item via :func:`evaluate`.
- ``parameters.instructions`` (optional) — system prompt. Surfaced on
  the output item as ``instructions`` so downstream nodes can observe
  the value without needing a separate capture step.
- ``parameters.outputField`` (optional, default ``"output"``) — the name
  of the field on the emitted item that carries the transformed text.

Mock surface:

- ``ctx.mocks['chain_output']`` — if callable, called with
  ``(prompt, item, params, ctx)`` and its return value is used as the
  transformed text. A static value is treated as a constant completion.
- ``ctx.mocks['agent_output']`` — same callable / static pattern,
  fallback for parity with the rest of the AI surface.

Offline fallback:

- Echo the resolved prompt back as the transformed text. This keeps
  templates and unit tests deterministic without requiring a real LLM
  credential.

The output item carries ``{<outputField>: <text>, prompt, model, source}``
merged with the upstream JSON so downstream nodes can still see the
original fields. ``model`` is only populated when a connected LM is
present in the graph (``ctx.lm_configs[id]['parameters']['model']``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.workflows.expression import ExpressionContext, evaluate
from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext


_DEFAULT_OUTPUT_FIELD = "output"


def _resolve_output_field(params: dict[str, Any]) -> str:
    """Pick the output field name, falling back to ``"output"``."""
    raw = params.get("outputField")
    if isinstance(raw, str):
        s = raw.strip()
        if s:
            return s
    return _DEFAULT_OUTPUT_FIELD


def _resolve_mock_text(
    ctx: "EngineContext",
    prompt: str,
    item: ExecutionItem,
    params: dict[str, Any],
) -> Any:
    """Return the mock-supplied transformation text, or ``None``."""
    if not ctx.mocks:
        return None
    for key in ("chain_output", "agent_output"):
        if key not in ctx.mocks:
            continue
        mock = ctx.mocks[key]
        if callable(mock):
            return mock(prompt, item, params, ctx)
        return mock
    return None


def _resolve_model(
    ctx: "EngineContext", lm_nodes: list[ExecNode]
) -> str | None:
    """Return the connected LM's configured model name, or ``None``."""
    if not lm_nodes:
        return None
    cfg = ctx.lm_configs.get(lm_nodes[0].id) or {}
    params = cfg.get("parameters") if isinstance(cfg.get("parameters"), dict) else {}
    raw = params.get("model")
    if isinstance(raw, str):
        s = raw.strip()
        if s:
            return s
    if isinstance(raw, dict):
        inner = raw.get("value")
        if isinstance(inner, str) and inner.strip():
            return inner.strip()
    return None


async def exec_ai_transform(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """AI Transform — evaluate a prompt template, return a transformed field per item.

    Reads ``parameters.prompt`` (required), ``parameters.instructions``
    (optional), and ``parameters.outputField`` (optional, default
    ``"output"``). Mocks surface through ``ctx.mocks['chain_output']``
    then ``ctx.mocks['agent_output']`` — a callable mock receives
    ``(prompt, item, params, ctx)``; a static value is used verbatim.
    With no mock configured, the executor echoes the resolved prompt so
    runs still complete deterministically.

    Emits one item per input carrying
    ``{<outputField>: <text>, prompt, model?, source: 'aiTransform'}``
    merged with the upstream JSON.
    """
    params = node.parameters or {}
    output_field = _resolve_output_field(params)
    instructions_raw = params.get("instructions")
    if not isinstance(instructions_raw, str):
        instructions_raw = ""

    lm_nodes = ctx.graph.ai_inputs(node.id, "ai_languageModel")
    for ln in lm_nodes:
        # Capture LM config so the model name is observable on ctx.lm_configs
        # (mirrors exec_chain_llm / exec_agent).
        from app.services.workflows.nodes.llm_agent import exec_lm_chat_openai

        await exec_lm_chat_openai(ln, [], ctx=ctx)
    model = _resolve_model(ctx, lm_nodes)

    out: list[ExecutionItem] = []
    for item in items:
        ectx = ExpressionContext(
            item=item, node_outputs=ctx.node_outputs, now=ctx.now
        )
        prompt = ""
        if params.get("prompt") is not None:
            prompt = str(evaluate(params.get("prompt"), ectx) or "")

        instructions = ""
        if instructions_raw:
            instructions = str(evaluate(instructions_raw, ectx) or "")

        mock_text = _resolve_mock_text(ctx, prompt, item, params)
        if mock_text is not None:
            text = str(mock_text)
        else:
            # Offline fallback: echo the resolved prompt so the workflow
            # still completes with a usable value when no LLM is wired.
            text = prompt

        ni = item.clone()
        merged: dict[str, Any] = {
            **item.json,
            output_field: text,
            "prompt": prompt,
            "source": "aiTransform",
        }
        if instructions:
            merged["instructions"] = instructions
        if model:
            merged["model"] = model
        ni.json = merged
        out.append(ni)
    return [(0, out)]
