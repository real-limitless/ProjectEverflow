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

### Quick install

```bash
./scripts/everflow-install.sh
```

Generates `.env` secrets, starts Compose, waits for `GET /api/v1/system/health`, then open the UI for **first-run setup** (platform admin + first organization).

Manual alternative:

```bash
cp .env.example .env
# edit SANDBOX_AGENT_TOKEN, SECRET_KEY, and CREDENTIALS_ENCRYPTION_KEY
docker compose up --build
```

### Production checklist (operators)

- Set `ENVIRONMENT=production` (API refuses default `SECRET_KEY` / `SANDBOX_AGENT_TOKEN`)
- Set unique `SECRET_KEY`, `SANDBOX_AGENT_TOKEN`, and `CREDENTIALS_ENCRYPTION_KEY`
- Prefer PostgreSQL via `DATABASE_URL=postgresql+asyncpg://…`
- Confirm `/dev/kvm` and `SANDBOX_MOCK=false` for real sandboxes
- Optional: `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` (+ `OAUTH_REDIRECT_BASE_URL`) for Sign in with GitHub
- After boot: complete first-run wizard → invite teammates → add GitHub PAT under Organization & Git

### Production-style stack

Built images, static UI (nginx), no source mounts:

```bash
docker compose up --build
```

- UI: http://localhost:3000  
- API docs: http://localhost:8000/docs  
- Health: `GET /api/v1/health` · Ready (DB + agent + setup flag): `GET /api/v1/ready`  
- First-run: `GET /api/v1/setup/status` · `POST /api/v1/setup/bootstrap`

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

Project create → backend provisions a detached sandbox via sandbox-agent. Create returns once the microVM is up; harness install (if needed) runs in the background.

### Prebaked guest image (recommended)

Project sandboxes boot an **OCI guest image** (separate from the sandbox-agent host image). Bake Node + Claude Code + OpenCode into that image so tools are ready immediately:

```bash
./deploy/build-sandbox-guest.sh
# optional: PUSH=true ./deploy/build-sandbox-guest.sh
# default tag: ghcr.io/limitless-rh/everflow-sandbox-guest:dev
```

Set `SANDBOX_DEFAULT_IMAGE=ghcr.io/limitless-rh/everflow-sandbox-guest:dev` (default in `.env.example`). Microsandbox must be able to pull the tag (local store or registry). First boot may pull/cache the image once; later creates stay fast.

See `deploy/sandbox-guest.Dockerfile` and `everflow-sandbox-agent/README.md`.

### App toolkits

Project create templates seed cloneable starters from [`toolkits/`](toolkits/README.md) (web, PHP, Expo/React Native, desktop, Python, full-stack). Mobile templates are labeled **(React Native)** and share the Expo toolkit; Preview uses phone/tablet device frames around Expo web (not real simulators).

- Local seed: `TOOLKIT_LOCAL_ROOT=/toolkits` (mounted/copied into the API image)
- Optional remote: `TOOLKIT_REPO_BASE=https://github.com/org/everflow-toolkit-{id}.git`

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


