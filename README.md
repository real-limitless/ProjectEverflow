# Project Everflow

## Overview

Project Everflow is an enterprise-grade collaborative AI application development platform enabling teams to build, review, and deploy AI-powered applications with built-in safety, compliance, and approval workflows. It solves the problem of balancing rapid innovation with corporate governance by providing a "governance-first" environment where global compliance, regulatory, and data-handling rules are enforced at the platform level.

Inspired by creative platforms like HuggingFace Spaces, Everflow adds critical oversight to prevent unrestricted development.
Users can freely create applications within pre-approved boundaries, ensuring consistency and inherent compliance for all tools.

Every **project** is backed by an isolated [microsandbox](https://agentsandbox.dev/) microVM. Clients talk only to the Everflow API; an internal **sandbox-agent** owns KVM and the microsandbox SDK.

## Docker Compose (recommended)

Three services:

| Service | Role | Ports |
|---------|------|--------|
| `frontend` | UI (nginx) | `3000` |
| `backend` | **Sole public API** (`everflow-platform-api`) | `8000` |
| `sandbox-agent` | Privileged microsandbox control plane (internal) | not published |

### Host requirements

- Linux with **`/dev/kvm`** for real microVMs (`ls -l /dev/kvm`)
- Docker or Podman with privileged containers + device passthrough
- Without KVM, set `SANDBOX_MOCK=true` (default in compose) for in-memory mock sandboxes

```bash
cp .env.example .env
# edit SANDBOX_AGENT_TOKEN and SECRET_KEY

docker compose up --build
```

- UI: http://localhost:3000  
- API docs: http://localhost:8000/docs  
- Health: `GET /api/v1/health` · Ready (DB + agent): `GET /api/v1/ready`

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
npm run dev
```

See [everflow-platform-api/README.md](everflow-platform-api/README.md), [everflow-sandbox-agent/README.md](everflow-sandbox-agent/README.md), and [PLAN.md](PLAN.md).

## License

This project is licensed under the terms described in [LICENSE](LICENSE).


