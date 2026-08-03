# Contributing to Project Everflow

Thanks for helping improve Everflow.

## Branches

| Branch | Purpose |
|--------|---------|
| **CORE** | Concept, methodology, and user-facing resources (GitHub default) |
| **Development-Everflow** | Runnable product — **use this for code contributions** |

Install scripts and the one-liner clone **`Development-Everflow`** by default.

## Prerequisites

- Linux with Docker or Podman + Compose V2
- `/dev/kvm` for real sandboxes (or `SANDBOX_MOCK=true` for API-only work)
- For host-side package work: Python 3.12+ / `uv`, and Node 20+ for the UI

## Product install (smoke test)

```bash
git clone -b Development-Everflow https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
./scripts/everflow install
./scripts/everflow setup-admin
# UI: http://localhost:3000
```

See [README.md](README.md) and [scripts/README.md](scripts/README.md).

## Development compose

Hot-reload stack:

```bash
cp .env.example .env   # if needed
docker compose -f docker-compose.dev.yml up --build
```

- UI: http://localhost:5173  
- API: http://localhost:8000/docs  

## Package-level development

| Package | Notes |
|---------|--------|
| `everflow-platform-api/` | FastAPI + Alembic; see package README |
| `everflow-platform-ui/` | React/Vite; `npm install && npm run dev` |
| `everflow-sandbox-agent/` | Privileged agent; mock mode for unit tests |
| `everflow-mcp/` | In-sandbox MCP server |

Run the package’s usual tests when you change behavior (`pytest`, `npm test`, etc.).

## Pull requests

1. Branch from `Development-Everflow`.
2. Keep diffs focused; match existing style in the package you edit.
3. Do not commit secrets (`.env`, keys, tokens). Follow `.env.example`.
4. Update docs when install or operator behavior changes.
5. Describe **what** changed and **why** in the PR body.

## AI coding agents

See [AGENTS.md](AGENTS.md) for repository layout and graphify-oriented navigation.

## Security

Report vulnerabilities privately — [SECURITY.md](SECURITY.md).

## License

Contributions are under the Apache License 2.0 — [LICENSE](LICENSE).
