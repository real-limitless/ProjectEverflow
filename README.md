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
| **Contributing** | [CONTRIBUTING.md](CONTRIBUTING.md) (DCO required; **no CLA**) |
| **Open source practices** | [OPEN_SOURCE.md](OPEN_SOURCE.md) · [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |

---

## Screenshots

Captured from a **live full stack** (Compose UI on `:3000` — not Vite demo / `npm run dev`). Real org, projects, and sandboxes.

```bash
./scripts/everflow start
cd scripts/screenshots && npm install
export EVERFLOW_EMAIL='you@example.com' EVERFLOW_PASSWORD='…'
# App surfaces:
node ../capture-screenshots.mjs --app-only
# Playground guided shots (headed — you open Desktop/Chat, then snap):
node ../capture-screenshots.mjs --interactive
```

Details: [`scripts/screenshots/README.md`](scripts/screenshots/README.md) · captions: [`docs/screenshots/CAPTIONS.md`](docs/screenshots/CAPTIONS.md)

### App surfaces

| Playground home | Marketplace |
|-----------------|-------------|
| ![Playground home](docs/screenshots/01-playground-home.png) | ![Marketplace](docs/screenshots/02-marketplace.png) |
| *Workbench entry — open or create a project bound to an isolated microVM* | *Skills, tools, and MCP servers installable into project harnesses* |

| Usage | Overview |
|-------|----------|
| ![Usage](docs/screenshots/03-usage.png) | ![Overview](docs/screenshots/04-overview.png) |
| *Org AI token / activity metrics from real sessions* | *Org dashboard surface* |

### Playground (Studio) — live components

Shot against the live stack (real org/projects/sandboxes). More panels (Desktop, Chat, Code, …) added as we capture them.

| Create Project | Connect repositories |
|----------------|----------------------|
| ![Create Project](docs/screenshots/playground/01-create-project.png) | ![Connect repos](docs/screenshots/playground/02-connect-repos.png) |
| **Create Project** — name, description, and URL **slug**. Each project gets an isolated microVM sandbox. | **Connect repos** — attach Git remotes so the sandbox and agents work on your real codebases. |

| Web search → Knowledge | Reader mode |
|------------------------|-------------|
| ![Web search and Knowledge](docs/screenshots/playground/03-web-search-knowledge.png) | ![Reader mode](docs/screenshots/playground/04-reader-mode.png) |
| **Web search & Knowledge** — search the internet, review results, and promote pages into **Knowledge** for model grounding. | **Reader mode** — pull clean page text from a site (no chrome/clutter) for review and LLM grounding. |

| Full website in Web search | Mind maps |
|----------------------------|-----------|
| ![Website view](docs/screenshots/playground/05-website-view.png) | ![Mind maps](docs/screenshots/playground/06-mind-maps.png) |
| **Website view** — open the **full live page** inside Web search (**Website** vs **Reader**), not only extracted text. | **Mind maps** — AI-built or user-defined maps of project knowledge the models can use for grounding. |

| Code editor | Git history & graph |
|-------------|--------------------|
| ![Code editor](docs/screenshots/playground/07-code-editor.png) | ![Git history and graph](docs/screenshots/playground/08-git-history-graph.png) |
| **Code editor** — browse the project tree, open files, and edit the codebase in the workbench. | **Git** — view commit history, commit yourself or via AI, and inspect the **repo graph**. |

| Live Preview (app in sandbox) | Full desktop environment |
|-------------------------------|---------------------------|
| ![Live Preview](docs/screenshots/playground/09-live-preview.png) | ![Desktop environment](docs/screenshots/playground/10-desktop-environment.png) |
| **Live Preview** — the chatbot starts websites/apps **inside the project sandbox**; **Preview** streams them live with no extra host setup. | **Desktop** — a real GUI desktop in the sandbox so agents can build GUI apps or drive **interactive browsers** in a safe, isolated environment. |

| Agents, skills, tools & MCP | SQL database |
|-----------------------------|--------------|
| ![Agents skills tools MCP](docs/screenshots/playground/11-agents-skills-tools.png) | ![SQL database](docs/screenshots/playground/12-sql-database.png) |
| **One control plane** — create **agents**, attach **skills**, **web/HTTP tools**, **MCP servers**, and **OpenCode plugins** in one place. | **SQL** — run your own queries or use **AI** to explore project databases from the workbench. |

| Workflows & CI/CD-style automation | Shared org skills |
|------------------------------------|-------------------|
| ![Workflows](docs/screenshots/playground/13-workflows.png) | ![Org shared skills](docs/screenshots/playground/14-org-shared-skills.png) |
| **Workflows** — design automated pipelines and CI/CD-style profiles so agents and triggers run project tasks without manual glue. | **Shared skills** — people in the organization create **skills** that can be reused across projects. |

More shots: [`docs/screenshots/playground/`](docs/screenshots/playground/) · captions: [`CAPTIONS.md`](docs/screenshots/CAPTIONS.md).

```bash
# while interactive capture is running:
echo 'snap playground/desktop-chat.png Agent chat driving a full Linux desktop in the project microVM' \
  > docs/screenshots/.capture-cmd
```

---

## Requirements

| Need | Notes |
|------|--------|
| **Linux** | Host with containers |
| **Docker** or **Podman** | Compose V2 (`docker compose` / `podman compose`) — **required** |
| **`/dev/kvm`** | Real microVMs (`ls -l /dev/kvm`) |
| Privileged containers + device passthrough | For `sandbox-agent` |

Without KVM (CI/dev only): set `SANDBOX_MOCK=true` in `.env` — not for product use.

No host Python or Node is required for the control plane.

### Supported runtime (only)

Everflow is a **multi-service** stack (frontend, backend, sandbox-agent, registry, searxng). Those services must run **together**.

| Supported | Not supported |
|-----------|----------------|
| `./scripts/everflow` (install / start / upgrade) | Host `npm run dev` + host `uvicorn` as a product stack |
| `docker compose` / `podman compose` with the repo Compose files | Starting only one package “to try Everflow” |
| `docker-compose.dev.yml` for contributor hot reload | Documented bare-metal multi-process installs |

Compose (Docker or Podman) is the **only** supported product runtime.

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

The wizard seeds an embedded local OCI registry, then starts the full **Compose** stack (frontend, backend, sandbox-agent, registry, searxng).

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

Full-stack development still uses **Compose** (bind-mounts for hot reload):

```bash
docker compose -f docker-compose.dev.yml up --build
# or: podman compose -f docker-compose.dev.yml up --build
```

- UI: http://localhost:5173  
- API: http://localhost:8000/docs  

Bind-mounts use the `:Z` SELinux label (Fedora/RHEL/Podman). Package READMEs document optional **unit tests** on the host; they are not a supported way to run the full platform. See [CONTRIBUTING.md](CONTRIBUTING.md).

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
