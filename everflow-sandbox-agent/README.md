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

## Production (KVM)

Requires Linux + `/dev/kvm`. Prefer Compose:

```bash
docker compose up sandbox-agent
```

The container runs privileged with `/dev/kvm` forwarded.
