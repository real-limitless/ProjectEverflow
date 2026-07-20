# Project Everflow

## Overview

Project Everflow is an enterprise-grade collaborative AI application development platform enabling teams to build, review, and deploy AI-powered applications with built-in safety, compliance, and approval workflows. It solves the problem of balancing rapid innovation with corporate governance by providing a "governance-first" environment where global compliance, regulatory, and data-handling rules are enforced at the platform level.

Inspired by creative platforms like HuggingFace Spaces, Everflow adds critical oversight to prevent unrestricted development.
Users can freely create applications within pre-approved boundaries, ensuring consistency and inherent compliance for all tools.

Every **project** is backed by an isolated [microsandbox](https://agentsandbox.dev/) microVM. Clients talk only to the Everflow API; an internal **sandbox-agent** owns KVM and the microsandbox SDK.

## Docker Compose

Three services:

| Service | Role | Ports (prod / dev) |
|---------|------|--------------------|
| `frontend` | UI | `3000` (nginx) / `5173` (Vite HMR) |
| `backend` | **Sole public API** (`everflow-platform-api`) | `8000` |
| `sandbox-agent` | Privileged microsandbox control plane | not published / `8090` in dev |

### Host requirements

- Linux with **`/dev/kvm`** for real microVMs (`ls -l /dev/kvm`)
- Docker or Podman with privileged containers + device passthrough
- Without KVM, set `SANDBOX_MOCK=true` (default in compose) for in-memory mock sandboxes

```bash
cp .env.example .env
# edit SANDBOX_AGENT_TOKEN and SECRET_KEY
```

### Production-style stack

Built images, static UI (nginx), no source mounts:

```bash
docker compose up --build
```

- UI: http://localhost:3000  
- API docs: http://localhost:8000/docs  
- Health: `GET /api/v1/health` · Ready (DB + agent): `GET /api/v1/ready`

### Development stack (hot reload)

Bind-mounts source and runs reload-friendly processes:

| Service | Reload behavior |
|---------|-----------------|
| `frontend` | Vite HMR (`deploy/frontend.dev.Dockerfile`) |
| `backend` | `uvicorn --reload` via `UVICORN_RELOAD=true` |
| `sandbox-agent` | `uvicorn --reload` |

```bash
docker compose -f docker-compose.dev.yml up --build
```

- UI: http://localhost:5173  
- API docs: http://localhost:8000/docs  
- Sandbox agent health: http://localhost:8090/health  

Edit files under `everflow-platform-ui/`, `everflow-platform-api/`, or `everflow-sandbox-agent/` on the host; containers pick up changes without rebuild.

**Notes:**

- Dependency changes (`package.json`, `pyproject.toml`) still need a rebuild / reinstall (`docker compose -f docker-compose.dev.yml up --build`).
- If Vite does not notice file changes (some Docker Desktop / remote FS setups), set `VITE_USE_POLLING=true` or `CHOKIDAR_USEPOLLING=true` in `.env`.
- Prefer the same `.env` as production compose; dev defaults `FRONTEND_URL` to `http://localhost:5173`.
- Host bind mounts use the `:Z` SELinux label (required on Fedora/RHEL/Podman). Without it, Alembic fails with `No 'script_location' key found` because the config file is unreadable.

For real microVMs:

```bash
# .env
SANDBOX_MOCK=false
SANDBOX_AGENT_TOKEN=your-long-secret
```

Project create → backend provisions a detached sandbox via sandbox-agent → bootstrap installs **Claude Code** + **OpenCode** harness stubs (full CLIs when image/network allow).

## Local development (without Compose)

### Platform API

```bash
cd everflow-platform-api
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
alembic upgrade head
# optional: point at a local sandbox-agent
export SANDBOX_AGENT_URL=http://localhost:8090
export SANDBOX_AGENT_TOKEN=dev-token
export SANDBOX_ENABLED=true
uvicorn app.main:app --reload --port 8000
```

### Sandbox agent

```bash
cd everflow-sandbox-agent
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
export SANDBOX_AGENT_TOKEN=dev-token
export SANDBOX_MOCK=true
export WORKSPACE_ROOT=/tmp/everflow-workspaces
uvicorn app.main:app --reload --port 8090
```

### UI

```bash
cd everflow-platform-ui
npm install
# Point at local API (default)
export VITE_API_URL=http://localhost:8000
npm run dev
```

Sign in (or register) in the UI — create project provisions a sandbox. Terminal/Code talk only to the Everflow API.

Offline UI mock (no API): `VITE_DEMO_MODE=true npm run dev`

See [everflow-platform-api/README.md](everflow-platform-api/README.md), [everflow-sandbox-agent/README.md](everflow-sandbox-agent/README.md), and [PLAN.md](PLAN.md).

## License

This project is licensed under the terms described in [LICENSE](LICENSE).


