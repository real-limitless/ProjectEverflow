# Everflow Sandbox Agent

Internal control plane for [microsandbox](https://agentsandbox.dev/) microVMs.

**Not a public API.** Only `everflow-platform-api` should call this service over the Docker network, authenticated with a shared bearer token.

## Responsibilities

- Create / start / stop / remove detached project sandboxes
- Exec + filesystem access inside microVMs
- Bootstrap agent harnesses (Claude Code, OpenCode)

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
