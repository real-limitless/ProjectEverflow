# AGENTS.md — Project Everflow

Instructions for AI coding agents working in this repository.

## What this project is

**Project Everflow** is a governance-first collaborative AI app platform. Teams build, review, and deploy AI-powered applications inside pre-approved boundaries. Every **project** runs in an isolated [microsandbox](https://agentsandbox.dev/) microVM.

Clients talk only to the Everflow API. An internal **sandbox-agent** owns KVM and the microsandbox SDK. See `README.md` for install and Compose details.

**Supported runtime:** Docker Compose or Podman Compose only (`./scripts/everflow`, `docker-compose.yml`, `docker-compose.dev.yml`). Do not document bare-metal multi-service runs (host `npm` + host `uvicorn` + host agent) as a product path.

**Open source norms:** No CLA — contributions use DCO (`Signed-off-by`). See `OPEN_SOURCE.md`, `DCO`, and `CONTRIBUTING.md`. Do not introduce CLA bots or copyright-assignment requirements.

**Releases:** When cutting a public beta/rc/stable tag, follow project skill `.grok/skills/release/SKILL.md` (slash `/release`). Same process as `BETA-v0.0.1`: `VERSION` + `CHANGELOG.md` + `docs/releases/<TAG>.md` + README/ROADMAP/SECURITY pins + CORE pointer + DCO commit + annotated tag; do not push until asked.

## Repository layout

| Path | Role |
|------|------|
| `everflow-platform-ui/` | React/Vite UI (PatternFly). Talks only to the platform API. |
| `everflow-platform-api/` | Sole public API (FastAPI). Auth, orgs, projects, knowledge, marketplace, sandbox proxy, git, harness. |
| `everflow-sandbox-agent/` | Privileged control plane for microVMs (not a public client API). |
| `everflow-mcp/` | MCP server exposing Everflow project/agent tools. |
| `everflow-edge/` | Edge/preview-related services. |
| `toolkits/` | Cloneable project starters (web, PHP, Expo, desktop, Python, fullstack). |
| `deploy/` | Dockerfiles, guest image build, sandbox guest scripts. |
| `scripts/` | Install and catalog sync helpers. |
| `graphify-out/` | Persistent codebase knowledge graph (query before browsing). |

Compose (only supported full stack): `frontend` + `backend` + `sandbox-agent` + `registry` + `searxng` (`docker-compose.yml` / `docker-compose.dev.yml` via Docker or Podman Compose).

---

## MANDATORY: use graphify for codebase connections

This repo has a knowledge graph at `graphify-out/` (`graph.json`, `GRAPH_REPORT.md`). **Do not explore architecture or file relationships with raw grep/find/read-first browsing.** Orient with graphify first.

### When you MUST use graphify

Use graphify before answering or changing code whenever the task involves:

- How does X work? What calls Y? Where is Z defined or used?
- Cross-package or cross-file relationships (UI ↔ API ↔ sandbox-agent ↔ MCP)
- Architecture, data flow, dependency paths, “who imports / who depends on”
- Finding the right place to implement a feature
- Subagents that explore the codebase (include these rules in every such subagent prompt)

### Required commands (prefer this order)

```bash
# Broad / natural-language question → scoped subgraph
graphify query "<question>"

# Relationship between two symbols, modules, or concepts
graphify path "<A>" "<B>"

# Focused explanation of one concept or node
graphify explain "<concept>"
```

Optional navigation:

- If `graphify-out/wiki/index.md` exists, use it for broad nav instead of walking the tree.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review, or when query/path/explain did not give enough context.

### After you change code

```bash
graphify update .
```

AST-only incremental update — keeps the graph current (no API cost).

### Hard rules

1. If `graphify-out/graph.json` exists, **run graphify before reading source files** for orientation.
2. Only open raw files after graphify has pointed you at the right symbols/paths, or when you already know the exact file/lines to edit or debug.
3. Prefer `graphify query` / `path` / `explain` over dumping large greps or reading `GRAPH_REPORT.md` end-to-end.
4. Do not skip graphify because grep “feels faster.” Graphify returns a scoped subgraph; that is the intended workflow.
5. Pass the same graphify-first rule into any subagent that explores code.

### Skill

Project skill: `.claude/skills/graphify/SKILL.md` (also mirrored under Cursor skills). Invoke `/graphify` or follow that skill when rebuilding or querying the graph.

---

## Architecture cheat sheet (for orientation only)

```
Browser / UI  →  everflow-platform-api (public)  →  everflow-sandbox-agent  →  microVM guest
                      ↑
                 everflow-mcp (tools over API)
```

- **UI** (`everflow-platform-ui/src/lib/api.ts`): HTTP client to the platform API only.
- **API** (`SandboxAgentClient`, `app/services/sandbox.py`): provisions and proxies sandbox operations; clients never call the agent directly in production.
- **Sandbox agent**: KVM/microsandbox, guest desktop, OpenCode harness, workspace ops.
- **Projects**: org-scoped; templates seed from `toolkits/`; preview/harness/git/knowledge hang off project + sandbox lifecycle.

For anything beyond this sketch, **query the graph** — do not invent connection maps from memory.

---

## Working conventions

- Match existing style in the package you edit; prefer minimal, focused diffs.
- Platform API: FastAPI + Alembic migrations under `everflow-platform-api/alembic/versions/`.
- UI: React + TypeScript; panel/shell structure under `everflow-platform-ui/src/components/`.
- UI visual work: read `.cursor/skills/frontend-design/SKILL.md` first (same text in `.claude/skills/frontend-design/`). Keep Everflow / PatternFly chrome; do not invent a second brand.
- Tests live next to each package (`tests/`). Run the package’s usual test command when you change behavior.
- Do not commit secrets (`.env`, tokens, keys). Follow `.env.example` for required vars.
- Do not create commits or PRs unless the user asks.
- After substantive code edits, run `graphify update .`.

## Cloud Agent / nested Compose

Product path is still **Compose only**. On a Cloud Agent VM, Docker is nested:

- Storage driver: `fuse-overlayfs`. Start `dockerd` if the socket is down.
- Use `docker-compose.dev.yml` so this checkout’s API/UI/agent source is bind-mounted.
- Keep `SANDBOX_MOCK=false` and seed the guest image (`./deploy/local-registry.sh seed` or `ONLY=guest ./deploy/local-registry.sh build-push`) so harnesses are real microVMs. `/dev/kvm` is required.
- Helpers: `scripts/cloud-agent/install.sh` (idempotent `.env`, no servers) and `scripts/cloud-agent/start.sh` (dockerd + compose up, then exit).
- First admin: `./scripts/everflow setup-admin` or `POST /api/v1/setup/bootstrap`. Do not commit passwords.

## Where to read more

| Doc | Use |
|-----|-----|
| `README.md` | Install, Compose, host requirements |
| `ROADMAP.md` | Public shipped / next / later |
| `CONTRIBUTING.md` | How to develop and open PRs |
| `SECURITY.md` | Vulnerability reporting |
| `everflow-platform-api/README.md` | API details |
| `everflow-sandbox-agent/README.md` | Agent / guest image |
| `toolkits/README.md` | Starter templates |
| `CLAUDE.md` | Short graphify reminder (Claude) |
| `graphify-out/GRAPH_REPORT.md` | Community hubs / broad architecture (local; gitignored) |
