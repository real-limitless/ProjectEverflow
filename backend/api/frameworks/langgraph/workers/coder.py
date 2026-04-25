"""Coder worker — reads, writes, edits files and searches code."""
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from ..portable import ToolBackend
from ..tool_factories import get_coder_tools

CODER_SYSTEM_PROMPT = SystemMessage(content="""\
You are the **Coder** worker in a multi-agent system.

Your responsibilities:
- Read existing files to understand the codebase
- Write new files or overwrite existing ones
- Edit files by replacing specific text sections
- Search code for patterns and references
- List directory contents to navigate the project

Guidelines:
- Always read a file before editing to understand its current state
- When editing, include enough surrounding context in old_text to make the match unique
- Prefer edit_file over write_file when only small changes are needed
- Report what you changed clearly so the orchestrator can verify
- If a task is ambiguous, read the relevant files first to gather context
""")


def create_coder_worker(model, backend: ToolBackend):
    """Return a compiled ReAct agent for coding tasks."""
    tools = get_coder_tools(backend)
    return create_react_agent(model, tools, prompt=CODER_SYSTEM_PROMPT)
