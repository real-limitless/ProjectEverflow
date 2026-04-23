"""
LangGraph framework for agentic chat.

New architecture (v2):
  - graph.create_agent_graph()  — single entry point for all modes
  - streaming.stream_agent_events()  — normalized event stream
  - state.AgentState / WorkerState  — shared typed state
  - model_factory.CustomChatModel  — LLM with proper tool binding
  - tool_factories.*  — per-role tool sets wrapping ToolBackend
  - workers/  — 5 specialized workers (coder, executor, researcher, tool_runner, reviewer)
  - orchestrator  — structured-output routing node
  - deep_agent  — deep reasoning mode with analyze→execute→reflect loop
  - portable/  — abstract ToolBackend (Podman vs native)

Legacy (deprecated — kept for backward compat):
  - agent.create_agent / run_agent_stream
  - adapter.CustomChatModel (old)
  - tools.get_workspace_tools
"""

# ── New API ──────────────────────────────────────────────────────────
from .graph import create_agent_graph
from .streaming import stream_agent_events
from .state import AgentState, WorkerState, RouteDecision
from .model_factory import CustomChatModel as NewCustomChatModel

# ── Legacy API (used by old LangGraphStreamConsumer) ─────────────────
try:
    from .agent import create_agent, run_agent_stream
    from .adapter import CustomChatModel
    from .tools import get_workspace_tools
except ImportError:
    # Legacy files may be removed in the future
    create_agent = None
    run_agent_stream = None
    CustomChatModel = NewCustomChatModel
    get_workspace_tools = None

__all__ = [
    # New
    "create_agent_graph",
    "stream_agent_events",
    "AgentState",
    "WorkerState",
    "RouteDecision",
    "NewCustomChatModel",
    # Legacy
    "create_agent",
    "run_agent_stream",
    "CustomChatModel",
    "get_workspace_tools",
]