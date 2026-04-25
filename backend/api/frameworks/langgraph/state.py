"""
Shared agent state definitions for the LangGraph agent system.

All graph nodes (orchestrator, workers, simple ReAct agents) share this state.
"""
import operator
from typing import Any, Dict, List, Literal, Optional, Sequence, TypedDict, Annotated

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic schemas used by the orchestrator for structured routing
# ---------------------------------------------------------------------------

class TodoItem(BaseModel):
    """A single agent task/todo item."""
    description: str = Field(description="What needs to be done")
    status: Literal["pending", "in_progress", "completed", "failed"] = Field(
        default="pending", description="Current status"
    )
    worker: Optional[str] = Field(
        default=None,
        description="Which worker should handle this (coder, executor, researcher, tool_runner, reviewer)",
    )
    details: Optional[str] = Field(default=None, description="Additional details or output")


class RouteDecision(BaseModel):
    """Structured output for the orchestrator to decide next step."""
    next: Literal[
        "coder", "executor", "researcher", "tool_runner", "reviewer", "FINISH"
    ] = Field(description="The worker to delegate to, or FINISH if done")
    reasoning: str = Field(description="Brief explanation of why this worker was chosen")
    task_description: str = Field(
        default="",
        description="Specific instruction for the chosen worker",
    )


# ---------------------------------------------------------------------------
# Graph state types
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """Main graph state shared between orchestrator and workers."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    plan: list  # List[TodoItem] as dicts
    next: str  # Next node to route to
    worker_outputs: Annotated[list, operator.add]  # Collects worker results
    context_files: list  # [{path, content}] from the UI
    mode: str  # ask, plan, agent, persona, deep
    iteration: int  # Current loop iteration
    max_iterations: int  # Safety limit


class WorkerState(TypedDict):
    """State for individual worker subgraphs (used with Send API)."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    task: str  # The specific task assigned by orchestrator
    worker_outputs: Annotated[list, operator.add]
