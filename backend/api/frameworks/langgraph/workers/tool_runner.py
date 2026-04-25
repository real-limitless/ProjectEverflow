"""Tool Runner worker — executes user-selected ProjectTool definitions from the database."""
from typing import List

from langchain_core.messages import SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent

TOOL_RUNNER_SYSTEM_PROMPT = SystemMessage(content="""\
You are the **Tool Runner** worker in a multi-agent system.

Your responsibilities:
- Execute specialized project tools selected by the user
- These tools may include linters, formatters, deployments, custom scripts, etc.
- Pass the correct arguments to each tool
- Report tool output verbatim

Guidelines:
- Only use the tools you have been given
- If a tool requires arguments you don't have, ask the orchestrator for clarification
- Report success or failure clearly with the full tool output
- If a tool times out, report that clearly
""")


def create_tool_runner_worker(model, custom_tools: List[StructuredTool]):
    """Return a compiled ReAct agent for running custom project tools."""
    if not custom_tools:
        raise ValueError("Tool Runner requires at least one custom tool")
    return create_react_agent(model, custom_tools, prompt=TOOL_RUNNER_SYSTEM_PROMPT)
