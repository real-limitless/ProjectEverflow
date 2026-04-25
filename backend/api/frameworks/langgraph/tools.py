"""
Workspace tools for LangGraph agents.
"""
import os
import subprocess
import asyncio
from typing import List, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from api.models import Project
from api.podman_orchestrator import PodmanOrchestrator


# Security constants
BLOCKED_PATTERNS = [
    r'rm\s+-rf\s+/',  # Dangerous rm commands
    r'sudo',  # Privilege escalation
    r'curl.*\|.*sh',  # Pipe to shell
    r'wget.*\|',  # Pipe wget
    r'nc\s+-',  # Netcat
    r'ssh\s+',  # SSH commands
    r'chmod\s+777',  # Dangerous permissions
    r'>\s*/etc/',  # Writing to system files
    r'dd\s+if=',  # Dangerous dd commands
]

MAX_OUTPUT_BYTES = 10240  # 10KB limit


def validate_path(path: str, base: str = "/workspace") -> str:
    """Validate and resolve file paths to prevent directory traversal."""
    if not path:
        raise ValueError("Path cannot be empty")

    # Resolve the path
    resolved = os.path.abspath(os.path.join(base, path))

    # Ensure it's within the base directory
    if not resolved.startswith(os.path.abspath(base)):
        raise ValueError(f"Path {path} is outside allowed directory {base}")

    return resolved


def validate_command(cmd: str, allowed_commands: List[str]) -> bool:
    """Validate command against allowed list and blocked patterns."""
    import re

    # Check if command starts with allowed command
    cmd_start = cmd.strip().split()[0]
    if cmd_start not in allowed_commands:
        return False

    # Check for blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False

    return True


def truncate_output(output: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """Truncate output to prevent memory exhaustion."""
    if len(output.encode('utf-8')) > max_bytes:
        truncated = output.encode('utf-8')[:max_bytes].decode('utf-8', errors='ignore')
        return truncated + "\n... [output truncated]"
    return output


def get_workspace_tools(project: Project, container_name: str) -> List:
    """Create workspace tools for the given project and container."""

    allowed_commands = project.allowed_commands or [
        'npm', 'yarn', 'pnpm', 'python', 'pip', 'git', 'cat', 'ls', 'grep', 'find',
        'echo', 'mkdir', 'touch', 'rm', 'mv', 'cp'
    ]
    timeout = project.command_timeout or 60

    def ensure_workspace_container():
        """Ensure the workspace container exists and is running."""
        try:
            orchestrator = PodmanOrchestrator()
            
            # Check if container exists
            if not orchestrator._container_exists(container_name):
                # Ensure volume exists
                volume_name = f"workspace-{project.id}"
                if not orchestrator._volume_exists(volume_name):
                    orchestrator._run(['volume', 'create', volume_name])
                
                # Create the container if it doesn't exist
                # Use the project's pod if it exists, otherwise create a standalone container
                pod_name = f"proj-pod-{project.id}"
                
                # Check if pod exists
                if orchestrator._pod_exists(pod_name):
                    # Create container in existing pod
                    run_args = [
                        'run', '-d', '--pod', pod_name, '--name', container_name,
                        '-v', f'{volume_name}:/workspace:Z',
                        'localhost/fedora-devtools:latest'
                    ]
                else:
                    # Create standalone container
                    run_args = [
                        'run', '-d', '--name', container_name,
                        '-v', f'{volume_name}:/workspace:Z',
                        'localhost/fedora-devtools:latest'
                    ]
                
                # Add environment variables
                run_args.extend(['-e', 'HOME=/workspace'])
                
                # Run the container
                orchestrator._run(run_args)
                
        except Exception as e:
            # Log error but don't fail - tools will handle individual command failures
            import logging
            logging.error(f"Failed to create workspace container {container_name}: {e}")

    # Ensure workspace container exists
    ensure_workspace_container()

    # Import RAG tools
    from .rag import get_rag_tools
    rag_tools = get_rag_tools(project, container_name)

    @tool
    def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Read contents of a file in the workspace.

        Args:
            path: Path to the file (relative to /workspace)
            start_line: Optional start line number (1-based)
            end_line: Optional end line number (1-based)
        """
        try:
            validated_path = validate_path(path)

            # Build command
            cmd = f"cat {validated_path}"
            if start_line and end_line:
                cmd = f"sed -n '{start_line},{end_line}p' {validated_path}"
            elif start_line:
                cmd = f"sed -n '{start_line},$p' {validated_path}"

            # Execute in container
            orchestrator = PodmanOrchestrator()
            result = orchestrator._run(['exec', container_name, 'sh', '-c', cmd], timeout=timeout)

            if result.returncode == 0:
                return truncate_output(result.stdout)
            else:
                return f"Error reading file: {result.stderr}"

        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def write_file(path: str, content: str) -> str:
        """Create or overwrite a file in the workspace.

        Args:
            path: Path to the file (relative to /workspace)
            content: Content to write to the file
        """
        try:
            validated_path = validate_path(path)

            # Use printf to handle special characters safely
            escaped_content = content.replace("'", "'\\''")
            cmd = f"printf '%s' '{escaped_content}' > {validated_path}"

            # Execute in container
            orchestrator = PodmanOrchestrator()
            result = orchestrator._run(['exec', container_name, 'sh', '-c', cmd], timeout=timeout)

            if result.returncode == 0:
                return f"Successfully wrote {len(content)} characters to {path}"
            else:
                return f"Error writing file: {result.stderr}"

        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def list_directory(path: str = ".", pattern: Optional[str] = None) -> str:
        """List files and directories in the workspace.

        Args:
            path: Directory path (relative to /workspace)
            pattern: Optional glob pattern to filter results
        """
        try:
            validated_path = validate_path(path)

            cmd = f"ls -la {validated_path}"
            if pattern:
                cmd = f"find {validated_path} -name '{pattern}' -type f"

            # Execute in container
            orchestrator = PodmanOrchestrator()
            result = orchestrator._run(['exec', container_name, 'sh', '-c', cmd], timeout=timeout)

            if result.returncode == 0:
                return truncate_output(result.stdout)
            else:
                return f"Error listing directory: {result.stderr}"

        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def search_code(query: str, path: str = ".", context_lines: int = 2) -> str:
        """Search for text in files within the workspace.

        Args:
            query: Text to search for
            path: Directory to search in (relative to /workspace)
            context_lines: Number of context lines around matches
        """
        try:
            validated_path = validate_path(path)

            # Use ripgrep if available, fallback to grep
            cmd = f"grep -rn -C {context_lines} '{query}' {validated_path} 2>/dev/null || find {validated_path} -type f -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' -o -name '*.java' -o -name '*.cpp' -o -name '*.c' -o -name '*.h' | xargs grep -n -C {context_lines} '{query}' 2>/dev/null || echo 'No matches found'"

            # Execute in container
            orchestrator = PodmanOrchestrator()
            result = orchestrator._run(['exec', container_name, 'sh', '-c', cmd], timeout=timeout)

            if result.returncode == 0:
                return truncate_output(result.stdout)
            else:
                return f"Error searching: {result.stderr}"

        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def run_command(command: str) -> str:
        """Execute a shell command in the workspace container.

        Args:
            command: Shell command to execute
        """
        try:
            # Validate command
            if not validate_command(command, allowed_commands):
                return f"Command not allowed: {command}"

            # Execute in container with workspace directory
            full_cmd = f"cd /workspace && {command}"
            orchestrator = PodmanOrchestrator()
            result = orchestrator._run(['exec', container_name, 'sh', '-c', full_cmd], timeout=timeout)

            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += result.stderr

            if result.returncode == 0:
                return truncate_output(f"Command executed successfully:\n{output}")
            else:
                return truncate_output(f"Command failed (exit code {result.returncode}):\n{output}")

        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def search_documentation(query: str) -> str:
        """Search for information in project documentation.

        Args:
            query: Search query for documentation
        """
        try:
            # Search in docs directory
            docs_path = "/workspace/docs"
            cmd = f"grep -rn -i '{query}' {docs_path} 2>/dev/null || echo 'No documentation matches found'"

            # Execute in container
            orchestrator = PodmanOrchestrator()
            result = orchestrator._run(['exec', container_name, 'sh', '-c', cmd], timeout=timeout)

            if result.returncode == 0:
                return truncate_output(result.stdout)
            else:
                return f"Error searching documentation: {result.stderr}"

        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def analyze_file(path: str, mode: str = 'quick', session_id: Optional[int] = None) -> str:
        """Analyze a file using lightweight heuristics. Mode can be 'quick' or 'deep'.

        If session_id is provided, progress updates will be sent to the Channels group
        `langgraph_session_{session_id}` as events of type 'analyze_update'.
        """
        try:
            validated_path = validate_path(path)

            # Read file content
            orchestrator = PodmanOrchestrator()
            result = orchestrator._run(['exec', container_name, 'sh', '-c', f"cat {validated_path}"], timeout=timeout)
            if result.returncode != 0:
                return f"Error reading file: {result.stderr}"

            content = result.stdout or ''

            def quick_summary(text: str) -> dict:
                lines = text.split('\n') if text else []
                todos = [l.strip() for l in lines if 'TODO' in l or 'FIXME' in l]
                lang = os.path.splitext(validated_path)[1].lstrip('.') or 'text'
                return {
                    'lines': len(lines),
                    'chars': len(text),
                    'lang': lang,
                    'todos_sample': todos[:5],
                    'requires_deep': len(text) > 5000
                }

            if mode == 'quick':
                return str(quick_summary(content))

            # Deep mode: chunk and return combined summary (synchronous)
            CHUNK_SIZE = 4000
            chunks = [content[i:i+CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]
            summaries = []
            from asgiref.sync import async_to_sync
            channel_layer = None
            if session_id:
                from channels.layers import get_channel_layer
                channel_layer = get_channel_layer()
                group_name = f"langgraph_session_{session_id}"

            for idx, ch in enumerate(chunks, start=1):
                lines = ch.split('\n')
                todo_count = sum(1 for l in lines if 'TODO' in l or 'FIXME' in l)
                func_count = sum(1 for l in lines if l.strip().startswith(('def ', 'function ', 'const ', 'class ')))
                summary = {'chunk_index': idx, 'lines': len(lines), 'todos': todo_count, 'functions': func_count}
                summaries.append(summary)

                # Send progress if requested
                if channel_layer:
                    payload = {'type': 'analyze_chunk', 'chunk_index': idx, 'total_chunks': len(chunks), 'summary': summary, 'progress': int((idx/len(chunks))*100)}
                    try:
                        async_to_sync(channel_layer.group_send)(group_name, {'type': 'analyze_update', 'payload': payload})
                    except Exception:
                        pass

            final = {'total_chunks': len(chunks), 'total_lines': sum(s['lines'] for s in summaries), 'total_todos': sum(s['todos'] for s in summaries)}
            if channel_layer:
                try:
                    async_to_sync(channel_layer.group_send)(group_name, {'type': 'analyze_update', 'payload': {'type': 'analyze_complete', 'final': final}})
                except Exception:
                    pass

            return str(final)

        except Exception as e:
            return f"Error: {str(e)}"

    return [read_file, write_file, list_directory, search_code, run_command, search_documentation] + rag_tools