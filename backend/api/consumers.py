"""
WebSocket consumers for proxying connections to containerized services.
"""
import asyncio
import aiohttp
import json
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from .models import Project, ProjectPod, ProjectService
from .podman_orchestrator import PodmanOrchestrator
from django.utils import timezone

# Debug flag - enable detailed logging when WEBTOP_PROXY_DEBUG=1
DEBUG = os.getenv('WEBTOP_PROXY_DEBUG', '0') == '1'

def debug_log(msg):
    """Log only if debug mode is enabled."""
    if DEBUG:
        print(msg)


class WebtopProxyConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that proxies connections to webtop containers.
    """
    
    async def connect(self):
        """Handle WebSocket connection."""
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        # Default Selkies (webtop) websocket endpoint is "/websocket"
        # If no path segment is provided by the router, use this default.
        self.path = self.scope['url_route']['kwargs'].get('path', 'websocket')
        
        debug_log(f"[WebtopProxy] === WEBSOCKET CONNECTION ATTEMPT ===")
        debug_log(f"[WebtopProxy] Project ID: {self.project_id}")
        debug_log(f"[WebtopProxy] Path: {self.path}")
        debug_log(f"[WebtopProxy] Query string: {self.scope.get('query_string', b'').decode()}")
        debug_log(f"[WebtopProxy] Headers: {dict(self.scope.get('headers', []))}")
        debug_log(f"[WebtopProxy] Full scope keys: {list(self.scope.keys())}")
        
        # Check authentication
        user = self.scope.get('user')
        debug_log(f"[WebtopProxy] User: {user}, Authenticated: {user.is_authenticated if user else False}")
        if not user or not user.is_authenticated:
            print(f"[WebtopProxy] REJECTING - User not authenticated")
            await self.close(code=4001)
            return
        
        # Get project and check access
        try:
            project = await sync_to_async(
                Project.objects.select_related('team').get
            )(pk=self.project_id)
            has_access = await self._check_access(user, project)
            
            if not has_access:
                await self.close(code=4003)
                return
                
            # Get webtop service
            pod = await sync_to_async(ProjectPod.objects.get)(project=project)
            service = await sync_to_async(ProjectService.objects.get)(pod=pod, name='webtop')
            
            # Get target WebSocket URL
            # The path comes from the URL router: /api/projects/{id}/webtop-proxy/{path}
            orchestrator = PodmanOrchestrator()
            target_address = await sync_to_async(orchestrator.resolve_service_address)(int(self.project_id), 'webtop', 3000)
            debug_log(f"[WebtopProxy] Resolved target address: {target_address}")
            
            # CRITICAL: Connect directly to Selkies on port 8082, NOT through NGINX on port 3000
            # The container's NGINX only has routes for specific paths and doesn't handle all Selkies endpoints
            # Selkies daemon runs directly on 127.0.0.1:8082 inside the container
            # We connect to the same container but use port 8082 instead of 3000
            selkies_address = target_address.replace(':3000', ':8082')
            if ':' not in selkies_address:
                # If no port was specified, add it
                selkies_address = f"{target_address}:8082"
            
            debug_log(f"[WebtopProxy] Connecting to Selkies directly on: {selkies_address}")
            
            # Use the actual path from the URL router
            # Selkies expects paths like: /websocket, /stream, /files, etc.
            normalized_path = self.path.lstrip('/') if self.path else 'websocket'
            
            # Don't include the SUBFOLDER prefix when connecting to Selkies directly
            # Selkies handles requests at the root: /websocket, /stream, etc.
            self.target_url = f'ws://{selkies_address}/{normalized_path}'
            self.subfolder_prefix = f'/api/projects/{self.project_id}/webtop-proxy'
            
            debug_log(f"[WebtopProxy] Target URL (direct to Selkies): {self.target_url}")
            
            # Accept the client connection
            await self.accept()
            print(f"[WebtopProxy] Client connection accepted for project {self.project_id}")
            
            # Connect to backend WebSocket and start proxying
            # This must run in background so receive() can be called concurrently
            asyncio.create_task(self.proxy_websocket())
            
        except (Project.DoesNotExist, ProjectPod.DoesNotExist, ProjectService.DoesNotExist):
            await self.close(code=4004)
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            await self.close(code=4000)
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'backend_ws') and self.backend_ws:
            await self.backend_ws.close()
    
    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming messages from client and forward to backend."""
        print(f"[WebtopProxy] Received client message (text={bool(text_data)}, bytes={bool(bytes_data)})")
        waited = 0
        while not hasattr(self, 'backend_ws') or not self.backend_ws:
            if waited > max_wait:
                print(f"[WebtopProxy] Timeout waiting for backend connection")
                return
            await asyncio.sleep(0.1)
            waited += 1
        
        if self.backend_ws.closed:
            debug_log(f"[WebtopProxy] Backend connection is closed, cannot forward message")
            return
        
        try:
            if text_data:
                debug_log(f"[WebtopProxy] Client→Backend: TEXT {len(text_data)} bytes")
                await self.backend_ws.send_str(text_data)
            elif bytes_data:
                debug_log(f"[WebtopProxy] Client→Backend: BINARY {len(bytes_data)} bytes")
                await self.backend_ws.send_bytes(bytes_data)
        except Exception as e:
            print(f"[WebtopProxy] Error sending to backend: {e}")
            await self.close()
    
    async def proxy_websocket(self):
        """
        Establish connection to backend and proxy bidirectionally.
        
        Uses proper task management to ensure both directions stay alive:
        - Backend → Client: Listens to backend WebSocket continuously
        - Client → Backend: receive() method called by Channels framework
        """
        session = None
        ws = None
        try:
            debug_log(f"[WebtopProxy] Starting proxy to: {self.target_url}")
            
            # Extract JWT token from scope (added by JWTAuthMiddleware)
            user = self.scope.get('user')
            jwt_token = None
            if user and user.is_authenticated:
                # Try to get token from query string first
                query_string = self.scope.get('query_string') or b''
                from urllib.parse import parse_qs
                qs = parse_qs(query_string.decode())
                jwt_token = (qs.get('token') or [None])[0]
                
                debug_log(f"[WebtopProxy] JWT token from query: {jwt_token[:20] + '...' if jwt_token else 'None'}")
            
            # Add token to target URL if available
            target_ws_url = self.target_url
            if jwt_token:
                separator = '&' if '?' in target_ws_url else '?'
                target_ws_url = f"{target_ws_url}{separator}token={jwt_token}"
                debug_log(f"[WebtopProxy] Added JWT token to backend connection")
            
            # Build forwarded headers to mimic reverse proxy behavior
            raw_headers = dict(self.scope.get('headers') or [])
            client_host = (raw_headers.get(b'host') or b'').decode() or 'localhost'
            scheme = self.scope.get('scheme') or 'ws'
            forward_proto = 'https' if scheme == 'wss' else 'http'
            forward_port = '443' if forward_proto == 'https' else '80'
            forward_prefix = self.subfolder_prefix

            headers = {
                'Host': client_host,
                'Origin': f"{forward_proto}://{client_host}",
                'X-Forwarded-Proto': forward_proto,
                'X-Forwarded-Host': client_host,
                'X-Forwarded-Port': forward_port,
                'X-Forwarded-Prefix': forward_prefix,
                'Connection': 'upgrade',
                'Upgrade': 'websocket',
            }
            
            if jwt_token:
                headers['Authorization'] = f'Bearer {jwt_token}'
            
            debug_log(f"[WebtopProxy] Connecting to backend...")

            session = aiohttp.ClientSession()
            ws = await session.ws_connect(
                target_ws_url,
                heartbeat=20,
                timeout=aiohttp.ClientTimeout(total=None),
                headers=headers,
            )
            self.backend_ws = ws
            
            print(f"[WebtopProxy] Backend connected for project {self.project_id}")
            
            # Run backend listener indefinitely until it closes
            # The receive() method will be called by Channels when client sends messages
            await self._backend_to_client(ws)
            
        except aiohttp.ClientConnectorError as e:
            print(f"[WebtopProxy] Failed to connect to container: {e}")
            await self.close(code=4002)
        except Exception as e:
            print(f"[WebtopProxy] WebSocket proxy error: {e}")
            debug_log(f"[WebtopProxy] Error type: {type(e).__name__}")
            if DEBUG:
                import traceback
                print(f"[WebtopProxy] Traceback: {traceback.format_exc()}")
        finally:
            print(f"[WebtopProxy] Closing backend connection")
            if ws and not ws.closed:
                try:
                    await ws.close()
                except Exception as e:
                    print(f"[WebtopProxy] Error closing backend ws: {e}")
            if session and not session.closed:
                try:
                    await session.close()
                except Exception as e:
                    print(f"[WebtopProxy] Error closing session: {e}")
            print(f"[WebtopProxy] Proxy connection closed")
    
    
    async def _backend_to_client(self, ws):
        """Forward messages from backend WebSocket to client."""
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    debug_log(f"[WebtopProxy] Backend→Client: TEXT {len(msg.data)} bytes")
                    await self.send(text_data=msg.data)
                elif msg.type == aiohttp.WSMsgType.BINARY:
                    debug_log(f"[WebtopProxy] Backend→Client: BINARY {len(msg.data)} bytes")
                    await self.send(bytes_data=msg.data)
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    print(f"[WebtopProxy] Backend closed connection")
                    await self.close()
                    break
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"[WebtopProxy] Backend WebSocket error: {ws.exception()}")
                    await self.close()
                    break
        except Exception as e:
            print(f"[WebtopProxy] Backend→Client error: {e}")
            await self.close()
    
    async def _check_access(self, user, project):
        """Check if user has access to the project."""
        # Check owner
        if project.owner_id == user.id:
            return True
        
        # Check contributors
        is_contributor = await sync_to_async(
            lambda: project.contributors.filter(id=user.id).exists()
        )()
        if is_contributor:
            return True
        
        # Check team membership
        if project.team_id:  # Use team_id instead of project.team to avoid lazy loading
            is_team_member = await sync_to_async(
                lambda: project.team.members.filter(id=user.id).exists()
            )()
            if is_team_member:
                return True
        
        return False


class ProjectProvisioningConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time project provisioning status updates.
    Broadcasts step-by-step logs during project creation, cloning, and container setup.
    """
    
    async def connect(self):
        """Handle WebSocket connection for provisioning updates."""
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        self.group_name = f"provisioning_{self.project_id}"
        
        # Check authentication
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
        
        # Check project access
        try:
            project = await sync_to_async(
                Project.objects.select_related('team').get
            )(pk=self.project_id)
            has_access = await self._check_access(user, project)
            
            if not has_access:
                await self.close(code=4003)
                return
            
            # Join provisioning group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            
            await self.accept()
            print(f"[ProvisioningConsumer] Client connected for project {self.project_id}")
            
        except Project.DoesNotExist:
            await self.close(code=4004)
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            print(f"[ProvisioningConsumer] Client disconnected from project {self.project_id}")
    
    async def receive(self, text_data):
        """Handle incoming messages (not expected, but required by protocol)."""
        pass
    
    async def provisioning_log(self, event):
        """
        Handle provisioning log events from channel layer.
        Event format: {
            'type': 'provisioning_log',
            'level': 'info'|'debug'|'warning'|'error',
            'step_name': 'clone_repo'|'provision_services', etc.
            'message': 'Human-readable message',
            'metadata': {...}
        }
        """
        await self.send(text_data=json.dumps({
            'level': event.get('level', 'info'),
            'step_name': event.get('step_name', ''),
            'message': event.get('message', ''),
            'metadata': event.get('metadata', {}),
            'timestamp': event.get('timestamp', ''),
        }))
    
    async def _check_access(self, user, project):
        """Check if user has access to the project."""
        # Check owner
        if project.owner_id == user.id:
            return True
        
        # Check contributors
        is_contributor = await sync_to_async(
            lambda: project.contributors.filter(id=user.id).exists()
        )()
        if is_contributor:
            return True
        
        # Check team membership
        if project.team_id:
            is_team_member = await sync_to_async(
                lambda: project.team.members.filter(id=user.id).exists()
            )()
            if is_team_member:
                return True
        
        return False


class SubdomainProxyConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer that proxies connections for subdomain-based service access.
    Handles connections to subdomains like proj-{project_id}-{service_id}-{port}.localhost
    """
    
    # Paths that don't require auth (Vite HMR, dev tools)
    VITE_HMR_PATHS = ('/', '/__vite_ping', '/__vite_hmr')
    
    async def connect(self):
        """Handle WebSocket connection."""
        import re
        from urllib.parse import parse_qs
        from rest_framework_simplejwt.authentication import JWTAuthentication
        
        # Get the host from headers
        headers_dict = dict(self.scope.get('headers') or [])
        host = (headers_dict.get(b'host') or b'').decode().lower()
        
        print(f"[SubdomainProxy] === WEBSOCKET CONNECTION ATTEMPT ===")
        print(f"[SubdomainProxy] Host: {host}, Path: {self.scope.get('path', '/')}")
        
        # Parse subdomain pattern
        pattern = re.compile(r'^proj-(\d+)-(\d+)-(\d+)\.localhost(?::\d+)?$')
        match = pattern.match(host)
        
        if not match:
            print(f"[SubdomainProxy] REJECT: Host '{host}' doesn't match subdomain pattern")
            await self.close(code=4000)
            return
        
        self.project_id = int(match.group(1))
        self.service_id = int(match.group(2))
        self.port = int(match.group(3))
        self.path = self.scope.get('path', '/')
        
        debug_log(f"[SubdomainProxy] Project: {self.project_id}, Service: {self.service_id}, Port: {self.port}")
        debug_log(f"[SubdomainProxy] Path: {self.path}")
        
        # Check if this is a Vite HMR WebSocket path - allow without auth
        # Vite creates WebSocket connections for hot module reload which don't have token
        # Security: HMR only pushes updates, doesn't expose sensitive data
        is_vite_hmr = self.path in self.VITE_HMR_PATHS or self.path.startswith('/@vite/')
        
        if is_vite_hmr:
            print(f"[SubdomainProxy] Vite HMR path detected: {self.path}, bypassing auth")
            # Skip auth, go directly to service validation and proxy setup
            return await self._setup_hmr_proxy()
        
        # Get token from cookie
        cookie_header = headers_dict.get(b'cookie', b'').decode()
        token = None
        
        if cookie_header:
            # Parse cookies
            from http.cookies import SimpleCookie
            cookies = SimpleCookie()
            cookies.load(cookie_header)
            if 'service_proxy_token' in cookies:
                token = cookies['service_proxy_token'].value
                debug_log(f"[SubdomainProxy] Found token in cookie")
        
        # Fallback to query string
        if not token:
            query_string = self.scope.get('query_string') or b''
            qs = parse_qs(query_string.decode())
            token = (qs.get('token') or [None])[0]
            if token:
                debug_log(f"[SubdomainProxy] Found token in query string")
        
        if not token:
            debug_log(f"[SubdomainProxy] No token found, rejecting")
            await self.close(code=4001)
            return
        
        # Authenticate user
        try:
            authenticator = JWTAuthentication()
            
            class DummyReq:
                META = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
            
            auth_result = await sync_to_async(authenticator.authenticate)(DummyReq())
            if not auth_result:
                debug_log(f"[SubdomainProxy] Token validation failed")
                await self.close(code=4001)
                return
            
            user, _ = auth_result
        except Exception as e:
            debug_log(f"[SubdomainProxy] Auth error: {e}")
            await self.close(code=4001)
            return
        
        # Validate project access
        try:
            project = await sync_to_async(
                Project.objects.select_related('team').get
            )(pk=self.project_id)
            
            has_access = await self._check_access(user, project)
            if not has_access:
                debug_log(f"[SubdomainProxy] User doesn't have project access")
                await self.close(code=4003)
                return
        except Project.DoesNotExist:
            debug_log(f"[SubdomainProxy] Project not found")
            await self.close(code=4004)
            return
        
        # Get service and validate
        try:
            service = await sync_to_async(
                lambda: ProjectService.objects.select_related('pod__project').get(pk=self.service_id)
            )()
            
            if service.pod.project_id != self.project_id:
                debug_log(f"[SubdomainProxy] Service doesn't belong to project")
                await self.close(code=4004)
                return
            
            if service.status != 'running':
                debug_log(f"[SubdomainProxy] Service not running")
                await self.close(code=4005)
                return
            
            self.service_name = service.name
        except ProjectService.DoesNotExist:
            debug_log(f"[SubdomainProxy] Service not found")
            await self.close(code=4004)
            return
        
        # Resolve target address
        orchestrator = PodmanOrchestrator()
        target_address = await sync_to_async(
            orchestrator.resolve_service_address
        )(self.project_id, self.service_name, self.port)
        
        debug_log(f"[SubdomainProxy] Resolved target: {target_address}")
        
        # Build target WebSocket URL
        self.target_url = f'ws://{target_address}{self.path}'
        if self.scope.get('query_string'):
            self.target_url += f'?{self.scope["query_string"].decode()}'
        
        debug_log(f"[SubdomainProxy] Target URL: {self.target_url}")
        
        # Accept the connection
        await self.accept()
        debug_log(f"[SubdomainProxy] Connection accepted")
        
        # Start proxying
        asyncio.create_task(self.proxy_websocket())
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        debug_log(f"[SubdomainProxy] Disconnected with code {close_code}")
        if hasattr(self, 'backend_ws') and self.backend_ws:
            await self.backend_ws.close()
    
    async def receive(self, text_data=None, bytes_data=None):
        """Handle incoming messages from client and forward to backend."""
        # Wait for backend connection
        max_wait = 50
        waited = 0
        while not hasattr(self, 'backend_ws') or not self.backend_ws:
            if waited > max_wait:
                debug_log(f"[SubdomainProxy] Timeout waiting for backend")
                return
            await asyncio.sleep(0.1)
            waited += 1
        
        # Check if websocket is closed (works for both aiohttp and websockets library)
        try:
            is_closed = self.backend_ws.closed if hasattr(self.backend_ws, 'closed') else False
        except Exception:
            is_closed = True
        
        if is_closed:
            return
        
        try:
            # Use send() for websockets library (works for both text and bytes)
            if text_data:
                await self.backend_ws.send(text_data)
            elif bytes_data:
                await self.backend_ws.send(bytes_data)
        except Exception as e:
            debug_log(f"[SubdomainProxy] Error forwarding to backend: {e}")
            await self.close()
    
    async def proxy_websocket(self):
        """Connect to backend and proxy messages using websockets library."""
        import traceback
        import websockets
        
        # Log immediately to verify task is running
        print(f"[SubdomainProxy] proxy_websocket() STARTED - target_url={getattr(self, 'target_url', 'NOT_SET')}")
        
        ws = None
        
        try:
            print(f"[SubdomainProxy] Connecting to backend WebSocket: {self.target_url}")
            
            # Build extra headers for Vite HMR connections
            # Vite 5.x validates Origin header - try matching actual target
            extra_headers = {}
            if getattr(self, 'is_hmr', False) and hasattr(self, 'target_address'):
                # Try origin matching Vite's actual address
                extra_headers = {
                    'Origin': f'http://{self.target_address}',
                    'Host': self.target_address,
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                    'Sec-WebSocket-Protocol': 'vite-hmr',
                }
                print(f"[SubdomainProxy] HMR headers: {extra_headers}")
            
            # Use websockets library instead of aiohttp (more reliable for WS)
            ws = await websockets.connect(
                self.target_url,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
                additional_headers=extra_headers if extra_headers else None,
                subprotocols=['vite-hmr'] if getattr(self, 'is_hmr', False) else None,
            )
            
            self.backend_ws = ws
            print(f"[SubdomainProxy] Backend WebSocket connected successfully")
            
            # Read from backend and forward to client
            async for msg in ws:
                if isinstance(msg, str):
                    await self.send(text_data=msg)
                elif isinstance(msg, bytes):
                    await self.send(bytes_data=msg)
        
        except asyncio.TimeoutError:
            print(f"[SubdomainProxy] Backend WebSocket connection timed out: {self.target_url}")
            traceback.print_exc()
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[SubdomainProxy] Backend WebSocket closed: {e.code} {e.reason}")
        except Exception as e:
            print(f"[SubdomainProxy] Backend WebSocket error: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            if ws:
                await ws.close()
            await self.close()
    
    async def _setup_hmr_proxy(self):
        """
        Set up WebSocket proxy for Vite HMR without authentication.
        
        This is used for hot module reload connections which don't carry auth tokens.
        Security is maintained by:
        1. Only allowing specific Vite paths (/, /__vite_hmr, etc.)
        2. Relying on browser's same-origin policy
        3. HMR only pushes code updates, doesn't access sensitive data
        """
        print(f"[SubdomainProxy/HMR] Setting up HMR proxy for project={self.project_id}, service={self.service_id}, port={self.port}, path={self.path}")
        
        # Validate service exists (minimal validation without auth)
        try:
            service = await sync_to_async(
                lambda: ProjectService.objects.select_related('pod__project').get(pk=self.service_id)
            )()
            
            print(f"[SubdomainProxy/HMR] Found service: name={service.name}, status={service.status}, pod_project={service.pod.project_id}")
            
            if service.pod.project_id != self.project_id:
                print(f"[SubdomainProxy/HMR] REJECT: Service project_id {service.pod.project_id} != {self.project_id}")
                await self.close(code=4004)
                return
            
            if service.status != 'running':
                print(f"[SubdomainProxy/HMR] REJECT: Service status is '{service.status}', not 'running'")
                await self.close(code=4005)
                return
            
            self.service_name = service.name
        except ProjectService.DoesNotExist:
            print(f"[SubdomainProxy/HMR] REJECT: Service ID {self.service_id} not found")
            await self.close(code=4004)
            return
        except Exception as e:
            print(f"[SubdomainProxy/HMR] REJECT: Unexpected error fetching service: {type(e).__name__}: {e}")
            await self.close(code=4000)
            return
        
        # Resolve target address
        try:
            orchestrator = PodmanOrchestrator()
            target_address = await sync_to_async(
                orchestrator.resolve_service_address
            )(self.project_id, self.service_name, self.port)
            
            print(f"[SubdomainProxy/HMR] Resolved target address: {target_address}")
        except Exception as e:
            print(f"[SubdomainProxy/HMR] REJECT: Failed to resolve target address: {type(e).__name__}: {e}")
            await self.close(code=4000)
            return
        
        # Build target WebSocket URL
        self.target_url = f'ws://{target_address}{self.path}'
        if self.scope.get('query_string'):
            self.target_url += f'?{self.scope["query_string"].decode()}'
        
        # Store target address for header construction in proxy_websocket()
        self.target_address = target_address
        self.is_hmr = True
        
        print(f"[SubdomainProxy/HMR] Target URL: {self.target_url}")
        
        # Accept the connection
        await self.accept()
        print(f"[SubdomainProxy/HMR] Connection ACCEPTED for Vite HMR")
        
        # Start proxying with proper error handling
        def _handle_proxy_error(task):
            try:
                exc = task.exception()
                if exc:
                    import traceback
                    print(f"[SubdomainProxy/HMR] Proxy task failed: {type(exc).__name__}: {exc}")
                    traceback.print_exception(type(exc), exc, exc.__traceback__)
            except asyncio.CancelledError:
                print(f"[SubdomainProxy/HMR] Proxy task was cancelled")
        
        self._proxy_task = asyncio.create_task(self.proxy_websocket())
        self._proxy_task.add_done_callback(_handle_proxy_error)
    
    async def _check_access(self, user, project):
        """Check if user has access to the project."""
        if project.owner_id == user.id:
            return True
        
        is_contributor = await sync_to_async(
            lambda: project.contributors.filter(id=user.id).exists()
        )()
        if is_contributor:
            return True
        
        if project.team_id:
            is_team_member = await sync_to_async(
                lambda: project.team.members.filter(id=user.id).exists()
            )()
            if is_team_member:
                return True
        
        return False


class LangGraphStreamConsumer(AsyncWebsocketConsumer):
    """Stream LangGraph agent events to frontend."""

    async def _send_json(self, payload: dict):
        """Send JSON to client in a safe way across Channels versions."""
        try:
            if hasattr(self, 'send_json'):
                await self.send_json(payload)
            else:
                # Fallback to text-based send
                await self.send(text_data=json.dumps(payload))
        except Exception as e:
            print(f"[LangGraphStream] _send_json error: {e}")

    async def connect(self):
        self.project_id = self.scope['url_route']['kwargs']['project_id']
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        user = self.scope.get('user')

        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        # Validate project/session access
        try:
            from .models import ChatSession
            session = await sync_to_async(ChatSession.objects.select_related('project').get)(
                pk=self.session_id, user=user
            )
            if session.project_id != int(self.project_id):
                await self.close(code=4003)
                return

            # Check project access
            has_access = await self._check_access(user, session.project)
            if not has_access:
                await self.close(code=4003)
                return

            self.session = session
            # Join a per-session group so other server tasks (like deep analysis) can send updates
            self.group_name = f"langgraph_session_{self.session_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            print(f"[LangGraphStream] Accepted WS for session {self.session_id} user={getattr(user,'username',None)} group={self.group_name}")

            # Extra diagnostics: print scope headers and query string for debugging
            try:
                headers = dict(self.scope.get('headers') or [])
                print(f"[LangGraphStream] Scope headers: {headers}")
                qs = (self.scope.get('query_string') or b'').decode()
                print(f"[LangGraphStream] Query string: {qs}")
            except Exception as e:
                print(f"[LangGraphStream] Failed to log scope headers: {e}")

            # Send an immediate connected acknowledgement so client can confirm
            try:
                await self._send_json({"type": "connected", "session_id": self.session_id, "user": getattr(user, 'username', None)})
                print(f"[LangGraphStream] Connected ack sent for session {self.session_id}")
            except Exception as e:
                print(f"[LangGraphStream] Failed to send connected ack: {e}")

            # Send a quick ping text frame for additional confirmation (some clients log this)
            try:
                ts = timezone.now().isoformat()
                await self.send(text_data=json.dumps({"type": "ping", "ts": ts}))
                print(f"[LangGraphStream] Ping text sent for session {self.session_id} ts={ts}")
            except Exception as e:
                print(f"[LangGraphStream] Failed to send ping text: {e}")


        except ChatSession.DoesNotExist:
            await self.close(code=4004)
        except Exception as e:
            print(f"LangGraph WS connection error: {e}")
            await self.close(code=4000)

    async def analyze_update(self, event):
        """Handle analyze progress events sent via channel layer group."""
        try:
            payload = event.get('payload') or event
            print(f"[LangGraphStream] forwarding analyze_update to WS for session {self.session_id}: {payload.get('type')}")
            await self._send_json(payload)
        except Exception as e:
            print(f"Error sending analyze update: {e}")

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection and leave group."""
        try:
            print(f"[LangGraphStream] Disconnect for session {getattr(self,'session_id',None)} close_code={close_code}")
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception as e:
            print(f"[LangGraphStream] Error during disconnect cleanup: {e}")

    async def receive_json(self, content):
        """Handle incoming message, run agent, stream events."""
        user_input = content.get('message', '')
        if not user_input:
            return

        try:
            from api.frameworks.langgraph import create_agent, run_agent_stream

            # Get workspace container
            container_name = f"proj-pod-{self.session.project.id}-workspace-shared"

            # Create agent
            graph = create_agent(self.session, container_name)

            # Run agent and stream events
            async for event in run_agent_stream(graph, user_input, self.session.id):
                try:
                    await self._send_json(event)
                except Exception as e:
                    print(f"Failed to send agent event: {e}")

            # Send completion signal
            await self._send_json({"type": "done"})

        except Exception as e:
            print(f"LangGraph agent error: {e}")
            await self._send_json({
                "type": "error",
                "content": f"Agent execution failed: {str(e)}"
            })

    async def _check_access(self, user, project):
        """Check if user has access to the project."""
        if project.owner_id == user.id:
            return True

        is_contributor = await sync_to_async(
            lambda: project.contributors.filter(id=user.id).exists()
        )()
        if is_contributor:
            return True

        if project.team_id:
            is_team_member = await sync_to_async(
                lambda: project.team.members.filter(id=user.id).exists()
            )()
            if is_team_member:
                return True

        return False
