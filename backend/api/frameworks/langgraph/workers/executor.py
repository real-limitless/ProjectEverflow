"""Executor worker — runs shell commands, manages processes."""
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from ..portable import ToolBackend
from ..tool_factories import get_executor_tools

EXECUTOR_SYSTEM_PROMPT = SystemMessage(content="""\
You are the **Executor** worker in a multi-agent system.

Your responsibilities:
- Run shell commands in the workspace container
- Install dependencies (npm install, pip install, etc.)
- Run build commands (npm run build, make, cargo build)
- Execute test suites
- Run deployment or setup scripts

Guidelines:
- Always cd to /workspace before running project commands
- Check command exit codes and report failures clearly
- For long-running processes, set reasonable expectations
- Never run destructive commands (rm -rf /, etc.)
- Report both stdout and stderr
- If a command fails, suggest potential fixes
""")


def create_executor_worker(model, backend: ToolBackend):
    """Return a compiled ReAct agent for command execution tasks."""
    tools = get_executor_tools(backend)
    return create_react_agent(model, tools, prompt=EXECUTOR_SYSTEM_PROMPT)
