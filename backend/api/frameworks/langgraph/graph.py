"""
Main entry point for creating LangGraph agent graphs.

``create_agent_graph()`` is the single factory that the consumer calls.
It builds the appropriate graph topology based on chat mode:

  - **ask / plan / persona** → Simple ReAct agent with all tools
  - **agent**               → Orchestrator-worker graph with 5 specialists
  - **deep**                → LangChain Deep Agent with subagents (delegated to deep_agent.py)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from api.models import ChatSession, ProjectTool

from .adapters import get_project_tools_definitions
from .model_factory import CustomChatModel
from .orchestrator import build_orchestrator_node
from .portable import PodmanToolBackend, ToolBackend
from .state import AgentState
from .tool_factories import get_all_workspace_tools
from .workers import (
    WORKER_REGISTRY,
    create_coder_worker,
    create_executor_worker,
    create_researcher_worker,
    create_reviewer_worker,
    create_tool_runner_worker,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompts per mode
# ---------------------------------------------------------------------------

MODE_PROMPTS: Dict[str, str] = {
    "ask": (
        "You are a helpful AI assistant for the project '{project_name}'. "
        "Answer questions directly and concisely. You have access to workspace "
        "tools to read files, run commands, and search code when needed."
    ),
    "plan": (
        "You are a planning assistant for the project '{project_name}'. "
        "When given a task, break it down into clear, numbered steps. "
        "Use workspace tools to gather context before planning. "
        "Provide actionable steps with file paths and specific changes."
    ),
    "persona": (
        "You are an AI assistant adopting a specific persona. "
        "The persona instructions will be in the conversation context. "
        "You have access to workspace tools. Stay in character while being helpful."
    ),
    "agent": (
        "You are an autonomous coding agent for the project '{project_name}'. "
        "You have a team of specialist workers to delegate tasks to. "
        "Break complex requests into steps, delegate to the right worker, "
        "and synthesize results into a comprehensive response."
    ),
    "deep": (
        "You are a deep agent for the project '{project_name}'. "
        "You can plan, write todos, spawn subagents, and manage files. "
        "Use the built-in planning tools to decompose complex tasks."
    ),
}


# ---------------------------------------------------------------------------
# Helper: resolve LLM and container
# ---------------------------------------------------------------------------

def _resolve_llm_and_container(session: ChatSession, container_name: str):
    """Return (CustomChatModel, actual_container_name)."""
    from api.views import ChatSessionViewSet

    viewset = ChatSessionViewSet()
    provider = viewset._resolve_provider_hierarchy(session)
    if not provider:
        raise ValueError("No LLM provider available for this session")

    # Try to resolve actual container name from the project
    actual_container = container_name
    try:
        from api.podman_manager import PodmanManager
        manager = PodmanManager(session.project)
        found = manager._get_workspace_container_name()
        if found:
            actual_container = found
    except Exception:
        pass

    llm = CustomChatModel(provider, session)
    return llm, actual_container


def _get_enabled_tool_ids(session: ChatSession) -> List[int]:
    """Read enabled tool IDs from the session M2M field."""
    try:
        return list(session.enabled_tools.values_list("id", flat=True))
    except Exception:
        return []


def _build_system_prompt(session: ChatSession, mode: str) -> str:
    """Build the system prompt including persona context."""
    base = MODE_PROMPTS.get(mode, MODE_PROMPTS["ask"]).format(
        project_name=session.project.name if session.project else "Unknown",
    )

    # Append persona instructions if set
    if session.persona and hasattr(session.persona, "system_prompt"):
        base += f"\n\nPersona instructions:\n{session.persona.system_prompt}"

    return base


# ---------------------------------------------------------------------------
# Simple ReAct graph (ask / plan / persona modes)
# ---------------------------------------------------------------------------

def _build_simple_graph(
    llm: CustomChatModel,
    backend: ToolBackend,
    custom_tools: list,
    system_prompt: str,
):
    """Build a simple ReAct agent with ALL workspace + custom tools."""
    tools = get_all_workspace_tools(backend) + custom_tools
    system_msg = SystemMessage(content=system_prompt)
    agent = create_react_agent(llm, tools, prompt=system_msg)
    return agent


# ---------------------------------------------------------------------------
# Orchestrator-Worker graph (agent mode)
# ---------------------------------------------------------------------------

def _build_orchestrator_graph(
    llm: CustomChatModel,
    backend: ToolBackend,
    custom_tools: list,
    system_prompt: str,
):
    """Build the full orchestrator → worker graph."""

    # Determine which workers are active
    active_workers = ["coder", "executor", "researcher", "reviewer"]
    if custom_tools:
        active_workers.append("tool_runner")

    # Build the orchestrator node
    orchestrator_node = build_orchestrator_node(llm, active_workers)

    # Build worker sub-agents
    worker_agents = {
        "coder": create_coder_worker(llm, backend),
        "executor": create_executor_worker(llm, backend),
        "researcher": create_researcher_worker(llm, backend),
        "reviewer": create_reviewer_worker(llm, backend),
    }
    if custom_tools:
        worker_agents["tool_runner"] = create_tool_runner_worker(llm, custom_tools)

    # Wrap each worker in an async node function
    async def _make_worker_node(worker_name):
        agent = worker_agents[worker_name]

        async def node_fn(state: AgentState):
            try:
                result = await agent.ainvoke({"messages": state["messages"]})
                last_msg = result["messages"][-1] if result.get("messages") else AIMessage(content="No output")
                return {
                    "messages": [last_msg],
                    "worker_outputs": [{"worker": worker_name, "content": last_msg.content}],
                }
            except Exception as e:
                logger.error("Worker '%s' failed: %s", worker_name, e)
                error_msg = AIMessage(content=f"[{worker_name} error]: {e}")
                return {
                    "messages": [error_msg],
                    "worker_outputs": [{"worker": worker_name, "content": f"Error: {e}"}],
                }

        return node_fn

    # Build the state graph
    workflow = StateGraph(AgentState)

    # Add orchestrator
    workflow.add_node("orchestrator", orchestrator_node)

    # Add each worker node
    import asyncio
    for name in active_workers:
        # We need to create the node function in a closure
        async def make_node(worker_name=name):
            agent = worker_agents[worker_name]

            async def node_fn(state: AgentState):
                try:
                    result = await agent.ainvoke({"messages": state["messages"]})
                    last_msg = result["messages"][-1] if result.get("messages") else AIMessage(content="No output")
                    return {
                        "messages": [last_msg],
                        "worker_outputs": [{"worker": worker_name, "content": last_msg.content}],
                    }
                except Exception as e:
                    logger.error("Worker '%s' failed: %s", worker_name, e)
                    error_msg = AIMessage(content=f"[{worker_name} error]: {e}")
                    return {
                        "messages": [error_msg],
                        "worker_outputs": [{"worker": worker_name, "content": f"Error: {e}"}],
                    }

            return node_fn

        # Build synchronously since we're just constructing the graph
        def _worker_node_sync(state, _name=name, _agent=worker_agents[name]):
            """Sync wrapper that creates the async call."""
            import asyncio

            async def _run():
                try:
                    result = await _agent.ainvoke({"messages": state["messages"]})
                    last_msg = result["messages"][-1] if result.get("messages") else AIMessage(content="No output")
                    return {
                        "messages": [last_msg],
                        "worker_outputs": [{"worker": _name, "content": last_msg.content}],
                    }
                except Exception as e:
                    logger.error("Worker '%s' failed: %s", _name, e)
                    error_msg = AIMessage(content=f"[{_name} error]: {e}")
                    return {
                        "messages": [error_msg],
                        "worker_outputs": [{"worker": _name, "content": f"Error: {e}"}],
                    }

            return _run()

        # Actually register as async nodes
        _agent = worker_agents[name]

        async def _worker_async(state, _wname=name, _wagent=_agent):
            try:
                result = await _wagent.ainvoke({"messages": state["messages"]})
                last_msg = result["messages"][-1] if result.get("messages") else AIMessage(content="No output")
                return {
                    "messages": [last_msg],
                    "worker_outputs": [{"worker": _wname, "content": last_msg.content}],
                }
            except Exception as e:
                logger.error("Worker '%s' failed: %s", _wname, e)
                error_msg = AIMessage(content=f"[{_wname} error]: {e}")
                return {
                    "messages": [error_msg],
                    "worker_outputs": [{"worker": _wname, "content": f"Error: {e}"}],
                }

        workflow.add_node(name, _worker_async)

    # Edges: START → orchestrator
    workflow.add_edge(START, "orchestrator")

    # Conditional edges from orchestrator → workers or END
    route_map = {w: w for w in active_workers}
    route_map["FINISH"] = END

    workflow.add_conditional_edges(
        "orchestrator",
        lambda state: state.get("next", "FINISH"),
        route_map,
    )

    # All workers route back to orchestrator
    for name in active_workers:
        workflow.add_edge(name, "orchestrator")

    # Compile with checkpointer
    memory = InMemorySaver()
    return workflow.compile(checkpointer=memory)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_agent_graph(
    session: ChatSession,
    container_name: str,
    mode: Optional[str] = None,
) -> Any:
    """Create and return a compiled LangGraph agent for the given session.

    Parameters
    ----------
    session : ChatSession
        The Django chat session (carries project, persona, enabled_tools, etc.)
    container_name : str
        Default workspace container name (may be auto-resolved)
    mode : str | None
        Override the session mode. If None, uses ``session.mode``.

    Returns
    -------
    A compiled LangGraph graph ready for ``.astream()`` / ``.astream_events()``.
    """
    mode = mode or session.mode or "ask"
    logger.info("Creating agent graph: mode=%s session=%s", mode, session.id)

    # 1. Resolve LLM and container
    llm, actual_container = _resolve_llm_and_container(session, container_name)

    # 2. Create tool backend
    backend = PodmanToolBackend(actual_container)

    # 3. Get custom project tools
    enabled_ids = _get_enabled_tool_ids(session)
    custom_tools = []
    if session.project and enabled_ids:
        custom_tools = get_project_tools_definitions(session.project, enabled_ids)

    # 4. Build system prompt
    system_prompt = _build_system_prompt(session, mode)

    # 5. Build the appropriate graph
    if mode == "deep":
        # Deep agent mode — defer to dedicated module
        try:
            from .deep_agent import create_deep_agent_graph
            return create_deep_agent_graph(
                llm=llm,
                backend=backend,
                custom_tools=custom_tools,
                system_prompt=system_prompt,
                session=session,
                container_name=actual_container,
            )
        except ImportError:
            logger.warning("deepagents not installed, falling back to orchestrator mode")
            return _build_orchestrator_graph(llm, backend, custom_tools, system_prompt)

    elif mode == "agent":
        return _build_orchestrator_graph(llm, backend, custom_tools, system_prompt)

    else:
        # ask, plan, persona → simple ReAct
        return _build_simple_graph(llm, backend, custom_tools, system_prompt)
