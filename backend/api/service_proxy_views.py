"""
HTTP Proxy for compose services in workspace containers.
Proxies to any compose service by service ID and port.
"""
import aiohttp
import logging
from urllib.parse import urljoin

from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.decorators import method_decorator
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import Project, ProjectService
from .podman_orchestrator import PodmanOrchestrator
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


def user_has_project_access_sync(user, project: Project) -> bool:
    """Check if user has access to project (synchronous)."""
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


async def authenticate_from_token(request):
    """
    Authenticate user from JWT token in query params or Authorization header.
    Returns the authenticated user or None.
    """
    from django.contrib.auth.models import AnonymousUser
    
    token = None
    
    # Try Authorization header first
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
    
    # Fallback to query parameter
    if not token:
        token = request.GET.get('token')
    
    if not token:
        return None
    
    try:
        authenticator = JWTAuthentication()
        
        class DummyReq:
            META = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        
        auth_result = await sync_to_async(authenticator.authenticate)(DummyReq())
        if auth_result:
            user, _ = auth_result
            return user
    except Exception as e:
        logger.warning(f"JWT authentication failed: {e}")
    
    return None


@method_decorator(xframe_options_exempt, name='dispatch')
class ServiceProxyView(View):
    """
    Proxy HTTP requests to compose services running in project containers.
    Path: /api/projects/{project_id}/service-proxy/{service_id}/{port}/{path}
    """
    
    async def dispatch(self, request, project_id: int, service_id: int, port: int, path: str = ''):
        """Handle HTTP requests to compose services."""
        
        # Authenticate from token (query param or header)
        user = await authenticate_from_token(request)
        if not user:
            return HttpResponseForbidden('Authentication required')
        
        try:
            # Get and validate project
            try:
                project = await sync_to_async(Project.objects.get)(pk=project_id)
            except Project.DoesNotExist:
                return HttpResponse('Project not found', status=404)
            
            has_access = await sync_to_async(user_has_project_access_sync)(user, project)
            if not has_access:
                return HttpResponseForbidden('Access denied')
            
            # Get service by ID and verify it belongs to this project
            try:
                service = await sync_to_async(
                    lambda: ProjectService.objects.select_related('pod__project').get(pk=service_id)
                )()
            except ProjectService.DoesNotExist:
                return HttpResponse('Service not found', status=404)
            
            if service.pod.project_id != project_id:
                return HttpResponse('Service not found', status=404)
            
            if service.status != 'running':
                return HttpResponse(f'Service {service.name} is not running', status=503)
            
            # Validate port is exposed by this service (if ports are defined)
            service_ports = [str(p) for p in (service.ports or [])]
            if service_ports and str(port) not in service_ports:
                return HttpResponse(f'Port {port} not exposed by service', status=400)
            
            # Resolve container address using orchestrator (gets IP address)
            orchestrator = PodmanOrchestrator()
            target_address = await sync_to_async(
                orchestrator.resolve_service_address
            )(project_id, service.name, port)
            target_url = f"http://{target_address}"
            
            # Build request path - exclude 'token' from query params forwarded to target
            request_path = f"/{path}" if path else "/"
            query_params = request.GET.copy()
            query_params.pop('token', None)  # Don't forward auth token
            if query_params:
                request_path += f"?{query_params.urlencode()}"
            
            full_url = urljoin(target_url, request_path)
            
            logger.debug(f"Proxying service request to {full_url}")
            
            # Set up headers - use resolved address for Host
            headers = {
                'Host': target_address,
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
                meta_key = f'HTTP_{header.upper().replace("-", "_")}'
                if meta_key in request.META:
                    headers[header] = request.META[meta_key]
            
            # Make async request
            return await self._proxy_http(request, full_url, headers)
            
        except Exception as e:
            logger.error(f"Service proxy error: {e}", exc_info=True)
            return HttpResponse('Internal server error', status=500)
    
    async def _proxy_http(self, request, target_url: str, headers: dict):
        """Proxy the HTTP request to target URL."""
        try:
            async with aiohttp.ClientSession() as session:
                method = request.method.lower()
                
                # Prepare request data
                data = None
                if method in ['post', 'put', 'patch']:
                    data = request.body if request.body else None
                
                async with session.request(
                    method=method,
                    url=target_url,
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
                    ]
                    
                    for header in response_headers:
                        if header in response.headers:
                            http_response[header] = response.headers[header]
                    
                    # Add CORS headers for iframe embedding
                    http_response['Access-Control-Allow-Origin'] = '*'
                    http_response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS'
                    http_response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                    
                    return http_response
                    
        except aiohttp.ClientError as e:
            logger.error(f"Service proxy connection error: {e}")
            return HttpResponse(f'Failed to connect to service: {str(e)}', status=502)


async def service_proxy_view(request, project_id, service_id, port, path=''):
    """Async function-based view wrapper."""
    view = ServiceProxyView()
    return await view.dispatch(request, int(project_id), int(service_id), int(port), path)
