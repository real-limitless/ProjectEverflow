"""
Subdomain-based service proxy middleware.
Routes requests from subdomains like `proj-{project_id}-{service_id}-{port}.localhost`
to the corresponding container service.

This approach allows SPAs (React, Vue, etc.) to work correctly since they see
themselves at the root path `/` instead of a proxy path prefix.
"""
import re
import aiohttp
import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken

from asgiref.sync import sync_to_async, iscoroutinefunction

from .models import Project, ProjectService
from .podman_orchestrator import PodmanOrchestrator

logger = logging.getLogger(__name__)

# Pattern: proj-{project_id}-{service_id}-{port}.localhost
SUBDOMAIN_PATTERN = re.compile(r'^proj-(\d+)-(\d+)-(\d+)\.localhost(?::\d+)?$')

# Cookie name for service proxy auth
SERVICE_PROXY_COOKIE = 'service_proxy_token'

# Cookie expiration - match JWT access token lifetime (15 minutes)
COOKIE_MAX_AGE = 900

# Paths that don't require auth (Vite dev server, source maps, HMR)
AUTH_EXEMPT_PATH_PREFIXES = (
    '/@vite/',
    '/@react-refresh',
    '/@fs/',
    '/node_modules/.vite/',
    '/__vite_ping',
)


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


async def authenticate_from_token(token: str):
    """
    Authenticate user from JWT token.
    Returns the authenticated user or None.
    """
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


class SubdomainProxyMiddleware:
    """
    Middleware to intercept subdomain-based service proxy requests.
    
    Handles requests to subdomains like `proj-{project_id}-{service_id}-{port}.localhost`
    by proxying them to the corresponding container service.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Check if get_response is async
        self._is_async = iscoroutinefunction(get_response)
    
    def __call__(self, request):
        # Parse the host header to check for subdomain pattern
        host = request.get_host().lower()
        match = SUBDOMAIN_PATTERN.match(host)
        
        if not match:
            # Not a subdomain proxy request, continue normally
            return self.get_response(request)
        
        # Extract project_id, service_id, and port from subdomain
        project_id = int(match.group(1))
        service_id = int(match.group(2))
        port = int(match.group(3))
        
        # Handle the proxy request asynchronously
        import asyncio
        from asgiref.sync import async_to_sync
        
        return async_to_sync(self._handle_proxy_request)(request, project_id, service_id, port)
    
    async def _handle_proxy_request(self, request, project_id: int, service_id: int, port: int):
        """Handle the subdomain proxy request."""
        
        # Handle the /auth endpoint at the subdomain
        if request.path == '/auth' or request.path == '/auth/':
            return await self._handle_auth_endpoint(request, project_id, service_id, port)
        
        # Check if this is a Vite dev path that doesn't require auth
        # These are development-only paths that are safe to serve without token
        request_path = request.path
        is_vite_dev_path = any(request_path.startswith(prefix) for prefix in AUTH_EXEMPT_PATH_PREFIXES)
        
        # Also allow .map files (source maps) without auth - they're dev-only
        if request_path.endswith('.map'):
            is_vite_dev_path = True
        
        if is_vite_dev_path:
            logger.debug(f"[SubdomainProxy] Allowing Vite dev path without auth: {request_path}")
            return await self._proxy_without_auth(request, project_id, service_id, port)
        
        # Try to find auth token from multiple sources (in priority order):
        # 1. Cookie (works in new tab)
        # 2. _auth_token in URL (initial iframe load)
        # 3. _auth_token in Referer header (subsequent iframe requests)
        token = request.COOKIES.get(SERVICE_PROXY_COOKIE)
        token_source = 'cookie' if token else None
        
        # If no cookie, check URL parameter
        if not token:
            token = request.GET.get('_auth_token')
            if token:
                token_source = 'url'
        
        # If still no token, check Referer header for _auth_token
        # This handles subsequent requests in iframe where the initial page had the token
        referer = request.META.get('HTTP_REFERER', '')
        if not token and '_auth_token=' in referer:
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(referer)
                params = parse_qs(parsed.query)
                if '_auth_token' in params:
                    token = params['_auth_token'][0]
                    token_source = 'referer'
            except Exception as e:
                logger.debug(f"[SubdomainProxy] Failed to parse referer: {e}")
        
        # If STILL no token, check if this is a same-subdomain request for static assets
        # This handles Vite HMR and dynamic imports that may not have token in Referer
        # Security: We only allow this if the Referer is from the same subdomain
        if not token and referer:
            try:
                from urllib.parse import urlparse
                parsed_referer = urlparse(referer)
                expected_host = f"proj-{project_id}-{service_id}-{port}.localhost"
                
                # Check if referer is from the same subdomain (with or without port)
                referer_host = parsed_referer.netloc.split(':')[0]  # Remove port
                if referer_host == expected_host:
                    # This is a same-subdomain request - likely an asset or HMR request
                    # Allow it through without token (trust the browser's same-origin policy)
                    token_source = 'same-origin-referer'
                    logger.debug(f"[SubdomainProxy] Allowing same-origin request from {referer}")
            except Exception as e:
                logger.debug(f"[SubdomainProxy] Failed to check referer origin: {e}")
        
        logger.debug(f"[SubdomainProxy] Request to proj-{project_id}-{service_id}-{port}{request.path}, "
                     f"token: {'yes' if token else 'no'}, source: {token_source or 'none'}")
        
        # If no token and no same-origin referer, redirect to auth
        if not token and token_source != 'same-origin-referer':
            logger.info(f"[SubdomainProxy] No auth token, redirecting to main app")
            return self._redirect_to_auth(request, project_id, service_id, port)
        
        # If we have a token, validate it and check project access
        if token:
            user = await authenticate_from_token(token)
            if not user:
                # Invalid token - redirect to main app
                return self._redirect_to_auth(request, project_id, service_id, port)
            
            # Validate project access
            try:
                project = await sync_to_async(Project.objects.get)(pk=project_id)
            except Project.DoesNotExist:
                return HttpResponse('Project not found', status=404)
            
            has_access = await sync_to_async(user_has_project_access_sync)(user, project)
            if not has_access:
                return HttpResponseForbidden('Access denied')
        
        # For same-origin requests without token, we trust the browser's same-origin policy
        # The user must have authenticated on the initial page load to get the Referer
        
        # Validate service exists and belongs to project
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
        
        # Resolve container address
        orchestrator = PodmanOrchestrator()
        target_address = await sync_to_async(
            orchestrator.resolve_service_address
        )(project_id, service.name, port)
        
        # Check for WebSocket upgrade
        if request.META.get('HTTP_UPGRADE', '').lower() == 'websocket':
            return await self._proxy_websocket(request, target_address, token)
        
        # Proxy HTTP request
        return await self._proxy_http(request, target_address)
    
    async def _handle_auth_endpoint(self, request, project_id: int, service_id: int, port: int):
        """
        Handle authentication at the subdomain /auth endpoint.
        
        This endpoint:
        1. Accepts a token in the query parameters
        2. Validates the token and checks project access
        3. Sets cookie (for new tab) AND redirects with _auth_token param (for iframe)
        """
        token = request.GET.get('token')
        redirect_path = request.GET.get('redirect', '/')  # Default to root
        
        if not token:
            logger.warning(f"[SubdomainAuth] No token provided to /auth endpoint")
            return HttpResponseForbidden('No token provided')
        
        # Validate token and authenticate user
        user = await authenticate_from_token(token)
        if not user:
            logger.warning(f"[SubdomainAuth] Token validation failed")
            return HttpResponseForbidden('Invalid token')
        
        # Validate project access
        try:
            project = await sync_to_async(Project.objects.get)(pk=project_id)
        except Project.DoesNotExist:
            logger.warning(f"[SubdomainAuth] Project {project_id} not found")
            return HttpResponse('Project not found', status=404)
        
        has_access = await sync_to_async(user_has_project_access_sync)(user, project)
        if not has_access:
            logger.warning(f"[SubdomainAuth] User {user.id} has no access to project {project_id}")
            return HttpResponseForbidden('Access denied')
        
        # All checks passed - redirect with _auth_token in URL
        # This works for both iframe (where cookies are blocked) and new tab (where cookies work)
        # Add _auth_token to redirect URL for iframe support
        if '?' in redirect_path:
            final_url = f"{redirect_path}&_auth_token={token}"
        else:
            final_url = f"{redirect_path}?_auth_token={token}"
        
        logger.info(f"[SubdomainAuth] Token validated for user {user.id}, redirecting to {final_url}")
        
        response = HttpResponseRedirect(final_url)
        
        # Also set cookie for new tab / direct access scenarios
        response.set_cookie(
            SERVICE_PROXY_COOKIE,
            token,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite='Lax',   # Lax works fine for new tab / direct access
            secure=False,
            path='/',
        )
        
        return response
    
    def _redirect_to_auth(self, request, project_id: int, service_id: int, port: int):
        """Redirect to auth endpoint to set cookie.
        
        Note: This is called when no valid cookie exists. Since we don't have a token,
        we redirect to the main app which will handle re-authentication.
        """
        # Build the redirect URL back to this subdomain
        scheme = 'https' if request.is_secure() else 'http'
        host = request.get_host()
        path = request.get_full_path()
        
        # Since we don't have a token, redirect to the main app's project page
        # The user will need to re-authenticate through the normal flow
        main_app_url = f"{scheme}://localhost:8080/my-applications/edit/{project_id}"
        
        logger.info(f"[SubdomainProxy] No auth cookie, redirecting to main app: {main_app_url}")
        
        return HttpResponseRedirect(main_app_url)
    
    async def _proxy_without_auth(self, request, project_id: int, service_id: int, port: int):
        """
        Proxy request to service without authentication.
        Used for static assets (JS, CSS, images, fonts) that don't need protection.
        """
        # Validate service exists and get container address
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
        
        # Resolve container address
        orchestrator = PodmanOrchestrator()
        target_address = await sync_to_async(
            orchestrator.resolve_service_address
        )(project_id, service.name, port)
        
        logger.info(f"[SubdomainProxy] Resolved service {service.name} to {target_address}")
        
        # Proxy the request
        return await self._proxy_http(request, target_address)
    
    async def _proxy_http(self, request, target_address: str):
        """Proxy HTTP request to the target service."""
        target_url = f"http://{target_address}{request.path}"
        
        # Add query string if present (but filter out _auth_token for cleaner proxying)
        query_string = request.META.get('QUERY_STRING', '')
        if query_string:
            # Remove _auth_token from query string before proxying
            from urllib.parse import parse_qs, urlencode
            params = parse_qs(query_string, keep_blank_values=True)
            params.pop('_auth_token', None)
            if params:
                target_url += f"?{urlencode(params, doseq=True)}"
        
        logger.info(f"[SubdomainProxy] Proxying {request.method} {request.path} to {target_url}")
        
        # Build headers
        headers = {
            'Host': target_address,
        }
        
        # Copy relevant headers
        forwarded_headers = [
            'Accept', 'Accept-Encoding', 'Accept-Language',
            'Cache-Control', 'Content-Type', 'User-Agent',
            'Referer', 'Origin', 'Cookie',
        ]
        
        for header in forwarded_headers:
            meta_key = f'HTTP_{header.upper().replace("-", "_")}'
            if meta_key in request.META:
                headers[header] = request.META[meta_key]
        
        # Handle Content-Type for POST/PUT
        if 'CONTENT_TYPE' in request.META:
            headers['Content-Type'] = request.META['CONTENT_TYPE']
        
        try:
            async with aiohttp.ClientSession() as session:
                method = request.method.lower()
                
                # Get request body
                data = None
                if method in ['post', 'put', 'patch']:
                    data = request.body if request.body else None
                
                async with session.request(
                    method=method,
                    url=target_url,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60),
                    allow_redirects=False,  # Let client handle redirects
                ) as response:
                    content = await response.content.read()
                    
                    logger.info(f"[SubdomainProxy] Got response: status={response.status}, "
                               f"content_length={len(content)}, content_type={response.headers.get('Content-Type', 'unknown')}")
                    
                    http_response = HttpResponse(content, status=response.status)
                    
                    # Copy response headers
                    skip_headers = {'transfer-encoding', 'content-encoding', 'connection'}
                    for header, value in response.headers.items():
                        if header.lower() not in skip_headers:
                            http_response[header] = value
                    
                    # Allow iframe embedding
                    if 'X-Frame-Options' in http_response:
                        del http_response['X-Frame-Options']
                    
                    return http_response
                    
        except aiohttp.ClientError as e:
            logger.error(f"[SubdomainProxy] Connection error: {e}")
            return HttpResponse(f'Failed to connect to service: {str(e)}', status=502)
    
    async def _proxy_websocket(self, request, target_address: str, token: str):
        """
        Handle WebSocket upgrade request.
        
        Note: This returns a special response indicating WebSocket should be
        handled by ASGI/Channels. The actual WebSocket proxying is done by
        SubdomainWebSocketConsumer in consumers.py.
        """
        logger.info(f"[SubdomainProxy] WebSocket upgrade request for {target_address}")
        
        # Return 426 to indicate this should be handled by ASGI
        return HttpResponse(
            'WebSocket connections should be handled by ASGI/Channels. '
            'Ensure SubdomainWebSocketConsumer is configured in asgi.py.',
            status=426,
            content_type='text/plain'
        )


@xframe_options_exempt
async def _service_proxy_auth_view_async(request):
    """
    Auth endpoint that validates JWT token and sets a cookie for subdomain access.
    
    GET /api/service-proxy-auth/?token=...&project_id=...&service_id=...&port=...&redirect=...
    
    1. Validates the JWT token from query param
    2. Validates user has access to the project
    3. Sets HttpOnly cookie for the specific subdomain
    4. Redirects to the subdomain URL
    """
    from django.http import HttpResponseBadRequest
    
    # Get parameters
    token = request.GET.get('token')
    project_id = request.GET.get('project_id')
    service_id = request.GET.get('service_id')
    port = request.GET.get('port')
    redirect_url = request.GET.get('redirect')
    
    logger.info(f"[ServiceProxyAuth] Request received - token: {'yes' if token else 'no'}, "
                f"project_id: {project_id}, service_id: {service_id}, port: {port}, "
                f"redirect: {redirect_url}, full_path: {request.get_full_path()}")
    
    if not all([token, project_id, service_id, port, redirect_url]):
        logger.warning(f"[ServiceProxyAuth] Missing params - query_string: {request.META.get('QUERY_STRING', 'none')}")
        return HttpResponseBadRequest('Missing required parameters: token, project_id, service_id, port, redirect')
    
    try:
        project_id = int(project_id)
        service_id = int(service_id)
        port = int(port)
    except ValueError:
        return HttpResponseBadRequest('Invalid project_id, service_id, or port')
    
    # Authenticate user
    user = await authenticate_from_token(token)
    if not user:
        return HttpResponseForbidden('Invalid or expired token')
    
    # Validate project access
    try:
        project = await sync_to_async(Project.objects.get)(pk=project_id)
    except Project.DoesNotExist:
        return HttpResponse('Project not found', status=404)
    
    has_access = await sync_to_async(user_has_project_access_sync)(user, project)
    if not has_access:
        return HttpResponseForbidden('Access denied to project')
    
    # Validate service exists
    try:
        service = await sync_to_async(
            lambda: ProjectService.objects.select_related('pod__project').get(pk=service_id)
        )()
    except ProjectService.DoesNotExist:
        return HttpResponse('Service not found', status=404)
    
    if service.pod.project_id != project_id:
        return HttpResponse('Service not found', status=404)
    
    # Redirect to subdomain's /auth endpoint to set the cookie
    # The /auth endpoint will validate the token, set the cookie, and redirect to the final destination
    # This works because cookies are set by the domain that receives the request
    auth_endpoint = f"{redirect_url}auth/?token={token}&redirect=/"
    
    logger.info(f"[ServiceProxyAuth] Validated, redirecting to subdomain /auth endpoint: {auth_endpoint}")
    
    return HttpResponseRedirect(auth_endpoint)


def service_proxy_auth_view(request):
    """Sync wrapper for the async auth view."""
    """Sync wrapper for the async auth view."""
    from asgiref.sync import async_to_sync
    return async_to_sync(_service_proxy_auth_view_async)(request)
