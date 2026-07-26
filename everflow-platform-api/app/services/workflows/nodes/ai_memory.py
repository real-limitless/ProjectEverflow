"""AI memory + output parser sub-nodes for the LangChain-compatible engine.

These are sub-nodes that connect to the AI Agent via ``ai_memory`` and
``ai_outputParser`` edges. The agent (see ``llm_agent.exec_agent``)
discovers them at runtime and uses them to:

- ``memoryBufferWindow`` — keep a sliding window of recent messages and
  inject them into the next LLM call.
- ``outputParserStructured`` — declare a JSON schema; the parser post-
  processes the LLM's response to extract structured fields and attaches
  them to the item.

Both executors register their config on the :class:`EngineContext` and
return empty items — they do not run on the main chain. The agent
consumes their config in :func:`llm_agent.exec_agent`.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from app.services.workflows.graph import ExecNode
from app.services.workflows.items import ExecutionItem

if TYPE_CHECKING:
    from app.services.workflows.engine import EngineContext


# ── Window Buffer Memory ─────────────────────────────────────────────


async def exec_memory_buffer_window(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Window Buffer Memory — store config; the agent reads it per call."""
    del items
    params = node.parameters or {}
    ctx_size = int(params.get("contextWindowLength") or params.get("maxMessages") or 5)
    session_id = str(params.get("sessionId") or params.get("sessionKey") or "default")
    ctx.memory_configs[node.id] = {
        "name": node.name,
        "type": "bufferWindow",
        "contextWindowLength": ctx_size,
        "sessionId": session_id,
    }
    return [(0, [])]


def memory_window_for(
    ctx: "EngineContext",
    *,
    session_id: str,
    limit: int,
) -> list[dict[str, str]]:
    """Return up to ``limit`` recent messages for ``session_id``."""
    sessions = ctx.memory_state.setdefault("sessions", {})
    msgs = sessions.get(session_id, [])
    return list(msgs[-limit:]) if msgs else []


def push_memory_message(
    ctx: "EngineContext",
    *,
    session_id: str,
    role: str,
    content: str,
) -> None:
    """Append a message to a session's memory buffer."""
    sessions = ctx.memory_state.setdefault("sessions", {})
    msgs = sessions.setdefault(session_id, [])
    msgs.append({"role": role, "content": content})


# ── Structured Output Parser ─────────────────────────────────────────


async def exec_output_parser_structured(
    node: ExecNode,
    items: list[ExecutionItem],
    *,
    ctx: "EngineContext",
) -> list[tuple[int, list[ExecutionItem]]]:
    """Structured Output Parser — declare a JSON schema; agent applies it."""
    del items
    params = node.parameters or {}
    schema_raw = params.get("jsonSchema") or params.get("schema") or {}
    if isinstance(schema_raw, str):
        try:
            schema_raw = json.loads(schema_raw)
        except (ValueError, TypeError):
            schema_raw = {}
    if not isinstance(schema_raw, dict):
        schema_raw = {}
    ctx.output_parsers[node.id] = {
        "name": node.name,
        "type": "structured",
        "schema": dict(schema_raw),
    }
    return [(0, [])]


def apply_structured_parser(
    text: str,
    parser_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Extract fields from ``text`` using a simple JSON / key:value heuristic.

    v1 strategies (in order):
    1. The whole text is a JSON object → return it.
    2. The text contains a JSON block in ``\\`\\`\\`json ... \\`\\`\\``` fences
       → parse and return.
    3. Otherwise, for each property in the schema, look for
       ``"<name>": <value>`` or ``<name>: <value>`` patterns.
    """
    schema = parser_cfg.get("schema") or {}
    properties = (
        schema.get("properties")
        if isinstance(schema, dict)
        else None
    )
    if not isinstance(properties, dict):
        properties = {}

    def _from_json_block(s: str) -> Any:
        s = s.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            pass
        # Strip ```json ... ``` fences
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (ValueError, TypeError):
                return None
        m = re.search(r"(\{[\s\S]*\})", s)
        if m:
            try:
                return json.loads(m.group(1))
            except (ValueError, TypeError):
                return None
        return None

    parsed = _from_json_block(text)
    if isinstance(parsed, dict):
        return parsed

    out: dict[str, Any] = {}
    for name in properties.keys():
        patterns = [
            rf'"{re.escape(name)}"\s*:\s*"([^"]*)"',
            rf'"{re.escape(name)}"\s*:\s*([\d.\-]+)',
            rf"{re.escape(name)}\s*:\s*([^\n,]+)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = m.group(1).strip()
                try:
                    if "." in val:
                        out[name] = float(val)
                    else:
                        out[name] = int(val)
                except ValueError:
                    out[name] = val
                break
    return out
