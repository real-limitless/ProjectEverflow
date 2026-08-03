# Contributing to Project Everflow

Thanks for helping improve Everflow.

Community participation here follows practices aligned with
[Red Hat’s Open Source Participation Guidelines](https://www.redhat.com/en/resources/open-source-participation-guidelines-overview)
— especially **DCO (not CLA)**, an open source license, and clear conduct norms.
See [OPEN_SOURCE.md](OPEN_SOURCE.md) for the full mapping.

## Branches

| Branch | Purpose |
|--------|---------|
| **CORE** | Concept, methodology, and user-facing resources (GitHub default) |
| **Development-Everflow** | Runnable product — **use this for code contributions** |

Install scripts and the one-liner clone **`Development-Everflow`** by default.

## Developer Certificate of Origin (required)

We do **not** use a Contributor License Agreement (CLA) or copyright assignment.

Instead, every commit must include a **Signed-off-by** line certifying the
[Developer Certificate of Origin 1.1](DCO) (same mechanism the Linux kernel uses).

```bash
# Prefer configuring git once, then always use -s:
git config user.name "Your Name"
git config user.email "you@example.com"

git commit -s -m "feat: short description"
```

That appends:

```text
Signed-off-by: Your Name <you@example.com>
```

- Use your **real name** and an email you control.
- Sign **every** commit in the PR (not only the tip).
- Fix missing sign-off: `git commit --amend -s` or rebase with `git rebase -i` and re-commit with `-s`.

CI enforces this via the **DCO** workflow (`.github/workflows/dco.yml`). PRs without valid sign-off will fail.

Full text: [DCO](DCO) · [developercertificate.org](https://developercertificate.org/)

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Prerequisites

- **Linux** with **Docker or Podman + Compose V2** (required for any full-stack work)
- `/dev/kvm` for real sandboxes (or `SANDBOX_MOCK=true` for API-only / CI)
- Optional host Python 3.12+ / `uv` or Node 20+ **only** for package unit tests — not for running the product stack

## Supported runtime

Everflow is a multi-service stack. The **only** supported way to run it is **Docker Compose or Podman Compose** (via `./scripts/everflow` or the Compose files in the repo root).

Running the UI, API, and sandbox-agent as separate host processes is **not** a supported product or contributor full-stack path.

## Product install (smoke test)

```bash
git clone -b Development-Everflow https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
./scripts/everflow install
./scripts/everflow setup-admin
# UI: http://localhost:3000
```

See [README.md](README.md) and [scripts/README.md](scripts/README.md).

## Full-stack development (Compose)

Hot-reload stack — still Compose:

```bash
cp .env.example .env   # if needed
docker compose -f docker-compose.dev.yml up --build
# or: podman compose -f docker-compose.dev.yml up --build
```

- UI: http://localhost:5173  
- API: http://localhost:8000/docs  

Edit sources under each package; bind-mounts reload inside the containers.

## Package-level work

| Package | Notes |
|---------|--------|
| `everflow-platform-api/` | FastAPI + Alembic; prefer Compose for the API; host `pytest` for unit tests |
| `everflow-platform-ui/` | React/Vite; prefer Compose for the UI; host `npm test` / typecheck optional |
| `everflow-sandbox-agent/` | Privileged agent in Compose; mock mode for unit tests |
| `everflow-mcp/` | Runs **inside** project sandboxes (guest), not as a host product service |

Run the package’s usual tests when you change behavior (`pytest`, `npm test`, etc.). Host `uvicorn` / `npm run dev` snippets in package READMEs are for **isolated unit work only**, not a supported full-stack Everflow runtime.

## Pull requests

1. Branch from `Development-Everflow`.
2. **Sign off every commit** (`git commit -s`) — DCO required.
3. Keep diffs focused; match existing style in the package you edit.
4. Do not commit secrets (`.env`, keys, tokens). Follow `.env.example`.
5. Update docs when install or operator behavior changes.
6. Describe **what** changed and **why** in the PR body (use the PR template checklist).
7. Prefer validating full-stack changes under Compose.

## AI coding agents

See [AGENTS.md](AGENTS.md) for repository layout and graphify-oriented navigation. Document Compose as the supported run path for agents and users. Agent-generated commits still need a valid human or bot identity with DCO sign-off per project policy.

## Security

Report vulnerabilities privately — [SECURITY.md](SECURITY.md).

## License

Contributions are under the Apache License 2.0 — [LICENSE](LICENSE).
By contributing (with DCO sign-off), you agree your contribution is provided under that license.
