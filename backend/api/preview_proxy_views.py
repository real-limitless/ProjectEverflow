"""
HTTP Proxy for live preview dev server in workspace containers.
Similar to webtop_proxy_view but forwards to dev server on port 5173.
"""
import asyncio
import aiohttp
import logging
from typing import Optional
from urllib.parse import urljoin

from django.http import HttpResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import Project, ProjectService, ProjectPod
from asgiref.sync import sync_to_async

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


@api_view(['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
@permission_classes([IsAuthenticated])
async def preview_proxy_view(request, project_id: int = None, path: str = None):
    """
    HTTP proxy for live preview server running in workspace container.
    
    Forwards requests to container:5173 (or configured preview port).
    
    GET /api/projects/{id}/preview-proxy/{path}
    """
    try:
        # Get and validate project
        try:
            project = await sync_to_async(Project.objects.get)(pk=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if not user_has_project_access(request.user, project):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        
        # Get workspace service
        try:
            pod = await sync_to_async(ProjectPod.objects.get)(project=project)
            service = await sync_to_async(
                ProjectService.objects.get
            )(pod=pod, service_type='ai-workspace')
        except (ProjectPod.DoesNotExist, ProjectService.DoesNotExist):
            return Response(
                {'error': 'Workspace not provisioned'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        if service.status != 'running':
            return Response(
                {'error': 'Workspace is not running'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        # Build target URL to container
        # Use container name as DNS (assumes containers can resolve each other)
        target_host = service.container_name
        target_port = 5173  # Standard dev server port
        target_url = f"http://{target_host}:{target_port}"
        
        # Build request path
        request_path = f"/{path}" if path else "/"
        if request.GET:
            request_path += f"?{request.GET.urlencode()}"
        
        full_url = urljoin(target_url, request_path)
        
        logger.debug(f"Proxying preview request to {full_url}")
        
        # Set up headers
        headers = {
            'Host': f'{target_host}:{target_port}',
        }
        
        # Copy relevant headers from client request
        forwarded_headers = [
            'Accept',
            'Accept-Encoding',
            'Accept-Language',
            'Cache-Control',
            'Content-Type',
            'User-Agent',
            'Referer',
            'Origin',
        ]
        
        for header in forwarded_headers:
            if header in request.META:
                meta_key = f'HTTP_{header.upper().replace("-", "_")}'
                if meta_key in request.META:
                    headers[header] = request.META[meta_key]
        
        # Make async request
        try:
            async with aiohttp.ClientSession() as session:
                method = request.method.lower()
                
                # Prepare request data
                data = None
                if method in ['post', 'put', 'patch']:
                    data = request.body if request.body else None
                
                async with session.request(
                    method=method,
                    url=full_url,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=30),
                    allow_redirects=True,
                ) as response:
                    # Read response content
                    content = await response.content.read()
                    
                    # Build response
                    http_response = HttpResponse(content, status=response.status)
                    
                    # Copy relevant response headers
                    response_headers = [
                        'Content-Type',
                        'Content-Length',
                        'Cache-Control',
                        'ETag',
                        'Last-Modified',
                        'Set-Cookie',
                        'Access-Control-Allow-Origin',
                    ]
                    
                    for header, value in response.headers.items():
                        if header in response_headers:
                            http_response[header] = value
                    
                    # Add CORS headers for dev mode
                    http_response['Access-Control-Allow-Origin'] = '*'
                    http_response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, OPTIONS'
                    http_response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                    
                    return http_response
        
        except asyncio.TimeoutError:
            logger.error(f"Timeout proxying to {full_url}")
            return Response(
                {'error': 'Preview server timeout'},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except aiohttp.ClientError as e:
            logger.error(f"Error proxying to {full_url}: {e}")
            return Response(
                {'error': f'Preview server error: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
    
    except Exception as e:
        logger.error(f"Error in preview_proxy_view: {e}", exc_info=True)
        return Response(
            {'error': 'Internal server error'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
