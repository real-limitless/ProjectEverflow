"""
Workspace Initializer Module

Handles initialization of project workspace volumes based on creation method.
Supports blank projects, git clones, templates, and AI-generated projects.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from .compose_parser import (
    COMPOSE_CANDIDATES,
    load_compose_from_text,
    build_service_specs,
    extract_dependency_order,
    ComposeParseError,
)
from .git_source_normalization import GitRepositoryNormalizationError, normalize_public_git_repository_input
from .podman_orchestrator import PodmanOrchestrator


logger = logging.getLogger(__name__)


class WorkspaceInitializerError(Exception):
    """Raised when workspace initialization fails"""
    pass


class WorkspaceInitializer:
    """
    Initializes workspace volumes for projects based on their creation method.
    """

    def __init__(self, volume_name: str, project_id: Optional[int] = None):
        self.volume_name = volume_name
        self.project_id = project_id
        self.podman = os.getenv('PODMAN_BIN', 'podman')
        self.channel_layer = get_channel_layer()

    def _log(self, level: str, step_name: str, message: str, metadata: Optional[Dict] = None):
        """
        Emit a provisioning log entry to both database and WebSocket.
        
        Args:
            level: Log level ('debug', 'info', 'warning', 'error')
            step_name: Step identifier (e.g., 'clone_repo', 'provision_services')
            message: Human-readable message
            metadata: Additional structured data
        """
        if not self.project_id:
            # If no project_id, just log to console
            logger.log(getattr(logging, level.upper(), logging.INFO), f"[{step_name}] {message}")
            return
        
        try:
            # Import here to avoid circular dependency
            from .models import ProvisioningLog, Project
            
            # Save to database
            project = Project.objects.get(pk=self.project_id)
            ProvisioningLog.objects.create(
                project=project,
                level=level,
                step_name=step_name,
                message=message,
                metadata=metadata or {}
            )
            
            # Broadcast via WebSocket
            if self.channel_layer:
                group_name = f"provisioning_{self.project_id}"
                async_to_sync(self.channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'provisioning_log',
                        'level': level,
                        'step_name': step_name,
                        'message': message,
                        'metadata': metadata or {},
                        'timestamp': datetime.now().isoformat(),
                    }
                )
        except Exception as e:
            # Don't let logging failures break provisioning
            logger.error(f"Failed to emit provisioning log: {e}")
        
        # Also log to console
        logger.log(getattr(logging, level.upper(), logging.INFO), f"[{step_name}] {message}")

    def _run_command(
        self,
        args: list,
        capture_output: bool = True,
        check: bool = True,
        input_data: Optional[Any] = None,
        stdin: Optional[Any] = None,
        text: bool = True,
        cwd: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
        """Run a command and return the result"""
        try:
            return subprocess.run(
                args,
                input=input_data,
                stdin=stdin,
                capture_output=capture_output,
                check=check,
                text=text,
                cwd=cwd,
            )
        except subprocess.CalledProcessError as exc:
            raise WorkspaceInitializerError(f"Command failed: {exc.stderr or exc.stdout or str(exc)}") from exc
        except FileNotFoundError as exc:
            raise WorkspaceInitializerError(f"Command not found: {args[0]}") from exc

    def _ensure_volume_exists(self) -> None:
        """Ensure the workspace volume exists"""
        try:
            self._run_command([self.podman, 'volume', 'inspect', self.volume_name], check=True)
        except WorkspaceInitializerError:
            # Volume doesn't exist, create it
            self._run_command([self.podman, 'volume', 'create', self.volume_name])

    def _write_files_to_volume(self, files: Dict[str, Dict[str, Any]]) -> None:
        """
        Write files to volume using a temporary alpine container.
        
        Args:
            files: Dict mapping file paths to file metadata
                  {path: {content: str, executable: bool}}
        """
        # Create a temporary directory with the files
        tmpdir = tempfile.mkdtemp()
        try:
            for file_path, metadata in files.items():
                full_path = Path(tmpdir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                content = metadata.get('content', '')
                full_path.write_text(content)
                
                if metadata.get('executable', False):
                    full_path.chmod(0o755)
            
            # Copy files from temp dir to volume using a container
            container_name = f"workspace-init-{self.volume_name}"
            try:
                # Run alpine container with volume mounted
                self._run_command([
                    self.podman, 'run', '--rm',
                    '--name', container_name,
                    '-v', f'{self.volume_name}:/workspace',
                    '-v', f'{tmpdir}:/source:ro',
                    'alpine:latest',
                    'sh', '-c', 'cp -r /source/* /workspace/ && chown -R 1000:1000 /workspace'
                ])
            except WorkspaceInitializerError as exc:
                raise WorkspaceInitializerError(f"Failed to copy files to volume: {exc}") from exc
        finally:
            # Clean up temp directory
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _create_directories_in_volume(self, directories: list) -> None:
        """
        Create directories in volume using a temporary alpine container.
        
        Args:
            directories: List of directory paths to create
        """
        if not directories:
            return
            
        mkdir_commands = ' && '.join([f'mkdir -p /workspace/{d}' for d in directories])
        container_name = f"workspace-mkdir-{self.volume_name}"
        
        try:
            self._run_command([
                self.podman, 'run', '--rm',
                '--name', container_name,
                '-v', f'{self.volume_name}:/workspace',
                'alpine:latest',
                'sh', '-c', f'{mkdir_commands} && chown -R 1000:1000 /workspace'
            ])
        except WorkspaceInitializerError as exc:
            raise WorkspaceInitializerError(f"Failed to create directories: {exc}") from exc

    def init_blank_workspace(self) -> None:
        """
        Initialize a blank workspace with basic project structure.
        Creates: README.md, src/, tests/, .gitignore
        """
        self.reset_workspace()
        
        # Create directories and files using a shell script
        shell_commands = [
            "mkdir -p /workspace/src /workspace/tests /workspace/docs",
            "touch /workspace/src/.gitkeep",
            "cat > /workspace/README.md << 'EOF'\n# New Project\n\nThis project was created with PatternFly Dash Brew.\n\n## Getting Started\n\nAdd your project documentation here.\nEOF",
            "cat > /workspace/.gitignore << 'EOF'\n__pycache__/\n*.pyc\n*.pyo\n*.pyd\n.Python\nnode_modules/\n.env\n.venv\ndist/\nbuild/\n*.egg-info/\n.DS_Store\nEOF",
            "chown -R 1000:1000 /workspace"
        ]
        
        cmd = " && ".join(shell_commands)
        
        container_name = f"workspace-init-{self.volume_name}"
        try:
            # Run alpine container with volume mounted to create structure
            self._run_command([
                self.podman, 'run', '--rm',
                '--name', container_name,
                '-v', f'{self.volume_name}:/workspace',
                'alpine:latest',
                'sh', '-c', cmd
            ])
        except WorkspaceInitializerError as exc:
            raise WorkspaceInitializerError(f"Failed to initialize blank workspace: {exc}") from exc

    def init_from_clone(self, git_url: str, branch: Optional[str] = None, credential: Optional[str] = None) -> None:
        """
        Initialize workspace by cloning a git repository.
        
        Args:
            git_url: URL of the git repository to clone
            branch: Optional branch name to checkout
            credential: Optional PAT used for authenticated clone via http.extraHeader (never logged)
        """
        self._log('info', 'clone_repo', f"Creating workspace volume: {self.volume_name}")
        self._ensure_volume_exists()
        
        branch_display = f" (branch: {branch})" if branch else " (default branch)"
        self._log('info', 'clone_repo', f"Cloning repository{branch_display}...")
        
        branch_arg = f" --branch {branch}" if branch else ""
        # Use a robust move to include dotfiles without tripping on . and ..
        token = (credential or '').strip()
        if token:
            git_prefix = f'git -c http.extraHeader="Authorization: token {token}"'
        else:
            git_prefix = 'git'
        clone_cmd = (
            f"{git_prefix} clone --depth 1{branch_arg} {git_url} /workspace/repo"
            " && cd /workspace/repo"
            " && find . -mindepth 1 -maxdepth 1 -exec mv -t /workspace {} +"
            " && cd /workspace && rm -rf /workspace/repo"
            " && chown -R 1000:1000 /workspace"
        )
        
        container_name = f"workspace-clone-{self.volume_name}"
        
        try:
            self._log('debug', 'clone_repo', "Executing git clone via alpine/git container")
            self._run_command([
                self.podman, 'run', '--rm',
                '--name', container_name,
                '-v', f'{self.volume_name}:/workspace',
                '--entrypoint', '/bin/sh',
                'docker.io/alpine/git:latest',
                '-c', clone_cmd
            ])
            self._log('info', 'clone_repo', "Repository cloned successfully")
        except WorkspaceInitializerError as exc:
            self._log('error', 'clone_repo', f"Failed to clone repository: {exc}")
            raise WorkspaceInitializerError(f"Failed to clone repository: {exc}") from exc

    def _read_compose_file(self) -> Optional[str]:
        """Read compose file content from the workspace volume if present."""
        candidates = ' '.join(COMPOSE_CANDIDATES)
        self._log('debug', 'provision_services', f"Searching for compose files: {', '.join(COMPOSE_CANDIDATES)}")
        find_cmd = (
            "for f in " + candidates + "; do "
            "if [ -f /workspace/$f ]; then echo \"Found: $f\" >&2 && cat /workspace/$f && exit 0; fi; "
            "done; echo \"Not found: checked {" + candidates + "}\" >&2 && exit 1"
        )
        container_name = f"workspace-compose-read-{self.volume_name}"
        try:
            result = self._run_command([
                self.podman, 'run', '--rm',
                '--name', container_name,
                '-v', f'{self.volume_name}:/workspace:ro',
                'alpine:latest',
                'sh', '-c', find_cmd
            ], capture_output=True, check=True)
            if result.stderr:
                self._log('info', 'provision_services', f"Compose file search: {result.stderr.strip()}")
            return result.stdout
        except WorkspaceInitializerError as exc:
            self._log('debug', 'provision_services', f"No compose file found in workspace volume: {exc}")
            return None

    def _get_volume_mountpoint(self) -> str:
        try:
            result = self._run_command([
                self.podman, 'volume', 'inspect', self.volume_name, '--format', '{{.Mountpoint}}'
            ])
            mountpoint = (result.stdout or '').strip()
            if not mountpoint:
                raise WorkspaceInitializerError("Unable to resolve volume mountpoint")
            return mountpoint
        except WorkspaceInitializerError as exc:
            raise WorkspaceInitializerError(f"Failed to inspect volume mountpoint: {exc}") from exc

    def _build_images(self, build_specs: List[Dict[str, Any]]) -> None:
        for build in build_specs:
            context = build.get('context') or '.'
            rel_context = context.lstrip('/') or '.'
            # Use a named volume for build context so both backend container and host podman can see it
            build_volume = f"build-ctx-{self.volume_name}-{build.get('name', 'svc')}"
            try:
                # Create volume for build context
                self._run_command([self.podman, 'volume', 'rm', '-f', build_volume], check=False)
                self._run_command([self.podman, 'volume', 'create', build_volume])

                # Copy context from workspace volume into build volume
                copy_cmd = (
                    "cd /workspace && "
                    f"if [ ! -d '{rel_context}' ]; then exit 44; fi; "
                    f"cp -a {rel_context}/. /build-ctx/"
                )
                try:
                    self._run_command([
                        self.podman, 'run', '--rm',
                        '-v', f'{self.volume_name}:/workspace:ro',
                        '-v', f'{build_volume}:/build-ctx',
                        'alpine:latest', 'sh', '-c', copy_cmd
                    ], capture_output=True)
                except WorkspaceInitializerError as exc:
                    if 'exit status 44' in str(exc) or 'code: 44' in str(exc):
                        raise WorkspaceInitializerError(f"Build context not found or not a directory: {context}") from exc
                    raise

                dockerfile_rel = os.path.normpath(build.get('dockerfile') or 'Dockerfile')

                # Verify Dockerfile exists in build volume
                check_cmd = f"test -f /build-ctx/{dockerfile_rel}"
                try:
                    self._run_command([
                        self.podman, 'run', '--rm',
                        '-v', f'{build_volume}:/build-ctx:ro',
                        'alpine:latest', 'sh', '-c', check_cmd
                    ], capture_output=True)
                except WorkspaceInitializerError:
                    raise WorkspaceInitializerError(f"Dockerfile not found at {dockerfile_rel} within context {context}")

                target = build.get('target')
                build_args = build.get('args') or {}
                image = build.get('image')
                service_name = build.get('name')

                self._log('info', 'provision_services', f"Building image '{image}' for service '{service_name}' from {context}")

                # Stream tar from build volume directly to podman build via shell pipe
                # This avoids needing direct host access to volume mountpoint
                tar_cmd = "tar -C /build-ctx -c ."
                
                build_args_str = ' '.join(f"--build-arg {k}={v}" for k, v in build_args.items())
                target_str = f"--target {target}" if target else ""
                dockerfile_str = f"-f {dockerfile_rel}" if dockerfile_rel != 'Dockerfile' else ""
                
                # Construct the full pipeline command
                pipeline_cmd = (
                    f"{self.podman} run --rm -v {build_volume}:/build-ctx:ro alpine:latest {tar_cmd} | "
                    f"{self.podman} build -t {image} {target_str} {build_args_str} {dockerfile_str} -"
                )
                
                self._log('debug', 'provision_services', f"Executing build pipeline: {pipeline_cmd}")
                
                # Run via shell to handle the pipe
                result = subprocess.run(
                    pipeline_cmd,
                    shell=True,
                    capture_output=False,
                    check=True,
                )
                
                self._log('info', 'provision_services', f"✓ Built image '{image}' successfully")
            except subprocess.CalledProcessError as exc:
                raise WorkspaceInitializerError(f"Build failed for {service_name}: {exc}") from exc
            finally:
                # Cleanup build volume
                self._run_command([self.podman, 'volume', 'rm', '-f', build_volume], check=False)

    def provision_compose_services(self, project) -> None:
        """Detect and provision services defined in a compose file inside the workspace."""
        self._log('info', 'provision_services', "Searching for compose file in workspace...")
        
        compose_text = self._read_compose_file()
        if not compose_text:
            self._log('info', 'provision_services', "No compose file found, skipping service provisioning")
            return

        self._log('info', 'provision_services', "Compose file found, parsing service definitions...")
        
        try:
            compose_data = load_compose_from_text(compose_text)
            network_name = f"proj-{project.id}-net"

            orchestrator = PodmanOrchestrator()
            # Default limits from workspace tier
            limits = orchestrator._get_resource_limits(project.workspace_size)
            default_cpu = limits.get('cpu', '1.0')
            default_mem = limits.get('memory', '2g')

            specs, build_specs = build_service_specs(
                compose=compose_data,
                project_id=project.id,
                workspace_volume=self.volume_name,
                network_name=network_name,
                default_cpu=default_cpu,
                default_mem=default_mem,
            )
            
            service_names = [s.name for s in specs]
            self._log('info', 'provision_services', f"Found {len(specs)} services (build steps: {len(build_specs)}): {', '.join(service_names)}")

            if build_specs:
                self._build_images(build_specs)

            # Respect depends_on ordering
            order = extract_dependency_order(compose_data)
            spec_lookup = {s.name: s for s in specs}
            ordered_specs = [spec_lookup[name] for name in order if name in spec_lookup]
            remaining = [s for s in specs if s.name not in spec_lookup or s.name not in order]
            ordered_specs.extend(remaining)

            # Ensure network exists once
            self._log('debug', 'provision_services', f"Creating network: {network_name}")
            orchestrator.ensure_network(network_name)

            successful_services = []
            failed_services = []
            
            for spec in ordered_specs:
                # Ensure workspace volume mount exists in spec
                has_workspace_mount = any(v.get('source') == self.volume_name for v in spec.volumes)
                if not has_workspace_mount:
                    spec.volumes.append({
                        'type': 'volume',
                        'source': self.volume_name,
                        'target': '/workspace',
                        'readonly': False,
                    })
                try:
                    self._log('info', 'provision_services', f"Starting service: {spec.name} (image: {spec.image})")
                    orchestrator.ensure_service(project.id, spec)
                    successful_services.append(spec.name)
                    self._log('info', 'provision_services', f"✓ Service '{spec.name}' started successfully")
                except Exception as exc:  # broad to ensure we keep provisioning others
                    failed_services.append(spec.name)
                    self._log('warning', 'provision_services', f"✗ Failed to start service '{spec.name}': {exc}", 
                             metadata={'service': spec.name, 'error': str(exc)})
            
            # Summary log
            if successful_services:
                self._log('info', 'provision_services', 
                         f"Service provisioning complete: {len(successful_services)} successful, {len(failed_services)} failed",
                         metadata={'successful': successful_services, 'failed': failed_services})
            else:
                self._log('warning', 'provision_services', "No services were successfully provisioned")
                
        except ComposeParseError as exc:
            self._log('error', 'provision_services', f"Failed to parse compose file: {exc}")
            raise

    def init_from_template(self, template_data: Dict[str, Any]) -> None:
        """
        Initialize workspace from a project template.
        
        Args:
            template_data: Template file structure
                          {files: {path: {content, executable}}, directories: []}
        """
        self._ensure_volume_exists()
        
        files = template_data.get('files', {})
        directories = template_data.get('directories', [])
        
        if files:
            self._write_files_to_volume(files)
        
        if directories:
            self._create_directories_in_volume(directories)

    def init_from_chat(self, ai_generated_files: Dict[str, Any]) -> None:
        """
        Initialize workspace from AI-generated project structure.
        
        Args:
            ai_generated_files: AI-generated file structure
                               {files: {path: {content, executable}}, directories: []}
        """
        # Same format as template, reuse the logic
        self.init_from_template(ai_generated_files)

    def reset_workspace(self) -> None:
        """
        Reset workspace by deleting and recreating the volume.
        WARNING: This will delete all data in the workspace.
        """
        try:
            # Remove the volume
            self._run_command([self.podman, 'volume', 'rm', '-f', self.volume_name])
        except WorkspaceInitializerError:
            # Volume might not exist, that's okay
            pass
        
        # Recreate the volume
        self._run_command([self.podman, 'volume', 'create', self.volume_name])


def initialize_project_workspace(project, clone_credential: Optional[str] = None) -> None:
    """
    Initialize workspace for a project based on its creation method.
    
    Args:
        project: Project model instance
        clone_credential: Optional decrypted PAT to use for authenticated git clone
    """
    volume_name = f"proj-{project.id}-workspace"
    initializer = WorkspaceInitializer(volume_name, project_id=project.id)
    
    try:
        initializer._log('info', 'init_start', f"Starting workspace initialization for project '{project.name}'")
        
        if project.creation_method == 'blank':
            initializer._log('info', 'init_method', "Initializing blank workspace")
            initializer.init_blank_workspace()
        elif project.creation_method == 'clone' and project.git_repo_url:
            normalized_git_url = project.git_repo_url
            try:
                normalized_repository = normalize_public_git_repository_input(project.git_repo_url)
                normalized_git_url = normalized_repository.clone_url
            except GitRepositoryNormalizationError:
                pass

            if normalized_git_url != project.git_repo_url:
                project.git_repo_url = normalized_git_url
                project.save(update_fields=['git_repo_url'])

            initializer._log('info', 'init_method', f"Cloning repository: {normalized_git_url}")
            initializer.init_from_clone(normalized_git_url, project.branch, credential=clone_credential)
            # After cloning, attempt to provision compose-defined services
            try:
                initializer.provision_compose_services(project)
            except ComposeParseError as exc:
                initializer._log('warning', 'provision_services', f"Failed to parse compose file: {exc}")
        elif project.creation_method == 'template' and project.template:
            initializer._log('info', 'init_method', f"Initializing from template: {project.template.name}")
            template_data = project.template.file_structure
            initializer.init_from_template(template_data)
        elif project.creation_method == 'chat':
            initializer._log('info', 'init_method', "Initializing from AI-generated content")
            # AI-generated files should be stored in project.pod.config['ai_files']
            if hasattr(project, 'pod') and project.pod:
                ai_files = project.pod.config.get('ai_files', {})
                if ai_files:
                    initializer.init_from_chat(ai_files)
                else:
                    # Fallback to blank if no AI files
                    initializer._log('warning', 'init_method', "No AI files found, falling back to blank workspace")
                    initializer.init_blank_workspace()
            else:
                initializer.init_blank_workspace()
        else:
            # Default to blank workspace
            initializer._log('info', 'init_method', "Defaulting to blank workspace")
            initializer.init_blank_workspace()
            
        # Mark workspace as initialized in pod config
        if hasattr(project, 'pod') and project.pod:
            project.pod.config['workspace_initialized'] = True
            project.pod.config['workspace_volume'] = volume_name
            project.pod.save(update_fields=['config'])
        
        initializer._log('info', 'init_complete', "Workspace initialization completed successfully")
            
    except WorkspaceInitializerError as exc:
        initializer._log('error', 'init_failed', f"Workspace initialization failed: {exc}")
        # Log the error but don't fail project creation
        print(f"Warning: Failed to initialize workspace for project {project.id}: {exc}")
        raise
