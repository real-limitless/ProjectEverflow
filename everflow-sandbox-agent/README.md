# Everflow Sandbox Agent

Internal control plane for [microsandbox](https://agentsandbox.dev/) microVMs.

**Not a public API.** Only `everflow-platform-api` should call this service over the Docker network, authenticated with a shared bearer token.

## Responsibilities

- Create / start / stop / remove detached project sandboxes
- Exec + filesystem access inside microVMs
- Bootstrap agent harnesses (Claude Code, OpenCode)

## Fast create (ready ≠ harnesses installed)

`POST /v1/sandboxes` returns **as soon as the microVM is up** (`status=running`).  
Agent harness install runs **in the background** only when tools are missing from the guest image.

- Terminal / FS work immediately after create.
- Soft-fail bootstrap leaves the sandbox running.
- Mount strategy: set `VOLUME_STRATEGY=named-volume|bind|no-volumes|auto` (default `auto` caches the last successful strategy in-process).

## Guest image vs agent image

| Image | Dockerfile | Role |
|-------|------------|------|
| **Agent host** | `deploy/sandbox-agent.Dockerfile` | Runs `msb` + this FastAPI service |
| **Project guest** | `deploy/sandbox-guest.Dockerfile` | Root FS for each project microVM |

**Recommended:** prebake harnesses into the guest image:

```bash
./deploy/build-sandbox-guest.sh
export SANDBOX_DEFAULT_IMAGE=everflow-sandbox-guest:dev   # or a registry ref
```

The guest image includes Node 22, `@anthropic-ai/claude-code`, and OpenCode CLI, plus `/etc/everflow/prebaked`. Bootstrap then only writes workspace markers.

Stock images (`python`, `ubuntu:24.04`) still work; bootstrap will install tools on first use (slower, needs network).

## Local run (mock mode)

Without KVM / microsandbox, mock mode stores sandboxes in memory:

```bash
cd everflow-sandbox-agent
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
export SANDBOX_AGENT_TOKEN=dev-token
export SANDBOX_MOCK=true
uvicorn app.main:app --reload --port 8090
```

## Production (real microVMs)

**Do not use a plain `python:slim` image.** Real sandboxes need the official
microsandbox runtime (`libkrunfw` + `msb`). Our Compose image is based on:

`ghcr.io/superradcompany/microsandbox:latest`

```bash
# SANDBOX_MOCK must be false (default in compose)
docker compose up --build sandbox-agent
```

Requirements:

- Linux host with `/dev/kvm` (read/write)
- `privileged: true` and device `/dev/kvm` (already in compose)
- Persistent volume on `/root/.microsandbox` for guest images

Verified on this stack: `Sandbox.create` + `exec` print from a real microVM.

Mock mode (`SANDBOX_MOCK=true`) exists only for CI without KVM — not for product use.
