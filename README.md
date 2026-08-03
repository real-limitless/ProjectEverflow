# Project Everflow

**Governance-first collaborative AI apps — on your infrastructure.**

Teams build, review, and deploy AI-powered applications inside pre-approved boundaries. Every **project** runs in an isolated [microsandbox](https://agentsandbox.dev/) microVM. Clients talk only to the Everflow API; an internal **sandbox-agent** owns KVM and the microsandbox SDK.

| | |
|---|---|
| **License** | [Apache-2.0](LICENSE) |
| **Concept / methodology** | Branch [`CORE`](https://github.com/real-limitless/ProjectEverflow/tree/CORE) (default on GitHub) |
| **Runnable product** | This branch: **`Development-Everflow`** |
| **Roadmap** | [ROADMAP.md](ROADMAP.md) |
| **Security** | [SECURITY.md](SECURITY.md) |
| **Contributing** | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## Requirements

| Need | Notes |
|------|--------|
| **Linux** | Host with containers |
| **Docker** or **Podman** | Compose V2 (`docker compose` / `podman compose`) |
| **`/dev/kvm`** | Real microVMs (`ls -l /dev/kvm`) |
| Privileged containers + device passthrough | For `sandbox-agent` |

Without KVM (CI/dev only): set `SANDBOX_MOCK=true` in `.env` — not for product use.

No host Python or Node is required for the control plane.

---

## Quick start (recommended)

### 1. Clone the product branch

```bash
git clone -b Development-Everflow https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
```

> **Note:** The default GitHub branch **`CORE`** is concept and methodology only. Install and run from **`Development-Everflow`** (or a release tag).

### 2. Run the install TUI

```bash
./scripts/everflow
# or non-interactive:
./scripts/everflow install
```

The wizard seeds an embedded local OCI registry, then starts the stack (frontend, backend, sandbox-agent, searxng).

### 3. Create the first admin

```bash
./scripts/everflow setup-admin
# non-interactive:
# EVERFLOW_ADMIN_EMAIL=you@example.com EVERFLOW_ADMIN_PASSWORD='…' ./scripts/everflow setup-admin
```

Or open the UI wizard at **http://localhost:3000**.

### 4. Open the platform

| Surface | URL |
|---------|-----|
| UI | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Health | `GET /api/v1/health` |
| Ready | `GET /api/v1/ready` |

Full menu (status, logs, upgrade, uninstall): [`scripts/README.md`](scripts/README.md).

---

## One-liner bootstrap

```bash
curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/Development-Everflow/scripts/get-everflow.sh | bash
```

Safer (inspect before run):

```bash
curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/Development-Everflow/scripts/get-everflow.sh -o get-everflow.sh
less get-everflow.sh
bash get-everflow.sh
```

What it does: check Docker/Podman → clone into `~/everflow` (product branch) → run `./scripts/everflow` (menu on TTY, `install` when non-interactive).

| Variable | Default | Purpose |
|----------|---------|---------|
| `EVERFLOW_DIR` | `$HOME/everflow` | Install path |
| `EVERFLOW_VERSION` | `Development-Everflow` | Git branch or tag |
| `EVERFLOW_ACTION` | `menu` (TTY) / `install` | After download |
| `EVERFLOW_NONINTERACTIVE=1` | — | Force `install` |
| `EVERFLOW_REPO` | this GitHub repo | Override source |

```bash
EVERFLOW_NONINTERACTIVE=1 EVERFLOW_DIR=/opt/everflow \
  curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/Development-Everflow/scripts/get-everflow.sh | bash
```

Details: [`scripts/get-everflow.sh`](scripts/get-everflow.sh) · [`scripts/README.md`](scripts/README.md).

---

## Install modes & registry

Everflow runs an **always-on private OCI registry** (`registry` compose service) so control-plane and **guest microVM** images stay local.

```bash
# Build + seed local registry, then start
BUILD_FROM_SOURCE=1 ./scripts/everflow install

# Mirror published GHCR images into the local registry (when published), then start
INSTALL_MODE=ghcr ./scripts/everflow install

# Airgap: export on online host, import offline
./deploy/local-registry.sh export /path/everflow-images.tar
./deploy/local-registry.sh import /path/everflow-images.tar
```

Registry-only: `./scripts/everflow registry status|seed|up`

Configure Docker/Podman for the HTTP registry (`insecure-registries` / Podman `insecure=true`) — see [`deploy/README.md`](deploy/README.md).

Quiet by default (logs → `.everflow-install.log`). If the local registry is empty, install falls back to build+seed.

---

## Stack services

| Service | Role | Ports (prod / dev) |
|---------|------|--------------------|
| `registry` | Embedded private OCI registry | `127.0.0.1:5000` |
| `frontend` | UI | `3000` / `5173` (Vite) |
| `backend` | **Sole public API** | `8000` |
| `sandbox-agent` | Privileged microsandbox control plane | not published / `8090` in dev |
| `searxng` | Internal knowledge search | not published |

```
Browser / UI  →  everflow-platform-api  →  everflow-sandbox-agent  →  microVM guest
```

---

## Production checklist

- Set `ENVIRONMENT=production` (API refuses default `SECRET_KEY` / `SANDBOX_AGENT_TOKEN`)
- Set unique `SECRET_KEY`, `SANDBOX_AGENT_TOKEN`, and `CREDENTIALS_ENCRYPTION_KEY`
- Prefer PostgreSQL via `DATABASE_URL=postgresql+asyncpg://…`
- Confirm `/dev/kvm` and `SANDBOX_MOCK=false` for real sandboxes
- Optional: GitHub/Google OAuth (`GITHUB_CLIENT_*`, `OAUTH_REDIRECT_BASE_URL`)
- After boot: first-run wizard → invite teammates → add Git credentials under Organization & Git

Copy env template: `cp .env.example .env` (or let `./scripts/everflow install` create it).

---

## Development compose (hot reload)

```bash
docker compose -f docker-compose.dev.yml up --build
```

- UI: http://localhost:5173  
- API: http://localhost:8000/docs  

Bind-mounts use the `:Z` SELinux label (Fedora/RHEL/Podman). See package READMEs for host-side contributor workflows.

---

## Publishing images (maintainers)

Default builds target the **local** registry. Optional public GHCR:

```bash
./deploy/local-registry.sh seed
docker login ghcr.io
EVERFLOW_REGISTRY=ghcr.io/real-limitless PUSH=true ./deploy/build-images.sh
EVERFLOW_IMAGE_TAG=v0.1.0 EVERFLOW_REGISTRY=ghcr.io/real-limitless PUSH=true ./deploy/build-images.sh
```

See [`deploy/README.md`](deploy/README.md).

---

## App toolkits

Project create templates seed starters from [`toolkits/`](toolkits/README.md) (web, PHP, Expo/React Native, desktop, Python, full-stack).

---

## Repository layout

| Path | Role |
|------|------|
| `everflow-platform-ui/` | React/Vite UI (PatternFly) |
| `everflow-platform-api/` | Public FastAPI platform |
| `everflow-sandbox-agent/` | MicroVM control plane (not a public client API) |
| `everflow-mcp/` | In-sandbox MCP tools |
| `everflow-edge/` | Edge / multi-node sketches |
| `toolkits/` | Cloneable project starters |
| `deploy/` | Dockerfiles, guest image, registry helpers |
| `scripts/` | **Install TUI** and lifecycle control |

More: [everflow-platform-api/README.md](everflow-platform-api/README.md) · [everflow-sandbox-agent/README.md](everflow-sandbox-agent/README.md) · [AGENTS.md](AGENTS.md) (AI coding agents).

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
