# Webtop Development Environment

## Overview

The platform provides per-project containerized development environments powered by **linuxserver/webtop** (Fedora KDE edition). Each project gets an isolated, persistent workspace accessible via an authenticated web proxy—no host port conflicts.

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
   - Image: `lscr.io/linuxserver/webtop:amd64-fedora-kde`
   - Includes full KDE desktop, development tools, Selkies for streaming
   - Persistent workspace volume mounted at `/config`
   - No exposed host ports—accessed via backend proxy

4. **Backend Proxy** (`backend/api/proxy_views.py`)
   - ASGI-based HTTP proxy at `/api/projects/{id}/webtop-proxy/{path}`
   - Authenticated: owner/contributors only
   - Forwards to container internal address (`container-name:3000`)
   - WebSocket support noted (requires Django Channels for full implementation)

5. **Frontend Components**
   - `WebtopTab.tsx`: Iframe viewer with lifecycle controls (start/stop/restart/kill)
   - `ContainerLogsTab.tsx`: Log viewer with tail control, auto-refresh, download
   - Integrated into `EditApplication.tsx` as new tabs

## Usage Workflow

### 1. Provision Webtop

Navigate to **Edit Project > Webtop** tab. Click **"Provision Webtop Workspace"**.

Backend creates:
- Pod for the project (if not exists)
- Persistent volume `proj-{id}-workspace`
- Webtop container with Fedora KDE desktop

Status polling (5s interval) reflects when the service is `running`.

### 2. Access Workspace

Once running, the Webtop appears in an iframe. Users interact with a full Linux desktop environment including:
- File manager, terminal, code editors
- Browser, development tools (Python, Node.js, Git, etc.)
- Persistent `/config` directory for user files

### 3. Manage Lifecycle

Control bar provides:
- **Start**: Launch stopped service
- **Stop**: Gracefully stop service (preserves state)
- **Restart**: Restart service (e.g., after config changes)
- **Kill**: Force-stop service

Status indicator shows real-time state (green = running, gray = stopped, yellow = transitioning).

### 4. View Logs

Switch to **Container Logs** tab:
- Select service (Webtop or future backend/frontend services)
- Adjust tail lines (default 1000, max 5000)
- Enable auto-refresh for live tailing
- Download logs as `.txt` file

## API Endpoints

### Webtop Provisioning
```http
POST /api/projects/:id/ensure_webtop/
```
Response:
```json
{
  "status": "success",
  "service": {
    "name": "webtop",
    "container_name": "proj-pod-1-webtop",
    "status": "running",
    "started_at": "2025-11-27T10:00:00Z",
    "proxy_url": "/api/projects/1/webtop-proxy/"
  },
  "workspace_volume": "proj-1-workspace"
}
```

### Service Lifecycle
```http
POST /api/project-services/:id/start/
POST /api/project-services/:id/stop/
POST /api/project-services/:id/restart/
POST /api/project-services/:id/kill/
```

### Logs Retrieval
```http
GET /api/project-services/:id/logs/?tail=1000&since=1h
```

### Proxy Access
```http
GET /api/projects/:id/webtop-proxy/:path
```
WebSocket upgrade supported (requires Django Channels config).

## Security Model

- **Authentication Required**: All endpoints require valid JWT tokens
- **Authorization**: Only project owner and contributors can access/manage services
- **No Host Port Exposure**: Webtop runs on pod internal network; accessed only via authenticated backend proxy
- **Volume Isolation**: Each project gets isolated persistent volume
- **Input Sanitization**: Environment variables and commands validated server-side

## Workspace File System API

The platform provides direct file system access to workspace containers via REST API:

### File Tree
```http
GET /api/projects/:id/workspace/files/tree/
```
Returns hierarchical file/directory structure of the workspace.

### Read File
```http
GET /api/projects/:id/workspace/files/read/:filepath
```
Returns file contents (text or binary).

### Create File
```http
POST /api/projects/:id/workspace/files/create/
Body: {"path": "/path/to/file", "content": "...", "executable": false}
```
Creates new file in workspace with optional executable flag.

### Update File
```http
PUT /api/projects/:id/workspace/files/update/:filepath
Body: {"content": "...", "executable": false}
```
Updates existing file contents.

### Delete File
```http
DELETE /api/projects/:id/workspace/files/delete/:filepath
```
Deletes file from workspace.

## Workspace Resource Tiers

Administrators can configure workspace resource tiers (t-shirt sizing) for CPU and memory limits:

### Tier Management
```http
GET /api/workspace-tiers/
POST /api/workspace-tiers/
GET /api/workspace-tiers/:slug/
PUT /api/workspace-tiers/:slug/
DELETE /api/workspace-tiers/:slug/
```

### Tier Structure
```json
{
  "name": "Standard",
  "slug": "standard",
  "cpu_limit": "2.0",
  "memory_limit": "4g",
  "is_default": true,
  "is_active": true
}
```

Projects reference tiers via `workspace_size` field. Examples:
- **Light**: 1.0 CPU, 2g memory
- **Standard**: 2.0 CPU, 4g memory
- **Heavy**: 4.0 CPU, 8g memory

## Workspace Initialization

Projects can be created with different initialization methods:

1. **Blank Project**: Empty workspace
2. **Clone Repository**: Git repository cloned into workspace
3. **AI-Assisted Planning**: Workspace initialized based on AI chat session
4. **Template**: Pre-configured file structure from project template

The `workspace_initializer.py` module handles initialization based on the project's `creation_method` field.

## Future Enhancements

### Kubernetes/OpenShift Support
Orchestrator interface ready for K8s implementation:
- Pods → Namespaces
- Services → Deployments + Services (ClusterIP)
- Volumes → PersistentVolumeClaims
- Lifecycle actions map to `kubectl` commands
- Proxy → Port-forward or Ingress routing

### Additional Features
- Code-server (VS Code in browser) as alternative to full desktop
- Snapshot/backup of workspace volumes
- Multi-user collaborative sessions (shared webtop)
- Real-time file watching and hot reload

## Troubleshooting

### Service Won't Start
- Check logs: "Container not found" → re-provision webtop
- Podman daemon running: `podman info`
- Permissions: ensure user in `podman` group

### Proxy Connection Errors
- Verify service status is `running`
- Check container network: `podman inspect proj-pod-{id}-webtop`
- CORS/CSRF: proxy exempts webtop paths from CSRF checks (configured in `settings.py`)

### Logs Not Loading
- Service must exist: check services list
- Timeout: reduce tail lines
- Auto-refresh disabled if service stopped

## Configuration

### Environment Variables
- `PODMAN_BIN`: Path to Podman binary (default: `podman`)
- `MAX_LOG_TAIL_LINES`: Max log lines retrievable (default: 5000)

### Django Settings
```python
# backend/settings.py
MAX_LOG_TAIL_LINES = 5000
DEFAULT_TOOL_IMAGE = 'docker.io/library/python:3.11-slim'
```

### Webtop Customization
Modify `ServiceSpec` in `views.py` `ensure_webtop` action:
- Change image tag for different desktop (e.g., `:ubuntu-kde`)
- Add environment variables (e.g., `CUSTOM_USER`, `PASSWORD`)
- Adjust volume mounts (e.g., read-only shared resources)

## Development Notes

### Orchestrator Interface
New orchestration backends (K8s, Docker Swarm) should implement `Orchestrator` ABC:
```python
from api.orchestrator import Orchestrator, ServiceSpec, ServiceStatus

class MyOrchestrator(Orchestrator):
    def ensure_pod(self, project_id: int) -> str:
        # Implementation
        pass
    # ... other methods
```

### Testing
Unit tests for orchestrator logic (mocking `subprocess.run`):
```python
from api.podman_orchestrator import PodmanOrchestrator
# Mock podman commands, assert correct args passed
```

Integration tests require Podman daemon (CI/CD setup).

## Rollout Plan

### Phase 1 (Current)
- Core Webtop provisioning and lifecycle
- HTTP-only proxy (WebSocket limited)
- Basic logging and status polling

### Phase 2
- Django Channels for full WebSocket proxy
- Resource quotas and monitoring
- Automated cleanup of orphaned containers

### Phase 3
- Kubernetes/OpenShift orchestrator
- Advanced workspace features (Git sync, templates)
- Multi-user collaboration

---

**Last Updated**: 2025-11-27  
**Related Docs**: `docs/agents/features.md`, `docs/agents/components.md`
