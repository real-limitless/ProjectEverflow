"""
Streaming event normalizer for LangGraph → WebSocket.

Converts the fine-grained events from ``graph.astream_events(version="v2")``
into a compact, typed event stream the frontend can consume.

Frontend event types:
  - ``text_chunk``   – a single token of LLM output
  - ``reasoning``    – a reasoning/thinking token (if provider supports it)
  - ``tool_start``   – a tool is about to be called
  - ``tool_result``  – a tool call completed
  - ``worker_start`` – orchestrator delegated to a worker
  - ``worker_end``   – worker finished
  - ``todos_update`` – updated todo/plan list
  - ``complete``     – final response ready
  - ``error``        – something went wrong
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage
from asgiref.sync import sync_to_async

from api.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


async def stream_agent_events(
    graph: Any,
    user_input: str,
    session: ChatSession,
    *,
    context_files: Optional[list] = None,
    max_iterations: int = 25,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run *graph* and yield normalized events for the WebSocket consumer.

    This function:
    1. Loads conversation history from the DB
    2. Runs the graph with ``astream_events(version="v2")``
    3. Normalises each LangGraph event into a frontend-friendly dict
    4. Collects the final response and yields a ``complete`` event
    """
    start_time = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Load conversation history
    # ------------------------------------------------------------------
    messages_qs = await sync_to_async(
        lambda: list(
            ChatMessage.objects.filter(session=session).order_by("created_at")
        )
    )()

    history = []
    for msg in messages_qs:
        if msg.message_type == "user":
            history.append(HumanMessage(content=msg.content))
        elif msg.message_type == "assistant":
            history.append(AIMessage(content=msg.content))

    initial_messages = history + [HumanMessage(content=user_input)]

    # Optional: inject context files as a system-level hint
    if context_files:
        ctx_parts = []
        for cf in context_files:
            path = cf.get("path", "unknown")
            content = (cf.get("content") or "")[:2000]
            ctx_parts.append(f"--- {path} ---\n{content}")
        ctx_text = "\n\n".join(ctx_parts)
        context_msg = HumanMessage(
            content=f"[Context files attached by user]:\n{ctx_text}"
        )
        initial_messages.insert(-1, context_msg)  # Before user message

    # ------------------------------------------------------------------
    # 2. Prepare graph config
    # ------------------------------------------------------------------
    config = {
        "configurable": {"thread_id": str(session.id)},
        "recursion_limit": max_iterations * 3,  # Each iteration may be 2-3 nodes
    }

    input_state = {
        "messages": initial_messages,
        "plan": [],
        "next": "",
        "worker_outputs": [],
        "context_files": context_files or [],
        "mode": session.mode or "ask",
        "iteration": 0,
        "max_iterations": max_iterations,
    }

    # ------------------------------------------------------------------
    # 3. Stream events
    # ------------------------------------------------------------------
    final_content = ""
    final_tool_calls = []
    final_reasoning = ""
    accumulated_content = ""
    current_run_id = None
    active_tools = {}  # run_id → tool info

    try:
        async for event in graph.astream_events(
            input_state,
            config=config,
            version="v2",
        ):
            kind = event.get("event", "")
            data = event.get("data", {})
            name = event.get("name", "")
            run_id = event.get("run_id", "")
            metadata = event.get("metadata", {})

            # ---- LLM token streaming ----
            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk:
                    content = getattr(chunk, "content", "")
                    if content:
                        accumulated_content += content
                        yield {
                            "type": "text_chunk",
                            "content": content,
                            "node": metadata.get("langgraph_node", ""),
                        }

                    # Check for tool call chunks (streaming tool calls)
                    tool_call_chunks = getattr(chunk, "tool_call_chunks", [])
                    for tc in tool_call_chunks:
                        if tc.get("name"):
                            yield {
                                "type": "tool_start",
                                "name": tc["name"],
                                "args": tc.get("args", ""),
                                "id": tc.get("id", ""),
                            }

            # ---- Tool execution events ----
            elif kind == "on_tool_start":
                tool_name = name or data.get("name", "unknown")
                tool_input = data.get("input", {})
                active_tools[run_id] = {"name": tool_name, "start": time.monotonic()}
                yield {
                    "type": "tool_start",
                    "name": tool_name,
                    "args": tool_input if isinstance(tool_input, (str, dict)) else str(tool_input),
                    "run_id": run_id,
                }

            elif kind == "on_tool_end":
                tool_output = data.get("output", "")
                if hasattr(tool_output, "content"):
                    tool_output = tool_output.content
                tool_info = active_tools.pop(run_id, {})
                tool_name = tool_info.get("name", name or "unknown")
                duration = time.monotonic() - tool_info.get("start", time.monotonic())

                final_tool_calls.append({
                    "name": tool_name,
                    "output": str(tool_output)[:500],
                    "duration": round(duration, 2),
                })

                yield {
                    "type": "tool_result",
                    "name": tool_name,
                    "output": str(tool_output)[:2000],
                    "duration": round(duration, 2),
                    "run_id": run_id,
                }

            # ---- Node lifecycle (worker tracking) ----
            elif kind == "on_chain_start" and metadata.get("langgraph_node"):
                node = metadata["langgraph_node"]
                if node in ("coder", "executor", "researcher", "tool_runner", "reviewer"):
                    yield {
                        "type": "worker_start",
                        "worker": node,
                    }

            elif kind == "on_chain_end" and metadata.get("langgraph_node"):
                node = metadata["langgraph_node"]
                if node in ("coder", "executor", "researcher", "tool_runner", "reviewer"):
                    # Extract content from the chain output
                    output = data.get("output", {})
                    worker_content = ""
                    if isinstance(output, dict):
                        msgs = output.get("messages", [])
                        if msgs:
                            last = msgs[-1] if isinstance(msgs, list) else msgs
                            worker_content = getattr(last, "content", str(last))
                    yield {
                        "type": "worker_end",
                        "worker": node,
                        "content": worker_content[:1000],
                    }

                # Check orchestrator output for plan/todos
                if node == "orchestrator":
                    output = data.get("output", {})
                    if isinstance(output, dict) and output.get("plan"):
                        yield {
                            "type": "todos_update",
                            "todos": output["plan"],
                        }

            # ---- LLM generation complete (per-node) ----
            elif kind == "on_chat_model_end":
                output = data.get("output")
                if output:
                    msg = None
                    if hasattr(output, "generations") and output.generations:
                        msg = output.generations[0].message
                    elif hasattr(output, "content"):
                        msg = output

                    if msg:
                        content = getattr(msg, "content", "")
                        if content:
                            final_content = content

                        # Collect tool calls from the final message
                        tc = getattr(msg, "tool_calls", [])
                        if tc:
                            for call in tc:
                                final_tool_calls.append({
                                    "name": call.get("name", ""),
                                    "args": call.get("args", {}),
                                })

    except Exception as e:
        logger.error("Agent stream error: %s", e, exc_info=True)
        yield {
            "type": "error",
            "message": str(e),
            "details": "",  # Don't leak tracebacks to frontend
        }
        return

    # ------------------------------------------------------------------
    # 4. Final event
    # ------------------------------------------------------------------
    elapsed = round(time.monotonic() - start_time, 2)

    # Use accumulated content if final_content is empty
    if not final_content and accumulated_content:
        final_content = accumulated_content

    yield {
        "type": "complete",
        "content": final_content,
        "tool_calls": final_tool_calls,
        "reasoning": final_reasoning,
        "elapsed_seconds": elapsed,
    }
