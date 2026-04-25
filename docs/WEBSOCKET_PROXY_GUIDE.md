# WebSocket Proxy Implementation Guide

## Overview

The webtop container uses WebSocket connections (Selkies) for interactive terminal, desktop streaming, and bidirectional communication. This guide documents the complete WebSocket proxy implementation that allows secure, authenticated access to these connections.

## Architecture

### Connection Flow

```
Browser (Frontend)
    ↓
[iframe with proxy URL + JWT token]
    ↓
Django Backend (Port 8000)
    ├─ HTTP Requests: Handled by WebtopProxyView (proxy_views.py)
    │   - GET /api/projects/{id}/webtop-proxy/... → aiohttp → container:3000
    │   - Returns HTML/CSS/JS to client
    │   - Injects JWT token into WebSocket URLs
    │
    └─ WebSocket Upgrade: Routed by Django Channels ASGI (asgi.py)
        └─ WebtopProxyConsumer (consumers.py)
            - Authenticates user via JWTAuthMiddleware (channels_auth.py)
            - Connects to container WebSocket: ws://container:3000
            - Proxies messages bidirectionally
            - Forwards JWT token to container

↓

Webtop Container (port 3000)
    - NGINX reverse proxy with SUBFOLDER env variable
    - Routes HTTP to Selkies web server
    - Routes WebSocket to Selkies daemon (port 8082)
    - Validates JWT token from requests
```

## Implementation Details

### 1. Frontend (Browser) → Backend HTTP View

**File**: `src/components/project/WebtopTab.tsx`

```tsx
const proxyUrl = getWebtopProxyUrl(project.id);
// Returns: http://localhost:8000/api/projects/1/webtop-proxy/?token=<jwt_token>

<iframe src={proxyUrl} />
```

The frontend passes the JWT token via query parameter to the proxy endpoint.

### 2. Backend HTTP Proxy View

**File**: `backend/api/proxy_views.py`

The `WebtopProxyView` handles HTTP requests:

```python
# HTTP request path
GET /api/projects/1/webtop-proxy/ HTTP/1.1

# Proxied to container
GET http://container:3000/api/projects/1/webtop-proxy/ HTTP/1.1

# Response includes HTML with injected script
```

**Key features**:
- Forward headers (excluding hop-by-hop headers)
- Rewrite redirects to maintain proxy path prefix
- Inject JWT token script for client-side WebSocket connections
- Set `X-Frame-Options: ALLOWALL` to permit iframe embedding

### 3. JWT Token Injection Script

The HTTP response includes a script that wraps the `WebSocket` constructor:

```javascript
// Injected by proxy_views.py (lines 143-176)
(function() {
    const originalWebSocket = window.WebSocket;
    window.WebSocket = function(url, protocols) {
        // If URL contains webtop-proxy, add token
        if (url.includes('webtop-proxy')) {
            const separator = url.includes('?') ? '&' : '?';
            url = url + separator + 'token=<JWT_TOKEN>';
        }
        console.log('WebSocket URL with token:', url);
        return new originalWebSocket(url, protocols);
    };
    window.WebSocket.prototype = originalWebSocket.prototype;
})();
```

This ensures any WebSocket connection initiated from Selkies includes the token automatically.

### 4. WebSocket Upgrade Request

When Selkies initiates a WebSocket connection:

```
GET /api/projects/1/webtop-proxy/websockets HTTP/1.1
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: ...
Sec-WebSocket-Version: 13
```

**Routing**:
- If route matches Django's URL patterns → HTTP 426 error (not properly routed)
- If route matches ASGI WebSocket URLRouter → `WebtopProxyConsumer`

### 5. ASGI Configuration

**File**: `backend/backend/asgi.py`

```python
application = ProtocolTypeRouter({
    "http": django_asgi_app,  # Regular HTTP requests
    "websocket": JWTAuthMiddlewareStack(
        URLRouter([
            # WebSocket requests match this pattern
            re_path(
                r'^api/projects/(?P<project_id>\d+)/webtop-proxy/(?P<path>.*)$',
                WebtopProxyConsumer.as_asgi()
            ),
        ])
    ),
})
```

**ASGI Server**: Daphne (installed in `requirements.txt`)
- Handles both HTTP and WebSocket protocols
- Routes based on `ProtocolTypeRouter`

### 6. JWT Authentication Middleware

**File**: `backend/api/channels_auth.py`

The middleware extracts JWT tokens from:
1. **Authorization header**: `Authorization: Bearer <token>`
2. **Query parameter**: `?token=<token>`
3. **Django session**: `sessionid` cookie (fallback)

```python
class JWTAuthMiddleware:
    async def __call__(self, scope, receive, send):
        # Extract token from headers or query string
        token = None
        
        # Try Authorization header first
        headers = dict(scope.get('headers') or [])
        auth_header = headers.get(b'authorization')
        if auth_header:
            parts = auth_header.decode().split()
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
        
        # Fallback to query parameter
        if not token:
            query_string = scope.get('query_string') or b''
            qs = parse_qs(query_string.decode())
            token = (qs.get('token') or [None])[0]
        
        # Validate token using DRF's JWTAuthentication
        if token:
            user = validate_jwt_token(token)
        else:
            user = AnonymousUser()
        
        scope['user'] = user
        return await self.inner(scope, receive, send)
```

### 7. WebSocket Consumer (Channels)

**File**: `backend/api/consumers.py`

The `WebtopProxyConsumer` proxies WebSocket connections:

```python
class WebtopProxyConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Handle WebSocket connection."""
        # 1. Extract project_id and path from URL route
        project_id = self.scope['url_route']['kwargs']['project_id']
        path = self.scope['url_route']['kwargs'].get('path', 'websocket')
        
        # 2. Authenticate user (via JWTAuthMiddleware)
        user = self.scope.get('user')
        if not user.is_authenticated:
            await self.close(code=4001)  # Unauthorized
            return
        
        # 3. Check access to project
        project = Project.objects.get(pk=project_id)
        if not user_has_access(user, project):
            await self.close(code=4003)  # Forbidden
            return
        
        # 4. Accept client connection
        await self.accept()
        
        # 5. Proxy to container WebSocket
        await self.proxy_websocket()
    
    async def proxy_websocket(self):
        """Connect to container and proxy messages."""
        # Build target URL
        target_address = resolve_container_address(project_id)
        target_url = f'ws://{target_address}/api/projects/{project_id}/webtop-proxy/websockets'
        
        # Forward JWT token to container
        query_string = self.scope.get('query_string') or b''
        qs = parse_qs(query_string.decode())
        jwt_token = (qs.get('token') or [None])[0]
        
        if jwt_token:
            target_url = f"{target_url}?token={jwt_token}"
        
        # Create aiohttp session and connect
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(target_url, headers={...}) as backend_ws:
                # Proxy messages in both directions
                async for msg in backend_ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self.send(text_data=msg.data)
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        await self.send(bytes_data=msg.data)
    
    async def receive(self, text_data=None, bytes_data=None):
        """Forward incoming client messages to backend."""
        if text_data:
            await self.backend_ws.send_str(text_data)
        elif bytes_data:
            await self.backend_ws.send_bytes(bytes_data)
```

## Token Flow Diagram

```
User Login
    ↓
    [Django REST Framework SimpleJWT]
    ↓
    JWT Token (stored in localStorage)
    ↓
Frontend: getWebtopProxyUrl(projectId)
    ├─ Get token from localStorage
    ├─ Build: /api/projects/{id}/webtop-proxy/?token=<jwt>
    └─ Set iframe src
    ↓
Browser loads iframe
    ├─ HTTP GET /api/projects/{id}/webtop-proxy/?token=<jwt>
    ├─ Backend extracts token from query param
    ├─ Backend validates with JWTAuthentication
    ├─ Backend injects script into HTML
    └─ Returns HTML with WebSocket wrapper
    ↓
Selkies initializes WebSocket
    ├─ Wrapped WebSocket constructor adds token to URL
    ├─ WebSocket GET /api/projects/{id}/webtop-proxy/websockets?token=<jwt>
    ├─ ASGI routes to WebtopProxyConsumer
    ├─ JWTAuthMiddleware extracts token from query param
    ├─ Consumer validates user and project access
    ├─ Consumer accepts connection
    └─ Consumer connects to container with forwarded token
    ↓
Container receives WebSocket
    ├─ NGINX routes /websockets to Selkies daemon
    ├─ Selkies extracts token from query param or Authorization header
    ├─ Selkies validates token (if configured)
    └─ Bidirectional communication established
```

## Troubleshooting

### Issue 1: WebSocket Connection Fails in Browser

**Symptoms**:
- Webtop iframe displays but no interaction
- Browser DevTools → Network → WS shows failed connection
- Error: `WebSocket is closed before the connection is established`

**Steps**:

1. **Check browser DevTools**:
   ```
   Open: DevTools → Network tab → Filter: WS
   Look for: GET /api/projects/{id}/webtop-proxy/websockets
   Expected Status: 101 (Switching Protocols) or similar
   ```

2. **Check token injection**:
   ```
   DevTools → Console
   Run: console.log(localStorage.getItem('accessToken'))
   Expected: JWT token visible
   
   Run: console.log(document.title)  // Verify page loaded
   Look for injected script: <script>(function() { const originalWebSocket = window.WebSocket; ...
   ```

3. **Verify ASGI server**:
   ```bash
   # Check if Daphne is running
   ps aux | grep daphne
   
   # Check logs for ASGI startup
   docker logs <container_name>
   # Expected: "Daphne starting up on ... address ..."
   ```

4. **Verify container connectivity**:
   ```bash
   # Inside container, check WebSocket endpoint
   curl -i http://localhost:3000/websockets
   # Should return: 400 Bad Request (normal for HTTP)
   
   # Try WebSocket directly (requires wscat or similar)
   wscat -c ws://localhost:3000/websockets
   # Should connect or timeout (depending on auth)
   ```

### Issue 2: 426 Upgrade Required Error

**Symptoms**:
- Browser shows HTTP 426 response
- Webtop appears but no interactive features work

**Cause**:
- WebSocket request is being handled by HTTP view instead of ASGI

**Steps**:

1. **Verify ASGI configuration**:
   ```python
   # backend/backend/asgi.py
   # Ensure ProtocolTypeRouter includes "websocket"
   application = ProtocolTypeRouter({
       "http": django_asgi_app,
       "websocket": JWTAuthMiddlewareStack(
           URLRouter([
               re_path(
                   r'^api/projects/(?P<project_id>\d+)/webtop-proxy/(?P<path>.*)$',
                   WebtopProxyConsumer.as_asgi()
               ),
           ])
       ),
   })
   ```

2. **Check ASGI_APPLICATION setting**:
   ```python
   # backend/backend/settings.py
   ASGI_APPLICATION = 'backend.asgi.application'
   ```

3. **Verify installed apps order**:
   ```python
   # backend/backend/settings.py - INSTALLED_APPS
   # Daphne MUST be first
   INSTALLED_APPS = [
       'daphne',  # ← Must be first
       'django.contrib.admin',
       ...
       'channels',
       'api',
   ]
   ```

### Issue 3: Authentication Fails

**Symptoms**:
- WebSocket closes with code 4001 (Unauthorized)
- Browser DevTools shows: `[JWTAuth] No token found`

**Steps**:

1. **Check token in iframe**:
   ```javascript
   // Inside iframe console
   const urlParams = new URLSearchParams(window.location.search);
   console.log('Token:', urlParams.get('token'));
   ```

2. **Verify token generation**:
   ```bash
   # Get token from login endpoint
   curl -X POST http://localhost:8000/api/auth/login/ \
     -H "Content-Type: application/json" \
     -d '{"username": "user", "password": "pass"}'
   # Expected: {"access": "eyJ...", "refresh": "..."}
   ```

3. **Check token format**:
   ```javascript
   // In browser console
   const token = localStorage.getItem('accessToken');
   const parts = token.split('.');
   console.log('Header:', JSON.parse(atob(parts[0])));
   console.log('Payload:', JSON.parse(atob(parts[1])));
   ```

4. **Verify middleware chain**:
   ```python
   # backend/api/channels_auth.py should handle:
   # 1. Authorization header: "Bearer <token>"
   # 2. Query parameter: "?token=<token>"
   # 3. Session cookie: "sessionid"
   
   # Add debug logging
   print(f"[JWTAuth] Token: {token[:20] if token else 'None'}...")
   ```

### Issue 4: Container WebSocket Connection Fails

**Symptoms**:
- User authenticated, but consumer can't connect to container
- Logs: `[WebtopProxy] WebSocket proxy error: Connection refused`

**Steps**:

1. **Check container is running**:
   ```bash
   podman ps -a | grep webtop
   # Should show: proj-pod-{id}-webtop (running)
   ```

2. **Verify container networking**:
   ```bash
   # From backend container, test connectivity
   podman exec <backend_container> curl -i http://proj-pod-1-webtop:3000/
   # Expected: 200 OK or 302 Found
   ```

3. **Check NGINX configuration in container**:
   ```bash
   # Verify container environment variables
   podman inspect proj-pod-1-webtop | grep -A 20 Env
   # Should show: "SUBFOLDER=/api/projects/1/webtop-proxy/"
   ```

4. **Test WebSocket endpoint directly**:
   ```bash
   # From backend container
   podman exec <backend_container> python -c "
   import asyncio
   import aiohttp
   
   async def test():
       async with aiohttp.ClientSession() as session:
           try:
               async with session.ws_connect('ws://proj-pod-1-webtop:3000/api/projects/1/webtop-proxy/websockets') as ws:
                   print('Connected!')
                   await ws.close()
           except Exception as e:
               print(f'Error: {e}')
   
   asyncio.run(test())
   "
   ```

### Issue 5: Messages Not Bidirectional

**Symptoms**:
- WebSocket connects but no input/output
- Terminal doesn't respond to keystrokes

**Steps**:

1. **Check consumer message handling**:
   ```python
   # backend/api/consumers.py
   # Ensure both receive() and proxy_websocket() are implemented
   
   async def receive(self, text_data=None, bytes_data=None):
       """Handle incoming messages from client."""
       if hasattr(self, 'backend_ws') and self.backend_ws:
           if text_data:
               await self.backend_ws.send_str(text_data)
           elif bytes_data:
               await self.backend_ws.send_bytes(bytes_data)
   ```

2. **Check async for loop**:
   ```python
   # proxy_websocket() should properly iterate over messages
   async for msg in backend_ws:
       if msg.type == aiohttp.WSMsgType.TEXT:
           await self.send(text_data=msg.data)
       elif msg.type == aiohttp.WSMsgType.BINARY:
           await self.send(bytes_data=msg.data)
   ```

3. **Monitor logs**:
   ```bash
   # Enable debug logging
   export LOGLEVEL=DEBUG
   daphne -b 0.0.0.0 -p 8000 backend.asgi:application
   ```

## Debugging Commands

### Check WebSocket Connection (Chrome DevTools)

```javascript
// In browser console
const ws = new WebSocket('ws://localhost:8000/api/projects/1/webtop-proxy/websockets?token=<jwt>');
ws.onopen = () => console.log('Connected');
ws.onerror = (e) => console.log('Error:', e);
ws.onmessage = (e) => console.log('Message:', e.data);
```

### Check Backend Logs

```bash
# Docker/Podman logs
docker logs -f <container_name>

# Look for lines:
# [WebtopProxy] === WEBSOCKET CONNECTION ATTEMPT ===
# [JWTAuth] Successfully authenticated user: ...
# [WebtopProxy] Successfully connected to backend WebSocket
```

### Test Token Validity

```bash
# Check if token works with REST API
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/api/projects/1/

# Expected: 200 OK with project data
# If 401: Token expired or invalid
```

## Configuration Checklist

- [ ] Daphne is first in `INSTALLED_APPS`
- [ ] `ASGI_APPLICATION = 'backend.asgi.application'`
- [ ] `asgi.py` has `ProtocolTypeRouter` with both "http" and "websocket"
- [ ] `WebtopProxyConsumer` is imported in `asgi.py`
- [ ] `JWTAuthMiddleware` extracts tokens from headers and query params
- [ ] Container is running and accessible on internal network
- [ ] `X-Forwarded-Prefix` header matches `SUBFOLDER` env variable
- [ ] JWT token is stored in `localStorage` as `accessToken`
- [ ] Token injection script is embedded in HTML response
- [ ] Browser allows WebSocket upgrades to the proxy endpoint

## See Also

- `docs/agents/webtop.md` - Webtop architecture and provisioning
- `backend/api/consumers.py` - Full consumer implementation
- `backend/api/proxy_views.py` - HTTP proxy implementation
- `backend/backend/asgi.py` - ASGI routing configuration
