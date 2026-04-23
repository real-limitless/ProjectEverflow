"""
Git operations API for managing repository in project workspaces.
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError

from .models import Project, ProjectService, ProjectPod
from .podman_orchestrator import PodmanOrchestrator, OrchestratorError
from .workspace_file_views import user_has_project_access

logger = logging.getLogger(__name__)


class GitViewSet(viewsets.ViewSet):
    """
    API for Git operations in project workspaces.
    
    Endpoints:
    - GET /api/projects/{project_id}/workspace/git/branches/
    - GET /api/projects/{project_id}/workspace/git/commits/
    - GET /api/projects/{project_id}/workspace/git/remote-status/
    - POST /api/projects/{project_id}/workspace/git/pull/
    - POST /api/projects/{project_id}/workspace/git/push/
    - POST /api/projects/{project_id}/workspace/git/fetch/
    - POST /api/projects/{project_id}/workspace/git/checkout/
    - POST /api/projects/{project_id}/workspace/git/commit/
    - POST /api/projects/{project_id}/workspace/git/rebase/
    """
    
    permission_classes = [permissions.IsAuthenticated]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orchestrator = PodmanOrchestrator()
    
    def _get_project(self, project_id: int) -> Project:
        """Get project and check access."""
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            raise NotFound('Project not found')
        
        if not user_has_project_access(self.request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        return project
    
    def _get_workspace_container(self, project: Project) -> str:
        """Get the ai-workspace container name for the project."""
        try:
            pod = ProjectPod.objects.get(project=project)
            service = ProjectService.objects.filter(
                pod=pod,
                service_type='ai-workspace'
            ).first()
            
            if not service:
                raise NotFound('Workspace not provisioned. Please start the workspace first.')
            
            return service.container_name
        except ProjectPod.DoesNotExist:
            raise NotFound('Workspace not provisioned. Please start the workspace first.')
    
    def _execute_in_container(
        self,
        container_name: str,
        command: str,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """Execute command in container and return result."""
        try:
            result = self.orchestrator._run(
                ['exec', container_name, 'sh', '-c', command],
                timeout=timeout
            )
            return {
                'success': True,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode,
            }
        except OrchestratorError as e:
            logger.error(f"Container execution failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'stdout': '',
                'stderr': str(e),
            }
    
    @action(detail=False, methods=['get'])
    def branches(self, request, project_id=None):
        """Get list of all branches (local and remote)."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            # Get current branch
            current_cmd = "git rev-parse --abbrev-ref HEAD"
            current_result = self._execute_in_container(container_name, current_cmd)
            current_branch = current_result.get('stdout', 'main').strip() if current_result['success'] else 'main'
            
            # Get all branches with upstream tracking info
            cmd = "git branch -a --format='%(refname:short)|%(upstream:short)|%(if)%(HEAD)%(then)*%(else) %(end)'"
            result = self._execute_in_container(container_name, cmd)
            
            if not result['success']:
                raise ValidationError(f"Failed to fetch branches: {result['stderr']}")
            
            branches = []
            for line in result['stdout'].strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('|')
                branch_name = parts[0].strip().replace('*', '').strip()
                upstream = parts[1].strip() if len(parts) > 1 else None
                is_current = '*' in parts[2] if len(parts) > 2 else False
                is_remote = branch_name.startswith('remotes/')
                
                if branch_name:
                    branches.append({
                        'name': branch_name.replace('remotes/origin/', '') if is_remote else branch_name,
                        'fullName': branch_name,
                        'isRemote': is_remote,
                        'isCurrent': is_current,
                        'upstream': upstream,
                    })
            
            return Response({
                'success': True,
                'currentBranch': current_branch,
                'branches': branches,
            })
        except (NotFound, PermissionDenied, ValidationError) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error fetching branches: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def commits(self, request, project_id=None):
        """Get list of recent commits."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            limit = request.query_params.get('limit', 50)
            branch = request.query_params.get('branch', 'HEAD')
            
            # Get commits with detailed format
            cmd = f"git log {branch} --pretty=format:'%H|%h|%s|%an|%ad|%aI' -n {limit} --date=short"
            result = self._execute_in_container(container_name, cmd)
            
            if not result['success']:
                raise ValidationError(f"Failed to fetch commits: {result['stderr']}")
            
            commits = []
            for line in result['stdout'].strip().split('\n'):
                if not line:
                    continue
                
                parts = line.split('|')
                if len(parts) >= 6:
                    commits.append({
                        'hash': parts[0].strip(),
                        'shortHash': parts[1].strip(),
                        'message': parts[2].strip(),
                        'author': parts[3].strip(),
                        'date': parts[4].strip(),
                        'timestamp': parts[5].strip(),
                    })
            
            return Response({
                'success': True,
                'commits': commits,
                'count': len(commits),
            })
        except (NotFound, PermissionDenied, ValidationError) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error fetching commits: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def remote_status(self, request, project_id=None):
        """Get remote tracking status - ahead/behind commits."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            # First fetch latest from remote
            fetch_cmd = "git fetch origin"
            self._execute_in_container(container_name, fetch_cmd)
            
            # Get current branch
            branch_cmd = "git rev-parse --abbrev-ref HEAD"
            branch_result = self._execute_in_container(container_name, branch_cmd)
            current_branch = branch_result.get('stdout', '').strip() or 'main'
            
            # Get remote tracking branch
            tracking_cmd = f"git rev-parse --abbrev-ref --symbolic-full-name @{{u}}"
            tracking_result = self._execute_in_container(container_name, tracking_cmd)
            tracking_branch = tracking_result.get('stdout', '').strip()
            
            if not tracking_branch:
                tracking_branch = f"origin/{current_branch}"
            
            # Count commits ahead and behind
            ahead_cmd = f"git rev-list --count {tracking_branch}..HEAD"
            ahead_result = self._execute_in_container(container_name, ahead_cmd)
            ahead_count = int(ahead_result.get('stdout', '0').strip()) if ahead_result['success'] else 0
            
            behind_cmd = f"git rev-list --count HEAD..{tracking_branch}"
            behind_result = self._execute_in_container(container_name, behind_cmd)
            behind_count = int(behind_result.get('stdout', '0').strip()) if behind_result['success'] else 0
            
            # Get list of commits ahead
            ahead_commits_cmd = f"git log {tracking_branch}..HEAD --pretty=format:'%h|%s' --reverse"
            ahead_commits_result = self._execute_in_container(container_name, ahead_commits_cmd)
            
            ahead_commits = []
            if ahead_commits_result['success']:
                for line in ahead_commits_result['stdout'].strip().split('\n'):
                    if line:
                        parts = line.split('|', 1)
                        if len(parts) == 2:
                            ahead_commits.append({'hash': parts[0], 'message': parts[1]})
            
            # Get list of commits behind
            behind_commits_cmd = f"git log HEAD..{tracking_branch} --pretty=format:'%h|%s' --reverse"
            behind_commits_result = self._execute_in_container(container_name, behind_commits_cmd)
            
            behind_commits = []
            if behind_commits_result['success']:
                for line in behind_commits_result['stdout'].strip().split('\n'):
                    if line:
                        parts = line.split('|', 1)
                        if len(parts) == 2:
                            behind_commits.append({'hash': parts[0], 'message': parts[1]})
            
            return Response({
                'success': True,
                'currentBranch': current_branch,
                'trackingBranch': tracking_branch,
                'aheadCount': ahead_count,
                'behindCount': behind_count,
                'aheadCommits': ahead_commits,
                'behindCommits': behind_commits,
                'needsPull': behind_count > 0,
                'needsPush': ahead_count > 0,
            })
        except (NotFound, PermissionDenied) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error fetching remote status: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def pull(self, request, project_id=None):
        """Pull latest changes from remote."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            cmd = "git pull"
            result = self._execute_in_container(container_name, cmd, timeout=60)
            
            if not result['success']:
                return Response({
                    'success': False,
                    'error': result['stderr'],
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'message': 'Pull completed successfully',
                'output': result['stdout'],
            })
        except (NotFound, PermissionDenied) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error pulling: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def push(self, request, project_id=None):
        """Push commits to remote."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            branch = request.data.get('branch')
            force = request.data.get('force', False)
            
            if not branch:
                # Get current branch
                result = self._execute_in_container(container_name, "git rev-parse --abbrev-ref HEAD")
                branch = result.get('stdout', 'main').strip()
            
            cmd = f"git push {'--force' if force else ''} origin {branch}".strip()
            result = self._execute_in_container(container_name, cmd, timeout=60)
            
            if not result['success']:
                return Response({
                    'success': False,
                    'error': result['stderr'],
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'message': f'Push to {branch} completed successfully',
                'output': result['stdout'],
            })
        except (NotFound, PermissionDenied) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error pushing: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def fetch(self, request, project_id=None):
        """Fetch from remote without merging."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            cmd = "git fetch origin"
            result = self._execute_in_container(container_name, cmd, timeout=60)
            
            if not result['success']:
                return Response({
                    'success': False,
                    'error': result['stderr'],
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'message': 'Fetch completed successfully',
                'output': result['stdout'],
            })
        except (NotFound, PermissionDenied) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error fetching: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def checkout(self, request, project_id=None):
        """Checkout a branch."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            branch = request.data.get('branch')
            if not branch:
                raise ValidationError('branch is required')
            
            cmd = f"git checkout {branch}"
            result = self._execute_in_container(container_name, cmd)
            
            if not result['success']:
                return Response({
                    'success': False,
                    'error': result['stderr'],
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'message': f'Checked out {branch}',
                'output': result['stdout'],
            })
        except (NotFound, PermissionDenied, ValidationError) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error checking out: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def commit(self, request, project_id=None):
        """Create a commit with specified message."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            message = request.data.get('message')
            all_changes = request.data.get('all', True)  # Stage all changes by default
            
            if not message:
                raise ValidationError('message is required')
            
            # Escape message for shell
            safe_message = message.replace("'", "'\\''")
            
            # Stage changes if all_changes is true
            if all_changes:
                stage_cmd = "git add -A"
                self._execute_in_container(container_name, stage_cmd)
            
            # Commit
            cmd = f"git commit -m '{safe_message}'"
            result = self._execute_in_container(container_name, cmd)
            
            if not result['success']:
                return Response({
                    'success': False,
                    'error': result['stderr'],
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'message': 'Commit created successfully',
                'output': result['stdout'],
            })
        except (NotFound, PermissionDenied, ValidationError) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error committing: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def rebase(self, request, project_id=None):
        """Rebase current branch onto another branch."""
        try:
            project = self._get_project(project_id)
            container_name = self._get_workspace_container(project)
            
            branch = request.data.get('branch')
            if not branch:
                raise ValidationError('branch is required')
            
            cmd = f"git rebase {branch}"
            result = self._execute_in_container(container_name, cmd, timeout=60)
            
            if not result['success']:
                return Response({
                    'success': False,
                    'error': result['stderr'],
                }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': True,
                'message': f'Rebase onto {branch} completed',
                'output': result['stdout'],
            })
        except (NotFound, PermissionDenied, ValidationError) as e:
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error rebasing: {e}")
            return Response({'success': False, 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
