"""
CustomChatModel adapter — bridges LangChain BaseChatModel to the platform's
multi-provider LLM system.

Key improvements over the legacy adapter.py:
  - ``bind_tools()`` properly stores tools and re-passes them on every call
  - ``_stream()`` yields real per-chunk ``AIMessageChunk`` objects
  - No ``bind_functions`` dependency (deprecated OpenAI API)
  - Thread-safe sync↔async bridging via a dedicated executor
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import re
import traceback
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from api.models import ChatSession, LLMProvider

logger = logging.getLogger(__name__)

# Dedicated executor to avoid deadlocks when LangGraph calls _generate
# from within an already-running event loop.
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm-adapter")


class CustomChatModel(BaseChatModel):
    """Wraps the platform's multi-provider LLM API as a LangChain BaseChatModel."""

    provider: LLMProvider
    session: ChatSession

    # --- internal bookkeeping (set via bind_tools) ---
    _bound_tools: list = []
    _bound_tool_schemas: list = []  # OpenAI-format tool schemas

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, provider: LLMProvider, session: ChatSession, **kwargs):
        super().__init__(provider=provider, session=session, **kwargs)
        self._bound_tools = kwargs.get("_bound_tools", [])
        self._bound_tool_schemas = kwargs.get("_bound_tool_schemas", [])

    @property
    def _llm_type(self) -> str:
        return "custom-provider"

    # ------------------------------------------------------------------
    # bind_tools  (the critical fix)
    # ------------------------------------------------------------------

    def bind_tools(self, tools: List[Any], **kwargs) -> "CustomChatModel":
        """Return a *copy* of this model with the given tools bound.

        The tool schemas are pre-computed once here and included in every
        subsequent ``_call_provider_api`` invocation so the LLM actually
        "sees" the tools and can emit ``tool_calls``.
        """
        schemas: List[dict] = []
        for t in tools:
            schema: dict = {}
            if hasattr(t, "name") and hasattr(t, "description"):
                # LangChain BaseTool / StructuredTool
                params = {}
                if hasattr(t, "args_schema") and t.args_schema is not None:
                    if hasattr(t.args_schema, "model_json_schema"):
                        params = t.args_schema.model_json_schema()
                    elif hasattr(t.args_schema, "schema"):
                        params = t.args_schema.schema()
                    elif isinstance(t.args_schema, dict):
                        params = t.args_schema
                schema = {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": params,
                    },
                }
            elif isinstance(t, dict):
                # Already in OpenAI schema form
                schema = t
            else:
                continue
            schemas.append(schema)

        new = CustomChatModel(
            provider=self.provider,
            session=self.session,
            _bound_tools=list(tools),
            _bound_tool_schemas=schemas,
        )
        return new

    # ------------------------------------------------------------------
    # _generate  (sync entry-point — bridges to async)
    # ------------------------------------------------------------------

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self._agenerate(messages, stop, run_manager, **kwargs)
                )
            finally:
                loop.close()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            future = _EXECUTOR.submit(_run)
            return future.result(timeout=120)
        else:
            return asyncio.run(
                self._agenerate(messages, stop, run_manager, **kwargs)
            )

    # ------------------------------------------------------------------
    # _agenerate  (async core)
    # ------------------------------------------------------------------

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            from api.views import ChatSessionViewSet

            viewset = ChatSessionViewSet()
            viewset.request = None

            # Convert LangChain messages → provider format
            system_prompt, formatted = self._format_messages(messages)

            # Merge bound tool schemas with any kwargs overrides
            tool_schemas = list(self._bound_tool_schemas)
            if "tools" in kwargs:
                tool_schemas.extend(kwargs.pop("tools"))

            # Call the platform provider API
            if self.provider.supports_function_calling and tool_schemas:
                response = await viewset._call_provider_api(
                    self.provider,
                    self.session,
                    formatted,
                    system_prompt or "",
                    tool_schemas,
                )
            else:
                # Fallback: inject tool descriptions into the user prompt
                enhanced = formatted
                if tool_schemas:
                    tool_desc = self._tool_desc_text(tool_schemas)
                    enhanced = f"{formatted}\n\n{tool_desc}"
                response = await viewset._call_provider_api(
                    self.provider,
                    self.session,
                    enhanced,
                    system_prompt or "",
                )

            return self._parse_response(response, tool_schemas)

        except Exception as exc:
            logger.error("CustomChatModel._agenerate error: %s\n%s", exc, traceback.format_exc())
            ai = AIMessage(content=f"Error calling LLM provider: {exc}")
            return ChatResult(generations=[ChatGeneration(message=ai)])

    # ------------------------------------------------------------------
    # _stream  (yields AIMessageChunk tokens)
    # ------------------------------------------------------------------

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Yield the response as a single chunk for now.

        TODO: hook into the provider's streaming endpoint for true
        per-token delivery.
        """
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        if result.generations:
            msg = result.generations[0].message
            chunk = AIMessageChunk(
                content=msg.content,
                tool_calls=getattr(msg, "tool_calls", []),
                tool_call_chunks=getattr(msg, "tool_call_chunks", []),
                response_metadata=getattr(msg, "response_metadata", {}),
                id=getattr(msg, "id", None),
            )
            yield ChatGenerationChunk(message=chunk)

    # ------------------------------------------------------------------
    # _astream  (async — used by LangGraph's astream_events)
    # ------------------------------------------------------------------

    async def _astream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Async stream — resolves to a single chunk wrapping the full response.

        Returning ``ChatGenerationChunk`` (not bare ``AIMessageChunk``)
        avoids the ``generation_info`` attribute error in LangChain's
        ``_agenerate_with_cache``.
        """
        result = await self._agenerate(messages, stop=stop, **kwargs)
        if result.generations:
            msg = result.generations[0].message
            chunk = AIMessageChunk(
                content=msg.content,
                tool_calls=getattr(msg, "tool_calls", []),
                tool_call_chunks=getattr(msg, "tool_call_chunks", []),
                response_metadata=getattr(msg, "response_metadata", {}),
                id=getattr(msg, "id", None),
            )
            gen_chunk = ChatGenerationChunk(message=chunk)
            if run_manager:
                await run_manager.on_llm_new_token(
                    chunk.content, chunk=gen_chunk
                )
            yield gen_chunk

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _format_messages(self, messages: List[BaseMessage]):
        """Return (system_prompt, formatted_conversation) from the message list.

        The platform API format is simple: one system string + one user
        string.  We concatenate **all** conversation history into the user
        string so the LLM retains context across ReAct loop turns.
        """
        system_prompt = None
        parts: List[str] = []

        for msg in messages:
            if msg.type == "system":
                system_prompt = msg.content
            elif msg.type == "human":
                parts.append(f"User: {msg.content}")
            elif msg.type == "ai":
                content = msg.content or ""
                # Include tool calls in the context so the LLM sees
                # what it previously requested
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    tc_text = json.dumps(msg.tool_calls, default=str)
                    content += f"\n[Tool calls: {tc_text}]"
                parts.append(f"Assistant: {content}")
            elif msg.type == "tool":
                tool_name = getattr(msg, "name", "tool")
                parts.append(f"Tool result ({tool_name}): {msg.content}")

        # Join the FULL conversation so the LLM sees the complete
        # history (original question, prior tool calls, tool results).
        user_text = "\n\n".join(parts) if parts else ""
        return system_prompt, user_text

    @staticmethod
    def _tool_desc_text(schemas: List[dict]) -> str:
        lines = ["Available tools (respond with JSON to call one):"]
        for s in schemas:
            fn = s.get("function", s)
            name = fn.get("name", "?")
            desc = fn.get("description", "")
            lines.append(f"- {name}: {desc}")
        lines.append(
            '\nTo call a tool reply with: {"tool": "<name>", "arguments": {...}}'
        )
        return "\n".join(lines)

    def _parse_response(self, response: Any, tool_schemas: list) -> ChatResult:
        """Normalize provider response into a ChatResult."""
        if response is None:
            ai = AIMessage(content="Error: no response from provider")
            return ChatResult(generations=[ChatGeneration(message=ai)])

        if isinstance(response, dict):
            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])
        else:
            content = str(response)
            tool_calls = []

        if not isinstance(content, str):
            content = str(content) if content else ""

        # Try to extract tool calls from text (fallback for non-function-call providers)
        if not tool_calls and tool_schemas:
            tool_calls, cleaned = self._extract_tool_calls_from_text(content)
            if tool_calls:
                # Remove raw JSON from the displayed content so the user
                # doesn't see the tool invocation syntax.
                content = cleaned.strip()

        ai = AIMessage(content=content, tool_calls=tool_calls)
        return ChatResult(generations=[ChatGeneration(message=ai)])

    @staticmethod
    def _extract_tool_calls_from_text(text: str):
        """Best-effort extraction of JSON tool calls from plain text.

        Returns (tool_calls_list, cleaned_text) where *cleaned_text* is
        the original text with matched JSON removed.
        """
        calls: list = []
        cleaned = text

        # --- Strategy 1: ```json fenced blocks ---
        fenced = re.finditer(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        for m in fenced:
            try:
                parsed = json.loads(m.group(1))
                if isinstance(parsed, dict) and ("tool" in parsed or "name" in parsed):
                    name = parsed.get("tool") or parsed.get("name", "")
                    args = parsed.get("arguments") or parsed.get("args", {})
                    calls.append({
                        "id": f"call_{len(calls)}",
                        "type": "tool_call",
                        "name": name,
                        "args": args if isinstance(args, dict) else {},
                    })
                    cleaned = cleaned.replace(m.group(0), "")
            except (json.JSONDecodeError, KeyError):
                continue
        if calls:
            return calls, cleaned

        # --- Strategy 2: balanced-brace scan for {"tool": ...} ---
        idx = 0
        spans_to_remove: list = []
        while idx < len(text):
            # Find next candidate start
            start = text.find('{', idx)
            if start == -1:
                break
            # Walk forward counting braces to find the matching close
            depth = 0
            end = start
            for i in range(start, len(text)):
                ch = text[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if depth != 0:
                idx = start + 1
                continue
            candidate = text[start:end]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and ("tool" in parsed or "name" in parsed):
                    name = parsed.get("tool") or parsed.get("name", "")
                    args = parsed.get("arguments") or parsed.get("args", {})
                    calls.append({
                        "id": f"call_{len(calls)}",
                        "type": "tool_call",
                        "name": name,
                        "args": args if isinstance(args, dict) else {},
                    })
                    spans_to_remove.append((start, end))
            except (json.JSONDecodeError, KeyError):
                pass
            idx = end if end > start else start + 1

        # Remove matched spans (reverse order to preserve indices)
        for s, e in reversed(spans_to_remove):
            cleaned = cleaned[:s] + cleaned[e:]

        return calls, cleaned
