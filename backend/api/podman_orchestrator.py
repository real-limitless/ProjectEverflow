"""
Podman implementation of the Orchestrator interface.
"""
import json
import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from django.conf import settings
from django.utils import timezone

from .orchestrator import (
    Orchestrator, 
    OrchestratorError, 
    ServiceSpec, 
    ServiceStatus, 
    LogEntry
)
from .models import Project, ProjectPod, ProjectService


class PodmanOrchestrator(Orchestrator):
    """Podman-based container orchestration."""
    
    def __init__(self):
        self.binary = os.getenv('PODMAN_BIN', 'podman')
    
    def _run(
        self, 
        args: List[str], 
        capture_output: bool = True, 
        check: bool = True,
        timeout: Optional[int] = None
    ) -> subprocess.CompletedProcess:
        """Execute podman command."""
        command = [self.binary] + args
        # logging.info(f"Executing podman command: {' '.join(command)}")
        try:
            result = subprocess.run(
                command,
                capture_output=capture_output,
                check=check,
                text=True,
                timeout=timeout,
            )
            if result.stdout:
                logging.debug(f"Command stdout: {result.stdout}")
            if result.stderr:
                logging.debug(f"Command stderr: {result.stderr}")
            return result
        except subprocess.CalledProcessError as exc:
            logging.error(f"Podman command failed: {' '.join(command)} - stderr: {exc.stderr} - stdout: {exc.stdout}", exc_info=True)
            raise OrchestratorError(exc.stderr or exc.stdout or str(exc)) from exc
        except FileNotFoundError as exc:
            logging.error(f"Podman binary not found: {self.binary}", exc_info=True)
            raise OrchestratorError('Podman binary not found. Please install Podman or set PODMAN_BIN.') from exc
        except subprocess.TimeoutExpired as exc:
            logging.error(f"Podman command timed out after {timeout}s: {' '.join(command)}", exc_info=True)
            raise OrchestratorError(f'Command timed out after {timeout}s') from exc
    
    def _get_project(self, project_id: int) -> Project:
        """Retrieve project or raise error."""
        try:
            return Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            raise OrchestratorError(f'Project {project_id} not found')
    
    def _generate_pod_name(self, project_id: int) -> str:
        """Generate consistent pod name for a project."""
        return f"proj-pod-{project_id}"
    
    def _generate_container_name(self, project_id: int, service_name: str) -> str:
        """Generate container name."""
        pod_name = self._generate_pod_name(project_id)
        return f"{pod_name}-{service_name}"[:250]
    
    def _pod_exists(self, pod_name: str) -> bool:
        """Check if pod exists."""
        try:
            result = self._run(['pod', 'exists', pod_name], check=False)
            return result.returncode == 0
        except OrchestratorError:
            return False
    
    def _container_exists(self, container_name: str) -> bool:
        """Check if container exists."""
        try:
            result = self._run(['container', 'exists', container_name], check=False)
            return result.returncode == 0
        except OrchestratorError:
            return False
    
    def _get_container_status(self, container_name: str) -> str:
        """Get container status from podman inspect."""
        try:
            result = self._run(['inspect', '--format', '{{.State.Status}}', container_name])
            raw_status = result.stdout.strip()
            # Normalize status for frontend
            if raw_status in ('exited', 'stopped', 'created', 'configured'):
                return 'stopped'
            elif raw_status in ('running', 'up'):
                return 'running'
            elif raw_status in ('paused',):
                return 'paused'
            else:
                return raw_status
        except OrchestratorError:
            return 'unknown'
    
    def _network_exists(self, network_name: str) -> bool:
        """Check if network exists."""
        try:
            result = self._run(['network', 'exists', network_name], check=False)
            return result.returncode == 0
        except OrchestratorError:
            return False
    
    def ensure_network(self, network_name: str) -> None:
        """Ensure network exists."""
        if not self._network_exists(network_name):
            self._run(['network', 'create', network_name])
    
    def _volume_exists(self, volume_name: str) -> bool:
        """Check if volume exists."""
        try:
            result = self._run(['volume', 'exists', volume_name], check=False)
            return result.returncode == 0
        except OrchestratorError:
            return False
    
    def ensure_pod(self, project_id: int) -> str:
        """Ensure pod exists for project."""
        project = self._get_project(project_id)
        pod_name = self._generate_pod_name(project_id)
        
        # Get or create database record
        pod, created = ProjectPod.objects.get_or_create(
            project=project,
            defaults={
                'pod_name': pod_name,
                'status': 'creating',
            }
        )
        
        # Ensure pod exists in Podman
        if not self._pod_exists(pod_name):
            self._run(['pod', 'create', '--name', pod_name])
        
        pod.status = 'running'
        pod.last_synced_at = timezone.now()
        pod.save(update_fields=['status', 'last_synced_at'])
        
        return pod_name
    
    def ensure_service(self, project_id: int, spec: ServiceSpec) -> ServiceStatus:
        """Ensure service is running according to spec."""
        project = self._get_project(project_id)
        pod_name = self.ensure_pod(project_id)
        container_name = self._generate_container_name(project_id, spec.name)
        
        # Get or create database record
        pod = ProjectPod.objects.get(project=project)
        service, created = ProjectService.objects.get_or_create(
            pod=pod,
            name=spec.name,
            defaults={
                'service_type': spec.service_type,
                'image': spec.image,
                'container_name': container_name,
                'ports': spec.ports,
                'environment': spec.environment,
                'status': 'creating',
                'autostart': spec.autostart,
                'cpu_limit': spec.cpu_limit,
                'memory_limit': spec.memory_limit,
                'config': {
                    'depends_on': spec.depends_on,
                    'labels': spec.labels,
                    'workdir': spec.workdir,
                },
            }
        )
        
        # If container doesn't exist, create it
        if not self._container_exists(container_name):
            network_name = spec.network or 'patternfly-network'
            # Ensure network exists
            self.ensure_network(network_name)
            
            # Use network instead of pod for better connectivity
            run_args = ['run', '-d', '--network', network_name, '--name', container_name]
            
            # Add port mappings
            for port_spec in spec.ports:
                run_args += ['-p', port_spec]
            
            # Add environment variables
            for key, value in spec.environment.items():
                run_args += ['-e', f'{key}={value}']

            # Add labels (e.g., Traefik)
            for key, value in spec.labels.items():
                run_args += ['--label', f'{key}={value}']
            
            # Add volume mounts
            for vol in spec.volumes:
                vol_type = vol.get('type', 'volume')
                source = vol.get('source', '')
                target = vol.get('target', '')
                readonly = vol.get('readonly', False)
                
                if vol_type == 'volume':
                    # Ensure volume exists
                    if source and not self._volume_exists(source):
                        self._run(['volume', 'create', source])
                    mount_spec = f'{source}:{target}'
                    if readonly:
                        mount_spec += ':ro'
                    run_args += ['-v', mount_spec]
                elif vol_type == 'bind':
                    mount_spec = f'{source}:{target}'
                    if readonly:
                        mount_spec += ':ro'
                    run_args += ['-v', mount_spec]
            
            # Resource limits
            if spec.cpu_limit:
                run_args += ['--cpus', spec.cpu_limit]
            if spec.memory_limit:
                run_args += ['--memory', spec.memory_limit]

            # Working directory
            if spec.workdir:
                run_args += ['-w', spec.workdir]

            # Add image
            run_args.append(spec.image)
            
            # Add command if specified
            if spec.command:
                run_args += ['sh', '-c', spec.command]
            
            self._run(run_args, timeout=120)
            service.status = 'running'
            service.last_started_at = timezone.now()
            service.save(update_fields=['status', 'last_started_at'])
        else:
            # Container exists, check status
            status = self._get_container_status(container_name)
            service.status = status
            service.save(update_fields=['status'])
        
        return self.get_service_status(project_id, spec.name)
    
    def get_service_status(self, project_id: int, service_name: str) -> ServiceStatus:
        """Get current service status."""
        container_name = self._generate_container_name(project_id, service_name)
        
        if not self._container_exists(container_name):
            return ServiceStatus(
                container_name=container_name,
                status='unknown',
                error_message='Container does not exist'
            )
        
        status = self._get_container_status(container_name)
        
        # Get start time
        started_at = None
        try:
            result = self._run(['inspect', '--format', '{{.State.StartedAt}}', container_name])
            started_str = result.stdout.strip()
            if started_str:
                started_at = datetime.fromisoformat(started_str.replace('Z', '+00:00'))
        except (OrchestratorError, ValueError):
            pass
        
        # Resolve internal address (container name + common port)
        internal_address = f"{container_name}:3000"  # Default, can be made configurable
        
        return ServiceStatus(
            container_name=container_name,
            status=status,
            started_at=started_at,
            internal_address=internal_address
        )
    
    def start_service(self, project_id: int, service_name: str) -> ServiceStatus:
        """Start a stopped service."""
        container_name = self._generate_container_name(project_id, service_name)
        
        if not self._container_exists(container_name):
            raise OrchestratorError(f'Container {container_name} does not exist')
        
        self._run(['start', container_name])
        
        # Update database
        try:
            project = self._get_project(project_id)
            pod = ProjectPod.objects.get(project=project)
            service = ProjectService.objects.get(pod=pod, name=service_name)
            service.status = 'running'
            service.last_started_at = timezone.now()
            service.save(update_fields=['status', 'last_started_at'])
        except (ProjectPod.DoesNotExist, ProjectService.DoesNotExist):
            pass
        
        return self.get_service_status(project_id, service_name)
    
    def stop_service(self, project_id: int, service_name: str) -> ServiceStatus:
        """Stop a running service."""
        container_name = self._generate_container_name(project_id, service_name)
        
        if not self._container_exists(container_name):
            raise OrchestratorError(f'Container {container_name} does not exist')
        
        self._run(['stop', container_name], timeout=30)
        
        # Update database
        try:
            project = self._get_project(project_id)
            pod = ProjectPod.objects.get(project=project)
            service = ProjectService.objects.get(pod=pod, name=service_name)
            service.status = 'stopped'
            service.save(update_fields=['status'])
        except (ProjectPod.DoesNotExist, ProjectService.DoesNotExist):
            pass
        
        return self.get_service_status(project_id, service_name)

    def start_container(self, container_name: str) -> None:
        """Start a container by name (used for bulk operations)."""
        if not self._container_exists(container_name):
            raise OrchestratorError(f'Container {container_name} does not exist')
        self._run(['start', container_name], timeout=60)

    def stop_container(self, container_name: str) -> None:
        """Stop a container by name (used for bulk operations)."""
        if not self._container_exists(container_name):
            raise OrchestratorError(f'Container {container_name} does not exist')
        self._run(['stop', container_name], timeout=30)
    
    def restart_service(self, project_id: int, service_name: str) -> ServiceStatus:
        """Restart a service."""
        container_name = self._generate_container_name(project_id, service_name)
        
        if not self._container_exists(container_name):
            raise OrchestratorError(f'Container {container_name} does not exist')
        
        self._run(['restart', container_name], timeout=60)
        
        # Update database
        try:
            project = self._get_project(project_id)
            pod = ProjectPod.objects.get(project=project)
            service = ProjectService.objects.get(pod=pod, name=service_name)
            service.status = 'running'
            service.last_started_at = timezone.now()
            service.save(update_fields=['status', 'last_started_at'])
        except (ProjectPod.DoesNotExist, ProjectService.DoesNotExist):
            pass
        
        return self.get_service_status(project_id, service_name)
    
    def kill_service(self, project_id: int, service_name: str) -> ServiceStatus:
        """Forcefully kill a service."""
        container_name = self._generate_container_name(project_id, service_name)
        
        if not self._container_exists(container_name):
            raise OrchestratorError(f'Container {container_name} does not exist')
        
        self._run(['kill', container_name])
        
        # Update database
        try:
            project = self._get_project(project_id)
            pod = ProjectPod.objects.get(project=project)
            service = ProjectService.objects.get(pod=pod, name=service_name)
            service.status = 'stopped'
            service.save(update_fields=['status'])
        except (ProjectPod.DoesNotExist, ProjectService.DoesNotExist):
            pass
        
        return self.get_service_status(project_id, service_name)
    
    def get_service_logs(
        self, 
        project_id: int, 
        service_name: str, 
        tail: int = 1000,
        since: Optional[str] = None
    ) -> LogEntry:
        """Retrieve service logs."""
        container_name = self._generate_container_name(project_id, service_name)
        
        if not self._container_exists(container_name):
            raise OrchestratorError(f'Container {container_name} does not exist')
        
        # Enforce max tail limit
        max_tail = getattr(settings, 'MAX_LOG_TAIL_LINES', 5000)
        tail = min(tail, max_tail)
        
        args = ['logs', '--tail', str(tail)]
        if since:
            args += ['--since', since]
        args.append(container_name)
        
        try:
            result = self._run(args, timeout=30)
            logs = result.stdout
            
            # Check if truncated (rough heuristic)
            truncated = len(logs.splitlines()) >= tail
            
            return LogEntry(logs=logs, truncated=truncated)
        except OrchestratorError as exc:
            raise OrchestratorError(f'Failed to retrieve logs: {exc}')
    
    def resolve_service_address(self, project_id: int, service_name: str, port: int) -> str:
        """Resolve internal network address for service."""
        container_name = self._generate_container_name(project_id, service_name)
        print(f"[PodmanOrchestrator] Resolving address for container: {container_name}, port: {port}")
        
        # Try to get the container's IP address in the shared network
        try:
            result = self._run([
                'inspect', 
                container_name,
                '--format', 
                '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
            ])
            ip_address = result.stdout.strip()
            print(f"[PodmanOrchestrator] Found container IP: {ip_address}")
            if ip_address:
                return f"{ip_address}:{port}"
        except OrchestratorError as e:
            print(f"[PodmanOrchestrator] Failed to get container IP: {e}")
        
        # Fallback to container name
        print(f"[PodmanOrchestrator] Using container name as fallback: {container_name}")
        return f"{container_name}:{port}"
    
    def ensure_volume(self, project_id: int, volume_name: str) -> str:
        """Ensure volume exists."""
        full_volume_name = f"proj-{project_id}-{volume_name}"
        
        if not self._volume_exists(full_volume_name):
            self._run(['volume', 'create', full_volume_name])
        
        return full_volume_name
    
    def list_services(self, project_id: int) -> List[ServiceStatus]:
        """List all services for a project."""
        project = self._get_project(project_id)
        
        try:
            pod = ProjectPod.objects.get(project=project)
            services = ProjectService.objects.filter(pod=pod)
            
            statuses = []
            for service in services:
                try:
                    status = self.get_service_status(project_id, service.name)
                    statuses.append(status)
                except OrchestratorError:
                    # Service exists in DB but not in Podman
                    statuses.append(ServiceStatus(
                        container_name=service.container_name,
                        status='unknown',
                        error_message='Container not found'
                    ))
            
            return statuses
        except ProjectPod.DoesNotExist:
            return []
    
    def delete_pod(self, project_id: int, force: bool = False) -> None:
        """Delete pod and all its services."""
        pod_name = self._generate_pod_name(project_id)
        
        if self._pod_exists(pod_name):
            args = ['pod', 'rm']
            if force:
                args.append('-f')
            args.append(pod_name)
            self._run(args, timeout=60)
        
        # Clean up database records
        project = self._get_project(project_id)
        ProjectPod.objects.filter(project=project).delete()
    
    def delete_service(self, project_id: int, service_name: str) -> None:
        """Delete a service container and database record."""
        container_name = self._generate_container_name(project_id, service_name)
        
        # Remove container if it exists
        if self._container_exists(container_name):
            self._run(['rm', '-f', container_name], timeout=30)
        
        # Clean up database record
        project = self._get_project(project_id)
        try:
            pod = ProjectPod.objects.get(project=project)
            ProjectService.objects.filter(pod=pod, name=service_name).delete()
        except ProjectPod.DoesNotExist:
            pass
    
    def _get_workspace_image_tag(self, workspace_image: str) -> str:
        """Map project workspace_image choice to local pre-built image."""
        image_mapping = {
            'fedora:43': 'localhost/fedora-devtools:43',
            'registry.access.redhat.com/ubi9/ubi': 'localhost/ubi9-devtools:latest',
        }
        return image_mapping.get(workspace_image, workspace_image)

    def _image_exists(self, image: str) -> bool:
        """Check whether an image exists locally."""
        try:
            result = self._run(['image', 'exists', image], check=False)
            return result.returncode == 0
        except OrchestratorError:
            return False

    def _get_workspace_image_build_spec(self, image: str) -> Optional[Dict[str, Any]]:
        """Return build configuration for managed local workspace images."""
        build_date = datetime.utcnow().strftime('%Y%m%d')
        workspace_images_dir = Path(
            os.getenv(
                'WORKSPACE_IMAGES_DIR',
                str(Path(__file__).resolve().parent.parent / 'workspace-images'),
            )
        )

        if image.startswith('localhost/fedora-devtools:'):
            return {
                'context': workspace_images_dir,
                'dockerfile': workspace_images_dir / 'Containerfile.fedora',
                'tags': [
                    'localhost/fedora-devtools:43',
                    f'localhost/fedora-devtools:43-{build_date}',
                    'localhost/fedora-devtools:latest',
                ],
            }

        if image.startswith('localhost/ubi9-devtools:'):
            return {
                'context': workspace_images_dir,
                'dockerfile': workspace_images_dir / 'Containerfile.ubi9',
                'tags': [
                    'localhost/ubi9-devtools:latest',
                    f'localhost/ubi9-devtools:{build_date}',
                ],
            }

        return None

    def _build_workspace_image(self, image: str) -> None:
        """Build a managed workspace image locally."""
        build_spec = self._get_workspace_image_build_spec(image)
        if not build_spec:
            raise OrchestratorError(
                f"Workspace image '{image}' is not available locally and no automatic build is configured."
            )

        context_dir = build_spec['context']
        dockerfile = build_spec['dockerfile']
        tags = build_spec['tags']

        if not context_dir.exists():
            raise OrchestratorError(f'Workspace image build context not found: {context_dir}')
        if not dockerfile.exists():
            raise OrchestratorError(f'Workspace image Containerfile not found: {dockerfile}')

        logging.info(
            'Workspace image %s is missing or needs refresh; building managed workspace image',
            image,
        )

        build_args = ['build', '-f', str(dockerfile)]
        for tag in tags:
            build_args += ['-t', tag]
        build_args.append(str(context_dir))

        self._run(build_args, capture_output=False, timeout=1800)

        if not self._image_exists(image):
            raise OrchestratorError(
                f"Workspace image '{image}' was built but is still unavailable locally."
            )

    def _ensure_workspace_image(self, image: str) -> None:
        """Ensure a managed workspace image exists locally before it is used."""
        if self._image_exists(image):
            return
        self._build_workspace_image(image)
    
    def _get_resource_limits(self, workspace_size: str) -> Dict[str, str]:
        """Get CPU and memory limits for workspace based on tier slug."""
        from .models import WorkspaceResourceTier
        
        try:
            tier = WorkspaceResourceTier.objects.get(slug=workspace_size, is_active=True)
            return {
                'cpu': tier.cpu_limit,
                'memory': tier.memory_limit,
            }
        except WorkspaceResourceTier.DoesNotExist:
            # Fallback to default limits
            logging.warning(f"Workspace tier '{workspace_size}' not found, using defaults")
            return {
                'cpu': '2.0',
                'memory': '4g',
            }
    
    def _get_image_digest(self, image: str) -> Optional[str]:
        """Get image digest for tracking updates."""
        if not self._image_exists(image):
            return None
        try:
            result = self._run(['image', 'inspect', '--format', '{{.Digest}}', image])
            return result.stdout.strip() or None
        except OrchestratorError:
            return None
    
    def ensure_workspace_service(self, project_id: int, user_id: Optional[int] = None) -> ServiceStatus:
        """
        Ensure AI workspace service is running for a project.
        
        Args:
            project_id: Project ID
            user_id: User ID for personal workspaces (ignored for shared mode)
        
        Returns:
            ServiceStatus for the workspace container
        """
        project = self._get_project(project_id)
        
        # Determine workspace mode and service name
        if project.workspace_mode == 'personal':
            if not user_id:
                raise OrchestratorError("user_id required for personal workspace mode")
            service_name = f"workspace-{user_id}"
        else:  # shared mode
            service_name = "workspace-shared"
        
        # Get resource limits from tier
        limits = self._get_resource_limits(project.workspace_size)
        
        # Map workspace image to pre-built local image
        local_image = self._get_workspace_image_tag(project.workspace_image)
        self._ensure_workspace_image(local_image)
        
        # Ensure workspace volume exists
        volume_name = self.ensure_volume(project_id, 'workspace')
        
        # Check if service exists and image has changed
        container_name = self._generate_container_name(project_id, service_name)
        pod = ProjectPod.objects.get_or_create(project=project, defaults={
            'pod_name': self._generate_pod_name(project_id),
            'status': 'creating',
        })[0]
        
        service, created = ProjectService.objects.get_or_create(
            pod=pod,
            name=service_name,
            defaults={
                'service_type': 'ai-workspace',
                'image': local_image,
                'container_name': container_name,
                'status': 'creating',
                'config': {},
            }
        )
        
        # Check if image has changed (rebuild needed)
        current_digest = self._get_image_digest(local_image)
        stored_digest = service.config.get('image_digest') if isinstance(service.config, dict) else None
        image_changed = stored_digest and current_digest and stored_digest != current_digest
        
        if image_changed or (self._container_exists(container_name) and service.image != local_image):
            logging.info(f"Workspace image changed for project {project_id}, rebuilding container")
            # Stop and remove old container
            try:
                self._run(['rm', '-f', container_name], timeout=30)
            except OrchestratorError:
                pass
        
        # Create workspace container if it doesn't exist
        if not self._container_exists(container_name):
            # Ensure network exists
            self.ensure_network('patternfly-network')
            
            # Build run command
            run_args = [
                'run', '-d',
                '--network', 'patternfly-network',
                '--name', container_name,
                '--cpus', limits['cpu'],
                '--memory', limits['memory'],
                '-v', f'{volume_name}:/workspace',
                '-w', '/workspace',
            ]
            
            # Add environment variables
            run_args += [
                '-e', f'PROJECT_ID={project_id}',
                '-e', f'WORKSPACE_MODE={project.workspace_mode}',
                '-e', 'COPILOT_MODE=true',
            ]
            
            if user_id:
                run_args += ['-e', f'USER_ID={user_id}']
            
            # Add image
            run_args.append(local_image)
            
            logging.info(f"Creating workspace container: {' '.join(run_args)}")
            self._run(run_args, timeout=120)
            
            # Update service record
            service.image = local_image
            service.status = 'running'
            service.last_started_at = timezone.now()
            service.config = service.config or {}
            service.config['image_digest'] = current_digest
            service.config['resource_limits'] = limits
            service.config['workspace_mode'] = project.workspace_mode
            service.save()
        else:
            # Container exists, check status
            status = self._get_container_status(container_name)
            
            # If container is stopped, start it
            if status == 'stopped':
                logging.info(f"Starting stopped workspace container: {container_name}")
                try:
                    self._run(['start', container_name], timeout=60)
                    status = 'running'
                    service.last_started_at = timezone.now()
                    service.save(update_fields=['status', 'last_started_at'])
                except OrchestratorError as exc:
                    logging.error(f"Failed to start workspace container {container_name}: {exc}")
                    service.status = 'error'
                    service.save(update_fields=['status'])
                    raise
            
            service.status = status
            service.save(update_fields=['status'])
        
        return self.get_service_status(project_id, service_name)
    
    def update_workspace_image(self, project_id: int) -> ServiceStatus:
        """
        Rebuild the managed workspace image and refresh containers.
        
        Args:
            project_id: Project ID
        
        Returns:
            ServiceStatus after rebuild
        """
        try:
            project = self._get_project(project_id)
            local_image = self._get_workspace_image_tag(project.workspace_image)
            
            logging.info(f"Rebuilding workspace image: {local_image}")
            
            # Get current digest
            old_digest = self._get_image_digest(local_image)
            
            self._build_workspace_image(local_image)

            new_digest = self._get_image_digest(local_image)
            
            if old_digest != new_digest:
                logging.info(f"Workspace image updated, digest changed from {old_digest} to {new_digest}")
            
            # Find and rebuild workspace services
            try:
                pod = ProjectPod.objects.get(project=project)
            except ProjectPod.DoesNotExist:
                raise OrchestratorError("Project pod not found. Please ensure workspace first.")
            
            services = ProjectService.objects.filter(pod=pod, service_type='ai-workspace')
            
            if not services.exists():
                raise OrchestratorError("No workspace service found. Please provision workspace first.")
            
            for service in services:
                container_name = service.container_name
                
                # Stop and remove container
                if self._container_exists(container_name):
                    logging.info(f"Removing old workspace container: {container_name}")
                    self._run(['stop', container_name], timeout=30, check=False)
                    self._run(['rm', '-f', container_name], timeout=30)
                
                # Update service config with new digest
                service.config = service.config or {}
                service.config['image_digest'] = new_digest
                service.status = 'stopped'
                service.save()
            
            # Return status (will show as stopped, user needs to start)
            service = services.first()
            return ServiceStatus(
                container_name=service.container_name,
                status='stopped',
                started_at=None,
                internal_address=None
            )
            
        except Exception as e:
            logging.error(f"Error updating workspace image for project {project_id}: {str(e)}", exc_info=True)
            raise OrchestratorError(f"Failed to update workspace image: {str(e)}")
    
    def reset_workspace_volume(self, project_id: int) -> None:
        """
        Reset workspace volume by deleting and recreating it.
        WARNING: This deletes all data in the workspace.
        
        Args:
            project_id: Project ID
        """
        volume_name = f"proj-{project_id}-workspace"
        
        logging.warning(f"Resetting workspace volume: {volume_name}")
        
        # Stop and REMOVE all workspace containers using this volume
        # We must remove (not just stop) to ensure containers are recreated fresh
        # with correct configuration after reset
        try:
            pod = ProjectPod.objects.get(project_id=project_id)
            services = ProjectService.objects.filter(pod=pod, service_type='ai-workspace')
            
            for service in services:
                if self._container_exists(service.container_name):
                    # Force remove the container (stops it first if running)
                    self._run(['rm', '-f', service.container_name], timeout=30, check=False)
                # Delete the database record so the service gets recreated fresh
                service.delete()
        except ProjectPod.DoesNotExist:
            pass
        
        # Remove volume
        if self._volume_exists(volume_name):
            self._run(['volume', 'rm', '-f', volume_name], timeout=30)
        
        # Recreate volume
        self._run(['volume', 'create', volume_name])
        
        # Reinitialize workspace based on project creation method
        from .workspace_initializer import initialize_project_workspace
        project = self._get_project(project_id)
        initialize_project_workspace(project)
