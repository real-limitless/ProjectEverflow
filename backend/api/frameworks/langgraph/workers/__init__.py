"""Worker registry and shared utilities."""
from .coder import create_coder_worker
from .executor import create_executor_worker
from .researcher import create_researcher_worker
from .tool_runner import create_tool_runner_worker
from .reviewer import create_reviewer_worker

WORKER_REGISTRY = {
    "coder": create_coder_worker,
    "executor": create_executor_worker,
    "researcher": create_researcher_worker,
    "tool_runner": create_tool_runner_worker,
    "reviewer": create_reviewer_worker,
}

__all__ = [
    "WORKER_REGISTRY",
    "create_coder_worker",
    "create_executor_worker",
    "create_researcher_worker",
    "create_tool_runner_worker",
    "create_reviewer_worker",
]
