# Project Everflow

## Overview

Project Everflow is an enterprise-grade collaborative AI application development platform enabling teams to build, review, and deploy AI-powered applications with built-in safety, compliance, and approval workflows. It solves the problem of balancing rapid innovation with corporate governance by providing a "governance-first" environment where global compliance, regulatory, and data-handling rules are enforced at the platform level.

Inspired by creative platforms like HuggingFace Spaces, Everflow adds critical oversight to prevent unrestricted development.
Users can freely create applications within pre-approved boundaries, ensuring consistency and inherent compliance for all tools.

Every **project** is backed by an isolated [microsandbox](https://agentsandbox.dev/) microVM. Clients talk only to the Everflow API; an internal **sandbox-agent** owns KVM and the microsandbox SDK.

## Install (Docker / Podman only)

The supported product install runs **entirely in containers**. The host only needs:

- **Docker** or **Podman** with the Compose V2 plugin (`docker compose` / `podman compose`)
- Linux with **`/dev/kvm`** for real microVMs (`ls -l /dev/kvm`)
- Privileged containers + device passthrough for `sandbox-agent`
- Without KVM, set `SANDBOX_MOCK=true` in `.env` (CI/dev only — not for product use)

No host Python, Node, or package installs are required for the control plane.

### One-liner (website / remote bootstrap)

Ship a **single bash script** on your site (or use the copy in this repo). Users run:

```bash
curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/main/scripts/get-everflow.sh | bash
```

Or host the same file on your domain (recommended for branding / stable URLs):

```bash
# After you publish scripts/get-everflow.sh as https://YOUR_DOMAIN/install
curl -fsSL https://YOUR_DOMAIN/install | bash
```

Safer (inspect before run):

```bash
curl -fsSL https://YOUR_DOMAIN/install -o get-everflow.sh
less get-everflow.sh
bash get-everflow.sh
```

What the bootstrap does: check Docker/Podman → clone/download ProjectEverflow into `~/everflow` → run `./scripts/everflow` (interactive menu on a TTY, or `install` when non-interactive).

Useful env vars:

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVERFLOW_DIR` | `$HOME/everflow` | Install path |
| `EVERFLOW_VERSION` | `main` | Git branch or tag |
| `EVERFLOW_ACTION` | `menu` (TTY) / `install` | What to run after download |
| `EVERFLOW_NONINTERACTIVE=1` | — | Force `install` (no menu) |
| `EVERFLOW_REPO` | this GitHub repo | Override source |

```bash
# Non-interactive example
EVERFLOW_NONINTERACTIVE=1 EVERFLOW_DIR=/opt/everflow \
  curl -fsSL https://YOUR_DOMAIN/install | bash
```

Details: [`scripts/get-everflow.sh`](scripts/get-everflow.sh) · [`scripts/README.md`](scripts/README.md).

### Quick install (from a git clone — embedded local registry)

Everflow runs an **always-on private OCI registry** (`registry` compose service) so control-plane and **guest microVM** images are pulled locally — microsandbox does not need GitHub Container Registry after seed.

**Recommended:** interactive installer — **ask → install registry → full stack**:

```bash
./scripts/everflow
# or:
./scripts/everflow install
# optional: CONTAINER_ENGINE=podman ./scripts/everflow install
```

The wizard asks how to fill the local registry (build / GHCR mirror / skip), then:

1. **Phase 1** — start the embedded registry and seed images  
2. **Phase 2** — start frontend, backend, sandbox-agent, searxng  

Registry-only: `./scripts/everflow registry status|seed|up`

`./scripts/everflow-install.sh` still works (wrapper around `everflow install`).

| Image | Host pull (compose) | Inside agent (msb) |
|-------|---------------------|--------------------|
| Frontend / backend / agent | `localhost:5000/everflow/everflow-*:latest` | — |
| Guest microVM | (same host path for push) | `registry:5000/everflow/everflow-sandbox-guest:latest` |
| SearXNG / microsandbox base | `localhost:5000/everflow/upstream-*:latest` | — |

Quiet by default (logs → `.everflow-install.log`). If the local registry is empty, install falls back to build+seed.

**Other install modes:**

```bash
# Build + seed local registry, then start
BUILD_FROM_SOURCE=1 ./scripts/everflow install

# Mirror published GHCR images into the local registry (no compile), then start
INSTALL_MODE=ghcr ./scripts/everflow install

# Airgap: on online host export, on offline host import
./deploy/local-registry.sh export /path/everflow-images.tar
./deploy/local-registry.sh import /path/everflow-images.tar
```

Configure Docker/Podman for the HTTP registry (`insecure-registries` / Podman `insecure=true`) — see [`deploy/README.md`](deploy/README.md).

**First-run admin** (platform admin + organization) — either:

```bash
./scripts/everflow setup-admin
# non-interactive:
# EVERFLOW_ADMIN_EMAIL=you@example.com EVERFLOW_ADMIN_PASSWORD='…' ./scripts/everflow setup-admin
```

…or open the UI wizard at http://localhost:3000. See [`scripts/README.md`](scripts/README.md) for the full menu (status, logs, upgrade, uninstall, reinstall).

Manual equivalents:

```bash
cp .env.example .env
# pull path (preferred for users):
docker compose pull && docker compose up -d --no-build
# build path:
docker compose up --build -d
```

> **Note:** Prebuilt frontend images use same-origin `/api` (nginx → backend), so one image works on any host without baking `VITE_API_URL` at build time. Publish images to GHCR from CI for the pull path to work without fallback.

### Stack services

| Service | Role | Ports (prod / dev) |
|---------|------|--------------------|
| `registry` | Embedded private OCI registry | `127.0.0.1:5000` (host push/pull) |
| `frontend` | UI | `3000` (nginx) / `5173` (Vite HMR) |
| `backend` | **Sole public API** (`everflow-platform-api`) | `8000` |
| `sandbox-agent` | Privileged microsandbox control plane | not published / `8090` in dev |
| `searxng` | Internal knowledge search | not published |

### Production checklist (operators)

- Set `ENVIRONMENT=production` (API refuses default `SECRET_KEY` / `SANDBOX_AGENT_TOKEN`)
- Set unique `SECRET_KEY`, `SANDBOX_AGENT_TOKEN`, and `CREDENTIALS_ENCRYPTION_KEY`
- Prefer PostgreSQL via `DATABASE_URL=postgresql+asyncpg://…` (run Postgres as another Compose service or external DB)
- Confirm `/dev/kvm` and `SANDBOX_MOCK=false` for real sandboxes
- Optional: `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` (+ `OAUTH_REDIRECT_BASE_URL`) for Sign in with GitHub
- After boot: complete first-run wizard → invite teammates → add GitHub PAT under Organization & Git

### Production-style stack

Built images, static UI (nginx), no source mounts:

```bash
docker compose up --build -d
# or: podman compose up --build -d
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

### Publishing images (maintainers)

Default build targets the **local** registry. GHCR remains optional for public distribution:

```bash
./deploy/local-registry.sh seed          # local product path
./deploy/build-images.sh                 # tag localhost:5000/everflow/*
PUSH=true ./deploy/build-images.sh

# Public GHCR publish:
docker login ghcr.io
EVERFLOW_REGISTRY=ghcr.io/limitless-rh PUSH=true ./deploy/build-images.sh
EVERFLOW_IMAGE_TAG=v0.1.0 EVERFLOW_REGISTRY=ghcr.io/limitless-rh PUSH=true ./deploy/build-images.sh
```

See [`deploy/README.md`](deploy/README.md).

### Prebaked guest image

Project sandboxes boot an **OCI guest image** (separate from the sandbox-agent host image). Microsandbox pulls it into `MSB_HOME` from the **embedded registry** by default:

```bash
SANDBOX_DEFAULT_IMAGE=registry:5000/everflow/everflow-sandbox-guest:latest
```

Use `localhost:5000/...` only for host-side `docker push`/`pull`. Inside the agent container, `localhost` is wrong — always use the compose service hostname `registry`.

The local registry is **HTTP-only**. microsandbox defaults to HTTPS, so the agent
marks `registry:5000` as insecure in `$MSB_HOME/config.json` on startup and
passes `insecure=True` when creating sandboxes from that image. If provision
fails with `https://registry:5000/... registry error`, seed the guest image
(`./deploy/local-registry.sh seed` or `ONLY=guest … build-push`) and restart
`sandbox-agent`.

### App toolkits

Project create templates seed cloneable starters from [`toolkits/`](toolkits/README.md) (web, PHP, Expo/React Native, desktop, Python, full-stack). Mobile templates are labeled **(React Native)** and share the Expo toolkit; Preview uses phone/tablet device frames around Expo web (not real simulators).

- Local seed: `TOOLKIT_LOCAL_ROOT=/toolkits` (mounted/copied into the API image)
- Optional remote: `TOOLKIT_REPO_BASE=https://github.com/org/everflow-toolkit-{id}.git`

## Contributor development (optional, not the product install)

Product deployments use Compose/Podman only (see above). The following is for
contributors iterating on a single service outside containers.

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


