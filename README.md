# Project Everflow

**Governance-first collaborative AI applications — on your infrastructure, with your rules.**

This is the **CORE** branch: concept, methodology, and orientation for users and operators.  
The **runnable software** lives on the product branch:

→ **[`Development-Everflow`](https://github.com/real-limitless/ProjectEverflow/tree/Development-Everflow)**

| | |
|---|---|
| **License** | [Apache-2.0](LICENSE) |
| **Install / code** | Product branch (link above) |
| **Roadmap** | [ROADMAP.md on Development-Everflow](https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/ROADMAP.md) |

---

## What Everflow is

Everflow is a **self-hosted platform** where teams build, review, and deploy AI-powered applications inside **pre-approved boundaries**. It is inspired by creative AI app spaces (e.g. HuggingFace Spaces) but adds **organizational governance** so innovation does not outrun compliance, data handling, and security policy.

### Core ideas

1. **Governance first** — Global rules for compliance, data access, and agent behavior sit at the platform layer, not as optional add-ons.
2. **Isolated projects** — Every project runs in its own [microsandbox](https://agentsandbox.dev/) microVM. Work is contained; tenants and projects stay separated by design.
3. **One public API** — Browsers and tools talk only to the Everflow platform API. A privileged **sandbox-agent** owns KVM and the microVM SDK; it is not a public client endpoint.
4. **Your infrastructure** — Docker/Podman compose install; images can stay in an embedded local registry. Data sovereignty is a product goal, not an afterthought.
5. **Agents with guardrails** — Coding and automation agents (harnesses, MCP tools, workflows) operate inside org policy and project scope.

### Typical flow

```text
Team member → Platform UI / API
                 → Project + policies
                 → Sandbox agent provisions microVM
                 → Agent harnesses + toolkits build the app
                 → Preview / review / deploy within org rules
```

---

## Methodology (how to think about Everflow)

| Layer | Responsibility |
|-------|----------------|
| **Organization** | Membership, invites, shared credentials, org-level policy |
| **Project** | One app/workspace; owns a sandbox lifecycle |
| **Sandbox** | Isolated microVM: filesystem, desktop/tools, harnesses |
| **Knowledge & marketplace** | Org-approved skills, docs, and tools agents may use |
| **Workflows** | Automation nodes (integrations, AI steps) under the same control plane |

**Design principles we optimize for:**

- **Least privilege by default** — sandboxes and tokens are scoped; mock mode is for CI/dev only.
- **Approve the boundary, free the builder** — once policies and tools are approved, individuals move fast inside that box.
- **Operator honesty** — production refuses default secrets; install is container-native, not a fragile host toolchain.
- **Open methodology, open code** — concept lives here on CORE; implementation is open on the product branch under Apache-2.0.

---

## Get the software

### Quick install (product branch)

```bash
git clone -b Development-Everflow https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
./scripts/everflow          # interactive TUI
./scripts/everflow setup-admin
# UI → http://localhost:3000
```

### One-liner

```bash
curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/Development-Everflow/scripts/get-everflow.sh | bash
```

**Host needs:** Linux, Docker or Podman + Compose, and `/dev/kvm` for real microVMs (or mock mode for limited dev).

Full install, production checklist, and architecture:  
[README on Development-Everflow](https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/README.md)

---

## Branch map

| Branch | Audience | Contents |
|--------|----------|----------|
| **CORE** (this branch) | Everyone | Concept, methodology, install pointers |
| **Development-Everflow** | Operators & developers | Runnable monorepo, scripts, compose, packages |
| Release tags (when published) | Operators | Pinned install via `EVERFLOW_VERSION=vX.Y.Z` |

### Private work

GitHub **cannot** hide individual branches on a public repository. For personal experiments, Red Hat pitch materials, or private notes, use a **private fork** or **private sibling repository** — never push secrets or internal-only docs to this public remote.

---

## Resources

- [Product README](https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/README.md) — install TUI, stack, production checklist  
- [ROADMAP](https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/ROADMAP.md) — shipped / next / later  
- [CONTRIBUTING](https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/CONTRIBUTING.md)  
- [SECURITY](https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/SECURITY.md)  
- [AGENTS.md](https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/AGENTS.md) — for AI coding agents working in the monorepo  

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
