"""
Deep agent mode — extended reasoning with iterative task decomposition.

Uses a LangGraph StateGraph that implements a "deep thinking" loop:
  1. Analyze: break the task into a TODO list
  2. Plan: create a step-by-step execution plan
  3. Execute: run each step through specialized workers
  4. Reflect: evaluate outcomes, update plan, iterate if needed
  5. Synthesize: produce final comprehensive response

This provides the same UX as ``deepagents`` without the external
dependency — uses standard LangGraph nodes + our existing workers.
"""
from __future__ import annotations

import logging
import operator
from typing import Annotated, Any, Dict, List, Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from .state import AgentState, TodoItem
from .model_factory import CustomChatModel
from .tool_factories import get_all_workspace_tools
from .portable import ToolBackend

logger = logging.getLogger(__name__)


# ── Deep Agent State ────────────────────────────────────────────────

class DeepAgentState(AgentState):
    """Extended state for deep reasoning."""
    todos: Annotated[list, operator.add]  # TodoItem dicts
    current_step: int
    total_steps: int
    reflection: str
    synthesis: str
    depth: int  # How many analyse→execute→reflect cycles
    max_depth: int


# ── Structured outputs for planning ────────────────────────────────

class TaskDecomposition(BaseModel):
    """Structured output: task analysis and TODO list."""
    understanding: str = Field(description="Brief understanding of the task")
    todos: List[TodoItem] = Field(description="Ordered list of action items")
    approach: str = Field(description="High-level approach description")


class StepPlan(BaseModel):
    """Structured output: how to execute the current TODO item."""
    step_description: str = Field(description="What this step accomplishes")
    tools_needed: List[str] = Field(description="Tool names needed for this step")
    expected_outcome: str = Field(description="What success looks like")


class ReflectionResult(BaseModel):
    """Structured output: reflection on progress."""
    progress_assessment: str = Field(description="How well we are doing")
    issues_found: List[str] = Field(description="Any problems identified")
    should_continue: bool = Field(description="Whether to continue iterating")
    adjustments: str = Field(description="Any plan adjustments needed")


# ── Node functions ──────────────────────────────────────────────────

ANALYZE_PROMPT = SystemMessage(content="""You are a deep-analysis AI assistant. Your job is to thoroughly understand the user's request and break it into concrete, actionable TODO items.

Analyze the request carefully:
1. Identify the core objective
2. Break it into ordered steps (each should be independently verifiable)
3. Consider edge cases and prerequisites
4. Describe your high-level approach

Be thorough but practical — each TODO item should be achievable with workspace tools (file read/write, code search, command execution).""")


EXECUTE_PROMPT = SystemMessage(content="""You are a focused executor. You are given one specific step to complete from a larger plan.

Follow the step plan exactly. Use the workspace tools available to you.
Report what you did and whether it succeeded.
If you encounter errors, try to fix them before reporting failure.""")


REFLECT_PROMPT = SystemMessage(content="""You are a reflective reviewer. Analyze the results of the executed steps so far.

Consider:
1. Were the steps completed successfully?
2. Are there any issues, bugs, or inconsistencies?
3. Does the plan need adjustment?
4. Should we continue with more iterations or is the task complete?

Be critical but constructive. If the task is essentially complete, set should_continue=false.""")


SYNTHESIZE_PROMPT = SystemMessage(content="""You are a synthesis expert. Create a comprehensive final response for the user summarizing:

1. What was requested
2. What was accomplished (with specifics — files changed, commands run, etc.)
3. Any open items or recommendations
4. Key decisions made and why

Be concise but complete.""")


def build_analyze_node(model: CustomChatModel):
    """Create the analysis/decomposition node."""

    async def analyze(state: DeepAgentState) -> Dict[str, Any]:
        messages = [ANALYZE_PROMPT] + state["messages"]

        try:
            structured_model = model.with_structured_output(TaskDecomposition)
            result = await structured_model.ainvoke(messages)
            todos = [t.model_dump() for t in result.todos]
        except Exception:
            # Fallback: ask for plain text analysis
            response = await model.ainvoke(messages)
            todos = [{"title": "Execute the requested task", "status": "not-started", "priority": 1}]
            result = type("R", (), {
                "understanding": response.content[:500],
                "todos": [],
                "approach": "Direct execution",
            })()

        plan_msg = AIMessage(content=f"**Analysis:**\n{result.understanding}\n\n**Approach:** {result.approach}")

        return {
            "messages": [plan_msg],
            "todos": todos,
            "plan": [t.get("title", str(t)) for t in todos],
            "total_steps": len(todos),
            "current_step": 0,
        }

    return analyze


def build_execute_node(model: CustomChatModel, tools: list):
    """Create the step execution node with tools."""
    from langchain_core.messages import HumanMessage as HM
    from langgraph.prebuilt import create_react_agent

    executor = create_react_agent(model, tools)

    async def execute(state: DeepAgentState) -> Dict[str, Any]:
        step_idx = state.get("current_step", 0)
        todos = state.get("todos", [])

        if step_idx >= len(todos):
            return {"messages": [AIMessage(content="All steps completed.")], "current_step": step_idx}

        current_todo = todos[step_idx]
        title = current_todo.get("title", str(current_todo))

        # Mark current as in-progress
        updated_todos = list(todos)
        if isinstance(updated_todos[step_idx], dict):
            updated_todos[step_idx] = {**updated_todos[step_idx], "status": "in-progress"}

        step_msg = HM(content=f"Execute this step: {title}\n\nContext from previous steps:\n" +
                       "\n".join(o[:200] for o in state.get("worker_outputs", [])[-3:]))

        config = {"recursion_limit": 30}
        result = await executor.ainvoke(
            {"messages": state["messages"] + [EXECUTE_PROMPT, step_msg]},
            config=config,
        )

        # Mark completed
        if isinstance(updated_todos[step_idx], dict):
            updated_todos[step_idx] = {**updated_todos[step_idx], "status": "completed"}

        last_msg = result["messages"][-1] if result.get("messages") else AIMessage(content="Step done.")
        step_output = getattr(last_msg, "content", str(last_msg))

        return {
            "messages": [AIMessage(content=f"**Step {step_idx + 1}/{len(todos)}:** {title}\n\n{step_output}")],
            "worker_outputs": [f"Step {step_idx + 1} ({title}): {step_output[:500]}"],
            "current_step": step_idx + 1,
            "todos": [],  # Will be merged via operator.add — we send empty to avoid duplication
        }

    return execute


def build_reflect_node(model: CustomChatModel):
    """Create the reflection/evaluation node."""

    async def reflect(state: DeepAgentState) -> Dict[str, Any]:
        outputs = state.get("worker_outputs", [])
        outputs_text = "\n---\n".join(outputs[-10:])

        reflect_msg = HumanMessage(
            content=f"Reflect on the progress so far:\n\n{outputs_text}\n\n"
                    f"Steps completed: {state.get('current_step', 0)}/{state.get('total_steps', 0)}\n"
                    f"Iteration depth: {state.get('depth', 0)}/{state.get('max_depth', 3)}"
        )

        try:
            structured_model = model.with_structured_output(ReflectionResult)
            result = await structured_model.ainvoke([REFLECT_PROMPT, reflect_msg])
            should_continue = result.should_continue and state.get("depth", 0) < state.get("max_depth", 3)
            reflection_text = f"{result.progress_assessment}\nIssues: {', '.join(result.issues_found) if result.issues_found else 'None'}"
        except Exception:
            response = await model.ainvoke([REFLECT_PROMPT, reflect_msg])
            should_continue = state.get("current_step", 0) < state.get("total_steps", 0)
            reflection_text = response.content

        return {
            "messages": [AIMessage(content=f"**Reflection:**\n{reflection_text}")],
            "reflection": reflection_text,
            "depth": state.get("depth", 0) + 1,
            "next": "execute" if should_continue else "synthesize",
        }

    return reflect


def build_synthesize_node(model: CustomChatModel):
    """Create the final synthesis node."""

    async def synthesize(state: DeepAgentState) -> Dict[str, Any]:
        outputs = state.get("worker_outputs", [])
        outputs_text = "\n---\n".join(outputs[-15:])
        reflection = state.get("reflection", "")

        synth_msg = HumanMessage(
            content=f"Create a final comprehensive response.\n\n"
                    f"Work completed:\n{outputs_text}\n\n"
                    f"Reflection:\n{reflection}"
        )

        response = await model.ainvoke(state["messages"] + [SYNTHESIZE_PROMPT, synth_msg])

        return {
            "messages": [response],
            "synthesis": response.content,
        }

    return synthesize


# ── Routing logic ───────────────────────────────────────────────────

def route_after_reflect(state: DeepAgentState) -> Literal["execute", "synthesize"]:
    """Decide whether to continue executing or synthesize."""
    return state.get("next", "synthesize")


def route_after_execute(state: DeepAgentState) -> Literal["reflect", "execute"]:
    """After executing a step, either continue or reflect."""
    step = state.get("current_step", 0)
    total = state.get("total_steps", 0)
    # Reflect every 3 steps or when done
    if step >= total or step % 3 == 0:
        return "reflect"
    return "execute"


# ── Graph builder ───────────────────────────────────────────────────

def create_deep_agent_graph(
    model: CustomChatModel,
    backend: ToolBackend,
    *,
    system_prompt: str = "",
    max_depth: int = 3,
):
    """Build the deep agent StateGraph.

    Returns a compiled graph ready for ``.astream_events()``.
    """
    tools = get_all_workspace_tools(backend)

    # Build nodes
    analyze = build_analyze_node(model)
    execute = build_execute_node(model, tools)
    reflect = build_reflect_node(model)
    synthesize = build_synthesize_node(model)

    # Build graph
    workflow = StateGraph(DeepAgentState)

    workflow.add_node("analyze", analyze)
    workflow.add_node("execute", execute)
    workflow.add_node("reflect", reflect)
    workflow.add_node("synthesize", synthesize)

    # Entry
    workflow.set_entry_point("analyze")

    # Edges
    workflow.add_edge("analyze", "execute")
    workflow.add_conditional_edges("execute", route_after_execute)
    workflow.add_conditional_edges("reflect", route_after_reflect)
    workflow.add_edge("synthesize", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
