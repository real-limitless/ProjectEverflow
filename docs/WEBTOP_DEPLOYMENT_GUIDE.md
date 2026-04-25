# Webtop WebSocket Proxy - Deployment & Operations Guide

## Quick Start

### Prerequisites
```bash
# Python packages
pip install daphne channels django-rest-framework djangorestframework-simplejwt aiohttp

# Container runtime
podman --version
podman info
```

### Local Development Setup

**Terminal 1: Start Backend with Daphne**
```bash
cd backend
export WEBTOP_PROXY_DEBUG=1  # Enable verbose logging
daphne -b 0.0.0.0 -p 8000 backend.asgi:application
```

**Terminal 2: Start Frontend (if needed)**
```bash
cd frontend
npm run dev
```

**Terminal 3: Monitor Logs**
```bash
WEBTOP_PROXY_DEBUG=1 daphne -b 0.0.0.0 -p 8000 backend.asgi:application | tee debug.log
```

### First Test
1. Login to frontend
2. Create or edit a project
3. Go to **Webtop** tab
4. Click **"Provision Webtop Workspace"**
5. Wait for status to turn green (running)
6. Click the iframe area
7. Try typing or moving mouse - should see desktop response
8. Enable debug logging and check message flow

---

## Production Deployment

### System Requirements

**Hardware**:
- 2+ CPU cores
- 4+ GB RAM (2 GB for backend, 2 GB for webtop container)
- 10+ GB disk space (for workspace volumes)

**Software**:
- Podman 3.0+
- Python 3.9+
- Django 4.2+
- Daphne 4.0+
- aiohttp 3.9+

### Build & Deploy

```bash
# 1. Build containers
podman-compose build

# 2. Set production environment
export DJANGO_DEBUG=False
export DJANGO_ALLOWED_HOSTS=yourdomain.com
export JWT_SECRET_KEY=<very-secure-random-key>
unset WEBTOP_PROXY_DEBUG

# 3. Start services
podman-compose up -d

# 4. Verify services running
podman-compose ps
podman logs backend | grep "Daphne"
```

### Reverse Proxy Configuration (nginx)

```nginx
upstream backend {
    server backend:8000;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # WebSocket support
    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }
    
    # Proxy WebSocket connections
    location ~ ^/api/.*/webtop-proxy/ {
        proxy_pass http://backend;
        
        # WebSocket headers (CRITICAL)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        
        # Timeout
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Proxy regular requests
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Frontend static files
    location / {
        root /path/to/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
}
```

### Docker/Podman Compose

```yaml
version: '3.8'

services:
  backend:
    image: your-registry/backend:latest
    ports:
      - "8000:8000"
    environment:
      - DJANGO_DEBUG=False
      - DJANGO_ALLOWED_HOSTS=yourdomain.com
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - DATABASE_URL=postgresql://user:pass@db:5432/appdb
      - WEBTOP_PROXY_DEBUG=0
    volumes:
      - ./backend:/app
      - workspace-volumes:/mnt/workspaces
    depends_on:
      - db
    command: daphne -b 0.0.0.0 -p 8000 backend.asgi:application

  db:
    image: postgres:15
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=appdb
    volumes:
      - postgres-data:/var/lib/postgresql/data
    
  frontend:
    image: your-registry/frontend:latest
    ports:
      - "3000:80"
    depends_on:
      - backend

volumes:
  workspace-volumes:
  postgres-data:
```

---

## Monitoring & Observability

### Logs

**Backend Logs**
```bash
# All logs
podman logs backend

# WebSocket events only
podman logs backend | grep WebSocket

# With timestamp
podman logs -f backend --timestamps

# Last 100 lines
podman logs backend --tail 100
```

**Container Logs**
```bash
# Webtop container
podman logs proj-pod-{id}-webtop

# NGINX errors
podman exec proj-pod-{id}-webtop tail -f /config/logs/nginx.log

# Selkies logs
podman exec proj-pod-{id}-webtop tail -f /config/logs/selkies.log
```

### Health Checks

**Backend Health**
```bash
curl -s http://localhost:8000/api/health/ | jq
# Should return: {"status": "ok"}
```

**WebSocket Connection Test**
```bash
# Quick test with timeout
timeout 5 wscat -c "ws://localhost:8000/api/projects/1/webtop-proxy/websocket?token=<token>" || echo "Connection working"
```

**Container Status**
```bash
# List all webtop containers
podman ps --filter "name=webtop" --format "table {{.Names}}\t{{.Status}}"

# Check specific container
podman inspect proj-pod-1-webtop | jq '.[0].State'
```

### Performance Metrics

**Real-time Connection Count**
```bash
# Connections to port 8000
netstat -an | grep ':8000' | grep ESTABLISHED | wc -l

# WebSocket connections specifically
ss -nt | grep :8000 | wc -l
```

**Resource Usage**
```bash
# Backend container
podman stats backend

# Webtop container
podman stats proj-pod-{id}-webtop

# All containers
podman stats --all
```

### Prometheus Metrics (Optional)

Add to `settings.py`:
```python
PROMETHEUS_METRICS = {
    'webtop_connections': Counter('webtop_connections_total', 'Total connections'),
    'webtop_messages': Counter('webtop_messages_total', 'Total messages forwarded'),
    'webtop_errors': Counter('webtop_errors_total', 'Total errors'),
}
```

---

## Troubleshooting

### WebSocket Connection Fails

**Check 1: Is Daphne running?**
```bash
ps aux | grep daphne
# Should show: daphne -b 0.0.0.0 -p 8000 backend.asgi:application
```

**Check 2: Are the right ports listening?**
```bash
netstat -tlnp | grep -E "8000|8082"
# Should show:
# 8000 - backend (Daphne)
# 8082 - webtop container (Selkies)
```

**Check 3: Is JWT token valid?**
```bash
# Check token expiration
curl http://localhost:8000/api/token/verify/ \
  -H "Content-Type: application/json" \
  -d "{\"token\":\"$TOKEN\"}"

# If 401, token expired or invalid
# If 200, token is valid
```

**Check 4: Enable debug logging**
```bash
export WEBTOP_PROXY_DEBUG=1
# Restart backend
# Check logs for connection flow
```

### Stream Not Loading

**Check 1: Is container running?**
```bash
podman ps | grep webtop
# Should show: proj-pod-{id}-webtop  Up
```

**Check 2: Is Selkies running?**
```bash
podman exec proj-pod-{id}-webtop ps aux | grep selkies
# Should show selkies process running
```

**Check 3: Is port 8082 accessible?**
```bash
podman exec backend nc -zv container 8082
# Should show: succeeded or connection succeeded
```

**Check 4: Enable debug and watch message flow**
```bash
WEBTOP_PROXY_DEBUG=1 podman logs -f backend | grep -E "Backend→Client|BINARY"
# Should see BINARY messages (video frames) flowing
```

### High Latency / Slow Response

**Check 1: Message throughput**
```bash
WEBTOP_PROXY_DEBUG=1 podman logs backend | grep -c "Backend→Client"
# Over 30 lines per second = good
# < 10 lines per second = bottleneck
```

**Check 2: Network latency**
```bash
ping container-ip
# < 10 ms = good
# 50+ ms = investigate network
```

**Check 3: Container resources**
```bash
podman stats proj-pod-{id}-webtop
# CPU < 50% available cores
# Memory < 50% limit
```

### Container OOM Killed

**Solution 1: Increase memory limit**
```yaml
services:
  webtop:
    deploy:
      resources:
        limits:
          memory: 2G  # Increase from default
        reservations:
          memory: 1G
```

**Solution 2: Cleanup volumes**
```bash
# List workspace volumes
podman volume ls | grep workspace

# Remove old workspaces (CAREFUL!)
podman volume rm proj-1-workspace
```

---

## Backup & Recovery

### Backup Workspace Volumes

```bash
# Create backup
podman run --rm \
  -v proj-1-workspace:/workspace \
  -v /backups:/backup \
  alpine tar czf /backup/proj-1-workspace-$(date +%s).tar.gz -C /workspace .

# List backups
ls -lh /backups/
```

### Restore Workspace

```bash
# Create new volume
podman volume create proj-1-workspace

# Restore from backup
podman run --rm \
  -v proj-1-workspace:/workspace \
  -v /backups:/backup \
  alpine tar xzf /backup/proj-1-workspace-1701234567.tar.gz -C /workspace
```

### Database Backup

```bash
# PostgreSQL backup
podman exec db pg_dump -U user appdb > backup-$(date +%s).sql

# Restore
cat backup-1701234567.sql | podman exec -i db psql -U user appdb
```

---

## Scaling

### Single Server (Current)
- ✅ 5-10 concurrent projects
- ✅ In-memory Channels layer
- ✅ SQLite or single PostgreSQL instance

### Multiple Servers

**Option 1: Load-balanced backends**
```yaml
# Add Redis for Channels cross-server communication
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('redis', 6379)],
        },
    },
}
```

**Option 2: Kubernetes**
- Deploy backend pods
- Deploy Daphne sidecar containers
- Use Channels layer Redis
- See `orchestrator.py` for K8s extension

---

## Security Hardening

### HTTPS/WSS

```python
# settings.py
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

### Rate Limiting

```python
# Add rate limiting for token endpoint
from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='10/m')
def token_view(request):
    ...
```

### Network Isolation

```bash
# Create isolated network for webtop containers
podman network create webtop-net

# Connect only specific containers
podman network connect webtop-net proj-pod-1-webtop
```

### Audit Logging

```python
# Log all webtop access
import logging

logger = logging.getLogger('webtop.audit')

# In consumer.py
logger.info(f"User {user} accessed webtop for project {project_id}")
logger.info(f"WebSocket closed: {close_code}")
```

---

## Maintenance

### Regular Tasks

**Daily**:
- Check disk space: `df -h /var/lib/containers`
- Monitor logs for errors: `podman logs --tail 100 backend`

**Weekly**:
- Cleanup old logs: `podman logs --tail 100 backend > backup.log && : > logs`
- Check outdated containers: `podman images`

**Monthly**:
- Backup workspace volumes
- Update container images: `podman pull lscr.io/linuxserver/webtop:latest`
- Review resource usage trends

### Cleanup Script

```bash
#!/bin/bash

# Clean up stopped containers
podman container prune -f

# Clean up unused volumes
podman volume prune -f

# Clean up unused images
podman image prune -f

# Clean up stopped webtop containers older than 7 days
podman ps -a --filter "name=webtop" --filter "status=exited" \
    --format "{{.ID}} {{.CreatedAt}}" | while read id created; do
    if [[ $(date -d "$created" +%s) -lt $(date -d "7 days ago" +%s) ]]; then
        podman rm $id
    fi
done
```

### Update Process

```bash
# 1. Build new image
podman build -t your-registry/backend:latest .

# 2. Push to registry
podman push your-registry/backend:latest

# 3. Stop current service
podman-compose down

# 4. Pull updated image
podman pull your-registry/backend:latest

# 5. Start service
podman-compose up -d

# 6. Verify health
sleep 5
curl http://localhost:8000/api/health/
```

---

## Support & Resources

- **Django Channels**: https://channels.readthedocs.io/
- **Daphne**: https://github.com/django/daphne
- **Podman**: https://podman.io/
- **Selkies**: https://github.com/selkies-project/selkies

---

**Last Updated**: December 4, 2025  
**Version**: 1.0  
**Status**: Production Ready
