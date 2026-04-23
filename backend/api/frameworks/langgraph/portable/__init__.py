"""
Tool backend abstraction for portable agent tools.

This module defines an abstract base for workspace tool execution, enabling the
same LangGraph graph to run:
  - Server-side via ``PodmanToolBackend`` (podman exec into containers)
  - Container-native via ``NativeToolBackend`` (direct filesystem I/O)

Each backend implements the same primitives: read_file, write_file, edit_file,
list_directory, search_code, run_command, search_documentation.
"""
from __future__ import annotations

import abc
import os
import re
import subprocess
from typing import List, Optional

# ---------------------------------------------------------------------------
# Security helpers (shared across backends)
# ---------------------------------------------------------------------------

BLOCKED_PATTERNS = [
    r'rm\s+-rf\s+/',
    r'sudo',
    r'curl.*\|.*sh',
    r'wget.*\|',
    r'nc\s+-',
    r'ssh\s+',
    r'chmod\s+777',
    r'>\s*/etc/',
    r'dd\s+if=',
]

MAX_OUTPUT_BYTES = 30_720  # 30 KB


def validate_path(path: str, base: str = "/workspace") -> str:
    """Resolve *path* relative to *base* and ensure it doesn't escape."""
    if not path or path.strip() == "":
        path = "."  # Default to current directory
    resolved = os.path.abspath(os.path.join(base, path.lstrip("/")))
    if not resolved.startswith(os.path.abspath(base)):
        raise ValueError(f"Path '{path}' escapes allowed directory '{base}'")
    return resolved


def validate_command(cmd: str, allowed_commands: Optional[List[str]] = None) -> bool:
    """Return True when *cmd* passes the allow-list / block-list checks."""
    default_allowed = [
        "npm", "yarn", "pnpm", "bun", "python", "python3", "pip", "pip3",
        "git", "cat", "ls", "grep", "find", "echo", "mkdir", "touch",
        "rm", "mv", "cp", "head", "tail", "wc", "sort", "sed", "awk",
        "curl", "wget", "node", "npx", "make", "cargo", "go",
    ]
    allowed = allowed_commands or default_allowed
    cmd_start = cmd.strip().split()[0] if cmd.strip() else ""
    if cmd_start not in allowed:
        return False
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False
    return True


def truncate_output(output: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    encoded = output.encode("utf-8")
    if len(encoded) > max_bytes:
        truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        return truncated + "\n... [output truncated]"
    return output


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class ToolBackend(abc.ABC):
    """Interface every tool backend must implement."""

    @abc.abstractmethod
    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        ...

    @abc.abstractmethod
    def write_file(self, path: str, content: str) -> str:
        ...

    @abc.abstractmethod
    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        """Replace the first occurrence of *old_text* with *new_text* in the file."""
        ...

    @abc.abstractmethod
    def list_directory(self, path: str = ".", pattern: Optional[str] = None) -> str:
        ...

    @abc.abstractmethod
    def search_code(self, query: str, path: str = ".", context_lines: int = 2) -> str:
        ...

    @abc.abstractmethod
    def run_command(self, command: str, workdir: str = "/workspace") -> str:
        ...

    @abc.abstractmethod
    def search_documentation(self, query: str) -> str:
        ...


# ---------------------------------------------------------------------------
# Podman (server-side) backend
# ---------------------------------------------------------------------------

class PodmanToolBackend(ToolBackend):
    """Execute workspace operations via ``podman exec`` into the project container."""

    def __init__(self, container_name: str, timeout: int = 60, allowed_commands: Optional[List[str]] = None):
        self.container_name = container_name
        self.timeout = timeout
        self.allowed_commands = allowed_commands

    def _exec(self, shell_cmd: str) -> str:
        """Run *shell_cmd* inside the container and return combined output."""
        from api.podman_orchestrator import PodmanOrchestrator
        orchestrator = PodmanOrchestrator()
        result = orchestrator._run(
            ["exec", self.container_name, "sh", "-c", shell_cmd],
            timeout=self.timeout,
        )
        combined = ""
        if result.stdout:
            combined += result.stdout
        if result.stderr:
            combined += result.stderr
        if result.returncode != 0 and not combined.strip():
            combined = f"Command failed with exit code {result.returncode}"
        return truncate_output(combined)

    # ---- primitives ----

    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        validated = validate_path(path)
        if start_line and end_line:
            cmd = f"sed -n '{start_line},{end_line}p' {validated}"
        elif start_line:
            cmd = f"sed -n '{start_line},$p' {validated}"
        else:
            cmd = f"cat {validated}"
        return self._exec(cmd)

    def write_file(self, path: str, content: str) -> str:
        validated = validate_path(path)
        # Ensure parent directory exists
        parent = os.path.dirname(validated)
        escaped = content.replace("'", "'\\''")
        cmd = f"mkdir -p {parent} && printf '%s' '{escaped}' > {validated}"
        out = self._exec(cmd)
        if "failed" in out.lower() or "error" in out.lower():
            return f"Error writing file: {out}"
        return f"Successfully wrote {len(content)} characters to {path}"

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        content = self.read_file(path)
        if old_text not in content:
            return f"Error: the specified old_text was not found in {path}"
        updated = content.replace(old_text, new_text, 1)
        return self.write_file(path, updated)

    def list_directory(self, path: str = ".", pattern: Optional[str] = None) -> str:
        path = path or "."  # Handle empty string from LLM
        validated = validate_path(path)
        if pattern:
            cmd = f"find {validated} -maxdepth 3 -name '{pattern}' -type f 2>/dev/null | head -100"
        else:
            cmd = f"ls -la {validated}"
        return self._exec(cmd)

    def search_code(self, query: str, path: str = ".", context_lines: int = 2) -> str:
        validated = validate_path(path)
        safe_query = query.replace("'", "'\\''")
        cmd = (
            f"grep -rn --include='*.py' --include='*.js' --include='*.ts' "
            f"--include='*.tsx' --include='*.java' --include='*.go' --include='*.rs' "
            f"-C {context_lines} '{safe_query}' {validated} 2>/dev/null | head -200"
        )
        return self._exec(cmd)

    def run_command(self, command: str, workdir: str = "/workspace") -> str:
        if not validate_command(command, self.allowed_commands):
            return f"Command not allowed: {command}"
        cmd = f"cd {workdir} && {command}"
        return self._exec(cmd)

    def search_documentation(self, query: str) -> str:
        safe_query = query.replace("'", "'\\''")
        cmd = f"grep -rni '{safe_query}' /workspace/docs 2>/dev/null || echo 'No documentation matches found'"
        return self._exec(cmd)


# ---------------------------------------------------------------------------
# Native (in-container) backend
# ---------------------------------------------------------------------------

class NativeToolBackend(ToolBackend):
    """Execute workspace operations directly on the local filesystem (for use inside containers)."""

    def __init__(self, workspace_root: str = "/workspace", timeout: int = 60, allowed_commands: Optional[List[str]] = None):
        self.workspace_root = workspace_root
        self.timeout = timeout
        self.allowed_commands = allowed_commands

    def _run_local(self, cmd: str, workdir: Optional[str] = None) -> str:
        try:
            result = subprocess.run(
                ["sh", "-c", cmd],
                capture_output=True, text=True,
                timeout=self.timeout,
                cwd=workdir or self.workspace_root,
            )
            combined = (result.stdout or "") + (result.stderr or "")
            if result.returncode != 0 and not combined.strip():
                combined = f"Command failed with exit code {result.returncode}"
            return truncate_output(combined)
        except subprocess.TimeoutExpired:
            return f"Command timed out after {self.timeout}s"
        except Exception as e:
            return f"Error: {e}"

    # ---- primitives ----

    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        validated = validate_path(path, self.workspace_root)
        try:
            with open(validated, "r", errors="replace") as f:
                lines = f.readlines()
            if start_line and end_line:
                lines = lines[start_line - 1 : end_line]
            elif start_line:
                lines = lines[start_line - 1 :]
            return truncate_output("".join(lines))
        except Exception as e:
            return f"Error reading file: {e}"

    def write_file(self, path: str, content: str) -> str:
        validated = validate_path(path, self.workspace_root)
        try:
            os.makedirs(os.path.dirname(validated), exist_ok=True)
            with open(validated, "w") as f:
                f.write(content)
            return f"Successfully wrote {len(content)} characters to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        validated = validate_path(path, self.workspace_root)
        try:
            with open(validated, "r") as f:
                content = f.read()
            if old_text not in content:
                return f"Error: the specified old_text was not found in {path}"
            updated = content.replace(old_text, new_text, 1)
            with open(validated, "w") as f:
                f.write(updated)
            return f"Successfully edited {path}"
        except Exception as e:
            return f"Error editing file: {e}"

    def list_directory(self, path: str = ".", pattern: Optional[str] = None) -> str:
        path = path or "."  # Handle empty string from LLM
        validated = validate_path(path, self.workspace_root)
        if pattern:
            cmd = f"find {validated} -maxdepth 3 -name '{pattern}' -type f 2>/dev/null | head -100"
        else:
            cmd = f"ls -la {validated}"
        return self._run_local(cmd)

    def search_code(self, query: str, path: str = ".", context_lines: int = 2) -> str:
        validated = validate_path(path, self.workspace_root)
        safe_query = query.replace("'", "'\\''")
        cmd = (
            f"grep -rn --include='*.py' --include='*.js' --include='*.ts' "
            f"--include='*.tsx' --include='*.java' --include='*.go' --include='*.rs' "
            f"-C {context_lines} '{safe_query}' {validated} 2>/dev/null | head -200"
        )
        return self._run_local(cmd)

    def run_command(self, command: str, workdir: str = "/workspace") -> str:
        if not validate_command(command, self.allowed_commands):
            return f"Command not allowed: {command}"
        return self._run_local(command, workdir=workdir)

    def search_documentation(self, query: str) -> str:
        safe_query = query.replace("'", "'\\''")
        docs_path = os.path.join(self.workspace_root, "docs")
        cmd = f"grep -rni '{safe_query}' {docs_path} 2>/dev/null || echo 'No documentation matches found'"
        return self._run_local(cmd)
