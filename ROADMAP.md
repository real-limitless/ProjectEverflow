# Roadmap

Public roadmap for **Project Everflow**. Status is honest about what runs on the product branch (`Development-Everflow`) today versus what is planned.

The **CORE** branch holds concept and methodology. This file tracks the **software**.

---

## Now (usable)

- **Platform API** (`everflow-platform-api`) — auth, orgs, invites, projects, providers, knowledge, marketplace skills, sandbox proxy, git credentials, preview
- **Platform UI** (`everflow-platform-ui`) — PatternFly app shell for teams
- **Isolated project sandboxes** via [microsandbox](https://agentsandbox.dev/) microVMs (`everflow-sandbox-agent`)
- **Self-host install TUI** — `./scripts/everflow` (install, registry seed, status, setup-admin, logs, upgrade, uninstall)
- **One-liner bootstrap** — `scripts/get-everflow.sh` (clones product branch by default)
- **Embedded local OCI registry** — control-plane + guest images without mandatory public registry after seed
- **App toolkits** — web, PHP, Expo/React Native, desktop, Python, fullstack starters
- **In-sandbox MCP** (`everflow-mcp`) — project/agent tools for harnesses (e.g. OpenCode)
- **Workflow engine foundations** — n8n-inspired node catalog path (see `docs/workflows-n8n.md`); many integrations still maturing
- **Live preview** — Host-based preview proxy for project endpoints
- **Public beta tag** — `BETA-v0.0.1` (pin installs with `EVERFLOW_VERSION=BETA-v0.0.1`)

---

## Next

- **Stable public images** on `ghcr.io/real-limitless/*` so `INSTALL_MODE=ghcr` works without a full local compile
- **Operator docs** — production PostgreSQL, backups, TLS, reverse proxy, multi-host notes
- **Install polish** — clearer first-run errors, KVM detection, mock-vs-real sandbox guidance
- **Workflow coverage** — deepen high-value nodes (HTTP, Git, cloud storage, AI providers) with real I/O and tests
- **Hardening** — security reviews of sandbox proxy boundaries, credential storage, SSRF defaults
- **Release cadence** — further beta/rc tags toward a stable `v1.x`

---

## Later

- **Edge / multi-node** — mature `everflow-edge` for attachable hosts and distributed previews
- **Broader PaaS surface** — richer deploy targets and environment promotion (beyond project sandboxes)
- **Marketplace depth** — share/fork apps and workflows across orgs with stronger guardrails
- **Observability** — first-class metrics, tracing, and audit exports for operators

---

## Exploring (not committed)

Ideas that appear in early product thinking but are **not** delivery promises:

- Full multi-orchestrator parity (OpenShift operator, vSphere, etc.)
- Selkies-style full desktop agent productization beyond current sandbox desktop paths
- Commercial hosting or hosted control plane

---

## Non-goals (for now)

- Replacing general-purpose cloud IDEs or CI systems end-to-end
- Shipping unvetted third-party marketplace code without org-level controls
- Requiring host-installed Python/Node for the supported product install path
- Supporting a host multi-process product runtime — **Compose only** (Docker or Podman); UI / API / sandbox-agent as separate host services is not a supported install

---

## How to influence the roadmap

- Open a GitHub Discussion or Issue describing the use case
- See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup
- Security-sensitive reports: [SECURITY.md](SECURITY.md)

Last updated: 2026-08
