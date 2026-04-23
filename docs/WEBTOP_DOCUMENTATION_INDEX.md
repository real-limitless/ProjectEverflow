# Webtop WebSocket Proxy - Documentation Index

## 📖 Documentation Guide

This folder contains comprehensive documentation for the Webtop containerized development environment and its WebSocket proxy implementation.

---

## 🚀 Start Here

### For First-Time Users
1. Read: **`WEBTOP_IMPLEMENTATION_COMPLETE.md`** (5 min overview)
2. Then: **`docs/agents/webtop.md`** (full feature guide)
3. Setup: **`WEBTOP_DEPLOYMENT_GUIDE.md`** (quick start section)

### For Developers
1. Read: **`WEBSOCKET_PROXY_CURRENT.md`** (architecture & implementation)
2. Check: `backend/api/consumers.py` (actual code)
3. Test: Debug logging section in `WEBTOP_DEPLOYMENT_GUIDE.md`

### For DevOps/Operations
1. Read: **`WEBTOP_DEPLOYMENT_GUIDE.md`** (all sections)
2. Setup: Deployment section + nginx config
3. Monitor: Monitoring & Observability section

### For Troubleshooting
1. Check: **`WEBTOP_DEPLOYMENT_GUIDE.md`** → Troubleshooting section
2. Enable: `WEBTOP_PROXY_DEBUG=1` environment variable
3. Read: Error messages in `WEBSOCKET_PROXY_CURRENT.md`

---

## 📚 Document Descriptions

### `WEBSOCKET_PROXY_CURRENT.md`
**Best for**: Technical details, architecture, debugging  
**Length**: ~500 lines  
**Topics**:
- Complete connection flow diagram
- Implementation details for all components
- Three critical issues (fixed) with explanations
- Debug logging system
- Performance considerations
- Production deployment
- Code examples and references

**When to use**: Understanding how WebSocket proxy works, debugging connection issues, reviewing implementation

---

### `WEBTOP_IMPLEMENTATION_COMPLETE.md`
**Best for**: High-level overview, status summary  
**Length**: ~400 lines  
**Topics**:
- What's implemented (checklist)
- Architecture diagram
- Key implementation details
- Fixed critical issues
- Configuration requirements
- Testing & verification
- Performance profile table
- Deployment checklist

**When to use**: Quick reference, understanding current status, planning deployment

---

### `WEBTOP_DEPLOYMENT_GUIDE.md`
**Best for**: Setup, operations, troubleshooting  
**Length**: ~700 lines  
**Topics**:
- Quick start (local & production)
- System requirements
- Build & deploy
- Reverse proxy setup (nginx)
- Docker/Podman compose
- Monitoring & observability
- Health checks
- Comprehensive troubleshooting matrix
- Backup & recovery
- Scaling strategies
- Security hardening
- Maintenance tasks

**When to use**: Setting up Webtop, monitoring production, troubleshooting issues, planning maintenance

---

### `docs/agents/webtop.md`
**Best for**: User-facing feature guide  
**Length**: ~600 lines  
**Topics**:
- Feature overview
- Architecture components
- Usage workflows
- API endpoints
- Security model
- Configuration
- Future enhancements
- Troubleshooting

**When to use**: User documentation, API reference, feature explanation

---

### `WEBTOP_IMPLEMENTATION.md` (existing)
**Status**: Historical reference  
**Use**: For git history and previous implementation details  
**Note**: Superseded by newer documentation

---

### `WEBSOCKET_PROXY_GUIDE.md` (existing)
**Status**: Historical reference  
**Use**: For git history and previous implementation details  
**Note**: Key concepts moved to `WEBSOCKET_PROXY_CURRENT.md`

---

## 🔍 Quick Topic Lookup

| Topic | Document | Section |
|-------|----------|---------|
| Architecture overview | WEBSOCKET_PROXY_CURRENT.md | Connection Flow |
| Port 8082 explanation | WEBSOCKET_PROXY_CURRENT.md | Why Port 8082? |
| Concurrent tasks | WEBSOCKET_PROXY_CURRENT.md | Concurrent Task Pattern |
| Debug logging | WEBTOP_DEPLOYMENT_GUIDE.md | Debug Logging |
| Local setup | WEBTOP_DEPLOYMENT_GUIDE.md | Quick Start |
| Production deploy | WEBTOP_DEPLOYMENT_GUIDE.md | Production Deployment |
| Nginx config | WEBTOP_DEPLOYMENT_GUIDE.md | Reverse Proxy Configuration |
| Troubleshooting | WEBTOP_DEPLOYMENT_GUIDE.md | Troubleshooting |
| Health checks | WEBTOP_DEPLOYMENT_GUIDE.md | Monitoring & Observability |
| Features | docs/agents/webtop.md | Usage Workflow |
| API endpoints | docs/agents/webtop.md | API Endpoints |
| Security | docs/agents/webtop.md | Security Model |

---

## 🚨 Common Issues & Solutions

### "Waiting for stream" message
**Documents**: `WEBSOCKET_PROXY_CURRENT.md` (Issue #2), `WEBTOP_DEPLOYMENT_GUIDE.md` (Stream Not Loading)  
**Solution**: Verify port 8082 connection, check container logs, enable debug

### Input not working
**Documents**: `WEBSOCKET_PROXY_CURRENT.md` (Issue #3), `WEBTOP_DEPLOYMENT_GUIDE.md` (Input Not Working)  
**Solution**: Verify bidirectional message flow, enable debug logging, check Client→Backend messages

### WebSocket connection fails
**Documents**: `WEBTOP_DEPLOYMENT_GUIDE.md` (WebSocket Connection Fails)  
**Steps**: Check Daphne running, verify JWT token, enable debug, check container

### Stream latency/high latency
**Documents**: `WEBTOP_DEPLOYMENT_GUIDE.md` (High Latency)  
**Solution**: Check message throughput, network latency, container resources

---

## 📋 Before Going to Production

- [ ] Read: `WEBTOP_DEPLOYMENT_GUIDE.md` → Deployment Checklist
- [ ] Setup: Daphne ASGI server (not development runserver)
- [ ] Setup: Reverse proxy with WebSocket support
- [ ] Setup: SSL/TLS certificates
- [ ] Setup: Database (PostgreSQL recommended)
- [ ] Test: Full end-to-end WebSocket connection
- [ ] Enable: Monitoring and logging
- [ ] Disable: `WEBTOP_PROXY_DEBUG=1` environment variable
- [ ] Document: Your specific setup and configuration

---

## 🔄 Updating Documentation

When making changes to Webtop implementation:

1. **Update code** in `backend/api/consumers.py` or related files
2. **Update documentation** in appropriate file:
   - Architecture change → `WEBSOCKET_PROXY_CURRENT.md`
   - Deployment change → `WEBTOP_DEPLOYMENT_GUIDE.md`
   - Feature change → `docs/agents/webtop.md`
3. **Update** timestamp in footer: `**Last Updated**: December 4, 2025`
4. **Add** note in DOCUMENTATION_UPDATE_SUMMARY.md if major change

---

## 📞 Document Status

| Document | Status | Last Updated | Coverage |
|----------|--------|--------------|----------|
| WEBSOCKET_PROXY_CURRENT.md | ✅ New | Dec 4, 2025 | Architecture, Implementation, Debugging |
| WEBTOP_IMPLEMENTATION_COMPLETE.md | ✅ New | Dec 4, 2025 | Summary, Status, Issues |
| WEBTOP_DEPLOYMENT_GUIDE.md | ✅ New | Dec 4, 2025 | Setup, Operations, Troubleshooting |
| docs/agents/webtop.md | ⚠️ Needs update | Nov 27, 2025 | Features, API, Security |
| DOCUMENTATION_UPDATE_SUMMARY.md | ✅ New | Dec 4, 2025 | Index, Summary |

---

## 🎯 Implementation Status

| Feature | Status | Documentation |
|---------|--------|-----------------|
| HTTP Proxy | ✅ Complete | WEBSOCKET_PROXY_CURRENT.md |
| WebSocket Proxy | ✅ Complete | WEBSOCKET_PROXY_CURRENT.md |
| JWT Authentication | ✅ Complete | WEBSOCKET_PROXY_CURRENT.md |
| Concurrent Tasks | ✅ Complete | WEBSOCKET_PROXY_CURRENT.md |
| Debug Logging | ✅ Complete | WEBTOP_DEPLOYMENT_GUIDE.md |
| Container Orchestration | ✅ Complete | docs/agents/webtop.md |
| Frontend UI | ✅ Complete | docs/agents/webtop.md |
| Deployment Guide | ✅ Complete | WEBTOP_DEPLOYMENT_GUIDE.md |

---

## 💡 Key Concepts

### Port 8082
- Selkies daemon runs on port 8082 (full WebSocket support)
- NGINX on port 3000 (limited routing)
- Consumer connects directly to 8082 to avoid routing issues

### JWT Token Flow
1. Frontend passes token: `?token=<jwt>`
2. HTTP proxy injects script
3. Script wraps WebSocket constructor
4. Consumer extracts token and validates
5. Backend WebSocket includes token

### Concurrent Tasks
- `asyncio.create_task()` starts proxy in background
- `_backend_to_client()` listens indefinitely
- `receive()` called by framework when client sends
- Both directions work simultaneously

### Debug Logging
- `export WEBTOP_PROXY_DEBUG=1` to enable
- Logs all connection and message details
- Disabled by default for clean production logs

---

## 🔗 Related Files

**Code**:
- `backend/api/consumers.py` - Main WebSocket consumer
- `backend/api/proxy_views.py` - HTTP proxy with token injection
- `backend/api/channels_auth.py` - JWT middleware
- `backend/backend/asgi.py` - ASGI routing

**Configuration**:
- `backend/settings.py` - Django settings
- `podman-compose.yml` - Container configuration
- `nginx.conf` - Reverse proxy setup (if needed)

**Frontend**:
- `src/components/project/WebtopTab.tsx` - UI component
- `src/lib/api.ts` - API client

---

**Documentation Version**: 1.0  
**Last Updated**: December 4, 2025  
**Status**: ✅ Complete and Ready for Production
