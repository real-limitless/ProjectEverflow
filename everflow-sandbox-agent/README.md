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
export SANDBOX_DEFAULT_IMAGE=registry:5000/everflow/everflow-sandbox-guest:latest
```

The guest image is **Fedora 44** with Node 22, `@anthropic-ai/claude-code`, OpenCode CLI, Playwright/Chromium, and `/etc/everflow/prebaked`. Bootstrap then only writes workspace markers.

### HTTP local registry (msb insecure)

The embedded Compose registry (`registry:5000`) is **plain HTTP**. microsandbox
defaults to **HTTPS** for OCI pulls, which fails with:

```text
registry error: error sending request for url
(https://registry:5000/v2/everflow/everflow-sandbox-guest/manifests/latest)
```

On startup the agent:

1. Merges `registries.hosts["registry:5000"].insecure = true` into `$MSB_HOME/config.json`
2. Passes `insecure=True` to `Sandbox.create` for local registry image refs
3. Optionally pre-pulls `DEFAULT_IMAGE` (`MSB_PREPULL_DEFAULT_IMAGE=true`)

This is **separate** from host Podman/Docker `insecure-registries` (those only
affect host push/pull of compose images as `localhost:5000/...`).

Manual recovery if the guest was never seeded:

```bash
ONLY=guest ./deploy/local-registry.sh build-push
# or inside a running agent container:
msb pull --insecure registry:5000/everflow/everflow-sandbox-guest:latest
```

Stock images (`python`, `ubuntu:24.04`) still work; bootstrap will install tools on first use (slower, needs network).

## Run with the product stack (supported)

The sandbox-agent is a **Compose service** (privileged, KVM passthrough). **Docker Compose or Podman Compose is the only supported product runtime** for Everflow — the agent, API, UI, registry, and searxng must run together.

```bash
# from repository root
./scripts/everflow install
# or full stack:
docker compose up --build
# hot reload agent (still Compose):
docker compose -f docker-compose.dev.yml up --build sandbox-agent
```

**Do not use a plain `python:slim` image for product.** Real sandboxes need the official
microsandbox runtime (`libkrunfw` + `msb`). Our Compose image is based on:

`ghcr.io/superradcompany/microsandbox:latest`

Requirements (product Compose):

- Linux host with `/dev/kvm` (read/write)
- `privileged: true` and device `/dev/kvm` (already in compose)
- Persistent volume on `/root/.microsandbox` for guest images
- `SANDBOX_MOCK=false` for real microVMs (default in product compose)

## Unit tests (mock mode — not a supported stack)

Without KVM / microsandbox, mock mode stores sandboxes in memory for **package unit tests** only. Host `uvicorn` is not a supported way to run the product agent.

```bash
cd everflow-sandbox-agent
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
export SANDBOX_AGENT_TOKEN=dev-token
export SANDBOX_MOCK=true
pytest
# optional isolated agent only (incomplete product stack):
# uvicorn app.main:app --reload --port 8090
```

Mock mode (`SANDBOX_MOCK=true`) exists only for CI without KVM — not for product use.
