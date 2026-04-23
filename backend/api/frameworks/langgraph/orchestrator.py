"""
Orchestrator node for the agent-mode graph.

Uses ``with_structured_output(RouteDecision)`` to pick the next worker.
Replaces the legacy supervisor.py that relied on deprecated
``bind_functions`` + ``JsonOutputFunctionsParser``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .state import AgentState, RouteDecision, TodoItem

logger = logging.getLogger(__name__)

# Which workers are available (always all five; the graph conditionally
# includes only those that have tools).
ALL_WORKERS = ["coder", "executor", "researcher", "tool_runner", "reviewer"]

ORCHESTRATOR_SYSTEM = """\
You are an **Orchestrator** managing a team of specialist workers.

Available workers:
{workers_desc}

Your job:
1. Understand the user's request from the conversation.
2. Break it into discrete steps if needed.
3. For each step, choose the most appropriate worker.
4. When ALL steps are done and the user's request is fully addressed, choose FINISH.

Guidelines:
- If the user asks to read/write/edit code → **coder**
- If the user asks to run commands, install deps, build → **executor**
- If the user asks to find information, search code, explore project → **researcher**
- If the user asks to use a specific tool/plugin → **tool_runner**
- If the user asks for a code review or quality check → **reviewer**
- If the request involves multiple steps, tackle them one at a time — pick the first worker needed.
- If a worker's output already answers the question, choose **FINISH**.
- ALWAYS choose FINISH when there's nothing left to do.

Current plan/todos (update as needed):
{plan}
"""

WORKER_DESCRIPTIONS = {
    "coder": "Coder — reads, writes, edits files; searches code",
    "executor": "Executor — runs shell commands, installs deps, builds, tests",
    "researcher": "Researcher — searches codebase & docs, gathers context",
    "tool_runner": "Tool Runner — executes custom project tools selected by the user",
    "reviewer": "Reviewer — code review, linting, compliance checks",
}


def build_orchestrator_node(model, active_workers: List[str]):
    """Return an async callable suitable as a LangGraph node.

    *active_workers* is the subset of ALL_WORKERS that actually have tools
    bound (e.g. tool_runner is only active when the user selected custom tools).
    """

    workers_desc = "\n".join(
        f"- **{w}**: {WORKER_DESCRIPTIONS.get(w, w)}"
        for w in active_workers
    )

    # Build the structured LLM — this uses the provider's native
    # structured-output / tool-calling support when available, falling
    # back to JSON-mode parsing.
    structured_llm = model.with_structured_output(RouteDecision)

    async def orchestrator(state: AgentState) -> Dict[str, Any]:
        plan_text = "No plan yet."
        if state.get("plan"):
            plan_lines = []
            for i, item in enumerate(state["plan"], 1):
                status = item.get("status", "pending") if isinstance(item, dict) else getattr(item, "status", "pending")
                desc = item.get("description", "?") if isinstance(item, dict) else getattr(item, "description", "?")
                plan_lines.append(f"  {i}. [{status}] {desc}")
            plan_text = "\n".join(plan_lines)

        system_content = ORCHESTRATOR_SYSTEM.format(
            workers_desc=workers_desc,
            plan=plan_text,
        )

        # Build prompt with full conversation context
        prompt_messages = [SystemMessage(content=system_content)] + list(state["messages"])

        try:
            decision: RouteDecision = await structured_llm.ainvoke(prompt_messages)
        except Exception as e:
            logger.warning("Orchestrator structured output failed, defaulting to FINISH: %s", e)
            decision = RouteDecision(
                next="FINISH",
                reasoning=f"Defaulting to FINISH due to error: {e}",
                task_description="",
            )

        logger.info(
            "Orchestrator decision: next=%s reasoning=%s",
            decision.next,
            decision.reasoning[:80],
        )

        # If the selected worker isn't active, fall back to FINISH
        if decision.next != "FINISH" and decision.next not in active_workers:
            logger.warning(
                "Orchestrator chose unavailable worker '%s', falling back to FINISH",
                decision.next,
            )
            decision = RouteDecision(
                next="FINISH",
                reasoning=f"Worker '{decision.next}' not available, finishing.",
                task_description="",
            )

        # Increment iteration counter
        iteration = state.get("iteration", 0) + 1
        max_iter = state.get("max_iterations", 25)
        if iteration >= max_iter and decision.next != "FINISH":
            logger.warning("Max iterations (%d) reached, forcing FINISH", max_iter)
            decision = RouteDecision(
                next="FINISH",
                reasoning=f"Reached max iterations ({max_iter}), finishing.",
                task_description="",
            )

        return {
            "next": decision.next,
            "iteration": iteration,
            # If we have a task description, we'll inject it as a human message
            # so the worker knows what to do.
            "messages": (
                [HumanMessage(content=f"[Orchestrator → {decision.next}]: {decision.task_description}")]
                if decision.next != "FINISH" and decision.task_description
                else []
            ),
        }

    return orchestrator
