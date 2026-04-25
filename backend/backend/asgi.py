"""
ASGI config for backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/asgi/
"""

import os
import asyncio
import re
from channels.routing import ProtocolTypeRouter, URLRouter
# Replace default auth with JWT auth for WebSocket
from api.channels_auth import JWTAuthMiddlewareStack
from django.core.asgi import get_asgi_application
from django.urls import re_path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# Initialize Django ASGI application early
django_asgi_app = get_asgi_application()

# Import after Django is initialized
from api.consumers import WebtopProxyConsumer, ProjectProvisioningConsumer, SubdomainProxyConsumer, LangGraphStreamConsumer
from api.unified_consumer import UnifiedAgentConsumer


class RawWebSocketTunnel:
    """
    Raw TCP/WebSocket tunnel for Vite HMR connections.
    
    Unlike normal WebSocket consumers that terminate the connection, this forwards
    the browser's exact HTTP Upgrade request bytes to Vite, so Vite sees the 
    original browser request and accepts the upgrade.
    
    Flow:
    1. ASGI gives us a 'websocket' scope - but we treat it as raw HTTP
    2. We reconstruct the browser's HTTP Upgrade request
    3. Open raw TCP to Vite container
    4. Forward the exact request bytes
    5. Relay all bytes bidirectionally
    """
    
    def __init__(self, require_auth=False):
        """
        Args:
            require_auth: If True, validate JWT before opening tunnel.
                          If False, only validate service access.
        """
        self.require_auth = require_auth
    
    async def __call__(self, scope, receive, send):
        """Handle the WebSocket connection as a raw tunnel."""
        headers = dict(scope.get('headers', []))
        host = (headers.get(b'host') or b'').decode().lower()
        path = scope.get('path', '/')
        query_string = scope.get('query_string', b'').decode()
        
        print(f"[RawTunnel] === Raw WebSocket Tunnel for HMR ===", flush=True)
        print(f"[RawTunnel] Host: {host}, Path: {path}", flush=True)
        
        # Parse subdomain to get project/service/port
        pattern = re.compile(r'^proj-(\d+)-(\d+)-(\d+)\.localhost(?::\d+)?$')
        match = pattern.match(host)
        
        if not match:
            print(f"[RawTunnel] REJECT: Invalid host pattern", flush=True)
            await self._send_error(send, 400, "Invalid host")
            return
        
        project_id = int(match.group(1))
        service_id = int(match.group(2))
        port = int(match.group(3))
        
        print(f"[RawTunnel] Project: {project_id}, Service: {service_id}, Port: {port}", flush=True)
        
        # Optional JWT authentication
        if self.require_auth:
            user = await self._validate_jwt(scope)
            if not user:
                print(f"[RawTunnel] REJECT: Invalid or missing JWT", flush=True)
                await self._send_error(send, 401, "Authentication required")
                return
            
            # Check project access
            has_access = await self._check_project_access(user, project_id)
            if not has_access:
                print(f"[RawTunnel] REJECT: User {user.id} lacks access to project {project_id}", flush=True)
                await self._send_error(send, 403, "Access denied")
                return
            print(f"[RawTunnel] JWT auth passed for user {user.id}", flush=True)
        
        # Validate service and get target address
        target_address = await self._get_service_address(project_id, service_id, port)
        if not target_address:
            print(f"[RawTunnel] REJECT: Service not found or not running", flush=True)
            await self._send_error(send, 404, "Service not available")
            return
        
        print(f"[RawTunnel] Target address: {target_address}", flush=True)
        
        # Parse target address
        if ':' in target_address:
            target_host, target_port = target_address.rsplit(':', 1)
            target_port = int(target_port)
        else:
            target_host = target_address
            target_port = port
        
        # Wait for the WebSocket connect message from ASGI
        message = await receive()
        if message['type'] != 'websocket.connect':
            print(f"[RawTunnel] Unexpected message type: {message['type']}", flush=True)
            return
        
        # Open raw TCP connection to Vite
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target_host, target_port),
                timeout=5.0
            )
            print(f"[RawTunnel] TCP connection established to {target_host}:{target_port}", flush=True)
        except Exception as e:
            print(f"[RawTunnel] Failed to connect to backend: {type(e).__name__}: {e}", flush=True)
            await self._send_error(send, 502, "Backend connection failed")
            return
        
        # Build the HTTP Upgrade request exactly as the browser sent it
        request_path = path
        if query_string:
            request_path += f"?{query_string}"
        
        # Reconstruct headers - forward browser's exact WebSocket headers
        http_request = f"GET {request_path} HTTP/1.1\r\n"
        http_request += f"Host: {target_host}:{target_port}\r\n"
        
        # Forward critical WebSocket headers from browser
        for key, value in scope.get('headers', []):
            key_lower = key.decode().lower()
            # Forward WebSocket-related headers, skip hop-by-hop headers we'll set
            if key_lower in ('upgrade', 'connection', 'sec-websocket-key', 
                            'sec-websocket-version', 'sec-websocket-extensions',
                            'sec-websocket-protocol', 'origin', 'user-agent'):
                http_request += f"{key.decode()}: {value.decode()}\r\n"
        
        http_request += "\r\n"
        
        print(f"[RawTunnel] Sending HTTP Upgrade request to Vite...", flush=True)
        
        # Send the upgrade request
        writer.write(http_request.encode())
        await writer.drain()
        
        # Read Vite's response
        try:
            response_line = await asyncio.wait_for(reader.readline(), timeout=10.0)
            print(f"[RawTunnel] Vite response: {response_line.decode().strip()}", flush=True)
        except asyncio.TimeoutError:
            print(f"[RawTunnel] Timeout waiting for Vite response", flush=True)
            writer.close()
            await self._send_error(send, 504, "Backend timeout")
            return
        
        # Check if Vite accepted the upgrade
        if b'101' not in response_line:
            # Read rest of response for debugging
            response_body = await reader.read(1024)
            print(f"[RawTunnel] Vite rejected upgrade: {response_body.decode()[:200]}", flush=True)
            writer.close()
            await self._send_error(send, 502, "Backend rejected WebSocket upgrade")
            return
        
        # Read and parse response headers to get accepted subprotocol
        accepted_subprotocol = None
        while True:
            line = await reader.readline()
            if line == b'\r\n' or line == b'':
                break
            # Parse header
            if b':' in line:
                header_name, header_value = line.decode().split(':', 1)
                header_name = header_name.strip().lower()
                header_value = header_value.strip()
                if header_name == 'sec-websocket-protocol':
                    accepted_subprotocol = header_value
                    print(f"[RawTunnel] Vite accepted subprotocol: {accepted_subprotocol}", flush=True)
        
        print(f"[RawTunnel] Vite accepted WebSocket upgrade!", flush=True)
        
        # Accept the WebSocket on our side (tell ASGI we're ready)
        # Pass the subprotocol if Vite accepted one
        accept_msg = {'type': 'websocket.accept'}
        if accepted_subprotocol:
            accept_msg['subprotocol'] = accepted_subprotocol
        await send(accept_msg)
        
        # Now relay data bidirectionally
        await self._relay_data(reader, writer, receive, send)
    
    async def _relay_data(self, reader, writer, receive, send):
        """Relay data between browser and Vite."""
        
        async def browser_to_vite():
            """Forward browser messages to Vite."""
            try:
                while True:
                    print(f"[RawTunnel] Waiting for browser message...", flush=True)
                    message = await receive()
                    print(f"[RawTunnel] Browser message: type={message.get('type')}", flush=True)
                    if message['type'] == 'websocket.receive':
                        # Forward text or binary data
                        if 'text' in message:
                            # WebSocket text frame
                            data = message['text'].encode()
                            print(f"[RawTunnel] Forwarding text to Vite: {data[:100]}", flush=True)
                            frame = self._encode_ws_frame(data, opcode=0x1)
                            writer.write(frame)
                            await writer.drain()
                        elif 'bytes' in message:
                            # WebSocket binary frame
                            print(f"[RawTunnel] Forwarding binary to Vite: {len(message['bytes'])} bytes", flush=True)
                            frame = self._encode_ws_frame(message['bytes'], opcode=0x2)
                            writer.write(frame)
                            await writer.drain()
                    elif message['type'] == 'websocket.disconnect':
                        print(f"[RawTunnel] Browser disconnected (code={message.get('code', 'none')})", flush=True)
                        break
            except Exception as e:
                import traceback
                print(f"[RawTunnel] browser_to_vite error: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
        
        async def vite_to_browser():
            """Forward Vite messages to browser."""
            try:
                while True:
                    print(f"[RawTunnel] Waiting for Vite frame...", flush=True)
                    # Read WebSocket frame from Vite
                    frame_data = await self._read_ws_frame(reader)
                    if frame_data is None:
                        print(f"[RawTunnel] Vite connection closed (no frame)", flush=True)
                        break
                    
                    opcode, payload = frame_data
                    print(f"[RawTunnel] Vite frame: opcode={opcode}, payload_len={len(payload)}", flush=True)
                    if opcode == 0x1:  # Text
                        text = payload.decode('utf-8', errors='replace')
                        print(f"[RawTunnel] Forwarding text to browser: {text[:100]}", flush=True)
                        await send({'type': 'websocket.send', 'text': text})
                    elif opcode == 0x2:  # Binary
                        print(f"[RawTunnel] Forwarding binary to browser: {len(payload)} bytes", flush=True)
                        await send({'type': 'websocket.send', 'bytes': payload})
                    elif opcode == 0x8:  # Close
                        print(f"[RawTunnel] Vite sent close frame", flush=True)
                        break
                    elif opcode == 0x9:  # Ping
                        print(f"[RawTunnel] Vite ping, sending pong", flush=True)
                        # Respond with pong
                        pong_frame = self._encode_ws_frame(payload, opcode=0xA)
                        writer.write(pong_frame)
                        await writer.drain()
                    elif opcode == 0xA:  # Pong
                        print(f"[RawTunnel] Vite pong (ignoring)", flush=True)
            except Exception as e:
                import traceback
                print(f"[RawTunnel] vite_to_browser error: {type(e).__name__}: {e}", flush=True)
                traceback.print_exc()
        
        # Run both directions concurrently
        print(f"[RawTunnel] Starting bidirectional relay...", flush=True)
        try:
            results = await asyncio.gather(
                browser_to_vite(),
                vite_to_browser(),
                return_exceptions=True
            )
            print(f"[RawTunnel] Relay ended. Results: {results}", flush=True)
        finally:
            print(f"[RawTunnel] Closing writer...", flush=True)
            writer.close()
            try:
                await send({'type': 'websocket.close'})
            except:
                pass
    
    def _encode_ws_frame(self, data: bytes, opcode: int = 0x1) -> bytes:
        """Encode data into a WebSocket frame (client-side, masked)."""
        import struct
        import os
        
        frame = bytearray()
        # FIN + opcode
        frame.append(0x80 | opcode)
        
        length = len(data)
        # Mask bit set (client frames must be masked)
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack('>H', length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack('>Q', length))
        
        # Generate mask key
        mask = os.urandom(4)
        frame.extend(mask)
        
        # Mask the data
        masked = bytearray(length)
        for i, byte in enumerate(data):
            masked[i] = byte ^ mask[i % 4]
        frame.extend(masked)
        
        return bytes(frame)
    
    async def _read_ws_frame(self, reader) -> tuple | None:
        """Read and decode a WebSocket frame from server (unmasked)."""
        import struct
        
        try:
            header = await reader.readexactly(2)
        except:
            return None
        
        fin = (header[0] >> 7) & 1
        opcode = header[0] & 0x0F
        masked = (header[1] >> 7) & 1
        length = header[1] & 0x7F
        
        if length == 126:
            ext = await reader.readexactly(2)
            length = struct.unpack('>H', ext)[0]
        elif length == 127:
            ext = await reader.readexactly(8)
            length = struct.unpack('>Q', ext)[0]
        
        if masked:
            mask = await reader.readexactly(4)
        
        payload = await reader.readexactly(length)
        
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        
        return (opcode, payload)
    
    async def _validate_jwt(self, scope) -> object | None:
        """Extract and validate JWT from cookies or query string."""
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import AccessToken
        from channels.db import database_sync_to_async
        
        headers = dict(scope.get('headers', []))
        
        # Try cookie first
        cookie_header = (headers.get(b'cookie') or b'').decode()
        token = None
        
        if cookie_header:
            for part in cookie_header.split(';'):
                part = part.strip()
                if part.startswith('access_token='):
                    token = part.split('=', 1)[1]
                    break
        
        # Try query string
        if not token:
            query_string = scope.get('query_string', b'').decode()
            from urllib.parse import parse_qs
            params = parse_qs(query_string)
            token = params.get('token', [None])[0]
        
        if not token:
            return None
        
        try:
            access_token = AccessToken(token)
            user_id = access_token['user_id']
            User = get_user_model()
            user = await database_sync_to_async(User.objects.get)(id=user_id)
            return user
        except Exception as e:
            print(f"[RawTunnel] JWT validation failed: {e}", flush=True)
            return None
    
    async def _check_project_access(self, user, project_id: int) -> bool:
        """Check if user has access to project."""
        from api.models import Project
        from channels.db import database_sync_to_async
        
        @database_sync_to_async
        def check():
            try:
                project = Project.objects.get(pk=project_id)
                if project.owner_id == user.id:
                    return True
                if project.contributors.filter(id=user.id).exists():
                    return True
                if project.team_id and project.team.members.filter(id=user.id).exists():
                    return True
                return False
            except Project.DoesNotExist:
                return False
        
        return await check()
    
    async def _get_service_address(self, project_id: int, service_id: int, port: int) -> str | None:
        """Get the target address for the service."""
        from api.models import ProjectService
        from api.podman_orchestrator import PodmanOrchestrator
        from channels.db import database_sync_to_async
        
        @database_sync_to_async
        def resolve():
            try:
                service = ProjectService.objects.select_related('pod__project').get(pk=service_id)
                
                if service.pod.project_id != project_id:
                    print(f"[RawTunnel] Service project mismatch: {service.pod.project_id} != {project_id}", flush=True)
                    return None
                
                if service.status != 'running':
                    print(f"[RawTunnel] Service not running: {service.status}", flush=True)
                    return None
                
                orchestrator = PodmanOrchestrator()
                return orchestrator.resolve_service_address(project_id, service.name, port)
            except ProjectService.DoesNotExist:
                print(f"[RawTunnel] Service {service_id} not found", flush=True)
                return None
            except Exception as e:
                print(f"[RawTunnel] Error resolving service: {e}", flush=True)
                return None
        
        return await resolve()
    
    async def _send_error(self, send, code: int, message: str):
        """Send an HTTP error response and close."""
        # For WebSocket scope, we need to close properly
        try:
            await send({
                'type': 'websocket.close',
                'code': 4000 + (code % 1000)  # Map to WebSocket close codes
            })
        except:
            pass

# Custom host-based router for WebSockets
class HostBasedRouter:
    """
    Routes WebSocket connections based on hostname.
    Subdomain pattern like proj-{project_id}-{service_id}-{port}.localhost goes to SubdomainProxyConsumer.
    Regular localhost goes to normal URL routing.
    
    Also handles Vite HMR fallback: when Vite client connects with wrong host (0.0.0.0:8000),
    we use the Referer header to identify which service it came from and route accordingly.
    
    For Vite HMR paths, uses RawWebSocketTunnel to forward browser's exact WebSocket
    upgrade request to Vite, allowing HMR to work through the proxy.
    """
    
    # Vite HMR paths that need raw tunnel treatment
    VITE_HMR_PATHS = ('/', '/__vite_ping', '/__vite_hmr')
    
    def __init__(self, subdomain_app, hmr_tunnel, default_app):
        self.subdomain_app = subdomain_app
        self.hmr_tunnel = hmr_tunnel
        self.default_app = default_app
        self.subdomain_pattern = re.compile(r'^proj-(\d+)-(\d+)-(\d+)\.localhost(?::\d+)?$')
        # Pattern to extract subdomain from referer URL
        self.referer_pattern = re.compile(r'https?://proj-(\d+)-(\d+)-(\d+)\.localhost(?::\d+)?')
    
    def _is_hmr_path(self, path: str) -> bool:
        """Check if path is a Vite HMR path that needs raw tunnel."""
        return path in self.VITE_HMR_PATHS or path.startswith('/@vite/')
    
    async def __call__(self, scope, receive, send):
        # Get host from headers
        headers = dict(scope.get('headers', []))
        host = (headers.get(b'host') or b'').decode().lower()
        path = scope.get('path', '')
        
        print(f"[HostBasedRouter] Incoming WS: host='{host}', path='{path}'", flush=True)
        
        # Check if host matches subdomain pattern directly
        match = self.subdomain_pattern.match(host)
        if match:
            # Check if this is an HMR path - use raw tunnel
            if self._is_hmr_path(path):
                print(f"[HostBasedRouter] HMR path on subdomain, using RawWebSocketTunnel", flush=True)
                return await self.hmr_tunnel(scope, receive, send)
            
            # Non-HMR subdomain requests go to regular consumer
            print(f"[HostBasedRouter] Matched subdomain pattern, routing to SubdomainProxyConsumer", flush=True)
            return await self.subdomain_app(scope, receive, send)
        
        # Check for Vite HMR fallback: wrong host but HMR path
        if self._is_hmr_path(path):
            referer = (headers.get(b'referer') or b'').decode()
            origin = (headers.get(b'origin') or b'').decode()
            
            print(f"[HostBasedRouter] Vite HMR path detected, checking Referer/Origin: referer='{referer}', origin='{origin}'", flush=True)
            
            # Try to extract subdomain info from Referer or Origin
            referer_match = self.referer_pattern.search(referer) or self.referer_pattern.search(origin)
            
            if referer_match:
                project_id, service_id, port = referer_match.groups()
                fake_host = f"proj-{project_id}-{service_id}-{port}.localhost:8000"
                print(f"[HostBasedRouter] HMR fallback: reconstructed host '{fake_host}' from Referer/Origin, using RawWebSocketTunnel", flush=True)
                
                # Modify scope to have the correct host header
                new_headers = [(k, v) for k, v in scope.get('headers', []) if k != b'host']
                new_headers.append((b'host', fake_host.encode()))
                
                modified_scope = dict(scope)
                modified_scope['headers'] = new_headers
                
                # Use raw tunnel for HMR
                return await self.hmr_tunnel(modified_scope, receive, send)
            else:
                print(f"[HostBasedRouter] HMR path but no valid Referer/Origin, cannot route", flush=True)
        
        print(f"[HostBasedRouter] No subdomain match, routing to default URLRouter", flush=True)
        # Route to default URL router
        return await self.default_app(scope, receive, send)


# Create the HMR tunnel instance (no auth required, matches current behavior)
hmr_tunnel = RawWebSocketTunnel(require_auth=False)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": HostBasedRouter(
        subdomain_app=SubdomainProxyConsumer.as_asgi(),
        hmr_tunnel=hmr_tunnel,
        default_app=JWTAuthMiddlewareStack(
            URLRouter([
                # No leading slash in WebSocket path matching
                re_path(r'^api/projects/(?P<project_id>\d+)/webtop-proxy/(?P<path>.*)$', WebtopProxyConsumer.as_asgi()),
                re_path(r'^api/projects/(?P<project_id>\d+)/provisioning-logs$', ProjectProvisioningConsumer.as_asgi()),
                # New unified agent consumer (preferred)
                re_path(r'^api/projects/(?P<project_id>\d+)/chat-sessions/(?P<session_id>\d+)/agent-stream$', UnifiedAgentConsumer.as_asgi()),
                # Legacy LangGraph consumer (kept for backward compat)
                re_path(r'^api/projects/(?P<project_id>\d+)/chat-sessions/(?P<session_id>\d+)/langgraph-stream$', LangGraphStreamConsumer.as_asgi()),
            ])
        ),
    ),
})