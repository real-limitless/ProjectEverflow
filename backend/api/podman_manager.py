import json
import os
import subprocess
import uuid
from typing import Dict, Any, Optional

from django.conf import settings
from django.utils import timezone

from .models import Project, ProjectPod, ProjectService, ProjectTool


class PodmanError(RuntimeError):
    """Raised when Podman commands fail."""


class ToolExecutionError(RuntimeError):
    """Raised when a tool execution fails."""


class PodmanManager:
    """Utility wrapper around Podman CLI for managing project pods and containers."""

    def __init__(self, project: Project):
        self.project = project
        self.binary = os.getenv('PODMAN_BIN', 'podman')

    def _run(self, args, capture_output: bool = True, check: bool = True, env: Optional[Dict[str, str]] = None, timeout: Optional[int] = None):
        command = [self.binary] + args
        try:
            return subprocess.run(
                command,
                capture_output=capture_output,
                check=check,
                text=True,
                env=env,
                timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            raise PodmanError(exc.stderr or exc.stdout or str(exc)) from exc
        except FileNotFoundError as exc:
            raise PodmanError('Podman binary not found. Please install Podman or set PODMAN_BIN.') from exc

    def ensure_pod(self) -> ProjectPod:
        pod, created = ProjectPod.objects.get_or_create(
            project=self.project,
            defaults={
                'pod_name': self._generate_pod_name(),
                'status': 'creating',
            }
        )

        exists = self._pod_exists(pod.pod_name)
        if not exists:
            self._run(['pod', 'create', '--name', pod.pod_name])
        pod.status = 'running'
        pod.last_synced_at = timezone.now()
        pod.save(update_fields=['status', 'last_synced_at'])
        return pod

    def _pod_exists(self, pod_name: str) -> bool:
        try:
            self._run(['pod', 'exists', pod_name])
            return True
        except PodmanError:
            return False

    def ensure_service(self, name: str, service_type: str, image: str, ports=None, environment=None) -> ProjectService:
        pod = self.ensure_pod()
        ports = ports or []
        environment = environment or {}
        container_name = f"{pod.pod_name}-{name}"[:250]

        service, _ = ProjectService.objects.get_or_create(
            pod=pod,
            name=name,
            defaults={
                'service_type': service_type,
                'image': image,
                'container_name': container_name,
                'ports': ports,
                'environment': environment,
            }
        )

        # Check container exists; if not, create and start it
        if not self._container_exists(service.container_name):
            run_args = ['run', '-d', '--pod', pod.pod_name, '--name', service.container_name]
            for port in ports:
                run_args += ['-p', port]
            for key, value in environment.items():
                run_args += ['-e', f'{key}={value}']
            run_args.append(image)
            self._run(run_args)
            service.status = 'running'
            service.last_started_at = timezone.now()
            service.save(update_fields=['status', 'last_started_at'])
        return service

    def _container_exists(self, container_name: str) -> bool:
        try:
            self._run(['container', 'exists', container_name])
            return True
        except PodmanError:
            return False

    def run_tool(self, tool: ProjectTool, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run a project tool inside the project's pod and return stdout/stderr."""
        payload = payload or {}
        
        if tool.workspace_tool:
            # Execute in workspace container via podman exec
            return self._run_workspace_tool(tool, payload)
        else:
            # Execute in new container within pod
            return self._run_container_tool(tool, payload)
    
    def _run_workspace_tool(self, tool: ProjectTool, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run a tool by executing command in the workspace container."""
        # Find the workspace container
        workspace_container = self._get_workspace_container_name()
        if not workspace_container:
            raise ToolExecutionError("No workspace container found for project")
        
        # For execute-command tool, use the command from payload
        if tool.slug == 'execute-command':
            command = payload.get('command', '')
            container = payload.get('container', 'default')
            
            # Validate command
            if not self._is_command_allowed(command):
                raise ToolExecutionError(f"Command not allowed: {command}")
            
            # For now, execute in workspace container regardless of container parameter
            # TODO: Support executing in different containers
            full_command = f"cd /workspace && {command}"
        else:
            # Build command with payload for other workspace tools
            env = tool.environment.copy() if tool.environment else {}
            env['TOOL_INPUT'] = json.dumps(payload)
            
            # Set environment variables
            env_vars = ' '.join([f"{k}='{v}'" for k, v in env.items()])
            if env_vars:
                env_vars = f"export {env_vars} && "
            
            # Execute command in workspace container
            full_command = f"{env_vars}cd /workspace && {tool.entrypoint}"
        
        timeout = tool.timeout_seconds or getattr(settings, 'DEFAULT_TOOL_TIMEOUT', 300)
        try:
            result = self._run(['exec', workspace_container, 'sh', '-c', full_command], timeout=timeout)
            return {'stdout': result.stdout, 'stderr': result.stderr, 'container_name': workspace_container}
        except PodmanError as exc:
            raise ToolExecutionError(str(exc)) from exc
    
    def _is_command_allowed(self, command: str) -> bool:
        """Check if command is in allowed list and doesn't contain dangerous patterns."""
        import re
        
        allowed_commands = [
            'ls', 'cat', 'grep', 'find', 'python', 'node', 'npm', 'yarn', 'pnpm',
            'git', 'echo', 'mkdir', 'touch', 'rm', 'mv', 'cp', 'psql', 'sql'
        ]
        
        blocked_patterns = [
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
        
        # Check if command starts with allowed command
        cmd_start = command.strip().split()[0]
        if cmd_start not in allowed_commands:
            return False
        
        # Check for blocked patterns
        for pattern in blocked_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False
        
        return True
    
    def _run_container_tool(self, tool: ProjectTool, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run a tool in a new container within the project's pod."""
        pod = self.ensure_pod()
        env = tool.environment.copy() if tool.environment else {}
        env['TOOL_INPUT'] = json.dumps(payload)

        image = tool.runtime_image or getattr(settings, 'DEFAULT_TOOL_IMAGE', 'docker.io/library/python:3.11-slim')
        container_name = f"tool-{tool.project.id}-{uuid.uuid4().hex[:8]}"

        run_args = ['run', '--rm', '--pod', pod.pod_name, '--name', container_name]
        for key, value in env.items():
            run_args += ['-e', f'{key}={value}']

        command = tool.entrypoint
        run_args.append(image)
        run_args += ['sh', '-c', command]

        timeout = tool.timeout_seconds or getattr(settings, 'DEFAULT_TOOL_TIMEOUT', 300)
        try:
            result = self._run(run_args, timeout=timeout)
            return {'stdout': result.stdout, 'stderr': result.stderr, 'container_name': container_name}
        except PodmanError as exc:
            raise ToolExecutionError(str(exc)) from exc
    
    def _get_workspace_container_name(self) -> Optional[str]:
        """Get the name of the workspace container for this project."""
        try:
            pod = self.project.pod
            if pod:
                workspace_service = pod.services.filter(service_type='ai-workspace').first()
                if workspace_service:
                    return workspace_service.container_name
        except Exception:
            pass
        return None

    @staticmethod
    def _generate_pod_name() -> str:
        return f"proj-pod-{uuid.uuid4().hex[:10]}"