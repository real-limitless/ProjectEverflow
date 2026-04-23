# Webtop Quick Start Guide

## Prerequisites

1. **Podman Installed**
   ```bash
   # Fedora/RHEL
   sudo dnf install podman
   
   # Ubuntu/Debian
   sudo apt install podman
   
   # Verify installation
   podman --version
   ```

2. **Backend Running**
   ```bash
   cd backend
   python manage.py runserver
   ```

3. **Frontend Running**
   ```bash
   npm run dev
   ```

4. **Authenticated User**
   - Login at http://localhost:8080/login
   - Ensure you have a project created

---

## Testing the Webtop Feature

### Step 1: Provision Webtop

1. Navigate to **My Projects** → select a project → **Edit**
2. Click the **Webtop** tab (new tab at the end)
3. Click **"Provision Webtop Workspace"**
4. Wait for provisioning (first time may take 2-3 minutes to pull image)
5. Status indicator should turn green when ready

**Expected Behavior**:
- Spinner shows while provisioning
- Toast notification on success
- Control bar appears with Start/Stop/Restart/Kill buttons
- Iframe loads showing Fedora KDE desktop

**Troubleshooting**:
- Check backend logs: `backend/logs/` or console output
- Verify Podman daemon: `podman info`
- Check image pull: `podman images | grep webtop`

### Step 2: Test Lifecycle Controls

1. Click **Stop** button → status turns gray, iframe shows "not running" message
2. Click **Start** button → status turns green, desktop reappears
3. Click **Restart** button → brief interruption, desktop reloads
4. Test **Kill** button (force stop)

**Expected Behavior**:
- Each action triggers toast notification
- Status updates within 5 seconds (auto-poll)
- Buttons disable/enable based on current state

### Step 3: View Container Logs

1. Switch to **Container Logs** tab
2. Select "webtop" from service dropdown
3. Adjust tail lines (try 500, 1000, 2000)
4. Enable "Auto-refresh" checkbox
5. Click **Download** to save logs

**Expected Behavior**:
- Logs appear in terminal-style display (green on black)
- Auto-refresh updates every 3 seconds
- Download saves `.txt` file with timestamp
- Truncation warning shows if logs exceed tail limit

---

## Manual Testing Checklist

### Provisioning
- [ ] Can provision webtop for new project
- [ ] Provisioning is idempotent (can call multiple times safely)
- [ ] Workspace volume persists after container restart
- [ ] Error handling works (e.g., Podman not installed)

### Lifecycle
- [ ] Start button works when stopped
- [ ] Stop button works when running
- [ ] Restart button works in any state
- [ ] Kill button force-stops service
- [ ] Buttons disable appropriately based on status
- [ ] Status polling updates UI automatically

### Logs
- [ ] Logs load for running service
- [ ] Logs load for stopped service
- [ ] Tail parameter controls line count
- [ ] Auto-refresh works when enabled
- [ ] Download saves correct content
- [ ] Service selector shows all services

### Security
- [ ] Non-owners cannot access other projects' webtops
- [ ] Unauthenticated users redirected to login
- [ ] Proxy requires valid session
- [ ] Direct container access blocked (no host ports)

### Persistence
- [ ] Files created in `/config` persist after restart
- [ ] Volume survives container removal (check with `podman volume ls`)
- [ ] Multiple projects get isolated volumes

---

## Backend API Testing

### Using curl

**Provision Webtop**:
```bash
TOKEN="your_jwt_token_here"
PROJECT_ID=1

curl -X POST "http://127.0.0.1:8000/api/projects/${PROJECT_ID}/ensure_webtop/" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json"
```

**Get Services**:
```bash
curl "http://127.0.0.1:8000/api/project-services/?project=${PROJECT_ID}" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Start Service**:
```bash
SERVICE_ID=1

curl -X POST "http://127.0.0.1:8000/api/project-services/${SERVICE_ID}/start/" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Get Logs**:
```bash
curl "http://127.0.0.1:8000/api/project-services/${SERVICE_ID}/logs/?tail=100" \
  -H "Authorization: Bearer ${TOKEN}"
```

**Access Proxy** (in browser, must be logged in):
```
http://127.0.0.1:8000/api/projects/1/webtop-proxy/
```

---

## Podman CLI Verification

**Check Pod**:
```bash
podman pod ls
# Should show: proj-pod-1 (or similar)
```

**Check Container**:
```bash
podman ps -a
# Should show: proj-pod-1-webtop
```

**Inspect Container**:
```bash
podman inspect proj-pod-1-webtop
```

**View Logs Directly**:
```bash
podman logs proj-pod-1-webtop
```

**Check Volume**:
```bash
podman volume ls
# Should show: proj-1-workspace
```

**Inspect Volume**:
```bash
podman volume inspect proj-1-workspace
```

---

## Performance Benchmarks

### Provisioning Times
- **First time** (image pull): 60-180 seconds
- **Subsequent provisions**: 10-20 seconds
- **Start existing container**: 3-5 seconds

### Resource Usage (Typical)
- **Webtop Container**: 
  - Memory: ~500MB idle, ~1-2GB with desktop usage
  - CPU: 5-10% idle, 20-40% active
  - Disk: ~2GB for image + workspace volume

### API Response Times
- `ensure_webtop`: 5-15s (first time), 1-3s (subsequent)
- Lifecycle actions: 200-500ms
- Logs retrieval (1000 lines): 100-300ms
- Service list: 50-150ms

---

## Known Issues & Workarounds

### Issue: WebSocket Connection Failed
**Symptom**: noVNC viewer shows connection error in webtop  
**Cause**: HTTP-only proxy doesn't support WebSocket upgrade  
**Workaround**: Use Django Channels (see `docs/agents/webtop.md` for setup)

### Issue: Container Won't Start
**Symptom**: Status stuck at "creating" or "error"  
**Solution**:
```bash
# Check Podman events
podman events --since 5m

# Remove stuck container
podman rm -f proj-pod-X-webtop

# Re-provision from UI
```

### Issue: Logs Show "Permission Denied"
**Symptom**: Log retrieval fails with permission error  
**Solution**: Ensure backend runs with correct Podman socket access
```bash
# Add user to podman group (if needed)
sudo usermod -aG podman $USER
newgrp podman
```

### Issue: Volume Not Persisting
**Symptom**: Files disappear after restart  
**Cause**: Volume mount path incorrect  
**Solution**: Verify volume mount in `ensure_webtop` action:
```python
volumes=[
    {
        'type': 'volume',
        'source': workspace_volume,
        'target': '/config',  # Must match webtop image convention
        'readonly': False,
    }
]
```

---

## Cleanup Commands

**Remove All Project Containers**:
```bash
podman pod rm -f proj-pod-1
```

**Remove Workspace Volume**:
```bash
podman volume rm proj-1-workspace
```

**Prune Unused Resources**:
```bash
podman system prune -a -f
```

**Reset Everything**:
```bash
# Stop all containers
podman stop -a

# Remove all containers and pods
podman rm -a -f
podman pod rm -a -f

# Remove all volumes
podman volume prune -f

# Remove all images
podman rmi -a -f
```

---

## Next Steps

1. **Add More Services**: Modify `ensure_webtop` to provision backend/frontend containers
2. **Git Integration**: Auto-clone project repo into workspace on provision
3. **Templates**: Create project templates with pre-configured environments
4. **Observability**: Set up Prometheus metrics endpoint
5. **Kubernetes**: Implement `KubernetesOrchestrator` class

---

**Last Updated**: 2025-11-27  
**Status**: Ready for Testing  
**Feedback**: Report issues to project maintainers
