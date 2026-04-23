# Update Instructions for docs/agents/webtop.md

This file contains the complete updated content for `docs/agents/webtop.md` to reflect the current working implementation.

**How to use**:
1. Open: `docs/agents/webtop.md`
2. Select all content
3. Replace with the content below
4. Save file

---

# Webtop Development Environment

## Overview

The platform provides per-project containerized development environments powered by **linuxserver/webtop** (XFCE edition). Each project gets an isolated, persistent workspace accessible via an authenticated WebSocket proxy—no host port conflicts. The implementation uses **Django Channels** with **Daphne ASGI server** for full bidirectional WebSocket support, enabling interactive desktop streaming and real-time input handling.

## Architecture

### Key Components

1. **Orchestrator Abstraction** (`backend/api/orchestrator.py`)
   - Abstract interface for container management
   - Supports Podman today, designed for Kubernetes/OpenShift future
   - Methods: `ensure_pod`, `ensure_service`, lifecycle (start/stop/restart/kill), `get_service_logs`, volume management

2. **Podman Implementation** (`backend/api/podman_orchestrator.py`)
   - Concrete implementation using Podman CLI
   - Manages pods (per-project namespaces), services (containers), and volumes
   - Consistent naming: `proj-pod-{id}`, `proj-pod-{id}-{service_name}`, `proj-{id}-workspace`

3. **Webtop Service**
   - Image: `lscr.io/linuxserver/webtop:amd64-el-xfce`
   - XFCE desktop, development tools, Selkies for streaming
   - Persistent workspace volume mounted at `/config`
   - NGINX on port 3000 (HTTP server)
   - Selkies daemon on port 8082 (WebSocket, full bidirectional support)
   - No exposed host ports—accessed via backend proxy

4. **HTTP Proxy** (`backend/api/proxy_views.py`)
   - ASGI-based async HTTP proxy at `/api/projects/{id}/webtop-proxy/{path}`
   - Authenticated: owner/contributors only
   - Forwards HTTP requests to container:3000
   - Injects JWT token script into HTML responses
   - JavaScript wrapper for client-side WebSocket auto-token-injection
   - Redirect header rewriting to maintain proxy prefix

5. **WebSocket Proxy Consumer** (`backend/api/consumers.py`)
   - ASGI WebSocket consumer for full bidirectional proxying
   - **Connects directly to Selkies on port 8082** (bypasses NGINX limitations)
   - Authenticates via `JWTAuthMiddleware`
   - Concurrent async tasks:
     - `proxy_websocket()`: Background task, connects to backend
     - `_backend_to_client()`: Listens indefinitely, forwards messages
     - `receive()`: Framework-called, waits for backend, forwards client messages
   - Supports text and binary messages (desktop streaming)
   - Debug logging via `WEBTOP_PROXY_DEBUG=1`

6. **JWT Authentication Middleware** (`backend/api/channels_auth.py`)
   - Extracts tokens from WebSocket query parameters or Authorization headers
   - Validates using `SimpleJWT` (Django REST Framework)
   - Injects authenticated user into WebSocket scope

7. **Frontend Components**
   - `WebtopTab.tsx`: Iframe viewer with lifecycle controls
   - `ContainerLogsTab.tsx`: Log viewer with tail control
   - Integrated into `EditApplication.tsx`

## Usage Workflow

### 1. Provision Webtop

Navigate to **Edit Project > Webtop** tab. Click **"Provision Webtop Workspace"**.

Backend creates:
- Pod for the project (if not exists)
- Persistent volume `proj-{id}-workspace`
- Webtop container with XFCE desktop

Status polling (5s interval) reflects service state.

### 2. Access Workspace

Once running, the Webtop appears in an iframe with:
- Full Linux desktop environment
- File manager, terminal, code editors
- Development tools (Python, Node.js, Git, etc.)
- Persistent `/config` directory
- **Full mouse and keyboard input support** via WebSocket
- **Real-time desktop streaming** from Selkies

### 3. Manage Lifecycle

Control bar provides:
- **Start**: Launch stopped service
- **Stop**: Gracefully stop service (preserves state)
- **Restart**: Restart service
- **Kill**: Force-stop service

### 4. View Logs

Switch to **Container Logs** tab to view and download container logs.

## API Endpoints

### Webtop Provisioning
```http
POST /api/projects/{id}/ensure_webtop/
```

### Service Lifecycle
```http
POST /api/project-services/{service_id}/start/
POST /api/project-services/{service_id}/stop/
POST /api/project-services/{service_id}/restart/
POST /api/project-services/{service_id}/kill/
```

### Logs Retrieval
```http
GET /api/project-services/{service_id}/logs/?tail=1000&since=1h
```

### Proxy Access (HTTP)
```http
GET /api/projects/{id}/webtop-proxy/{path}
```

### Proxy Access (WebSocket)
```
ws://localhost:8000/api/projects/{id}/webtop-proxy/websocket?token=<jwt>
```

## WebSocket Implementation

### Connection Flow

The WebSocket proxy enables full bidirectional communication between browser and webtop container:

```
Browser → HTTP Proxy → Webtop (HTTP)
           ↓ injects JWT script
         Webtop UI initiates WebSocket
           ↓
        Channels ASGI → JWT Middleware → Consumer
           ↓
        Selkies (ws://container:8082)
           ↓ bidirectional
        Messages (text/binary) ↔ Consumer ↔ Browser
```

### Key Details

**Port 8082 Connection**: Consumer connects directly to Selkies on port 8082 (not through NGINX on port 3000) because NGINX has limited WebSocket routing and doesn't proxy all Selkies endpoints.

**Concurrent Tasks**: 
- `proxy_websocket()` runs as background task (doesn't block)
- `_backend_to_client()` listens indefinitely for backend messages
- `receive()` called by framework when client sends messages
- Both directions active simultaneously without deadlock

**Debug Logging**: Enable with `WEBTOP_PROXY_DEBUG=1` environment variable for detailed message logging. Disabled by default for clean production logs.

## Security Model

- **Authentication Required**: All endpoints require valid JWT tokens
- **Authorization**: Only project owner and contributors can access
- **No Host Port Exposure**: No exposed container ports
- **Volume Isolation**: Each project has isolated workspace
- **Token Injection**: Automatic token attachment for WebSocket connections

## Configuration

### Django Settings (Required)
```python
# settings.py
INSTALLED_APPS = [
    'daphne',  # MUST be before django.contrib.contenttypes
    'django.contrib.contenttypes',
    ...
]

ASGI_APPLICATION = 'backend.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}
```

### ASGI Routing (Required)
```python
# backend/asgi.py
from channels.routing import ProtocolTypeRouter, URLRouter
from api.channels_auth import JWTAuthMiddlewareStack
from api.consumers import WebtopProxyConsumer
import re

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JWTAuthMiddlewareStack(
        URLRouter([
            re.path(
                r'^api/projects/(?P<project_id>\d+)/webtop-proxy/(?P<path>.*)$',
                WebtopProxyConsumer.as_asgi()
            ),
        ])
    ),
})
```

### Server (Required)
```bash
# MUST use Daphne (not development runserver)
daphne -b 0.0.0.0 -p 8000 backend.asgi:application
```

## Troubleshooting

### WebSocket Connection Fails
- Verify Daphne is running (not development server)
- Check JWT token is valid: look for token in query string
- Enable debug: `export WEBTOP_PROXY_DEBUG=1`
- Check browser console for WebSocket errors

### Stream Not Loading ("Waiting for stream")
- Enable debug: `WEBTOP_PROXY_DEBUG=1`
- Check logs for: `Backend connected for project X`
- Verify container running: `podman ps | grep webtop`
- Check container logs: `podman logs proj-pod-{id}-webtop`

### Input Not Responsive
- Enable debug and check for `Client→Backend: TEXT` messages
- Verify bidirectional message flow
- Check network latency
- Ensure iframe has focus

### Service Won't Start
- Check Podman daemon: `podman info`
- Check logs: `podman logs proj-pod-{id}-webtop`
- Re-provision webtop if container not found
- Ensure user in podman group or running with sudo

## Future Enhancements

- Kubernetes/OpenShift support
- Code-server (VS Code in browser) alternative
- Resource quotas (CPU, memory)
- Workspace snapshots/backups
- Multi-user collaborative sessions
- Project template integration

---

**Last Updated**: December 4, 2025  
**Status**: ✅ Production Ready - Full WebSocket Support  
**Related Docs**: `docs/WEBSOCKET_PROXY_CURRENT.md`, `docs/WEBTOP_DEPLOYMENT_GUIDE.md`

---

## How to Apply This Update

1. Open your editor
2. Navigate to: `docs/agents/webtop.md`
3. Select all content (Ctrl+A)
4. Delete
5. Paste the content above (from "# Webtop Development Environment")
6. Save file

Or use your terminal:

```bash
cat > docs/agents/webtop.md << 'EOF'
[PASTE ENTIRE CONTENT ABOVE]
EOF
```

---

**This completes the Webtop documentation update.**
