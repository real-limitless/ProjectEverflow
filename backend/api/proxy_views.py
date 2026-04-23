"""
ASGI proxy view for webtop access.
Forwards HTTP and WebSocket traffic to container services without exposing host ports.
"""
import aiohttp
from django.http import HttpResponse, HttpResponseForbidden
from django.views import View
from django.views.decorators.clickjacking import xframe_options_exempt
from django.utils.decorators import method_decorator
from asgiref.sync import sync_to_async
from urllib.parse import urlparse, parse_qs

from .models import Project, ProjectPod, ProjectService
from .podman_orchestrator import PodmanOrchestrator


def user_has_project_access_sync(user, project):
    """Synchronous project access check."""
    if not project:
        return False
    if project.owner_id == user.id:
        return True
    if project.contributors.filter(id=user.id).exists():
        return True
    # Check if user is in the project's team
    if project.team and project.team.members.filter(id=user.id).exists():
        return True
    return False


@method_decorator(xframe_options_exempt, name='dispatch')
class WebtopProxyView(View):
    """
    Proxy HTTP and WebSocket requests to the webtop container.
    Path: /api/projects/{project_id}/webtop-proxy/{path}
    """
    
    async def dispatch(self, request, project_id, path=''):
        """Handle both HTTP and WebSocket requests."""
        # Check authentication
        # if not request.user.is_authenticated:
        #     return HttpResponseForbidden('Authentication required')
        
        # Get project and check access
        try:
            project = await sync_to_async(Project.objects.get)(pk=project_id)
        except Project.DoesNotExist:
            return HttpResponse('Project not found', status=404)
        
        has_access = await sync_to_async(user_has_project_access_sync)(request.user, project)
        # if not has_access:
        #     return HttpResponseForbidden('Access denied')
        
        # Get webtop service
        try:
            pod = await sync_to_async(ProjectPod.objects.get)(project=project)
            service = await sync_to_async(ProjectService.objects.get)(pod=pod, name='webtop')
        except (ProjectPod.DoesNotExist, ProjectService.DoesNotExist):
            return HttpResponse('Webtop service not found', status=404)
        
        # Resolve container address
        orchestrator = PodmanOrchestrator()
        
        # Check if the webtop container actually exists and is running
        container_name = orchestrator._generate_container_name(project_id, 'webtop')
        if not orchestrator._container_exists(container_name):
            return HttpResponse(
                'Webtop container is not running. Try starting or reprovisioning the project.',
                status=503,
                content_type='text/plain'
            )
        
        target_address = orchestrator.resolve_service_address(project_id, 'webtop', 3000)
        # Include SUBFOLDER prefix to match NGINX routes in the container
        subfolder_prefix = f'/api/projects/{project_id}/webtop-proxy'
        target_url = f'http://{target_address}{subfolder_prefix}/{path}'
        
        # Check if WebSocket upgrade
        if request.META.get('HTTP_UPGRADE', '').lower() == 'websocket':
            return await self._proxy_websocket(request, target_url)
        else:
            return await self._proxy_http(request, target_url, subfolder_prefix)
    
    async def _proxy_http(self, request, target_url, subfolder_prefix: str):
        """Proxy HTTP request."""
        # Prepare headers (exclude hop-by-hop headers)
        headers = {}
        excluded_headers = {
            'host', 'connection', 'keep-alive', 'proxy-authenticate',
            'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade'
        }
        
        for key, value in request.META.items():
            if key.startswith('HTTP_'):
                header_name = key[5:].replace('_', '-').lower()
                if header_name not in excluded_headers:
                    headers[header_name] = value
        
        # Forward request
        async with aiohttp.ClientSession() as session:
            try:
                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    data=request.body,
                    allow_redirects=False,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    # Stream response back
                    content = await response.read()
                    
                    # Get content type as string
                    content_type = str(response.content_type) if response.content_type else 'text/html'
                    
                    django_response = HttpResponse(
                        content=content,
                        status=response.status,
                        content_type=content_type
                    )
                    
                    # Copy response headers - ensure all are strings
                    # Exclude x-frame-options from backend and let Django handle it
                    for key, value in response.headers.items():
                        key_lower = str(key).lower()
                        if key_lower not in excluded_headers and key_lower not in ['content-type', 'x-frame-options']:
                            django_response[str(key)] = str(value)
                    
                    # Rewrite redirects to stay under the proxy prefix
                    if 300 <= response.status < 400:
                        loc = response.headers.get('Location') or response.headers.get('location')
                        if loc:
                            try:
                                parsed = urlparse(loc)
                                new_path = None
                                if parsed.scheme and parsed.netloc:
                                    # Absolute URL, take only path
                                    new_path = parsed.path or '/'
                                else:
                                    # Relative or root path
                                    new_path = loc
                                if new_path.startswith('/'):
                                    django_response['Location'] = f"{subfolder_prefix}{new_path}"
                                else:
                                    # relative path, join with prefix
                                    django_response['Location'] = f"{subfolder_prefix}/{new_path}"
                            except Exception:
                                pass

                    # Check if this is HTML content and inject JWT token for WebSocket auth
                    content_type_lower = content_type.lower()
                    if 'text/html' in content_type_lower and b'</body>' in content:
                        # Extract token from query parameters
                        from urllib.parse import parse_qs
                        query_dict = parse_qs(request.META.get('QUERY_STRING', ''))
                        token = (query_dict.get('token') or [None])[0]
                        
                        if token:
                            # Inject script to override WebSocket constructor to include JWT token
                            token_script = f'''
<script>
(function() {{
    const originalWebSocket = window.WebSocket;
    const token = '{token}';
    window.WebSocket = function(url, protocols) {{
        console.log('[Token Injection] Original WebSocket URL:', url);
        
        if (typeof url === 'string') {{
            // Add token to any relative URL (e.g., /api/projects/3/webtop-proxy/...)
            if (url.startsWith('/')) {{
                const separator = url.includes('?') ? '&' : '?';
                url = url + separator + 'token=' + token;
                console.log('[Token Injection] Added token to relative URL:', url);
            }}
            // Add token to absolute URLs pointing to localhost:8000
            else if (url.includes('localhost:8000')) {{
                const separator = url.includes('?') ? '&' : '?';
                url = url + separator + 'token=' + token;
                console.log('[Token Injection] Added token to absolute URL:', url);
            }}
            // Add token to ws:// URLs from any origin (for container direct access)
            else if (url.startsWith('ws://') || url.startsWith('wss://')) {{
                const separator = url.includes('?') ? '&' : '?';
                url = url + separator + 'token=' + token;
                console.log('[Token Injection] Added token to WebSocket URL:', url);
            }}
        }}
        
        console.log('[Token Injection] Final WebSocket URL:', url);
        return new originalWebSocket(url, protocols);
    }};
    // Copy prototype and static methods
    window.WebSocket.prototype = originalWebSocket.prototype;
    window.WebSocket.CONNECTING = originalWebSocket.CONNECTING;
    window.WebSocket.OPEN = originalWebSocket.OPEN;
    window.WebSocket.CLOSING = originalWebSocket.CLOSING;
    window.WebSocket.CLOSED = originalWebSocket.CLOSED;
}})();
</script>
</body>'''
                            # Replace closing body tag with our script
                            content = content.replace(b'</body>', token_script.encode())
                            django_response.content = content
                    
                    # The @xframe_options_exempt decorator prevents Django from adding X-Frame-Options
                    # Explicitly ensure it's not set to allow iframe embedding
                    if 'X-Frame-Options' in django_response:
                        del django_response['X-Frame-Options']
                    
                    return django_response
            except aiohttp.ClientError as exc:
                return HttpResponse(
                    f'Bad Gateway: Could not connect to webtop service. '
                    f'The container may still be starting up. Error: {exc}',
                    status=502,
                    content_type='text/plain'
                )
            except Exception as exc:
                return HttpResponse(f'Internal error: {exc}', status=500)
    
    async def _proxy_websocket(self, request, target_url):
        """
        Handle WebSocket upgrade requests.
        
        Note: Django's standard HTTP views cannot directly handle WebSocket protocol upgrades.
        WebSocket connections to this endpoint should be routed through Django Channels ASGI
        configuration (see asgi.py), which has WebtopProxyConsumer configured to handle
        connections at the same path pattern.
        
        This method is called when a WebSocket upgrade is detected on an HTTP request,
        which indicates a misconfiguration in the ASGI routing.
        """
        ws_url = target_url.replace('http://', 'ws://', 1)
        
        print(f"[WebSocketProxy] WebSocket upgrade request received")
        print(f"[WebSocketProxy] This should be handled by ASGI/Channels, not HTTP view")
        print(f"[WebSocketProxy] Target would be: {ws_url}")
        print(f"[WebSocketProxy] Make sure ASGI is properly configured in asgi.py")
        
        # Return 426 Upgrade Required to indicate client should retry via WebSocket protocol
        return HttpResponse(
            'WebSocket upgrade requires ASGI/Channels handler. '
            'This endpoint is configured in asgi.py for WebSocket connections. '
            'Ensure your ASGI server (Daphne) is running and routing is correct.',
            status=426,
            content_type='text/plain'
        )


async def webtop_proxy_view(request, project_id, path=''):
    """Async function-based view wrapper."""
    view = WebtopProxyView()
    return await view.dispatch(request, project_id, path)
