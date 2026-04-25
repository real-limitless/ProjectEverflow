"""
Workspace file system API for managing project files in containers.
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, NotFound, ValidationError
from django.utils import timezone
from django.http import StreamingHttpResponse

from .models import Project, ProjectService, ProjectPod
from .podman_orchestrator import PodmanOrchestrator, OrchestratorError

logger = logging.getLogger(__name__)


def user_has_project_access(user, project: Project) -> bool:
    """Check if user has access to project."""
    if not project:
        return False
    owner_id = project.owner.id if hasattr(project.owner, 'id') else project.owner_id
    if owner_id == user.id:
        return True
    if project.contributors.filter(id=user.id).exists():
        return True
    if project.team and project.team.members.filter(id=user.id).exists():
        return True
    return False


class WorkspaceFileViewSet(viewsets.ViewSet):
    """
    API for managing files in project workspaces.
    
    Endpoints:
    - GET /api/projects/{project_id}/workspace/files/tree/
    - GET /api/projects/{project_id}/workspace/files/read/{path}
    - POST /api/projects/{project_id}/workspace/files/create/
    - PUT /api/projects/{project_id}/workspace/files/update/{path}
    - DELETE /api/projects/{project_id}/workspace/files/delete/{path}
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
            
            # Try to find the workspace service - could be 'workspace' or 'workspace-shared'
            # depending on workspace mode
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
    
    def _build_file_tree(self, container_name: str, path: str = '/workspace', level: int = 0) -> Dict[str, Any]:
        """
        Build file tree structure using optimized single find command.
        
        Returns:
        {
            'name': 'filename',
            'type': 'file|folder',
            'path': '/workspace/relative/path',
            'children': [...] (only for folders)
        }
        """
        # Escape path for shell safety
        safe_path = path.replace("'", "'\\''")
        
        # Use single find command with printf to get all files and their types at once
        # Format: type|path (f=file, d=directory, l=symlink)
        cmd = f"find '{safe_path}' -printf '%y|%p\\n' 2>/dev/null | sort -t'|' -k2"
        result = self._execute_in_container(container_name, cmd)
        
        if not result['success']:
            logger.warning(f"Failed to list directory {path}: {result['stderr']}")
            return None
        
        # Parse output and build hierarchical structure
        lines = [line for line in result['stdout'].strip().split('\n') if line]
        if not lines:
            return None
        
        # Build path map for quick lookup
        path_map = {}
        for line in lines:
            if '|' not in line:
                continue
            file_type, file_path = line.split('|', 1)
            path_map[file_path] = {
                'name': os.path.basename(file_path) or 'workspace',
                'type': 'folder' if file_type == 'd' else 'file',
                'path': file_path,
                'children': [] if file_type == 'd' else None
            }
        
        # Build tree structure by linking parents and children
        for file_path, node in path_map.items():
            if file_path == path:
                continue
            parent_path = os.path.dirname(file_path)
            if parent_path in path_map and path_map[parent_path]['children'] is not None:
                path_map[parent_path]['children'].append(node)
        
        # Return root node
        root = path_map.get(path)
        if not root:
            # If root not found, create it
            root = {
                'name': os.path.basename(path) or 'workspace',
                'type': 'folder',
                'path': path,
                'children': [node for p, node in path_map.items() if os.path.dirname(p) == path]
            }
        
        return root
    
    def get_file_tree(self, request, project_id: int = None):
        """
        GET /api/projects/{project_id}/workspace/files/tree/
        Get complete file tree of workspace.
        """
        project = self._get_project(project_id)
        container_name = self._get_workspace_container(project)
        
        try:
            tree = self._build_file_tree(container_name)
            return Response({
                'success': True,
                'tree': tree,
                'timestamp': timezone.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Error building file tree: {e}")
            return Response({
                'success': False,
                'error': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def read_file(self, request, project_id: int = None, filepath: str = None):
        """
        GET /api/projects/{project_id}/workspace/files/read/{filepath}
        Read file content from workspace.
        """
        project = self._get_project(project_id)
        container_name = self._get_workspace_container(project)
        
        if not filepath:
            raise ValidationError('filepath is required')
        
        # Security: Prevent directory traversal
        filepath = filepath.lstrip('/')
        
        # Handle paths that already include 'workspace/' prefix to avoid duplication
        if filepath.startswith('workspace/'):
            full_path = f'/{filepath}'
        else:
            full_path = f'/workspace/{filepath}'
        
        # Check if path tries to escape workspace
        if not full_path.startswith('/workspace/') and full_path != '/workspace':
            raise PermissionDenied('Access denied: path outside workspace')
        
        # Read file
        safe_path = full_path.replace("'", "'\\''")
        cmd = f"cat '{safe_path}'"
        result = self._execute_in_container(container_name, cmd)
        
        if not result['success']:
            if 'Is a directory' in result['stderr']:
                return Response({
                    'error': 'Path is a directory, not a file',
                }, status=status.HTTP_400_BAD_REQUEST)
            return Response({
                'error': 'File not found or cannot be read',
                'details': result['stderr'],
            }, status=status.HTTP_404_NOT_FOUND)
        
        return Response({
            'success': True,
            'path': full_path,
            'content': result['stdout'],
        })
    
    def create_file(self, request, project_id: int = None):
        """
        POST /api/projects/{project_id}/workspace/files/create/
        Create new file in workspace.
        
        Request body:
        {
            'path': 'src/components/Button.tsx',
            'content': '...'
        }
        """
        project = self._get_project(project_id)
        container_name = self._get_workspace_container(project)
        
        filepath = request.data.get('path', '').strip()
        content = request.data.get('content', '')
        
        if not filepath:
            raise ValidationError('path is required')
        
        # Security: Prevent directory traversal
        filepath = filepath.lstrip('/')
        
        # Handle paths that already include 'workspace/' prefix to avoid duplication
        if filepath.startswith('workspace/'):
            full_path = f'/{filepath}'
        else:
            full_path = f'/workspace/{filepath}'
        
        if not full_path.startswith('/workspace/') and full_path != '/workspace':
            raise PermissionDenied('Access denied: path outside workspace')
        
        # Create directory if needed
        directory = os.path.dirname(full_path)
        safe_dir = directory.replace("'", "'\\''")
        mkdir_cmd = f"mkdir -p '{safe_dir}'"
        mkdir_result = self._execute_in_container(container_name, mkdir_cmd)
        
        if not mkdir_result['success']:
            logger.error(f"Failed to create directory {directory}: {mkdir_result['stderr']}")
            return Response({
                'error': 'Failed to create directory',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Write file using temporary file to support large files
        import tempfile
        import os as os_module
        
        # Create temporary file with content
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp') as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Copy file into container
            orchestrator = self.orchestrator if hasattr(self, 'orchestrator') and self.orchestrator else PodmanOrchestrator()
            copy_result = orchestrator._run(['cp', tmp_path, f'{container_name}:{full_path}'])
            
            if copy_result.returncode != 0:
                write_result = {'success': False, 'stderr': copy_result.stderr or 'Copy failed'}
            else:
                write_result = {'success': True}
        finally:
            # Clean up temp file
            try:
                os_module.unlink(tmp_path)
            except:
                pass
        
        if not write_result['success']:
            logger.error(f"Failed to write file {full_path}: {write_result['stderr']}")
            return Response({
                'error': 'Failed to create file',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': True,
            'path': full_path,
            'message': 'File created successfully',
        }, status=status.HTTP_201_CREATED)
    
    def update_file(self, request, project_id: int = None, filepath: str = None):
        """
        PUT /api/projects/{project_id}/workspace/files/update/{filepath}
        Update file content in workspace.
        
        Request body:
        {
            'content': '...'
        }
        """
        project = self._get_project(project_id)
        container_name = self._get_workspace_container(project)
        
        if not filepath:
            raise ValidationError('filepath is required')
        
        content = request.data.get('content', '')
        
        # Security: Prevent directory traversal
        filepath = filepath.lstrip('/')
        
        # Handle paths that already include 'workspace/' prefix to avoid duplication
        if filepath.startswith('workspace/'):
            full_path = f'/{filepath}'
        else:
            full_path = f'/workspace/{filepath}'
        
        if not full_path.startswith('/workspace/') and full_path != '/workspace':
            raise PermissionDenied('Access denied: path outside workspace')
        
        # Write file using temporary file to support large files
        import tempfile
        import os as os_module
        
        # Create temporary file with content
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tmp') as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # Copy file into container
            orchestrator = self.orchestrator if hasattr(self, 'orchestrator') and self.orchestrator else PodmanOrchestrator()
            copy_result = orchestrator._run(['cp', tmp_path, f'{container_name}:{full_path}'])
            
            if copy_result.returncode != 0:
                write_result = {'success': False, 'stderr': copy_result.stderr or 'Copy failed'}
            else:
                write_result = {'success': True}
        finally:
            # Clean up temp file
            try:
                os_module.unlink(tmp_path)
            except:
                pass
        
        if not write_result['success']:
            logger.error(f"Failed to update file {full_path}: {write_result['stderr']}")
            return Response({
                'error': 'Failed to update file',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': True,
            'path': full_path,
            'message': 'File updated successfully',
        })
    
    def delete_file(self, request, project_id: int = None, filepath: str = None):
        """
        DELETE /api/projects/{project_id}/workspace/files/delete/{filepath}
        Delete file from workspace.
        """
        project = self._get_project(project_id)
        container_name = self._get_workspace_container(project)
        
        if not filepath:
            raise ValidationError('filepath is required')
        
        # Security: Prevent directory traversal
        filepath = filepath.lstrip('/')
        
        # Handle paths that already include 'workspace/' prefix to avoid duplication
        if filepath.startswith('workspace/'):
            full_path = f'/{filepath}'
        else:
            full_path = f'/workspace/{filepath}'
        
        if not full_path.startswith('/workspace/') and full_path != '/workspace':
            raise PermissionDenied('Access denied: path outside workspace')
        
        # Delete file
        safe_path = full_path.replace("'", "'\\''")
        delete_cmd = f"rm -rf '{safe_path}'"
        delete_result = self._execute_in_container(container_name, delete_cmd)
        
        if not delete_result['success']:
            logger.error(f"Failed to delete {full_path}: {delete_result['stderr']}")
            return Response({
                'error': 'Failed to delete file',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': True,
            'path': full_path,
            'message': 'File deleted successfully',
        })    
    
    def get_git_status(self, request, project_id: int = None):
        """
        GET /api/projects/{project_id}/workspace/files/git-status/
        Get git status showing uncommitted changes.
        Returns structured data about modified, staged, and untracked files.
        """
        project = self._get_project(project_id)
        container_name = self._get_workspace_container(project)
        
        # Run git status --porcelain to get machine-readable output
        git_cmd = "cd /workspace && git status --porcelain 2>&1"
        result = self._execute_in_container(container_name, git_cmd)

    @action(detail=True, methods=['post'], url_path='workspace/files/analyze')
    def analyze_file(self, request, project_id: int = None):
        """
        POST /api/projects/{project_id}/workspace/files/analyze/
        Analyze a file in the workspace. Supports quick and deep (chunked) analysis.

        Request body:
        {
            'path': 'src/components/Button.tsx',
            'mode': 'quick'|'deep',
            'session_id': <optional chat session id to stream progress>,
        }
        """
        project = self._get_project(project_id)
        container_name = self._get_workspace_container(project)

        path = (request.data.get('path') or request.query_params.get('path') or '').strip()
        mode = (request.data.get('mode') or request.query_params.get('mode') or 'quick').lower()
        session_id = request.data.get('session_id') or request.query_params.get('session_id')

        if not path:
            raise ValidationError('path is required')

        # Normalize path similar to read_file
        filepath = path.lstrip('/')
        if filepath.startswith('workspace/'):
            full_path = f'/{filepath}'
        else:
            full_path = f'/workspace/{filepath}'

        if not full_path.startswith('/workspace/') and full_path != '/workspace':
            raise PermissionDenied('Access denied: path outside workspace')

        # Read file content
        safe_path = full_path.replace("'", "'\\''")
        cmd = f"cat '{safe_path}'"
        result = self._execute_in_container(container_name, cmd, timeout=120)

        if not result['success']:
            return Response({
                'error': 'File not found or cannot be read',
                'details': result.get('stderr')
            }, status=status.HTTP_404_NOT_FOUND)

        content = result['stdout'] or ''

        # Quick analysis: metadata and lightweight heuristics
        def quick_summary(text: str) -> dict:
            import re
            lines = text.split('\n') if text else []
            todos = []
            for i, line in enumerate(lines, start=1):
                if 'TODO' in line or 'FIXME' in line:
                    todos.append({'line': i, 'text': line.strip()})
            lang = os.path.splitext(full_path)[1].lstrip('.') or 'text'
            first = text[:2000]
            last = text[-500:]
            return {
                'lines': len(lines),
                'chars': len(text),
                'lang': lang,
                'first_chars': first,
                'last_chars': last,
                'todos': todos,
                'requires_deep': len(text) > 5000
            }

        # Deep analysis: chunk file and send progress events (if session_id provided)
        def analyze_deep_sync(text: str, group_name: str | None = None):
            import math
            from asgiref.sync import async_to_sync
            channel_layer = None
            if group_name:
                from channels.layers import get_channel_layer
                channel_layer = get_channel_layer()

            CHUNK_SIZE = 4000  # characters
            chunks = [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
            summaries = []
            total = len(chunks)
            print(f"Starting deep analysis: {total} chunks for group {group_name}")
            for idx, ch in enumerate(chunks, start=1):
                # Simple heuristic summary for chunk
                lines = ch.split('\n')
                todo_count = sum(1 for l in lines if 'TODO' in l or 'FIXME' in l)
                func_count = sum(1 for l in lines if l.strip().startswith(('def ', 'function ', 'const ', 'class ')))
                long_lines = sum(1 for l in lines if len(l) > 200)
                snippet = ch[:1000]
                summary = {
                    'chunk_index': idx,
                    'total_chunks': total,
                    'lines': len(lines),
                    'todos': todo_count,
                    'functions': func_count,
                    'long_lines': long_lines,
                    'snippet': snippet,
                }
                summaries.append(summary)

                # Send progress event if group available
                if channel_layer and group_name:
                    payload = {
                        'type': 'analyze_chunk',
                        'chunk_index': idx,
                        'total_chunks': total,
                        'summary': summary,
                        'progress': int((idx / total) * 100)
                    }
                    try:
                        print(f"Sending analyze_chunk {idx}/{total} to group {group_name}")
                        async_to_sync(channel_layer.group_send)(group_name, {'type': 'analyze_update', 'payload': payload})
                        print(f"Sent analyze_chunk {idx}/{total}")
                    except Exception as e:
                        # Log but continue
                        print(f"Failed to send analyze update: {e}")

            # Final summary
            final = {
                'chunks': summaries,
                'total_chunks': total,
                'total_lines': sum(s['lines'] for s in summaries),
                'total_todos': sum(s['todos'] for s in summaries),
                'total_functions': sum(s['functions'] for s in summaries),
            }
            if channel_layer and group_name:
                try:
                    print(f"Sending analyze_complete to group {group_name}")
                    async_to_sync(channel_layer.group_send)(group_name, {'type': 'analyze_update', 'payload': {'type': 'analyze_complete', 'final': final}})
                    print(f"Sent analyze_complete to group {group_name}")
                except Exception as e:
                    print(f"Failed to send final analyze update: {e}")
            else:
                if group_name and channel_layer is None:
                    print(f"Channel layer unavailable; cannot send analyze_complete to group {group_name}")
            return final

        if mode == 'quick':
            return Response({'success': True, 'mode': 'quick', 'summary': quick_summary(content)})
        elif mode == 'deep':
            # If session_id is provided, validate access and run in background thread to stream events
            group_name = None
            if session_id:
                from .models import ChatSession
                try:
                    session = ChatSession.objects.get(pk=int(session_id))
                    if session.project_id != project.id:
                        return Response({'error': 'Session does not belong to this project'}, status=status.HTTP_400_BAD_REQUEST)
                    group_name = f"langgraph_session_{session_id}"
                except ChatSession.DoesNotExist:
                    return Response({'error': 'Session not found'}, status=status.HTTP_404_NOT_FOUND)

            # Run in background thread to avoid blocking request
            import threading
            thread = threading.Thread(target=analyze_deep_sync, args=(content, group_name), daemon=True)
            thread.start()

            # If streaming requested, send an initial 'analyze_started' event to the session group
            streaming = bool(group_name)
            if streaming:
                try:
                    from asgiref.sync import async_to_sync
                    from channels.layers import get_channel_layer
                    channel_layer = get_channel_layer()
                    if channel_layer is None:
                        print(f"Channel layer is not configured; cannot stream analyze_started to group {group_name}")
                    else:
                        async_to_sync(channel_layer.group_send)(group_name, {'type': 'analyze_update', 'payload': {'type': 'analyze_started', 'message': 'Deep analysis started'}})
                except Exception as e:
                    print(f"Failed to send analyze_started event: {e}")

            return Response({
                'success': True,
                'mode': 'deep',
                'message': 'Deep analysis started',
                'chunks_estimated': max(1, (len(content) // 4000) + 1),
                'streaming': streaming,
                'session_id': int(session_id) if session_id else None
            })
        else:
            raise ValidationError('mode must be quick or deep')

    @action(detail=False, methods=['POST'], url_path='analyze-stream')
    def analyze_stream(self, request, project_id: int = None):
        """
        POST /api/projects/{project_id}/workspace/files/analyze-stream/
        Analyze a file with SSE streaming for real-time progress.

        Request body:
        {
            'path': 'src/components/Button.tsx',
            'mode': 'quick'|'deep' (default: 'quick'),
        }

        Response: SSE stream with events
        - 'analyze_start' - Analysis started
        - 'analyze_progress' - Progress event with chunk summary
        - 'analyze_complete' - Final results
        - 'analyze_error' - Error occurred
        """
        project = self._get_project(project_id)
        container_name = self._get_workspace_container(project)

        path = (request.data.get('path') or request.query_params.get('path') or '').strip()
        mode = (request.data.get('mode') or request.query_params.get('mode') or 'quick').lower()

        if not path:
            raise ValidationError('path is required')

        # Normalize path similar to read_file
        filepath = path.lstrip('/')
        if filepath.startswith('workspace/'):
            full_path = f'/{filepath}'
        else:
            full_path = f'/workspace/{filepath}'

        if not full_path.startswith('/workspace/') and full_path != '/workspace':
            raise PermissionDenied('Access denied: path outside workspace')

        # Read file content
        safe_path = full_path.replace("'", "'\\''")
        cmd = f"cat '{safe_path}'"
        result = self._execute_in_container(container_name, cmd, timeout=120)

        if not result['success']:
            def error_stream():
                yield f'data: {json.dumps({"type": "analyze_error", "message": "File not found or cannot be read", "details": result.get("stderr")})}\n\n'
            return StreamingHttpResponse(error_stream(), content_type='text/event-stream')

        content = result['stdout'] or ''

        def event_stream():
            """Generator that yields SSE events for file analysis."""
            try:
                # Send start event
                yield f'data: {json.dumps({"type": "analyze_start", "path": full_path})}\n\n'

                if mode == 'quick':
                    # Quick analysis
                    import re
                    lines = content.split('\n') if content else []
                    todos = []
                    for i, line in enumerate(lines, start=1):
                        if 'TODO' in line or 'FIXME' in line:
                            todos.append({'line': i, 'text': line.strip()})

                    lang = os.path.splitext(full_path)[1].lstrip('.') or 'text'
                    summary = {
                        'lines': len(lines),
                        'chars': len(content),
                        'lang': lang,
                        'todos': todos,
                        'requires_deep': len(content) > 5000
                    }
                    yield f'data: {json.dumps({"type": "analyze_progress", "summary": summary, "progress": 100})}\n\n'

                elif mode == 'deep':
                    # Deep analysis with progress
                    CHUNK_SIZE = 4000  # characters
                    chunks = [content[i:i+CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]
                    total = len(chunks)
                    summaries = []

                    for idx, chunk in enumerate(chunks, start=1):
                        # Simple heuristic summary for chunk
                        lines = chunk.split('\n')
                        todo_count = sum(1 for l in lines if 'TODO' in l or 'FIXME' in l)
                        func_count = sum(1 for l in lines if l.strip().startswith(('def ', 'function ', 'const ', 'class ')))
                        long_lines = sum(1 for l in lines if len(l) > 200)
                        snippet = chunk[:500]

                        chunk_summary = {
                            'chunk_index': idx,
                            'total_chunks': total,
                            'lines': len(lines),
                            'todos': todo_count,
                            'functions': func_count,
                            'long_lines': long_lines,
                            'snippet': snippet,
                        }
                        summaries.append(chunk_summary)

                        # Send progress event for this chunk
                        progress = int((idx / total) * 100)
                        yield f'data: {json.dumps({"type": "analyze_progress", "chunk": chunk_summary, "progress": progress})}\n\n'

                    # Final summary
                    final = {
                        'chunks': summaries,
                        'total_chunks': total,
                        'total_lines': sum(s['lines'] for s in summaries),
                        'total_todos': sum(s['todos'] for s in summaries),
                        'total_functions': sum(s['functions'] for s in summaries),
                    }
                    yield f'data: {json.dumps({"type": "analyze_complete", "summary": final})}\n\n'

                else:
                    yield f'data: {json.dumps({"type": "analyze_error", "message": "Invalid mode. Must be quick or deep."})}\n\n'

            except Exception as e:
                logger.error(f"Error in analyze stream: {e}")
                yield f'data: {json.dumps({"type": "analyze_error", "message": str(e)})}\n\n'

        return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
        
        if not result['success']:
            return Response({
                'error': 'Failed to get git status',
                'details': result.get('error', 'Unknown error'),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Check if it's not a git repository
        if 'not a git repository' in result['stderr'].lower():
            return Response({
                'is_git_repo': False,
                'modified': [],
                'staged': [],
                'untracked': [],
                'deleted': [],
                'total_changes': 0,
            })
        
        # Parse porcelain output
        # Format: XY PATH where X=index status, Y=working tree status
        # Status codes:
        # ' ' = unmodified
        # M = modified
        # A = added
        # D = deleted
        # R = renamed
        # C = copied
        # U = updated but unmerged
        # ? = untracked
        # ! = ignored
        
        lines = result['stdout'].strip().split('\n') if result['stdout'].strip() else []
        
        staged = []
        modified = []
        untracked = []
        deleted = []
        
        for line in lines:
            if not line:
                continue
            
            # Porcelain format: 2 character status + space + path
            if len(line) < 3:
                continue
            
            index_status = line[0]
            worktree_status = line[1]
            filepath = line[3:]  # Skip the two status chars and space
            
            # Staged changes (index status)
            if index_status in ['M', 'A', 'R', 'C']:
                staged.append({
                    'path': filepath,
                    'status': 'added' if index_status == 'A' else 'modified',
                })
            elif index_status == 'D':
                staged.append({
                    'path': filepath,
                    'status': 'deleted',
                })
            
            # Working tree changes (not staged)
            if worktree_status == 'M':
                modified.append({
                    'path': filepath,
                    'status': 'modified',
                })
            elif worktree_status == 'D':
                deleted.append({
                    'path': filepath,
                    'status': 'deleted',
                })
            elif worktree_status == '?':
                untracked.append({
                    'path': filepath,
                    'status': 'untracked',
                })
        
        total_changes = len(staged) + len(modified) + len(untracked) + len(deleted)
        
        return Response({
            'is_git_repo': True,
            'staged': staged,
            'modified': modified,
            'untracked': untracked,
            'deleted': deleted,
            'total_changes': total_changes,
            'has_uncommitted_changes': total_changes > 0,
        })