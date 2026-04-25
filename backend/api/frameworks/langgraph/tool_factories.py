"""
LangChain tool factories that wrap a ToolBackend.

Each function returns a list of ``@tool``-decorated callables that the
LangGraph agent can bind.  The *backend* parameter controls whether
execution goes through ``podman exec`` or direct filesystem I/O.

All tool functions include try/except blocks to catch exceptions and return
error strings instead of raising. This allows the LLM agent to see the error
and adapt its approach.
"""
from __future__ import annotations

from typing import List, Optional

from langchain_core.tools import tool as lc_tool

from .portable import ToolBackend


def get_coder_tools(backend: ToolBackend) -> list:
    """Tools for the Coder worker: file read/write/edit, directory listing, code search."""

    @lc_tool
    def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read the contents of a file in the workspace.

        Args:
            path: File path relative to /workspace.
            start_line: Optional 1-based start line.
            end_line: Optional 1-based end line.
        """
        try:
            return backend.read_file(path, start_line, end_line)
        except Exception as e:
            return f"Error reading file: {type(e).__name__}: {str(e)}"

    @lc_tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file in the workspace.

        Args:
            path: File path relative to /workspace.
            content: Full content to write.
        """
        try:
            return backend.write_file(path, content)
        except Exception as e:
            return f"Error writing file: {type(e).__name__}: {str(e)}"

    @lc_tool
    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """Replace the first occurrence of old_text with new_text in a file.

        Args:
            path: File path relative to /workspace.
            old_text: Exact text to find (include surrounding context for uniqueness).
            new_text: Replacement text.
        """
        try:
            return backend.edit_file(path, old_text, new_text)
        except Exception as e:
            return f"Error editing file: {type(e).__name__}: {str(e)}"

    @lc_tool
    def list_directory(path: str = ".", pattern: Optional[str] = None) -> str:
        """List files and directories in the workspace.

        Args:
            path: Directory path relative to /workspace. Use '.' for root.
            pattern: Optional glob pattern to filter results.
        """
        try:
            return backend.list_directory(path or ".", pattern)
        except Exception as e:
            return f"Error listing directory: {type(e).__name__}: {str(e)}"

    @lc_tool
    def search_code(query: str, path: str = ".", context_lines: int = 2) -> str:
        """Search for text across source files in the workspace.

        Args:
            query: Text or regex to search for.
            path: Directory to search in (relative to /workspace).
            context_lines: Number of surrounding lines to include.
        """
        try:
            return backend.search_code(query, path or ".", context_lines)
        except Exception as e:
            return f"Error searching code: {type(e).__name__}: {str(e)}"

    return [read_file, write_file, edit_file, list_directory, search_code]


def get_executor_tools(backend: ToolBackend) -> list:
    """Tools for the Executor worker: run shell commands."""

    @lc_tool
    def run_command(command: str, workdir: str = "/workspace") -> str:
        """Execute a shell command inside the workspace container.

        Args:
            command: Shell command to run (must be in the allowed list).
            workdir: Working directory (defaults to /workspace).
        """
        try:
            return backend.run_command(command, workdir)
        except Exception as e:
            return f"Error running command: {type(e).__name__}: {str(e)}"

    return [run_command]


def get_researcher_tools(backend: ToolBackend) -> list:
    """Tools for the Researcher worker: code search and documentation lookup."""

    @lc_tool
    def search_code(query: str, path: str = ".", context_lines: int = 3) -> str:
        """Search the codebase for a text pattern.

        Args:
            query: Text or regex to search for.
            path: Directory to search in (relative to /workspace).
            context_lines: Number of surrounding lines.
        """
        try:
            return backend.search_code(query, path or ".", context_lines)
        except Exception as e:
            return f"Error searching code: {type(e).__name__}: {str(e)}"

    @lc_tool
    def search_documentation(query: str) -> str:
        """Search project documentation for a topic.

        Args:
            query: Keyword or phrase to find in docs.
        """
        try:
            return backend.search_documentation(query)
        except Exception as e:
            return f"Error searching documentation: {type(e).__name__}: {str(e)}"

    @lc_tool
    def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read a file to understand code or documentation.

        Args:
            path: File path relative to /workspace.
            start_line: Optional 1-based start line.
            end_line: Optional 1-based end line.
        """
        try:
            return backend.read_file(path, start_line, end_line)
        except Exception as e:
            return f"Error reading file: {type(e).__name__}: {str(e)}"

    @lc_tool
    def list_directory(path: str = ".", pattern: Optional[str] = None) -> str:
        """List files and directories to discover project structure.

        Args:
            path: Directory path relative to /workspace. Use '.' for root.
            pattern: Optional glob pattern.
        """
        try:
            return backend.list_directory(path or ".", pattern)
        except Exception as e:
            return f"Error listing directory: {type(e).__name__}: {str(e)}"

    return [search_code, search_documentation, read_file, list_directory]


def get_reviewer_tools(backend: ToolBackend) -> list:
    """Tools for the Reviewer worker: read files, search code, run linters."""

    @lc_tool
    def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read file contents for code review.

        Args:
            path: File path relative to /workspace.
            start_line: Optional 1-based start line.
            end_line: Optional 1-based end line.
        """
        try:
            return backend.read_file(path, start_line, end_line)
        except Exception as e:
            return f"Error reading file: {type(e).__name__}: {str(e)}"

    @lc_tool
    def search_code(query: str, path: str = ".", context_lines: int = 3) -> str:
        """Search for patterns that may indicate issues.

        Args:
            query: Text or regex to search for.
            path: Directory to search in.
            context_lines: Surrounding context lines.
        """
        try:
            return backend.search_code(query, path or ".", context_lines)
        except Exception as e:
            return f"Error searching code: {type(e).__name__}: {str(e)}"

    @lc_tool
    def run_linter(command: str) -> str:
        """Run a linter or static analysis command.

        Args:
            command: Linter command (e.g., 'npm run lint', 'python -m flake8 .').
        """
        try:
            return backend.run_command(command)
        except Exception as e:
            return f"Error running linter: {type(e).__name__}: {str(e)}"

    @lc_tool
    def list_directory(path: str = ".", pattern: Optional[str] = None) -> str:
        """List files to locate targets for review.

        Args:
            path: Directory path relative to /workspace. Use '.' for root.
            pattern: Optional glob pattern.
        """
        try:
            return backend.list_directory(path or ".", pattern)
        except Exception as e:
            return f"Error listing directory: {type(e).__name__}: {str(e)}"

    return [read_file, search_code, run_linter, list_directory]


def get_all_workspace_tools(backend: ToolBackend) -> list:
    """Return the full, deduplicated set of workspace tools (used by simple ReAct agent)."""

    @lc_tool
    def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read the contents of a file in the workspace.

        Args:
            path: File path relative to /workspace.
            start_line: Optional 1-based start line.
            end_line: Optional 1-based end line.
        """
        try:
            return backend.read_file(path, start_line, end_line)
        except Exception as e:
            return f"Error reading file: {type(e).__name__}: {str(e)}"

    @lc_tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file in the workspace.

        Args:
            path: File path relative to /workspace.
            content: Full content to write.
        """
        try:
            return backend.write_file(path, content)
        except Exception as e:
            return f"Error writing file: {type(e).__name__}: {str(e)}"

    @lc_tool
    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """Replace the first occurrence of old_text with new_text in a file.

        Args:
            path: File path relative to /workspace.
            old_text: Exact text to find.
            new_text: Replacement text.
        """
        try:
            return backend.edit_file(path, old_text, new_text)
        except Exception as e:
            return f"Error editing file: {type(e).__name__}: {str(e)}"

    @lc_tool
    def list_directory(path: str = ".", pattern: Optional[str] = None) -> str:
        """List files and directories in the workspace.

        Args:
            path: Directory path relative to /workspace. Use '.' for root.
            pattern: Optional glob pattern.
        """
        try:
            return backend.list_directory(path or ".", pattern)
        except Exception as e:
            return f"Error listing directory: {type(e).__name__}: {str(e)}"

    @lc_tool
    def search_code(query: str, path: str = ".", context_lines: int = 2) -> str:
        """Search for text across source files in the workspace.

        Args:
            query: Text or regex to search for.
            path: Directory to search in.
            context_lines: Surrounding context lines.
        """
        try:
            return backend.search_code(query, path or ".", context_lines)
        except Exception as e:
            return f"Error searching code: {type(e).__name__}: {str(e)}"

    @lc_tool
    def run_command(command: str, workdir: str = "/workspace") -> str:
        """Execute a shell command inside the workspace container.

        Args:
            command: Shell command (must be in the allowed list).
            workdir: Working directory.
        """
        try:
            return backend.run_command(command, workdir)
        except Exception as e:
            return f"Error running command: {type(e).__name__}: {str(e)}"

    @lc_tool
    def search_documentation(query: str) -> str:
        """Search project documentation for a topic.

        Args:
            query: Keyword or phrase to find in docs.
        """
        try:
            return backend.search_documentation(query)
        except Exception as e:
            return f"Error searching documentation: {type(e).__name__}: {str(e)}"

    return [read_file, write_file, edit_file, list_directory, search_code, run_command, search_documentation]
