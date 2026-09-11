# Competitive feature gap: Everflow vs similar platforms

**Status:** living analysis for GitHub tracking  
**Product ref:** `Development-Everflow` (public beta `BETA-v0.0.1` plus later hardening)  
**Compared as of:** 2026-09-11  
**Related:** GitHub [#20](https://github.com/real-limitless/ProjectEverflow/issues/20) (this analysis), [ROADMAP.md](../ROADMAP.md), [#4 OpenFlow](https://github.com/real-limitless/ProjectEverflow/issues/4), [#5 mcp-flow + ansible-flow](https://github.com/real-limitless/ProjectEverflow/issues/5)

This document is the canonical copy of the competitive gap issue. Competitor claims are from public product docs and repos as of the date above. They will drift. Re-check a vendor before treating a cell as a purchase decision.

---

## Summary

Everflow’s CORE pitch is **governance-first collaborative AI apps on your infrastructure**: teams build, review, and deploy inside pre-approved boundaries; every project is an isolated [microsandbox](https://agentsandbox.dev/) microVM; browsers talk only to the platform API.

No single competitor occupies that whole shape. The market is a pile of adjacent products:

| Adjacent job | Typical products |
| --- | --- |
| Self-hosted coding-agent control plane | OpenHands Agent Canvas, Goose, Coder Agents |
| AI sandbox / microVM infrastructure | E2B, Daytona, Modal, microsandbox itself |
| Self-hosted LLM app / workflow builder | Dify, Langflow, Flowise, n8n, Windmill |
| Self-hosted chat / RAG workspace | Open WebUI, LibreChat, AnythingLLM |
| Hosted coding agents and AI IDEs | Cursor Cloud Agents, Devin, GitHub Copilot coding agent, Replit Agent, Claude Code, Codex |
| Creative AI app hosting | Hugging Face Spaces (the CORE inspiration) |
| Enterprise company knowledge agents | Dust.tt |
| Multi-agent “crew / org” frameworks | CrewAI, Microsoft Agent Framework, LangGraph |
| Hyperscaler agent platforms | Bedrock Agents, Vertex Agent Builder, Azure AI Foundry |

**The honest gap:** Everflow already has a distinctive *control-plane story* (org chart of human and bot seats, constitution, Room, microVM + desktop, Apache-2.0 Compose install). It does **not** yet have the *enterprise governance table-stakes* that Dust, Open WebUI, Coder, Hugging Face Enterprise, and Devin sell: SSO/SCIM, SIEM-grade audit, model/tool policy, connectors, operator HA, and ticket-to-PR automations.

That mismatch is the risk. CORE says “governance first.” Buyers will compare Everflow to products that already ship SSO, audit logs, and RBAC even if those products have weaker isolation.

---

## What Everflow is (and is not)

### Is

- A **self-hosted platform** (Compose / Podman Compose only) for teams.
- A **project = microVM** isolation model via privileged `everflow-sandbox-agent`.
- A **workbench** (PatternFly): chat, code, git, terminal, preview, knowledge, workflows, desktop (noVNC), agents, tools/MCP, jobs, tests, deploy.
- An **org-chart control plane** (seats, teams, hire/pause/fire, constitution.md, Room channels, bot bus / run compiler).
- A **marketplace** for skills, commands, plugins, HTTP tools, and MCP (ECC-vendored catalog plus Everflow-native items).
- **Harness-aware**: OpenCode and Claude Code inside the guest; in-sandbox `everflow-mcp`.
- **Apache-2.0, DCO, no CLA.**

### Is not (today)

- A hosted SaaS coding agent (Cursor / Devin / Copilot).
- A general cloud IDE or CI replacement (explicit non-goal in ROADMAP).
- A Kubernetes operator or multi-orchestrator (OpenShift / vSphere are “exploring”).
- A 400-integration iPaaS (n8n). Native workflows exist; OpenFlow replacement is [#4](https://github.com/real-limitless/ProjectEverflow/issues/4).
- SOC 2 / HIPAA certified software. Operators inherit their own compliance.

---

## Everflow today (honest inventory)

Shipped on `Development-Everflow` unless marked otherwise. Screenshots in the README are from a live stack; some surfaces are thinner than the caption implies.

### Strong (real product paths)

| Area | What actually runs |
| --- | --- |
| Install | `./scripts/everflow` TUI, one-liner bootstrap, local OCI registry, airgap export/import helpers |
| Isolation | Per-project microsandbox microVM (KVM). Mock mode is CI/dev only; production refuses it |
| API / auth | FastAPI, JWT, GitHub/Google OAuth, org invites, roles `owner` / `admin` / `member` |
| Workbench | Docked studio: Chat, Preview, Knowledge, Code, Git, Terminal, Workflows, Database, Jobs, Agents, Tools/MCP, Env, Tests, Deploy, Desktop, Room, Chart |
| Knowledge | Canvases, collections + agent grants, SearxNG web search, reader mode, mind maps / graph, retrieval, golden-set eval |
| Harnesses | Claude Code + OpenCode in the guest image; harness pack (agents, skills, MCP, plugins) |
| Marketplace | Catalog kinds `skill` / `command` / `plugin` / `tool` / `mcp`; install into sandbox |
| Usage | Token usage ingest + org/project/model charts (7/30/90d) |
| Org chart | Teams, seats (human/bot), reporting lines, constitution, hire/pause/fire/attach, Room, bus events, run compile |
| Preview / desktop | Host-based preview proxy; guest noVNC desktop on 6080 |
| Git | Org git credentials, pull/push/fetch inside the sandbox |
| Providers | Encrypted vault: OpenRouter, OpenAI, Anthropic, xAI (user and project scope) |
| Security posture | Fail-closed default secrets, `CREDENTIALS_ENCRYPTION_KEY`, SSRF guards, sandbox-agent not published |

### Thin, stubbed, or screenshot-only

| Area | Gap |
| --- | --- |
| Plans & billing | README screenshot exists; no Plans route in the UI. Usage charts are not billing |
| Harness catalog cards | GitHub Actions, GitLab CI, Kubernetes deploy, ephemeral preview, Postgres are catalog entries. Claude Code / OpenCode are the ones wired into the guest |
| Workflows | Native n8n-compatible engine + canvas. ROADMAP: many integrations still maturing. Replacement planned in #4 |
| Deploy / edge | Deploy keys/nodes/routes exist; remote compose + Traefik is MVP; UI still partly simulated |
| Multi-node | `everflow-edge` is sketches + heartbeat stubs |
| GHCR | Publish workflow exists; `INSTALL_MODE=ghcr` fails closed if packages are unpublished |
| Operator docs | Postgres, backups, TLS, reverse proxy, multi-host: ROADMAP “Next”, not a runbook yet |
| Marketplace policy | Browse/install is not allowlisted. That is the point of #5 |
| Observability | Token usage only. No metrics, traces, or audit export |
| Provider catalog | No Ollama, Azure OpenAI, Bedrock, Gemini, Mistral, or OpenAI-compatible generic endpoint in the vault catalog |

---

## Competitor landscape

### 1. Self-hosted coding-agent control planes (closest overall)

#### OpenHands (Agent Canvas)

Open-source developer control center for coding agents. Browser UI over backends (local, Docker, VM, Modal, OpenHands Cloud). ACP agents (Claude Code, Codex, Gemini). Automations (GitHub PR review, Slack monitors, schedules). Docker runtime is the usual sandbox.

| OpenHands has that Everflow lacks | Everflow has that OpenHands lacks |
| --- | --- |
| GitHub/Slack automations and issue-driven loops | Per-project **microVM** (own kernel) rather than Docker-by-default |
| ACP catalog (Codex, Gemini, …) as first-class backends | Org chart, constitution, Room, marketplace, knowledge canvases |
| Cloud / Modal backends without operating KVM | App toolkits, live preview proxy, noVNC desktop, n8n-shaped workflows |
| Larger community and docs | Org membership, invites, PatternFly team shell, local OCI registry |

**Gap implication:** OpenHands is the product a platform team will try first if they only want “self-hosted coding agents.” Everflow wins if the buyer wants **apps + governance + isolation**, not only an agent IDE.

#### Goose (Block / AAIF)

Apache-2.0, Linux Foundation AAIF. Desktop + CLI + API. MCP extensions. Local models via Ollama. Runs on the **user machine**, not a multi-tenant control plane.

Everflow should treat Goose as a **harness candidate** (like OpenCode), not a platform peer. Gap: Goose is not in the harness catalog.

#### Coder (Coder Agents + Agent Relay)

Self-hosted IDP. Terraform workspace templates, air-gap, SSO, audit, AI Bridge (prompts/tools/tokens logged in your SIEM). Coder Agents keep LLM keys out of the workspace. Agent Relay can run Cursor-class agents inside Coder workspaces.

| Coder has | Everflow has |
| --- | --- |
| Mature workspace platform, Kubernetes, air-gap, SSO, SIEM audit | MicroVM guests with desktop + marketplace + org-of-bots |
| Model governance and spend limits as platform features | Project constitution and seat-level tool allow/deny in OpenCode frontmatter |
| No “build an AI app inside a governed sandbox” product | Workbench + knowledge + workflows + preview |

**Gap implication:** For a CISO, Coder currently *looks* more “governance-first” than Everflow, even though Everflow’s isolation story (microVM + constitution + seat permissions) is more opinionated.

### 2. Sandbox infrastructure (building blocks, not products)

| Product | Isolation | Self-host | Notes vs Everflow |
| --- | --- | --- | --- |
| **microsandbox** | libkrun / KVM microVM | Yes (Apache-2.0) | Everflow’s guest runtime. Snapshot/fork exist upstream; Everflow does not expose pause/fork/snapshot as product APIs |
| **E2B** | Firecracker microVM | Infra is OSS but operations-heavy | Pause/resume, network allow/deny, desktop sandboxes, managed cloud. Not a team workbench |
| **Daytona** | Container default; VM class for pause/fork | Going closed-source (2026) | Persistent workspaces, GPU. License/community risk |
| **Modal / Vercel Sandbox** | gVisor or Firecracker | No (cloud) | Fast ephemeral exec, not an org platform |
| **DifySandbox / Judge0** | seccomp/chroot or namespaces | Yes | Code-exec only; far weaker isolation |

**Gap implication:** Buyers who care about untrusted agent code will ask for **pause, fork, network policy UI, and snapshot restore**. Everflow has the right runtime and does not yet productize those primitives.

### 3. Self-hosted LLM app platforms

#### Dify

Visual workflows, RAG, agents, APIs, observability, MCP. Docker Compose + optional K8s. Container sandbox for code nodes. License **restricts offering Dify as a multi-tenant SaaS**.

#### Langflow / Flowise

Visual LangChain/LangGraph builders. Langflow is MIT. Flowise core is Apache-2.0; **SSO/identity/workspace governance is separately licensed**.

| They have | Everflow has |
| --- | --- |
| Deep RAG pipelines, prompt versioning (Dify), huge node catalogs | Coding workbench, git, microVM, desktop, org chart |
| One-click expose flow as an API | Preview of the *app in the sandbox*, not “publish this flow as a product API” |
| Lighter host requirements (no KVM) | Stronger tenant isolation |

**Gap implication:** If the buyer is “chat with docs / ship a support bot,” Dify wins. Everflow should not try to out-Dify Dify. The workflow gap is already owned by [#4 OpenFlow](https://github.com/real-limitless/ProjectEverflow/issues/4).

### 4. Self-hosted chat / RAG

**Open WebUI, LibreChat, AnythingLLM**

Open WebUI in particular ships SSO/OIDC/LDAP, SCIM 2.0, RBAC, channels, MCP, tools, RAG across many vector DBs. LibreChat is the multi-provider ChatGPT workbench. AnythingLLM is document workspaces.

**Gap implication:** These are not coding platforms, but they set the **identity and knowledge bar**. A team that already runs Open WebUI will ask why Everflow cannot SSO the same IdP.

### 5. Hosted coding agents (what users compare in demos)

| Product | Execution | Governance they sell | vs Everflow |
| --- | --- | --- | --- |
| **Cursor Cloud Agents** | Isolated VMs on Cursor infra | Enterprise audit, SSO, Blame | Not self-hosted. Stronger IDE. No org-of-bots |
| **Devin (Cognition)** | Cloud / dedicated / customer VPC | RBAC, per-session audit, metering, ticket intake | Closest *delegation* model. Everflow’s seats/bus are the OSS analogue, less mature |
| **GitHub Copilot coding agent** | GitHub Actions | GitHub Enterprise SSO, policy, audit | Wins wherever GitHub is already the control plane |
| **Replit Agent** | Hosted repl + deploy | Collaboration, hosting | Fastest “idea to URL.” Weak on-prem story |
| **Claude Code / Codex** | Local CLI or vendor cloud | Enterprise seats, MCP | Everflow already embeds Claude Code; Codex is mentioned in README screenshots more than in the harness catalog |

**Gap implication:** Everflow will be demoed against Cursor/Devin. The demo must show **isolation + org chart + preview**, not a worse editor. Ticket-to-PR and always-on automations are the features those products use to close enterprise deals.

### 6. Hugging Face Spaces (CORE inspiration)

Spaces: Gradio/Docker apps, GPUs, duplicate/fork, public/protected/private, Team/Enterprise SSO/SCIM/audit, resource groups.

Everflow’s differentiator vs Spaces is **self-host + microVM + agent harnesses + org policy**. Gaps vs Spaces: GPU SKUs, one-click public sharing, community discoverability, custom domains as a polished product, hardware picker.

### 7. Enterprise knowledge agents

**Dust.tt:** 70+ connectors (Slack, Notion, Drive, GitHub, Salesforce, Zendesk), dual-layer permissions, SCIM, SSO, audit, US/EU residency, SOC 2. Hosted (single-tenant option). Not a code sandbox.

**Gap implication:** Dust is what GTM will name-drop for “governed company agents.” Everflow’s knowledge plane is project-local (canvases, SearxNG, eval sets). It does not ingest the company’s existing systems with permission sync.

### 8. Workflow automation

**n8n** (fair-code, 400+ integrations, AI Agent node), **Windmill** (code-first, AGPL), **Temporal** (durable), **Activepieces** (MIT).

Everflow’s native engine imports n8n JSON for a subset and runs in-process (no Redis/Celery; multi-replica is “pick a leader”). That is a **depth gap**, which [#4](https://github.com/real-limitless/ProjectEverflow/issues/4) already plans to close by embedding OpenFlow rather than forever cloning n8n.

### 9. Multi-agent frameworks (org-chart cousins)

**CrewAI:** role-based crews (closest *mental model* to Everflow seats). Framework + paid AMP studio. Not a sandbox platform.

**Microsoft Agent Framework** (AutoGen successor): sequential/concurrent/handoff/group-chat/Magentic-One, HITL pause/resume, OpenTelemetry.

**LangGraph + LangSmith:** stateful graphs, checkpointing, traces.

**Letta:** persistent agent memory.

Everflow’s unique bet is making the org chart a **product control plane** (UI + API + constitution + Room), not a Python object. The gap is **reliability, HITL enforcement, traces, and memory** relative to those frameworks.

### 10. Hyperscalers

Bedrock Agents / AgentCore, Vertex Agent Builder / Agentspace, Azure AI Foundry / Copilot Studio, Palantir AIP, Databricks Mosaic, Snowflake Cortex.

These win on IAM, VPC, compliance attestations, and data-plane gravity. Everflow should stay the **on-prem / air-gapped / Apache-2.0** alternative, not a cloud-console clone.

---

## Feature matrix

Legend: **Y** = product-grade, **P** = partial / beta / stub, **N** = no, **S** = SaaS-only or paid enterprise module, **n/a** = not that kind of product.

| Capability | Everflow | OpenHands | Coder | Dify | Open WebUI | Dust | Cursor/Devin | HF Spaces | n8n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Self-host, your VPC | Y | Y | Y | Y | Y | S | P (Devin VPC) | N | Y |
| Apache-2.0 / no CLA core | Y | Y (OSS) | Y (OSS core) | restricted SaaS clause | custom license | MIT repo / hosted | proprietary | mixed | fair-code |
| Per-project microVM (own kernel) | Y | P (Docker typical) | P (K8s/VM templates) | N (container sandbox) | N | N | Y (cloud VMs) | N (containers) | N |
| Full guest desktop / computer use | Y (noVNC) | P | N | N | N | N | Y (Devin/Cursor) | N | N |
| Team orgs, invites, roles | P (3 roles) | P | Y | Y | Y | Y | Y | Y | S |
| SSO / SAML / OIDC | P (GitHub/Google OAuth) | P | Y | S/P | Y | Y | Y | Y (Team+) | S |
| SCIM lifecycle | N | N | Y | N/S | Y | Y | Y | Y (Enterprise) | S |
| Audit log export / SIEM | N | P | Y | P | P | Y | Y | Y (Team+) | S |
| Model allowlist / spend caps | P (usage charts only) | P | Y | P | P | Y | Y | P | P |
| Marketplace allowlist | N (#5) | n/a | templates | N | N | Y (admin) | MCP admin | Y | n/a |
| Ticket / Slack / GitHub automations | N | Y | Y | P | P | Y | Y | N | Y |
| Visual workflows + 100s of connectors | P (#4) | N | N | Y | N | P | N | N | Y |
| RAG + company connectors | P (canvases) | N | N | Y | Y | Y | P | N | P |
| Coding workbench + git | Y | Y | Y | N | N | N | Y | P | N |
| Live app preview | Y | P | Y | embed chat | N | N | Y | Y | N |
| Org-chart multi-agent control plane | Y | N | N | N | N | P | N | N | N |
| GPU guests | N | P | P | P | N | N | P | Y | N |
| K8s operator / HA control plane | N | P | Y | Y | P | S | S | S | P |
| Air-gap install story | P (local registry) | P | Y | P | P | N | N | N | P |
| SOC 2 / compliance pack | N (self-host) | S | Y | S | N | Y | Y | Y | S |

---

## Feature gaps (prioritized)

Each gap is **Everflow vs the set of products a serious buyer will actually shortlist**, not vs every feature on earth.

### P0 — Table-stakes for the CORE claim (“governance first”)

These are the gaps that make the pitch feel unfinished next to Coder, Dust, Open WebUI, Hugging Face Enterprise, and Devin.

| ID | Gap | Who already has it | Why it matters | Notes |
| --- | --- | --- | --- | --- |
| **G0.1** | **SSO beyond GitHub/Google OAuth** (OIDC/SAML, Entra/Okta) | Open WebUI, Coder, Dust, HF Team, Copilot, Cursor Enterprise | Enterprises will not mint local passwords | Preview UI still shows an SSO mock. Real IdP is missing |
| **G0.2** | **SCIM 2.0** join/leave | Open WebUI, Dust, HF Enterprise, Coder | Joiners/leavers are a compliance control | Invites exist; no IdP lifecycle |
| **G0.3** | **Immutable audit trail + export** (auth, policy, install, exec, deploy, seat fire) | Coder AI Bridge, Dust, Devin per-session, HF audit logs | Room “is the audit log” is a product metaphor, not a SIEM feed | Bus events are a start. Need retention, hash chain or append-only store, webhook to Splunk/ELK |
| **G0.4** | **Org policy engine**: allowed models, MCP, skills, egress, data classes | Coder model governance, Dust dual-layer perms, HF resource groups | Marketplace install is currently “if you can see it, you can install it” | #5 is the MCP allowlist slice. Need the same for models, skills, and HTTP tools |
| **G0.5** | **RBAC finer than owner/admin/member** | Coder, Dust, Open WebUI, Dify workspaces | Cannot express “can chat, cannot deploy, cannot install MCP” | Seat `permission` JSON is for bots, not human org members |
| **G0.6** | **Operator production pack** | Coder, Dify Helm, n8n | ROADMAP already lists this | TLS, Postgres, backups, reverse proxy, multi-host, secret rotation runbooks |
| **G0.7** | **Fail-closed marketplace** | #5 design, Dust admin, HF | Unvetted third-party MCP is an explicit non-goal | Do not ship a public MCP gallery without G0.4 |

### P1 — Parity to be taken seriously as an agent platform

| ID | Gap | Who already has it | Why it matters | Notes |
| --- | --- | --- | --- | --- |
| **G1.1** | **Workflow engine that operators trust** | n8n, OpenFlow, Dify, Langflow | Native engine is a subset; in-process scheduler does not HA | Owned by #4 |
| **G1.2** | **External intake**: GitHub issues, Slack, webhooks, cron that survives API restart | OpenHands automations, Devin, Copilot, n8n | This is how Devin/Cursor close “delegation” deals | Bus `compile_sentence` is internal. No GitHub App |
| **G1.3** | **Human-in-the-loop that is enforced** | Microsoft Agent Framework, LangGraph, Devin review | Constitution says confirm on deploy/merge; needs a real approval object + block | `ask_human` / reports_to is specified; productize it |
| **G1.4** | **Provider coverage**: Ollama, OpenAI-compatible, Azure, Bedrock, Gemini | Goose, Open WebUI, LibreChat, Coder | Self-host buyers start with Ollama | Vault catalog is four SaaS keys |
| **G1.5** | **Hard budgets**: tokens / $ / seat / project, kill switch when exceeded | Coder, Dust, Devin metering | `budget_tokens` on Seat is a field; usage page is observational | Need enforce + notify |
| **G1.6** | **Sandbox lifecycle: pause / resume / snapshot / fork** | E2B, Daytona VM class, microsandbox upstream | Idle cost and branch-and-eval agents | Everflow start/stop/exec/fs only |
| **G1.7** | **Egress policy UI** (DNS allowlist, per-project) | E2B allow/deny, Modal, Daytona firewall, Coder firewall | SSRF deny-lists are host-global | Per-sandbox network policy is the isolation story’s missing half |
| **G1.8** | **mcp-flow gallery + allowlist** | #5, Claude/Cursor MCP admin | Catalog freshness and supply chain | Do not scrape the registry in Everflow |
| **G1.9** | **Ansible hub/spoke** | #5, ansible-flow-mcp | Fleet of spokes vs one microVM | Platform control plane, not a third runner in FastAPI |
| **G1.10** | **Air-gap completeness** | Coder | GHCR unpublished; docs thin | Local registry path works; first-run still painful |

### P2 — Workbench and PaaS gaps vs Cursor / Replit / Spaces / Dify

| ID | Gap | Who already has it | Why it matters |
| --- | --- | --- | --- |
| **G2.1** | Harness catalog: Codex, Gemini CLI, Goose, Aider (ACP) | OpenHands ACP, Goose | README implies “Claude Code, Codex CLI, and more”; catalog wires two CLIs |
| **G2.2** | Issue-to-PR coding agent loop with review UI | Copilot, Devin, OpenHands PR automation, Cursor Bugbot | |
| **G2.3** | Knowledge **connectors** with permission sync (Drive, Slack, Notion, Confluence, GitHub) | Dust, Dify, AnythingLLM | Canvases + SearxNG are not a company brain |
| **G2.4** | Agent **tracing** (tool calls, prompts, retries) | LangSmith, Coder AI Bridge, Dify | Usage events are tokens, not traces |
| **G2.5** | Persistent **scoped memory** productization | Letta, LangGraph checkpointers | `MemoryBlock` exists on the bus; not a memory product |
| **G2.6** | Environment promotion (dev/stage/prod) and richer deploy targets | Replit, HF Spaces, Dify, Coder | ROADMAP “Later” PaaS. Edge is MVP |
| **G2.7** | Share / fork apps and workflows across orgs | HF Spaces duplicate, Dify DSL | ROADMAP “Later” marketplace depth |
| **G2.8** | GPU guests / model-in-sandbox | HF Spaces, Modal, Daytona | Out of scope until CPU isolation is boring |
| **G2.9** | Kubernetes / HA control plane | Coder, Dify Helm | Compose-only is a locked product decision. Gap is “scale-out later,” not a silent rewrite |
| **G2.10** | Plans, seats-as-billing, invoices | Cursor, HF, Devin | Screenshot-only. Fine to stay “bring your own keys” if we say so |
| **G2.11** | IDE extensions (VS Code / JetBrains) | Continue, Copilot, Cursor | Possible explicit non-goal (ROADMAP: not a general cloud IDE) |
| **G2.12** | Host OS: Linux+KVM only | Goose (macOS/Win/Linux desktop) | Document clearly. Do not fake macOS KVM |
| **G2.13** | Eval beyond knowledge golden sets (agent eval, red-team) | Dify, promptfoo, HF Jobs | Knowledge Eval tab exists; no harness eval harness |
| **G2.14** | Public/embeddable app URL + custom domain as a polished product | HF Spaces, Replit | Preview proxy is internal-first |
| **G2.15** | Real-time human collab (presence, CRDT) | Replit, HF, Dust | Room is chat, not pair-programming |

### P3 — Differentiation to double down on (do not copy blindly)

Do **not** spend the next cycles becoming a worse Cursor or a worse n8n. Protect and deepen:

1. **Org chart as control plane** (hire/pause/fire, reporting lines = permission lines). CrewAI is code; Everflow is a company UI.
2. **constitution.md as project law** written into the sandbox.
3. **Room as the human-visible audit surface** (then back it with G0.3 so it is not theater).
4. **MicroVM + noVNC desktop** for GUI and headed browser agents.
5. **Approve the boundary, free the builder** (marketplace + harness pack inside policy).
6. **Apache-2.0 + DCO + no CLA** vs Dify’s SaaS clause and Flowise’s commercial identity module.
7. **Local OCI registry / air-gap path.**
8. **Compose-only honesty** (supported runtime is one thing, documented).

---

## Recommended sequencing

Aligned with what is already planned. This issue does not replace #4 or #5.

| Phase | Outcome | Gaps | Depends on |
| --- | --- | --- | --- |
| **Now** | Keep isolation and org-chart quality high; do not advertise Plans/SSO/K8s that are not real | Honest docs (this file, ROADMAP, README captions) | — |
| **P0a** | Governance skeleton: SSO OIDC, audit export, org policy object, marketplace allowlist | G0.1–G0.5, G0.7, G1.8 | #5 |
| **P0b** | Operator pack: Postgres, TLS, backup, GHCR actually published | G0.6, G1.10 | ROADMAP Next |
| **P1a** | OpenFlow embed (delete native engine) | G1.1 | #4 |
| **P1b** | Intake + HITL + budgets + Ollama | G1.2–G1.5 | P0a |
| **P1c** | Sandbox pause/snapshot/egress UI | G1.6, G1.7 | sandbox-agent + microsandbox |
| **P2** | Connectors, traces, deploy promotion, extra harnesses | G2.* | P0 + P1 |
| **Later** | Edge multi-node, GPU, K8s (only if Compose is operationally proven) | G2.6, G2.8, G2.9 | ROADMAP Later |

### Suggested first GitHub follow-ups (new issues, not this one)

- [ ] OIDC SSO (Entra / Okta / Keycloak) for the control plane
- [ ] Append-only audit log + export API
- [ ] Org policy: model allowlist, MCP/skill allowlist, egress profile
- [ ] Provider: generic OpenAI-compatible + Ollama
- [ ] Seat/org token budget enforcement
- [ ] Sandbox snapshot/pause API (upstream microsandbox)
- [ ] GitHub App intake (issue comment → bus run)
- [ ] HITL approval objects for deploy/merge/delete

---

## What we should not chase

| Temptation | Why not (for now) |
| --- | --- |
| Replacing VS Code / Cursor as an editor | ROADMAP non-goal. Workbench is good enough to supervise agents |
| Cloning n8n’s 400 nodes in Python | #4: embed OpenFlow |
| Hosted multi-tenant Everflow Cloud | CORE “exploring,” not a promise. License is Apache-2.0; ops are not |
| GPU training / fine-tune PaaS | HF and Modal exist |
| Windows/macOS KVM | Product is Linux KVM. Goose covers the laptop agent |
| SOC 2 on the project itself before SSO/audit exist | Certify a story we have not built |

---

## Success criteria

This analysis is doing its job when:

1. A buyer can see **where Everflow wins** (microVM, org chart, constitution, self-host Apache-2.0, workbench) without us over-claiming SSO, billing, or K8s.
2. P0 gaps are tracked as issues, not only README vibes.
3. #4 and #5 stay the workflow/marketplace vehicles; this issue does not fork them.
4. A CISO comparing Everflow to **Coder + Open WebUI + OpenHands** can see a path to identity, audit, and policy that is not “install those three instead.”
5. Product marketing (README screenshots for Plans, “Codex CLI,” Overview-as-dashboard) matches the software.

---

## How this was built

- Product inventory: `Development-Everflow` API routers, UI nav/panels, ROADMAP, READMEs, marketplace/harness catalogs, org/seat/bus models, SECURITY.md.
- Competitors: public docs/repos for OpenHands, Goose, Coder, E2B, Daytona, microsandbox, Dify, Langflow, Flowise, Open WebUI, LibreChat, AnythingLLM, Dust, Cursor, Devin, GitHub Copilot, Replit, Hugging Face Spaces/Enterprise, n8n, Windmill, CrewAI, Microsoft Agent Framework, LangGraph, Bedrock/Vertex/Azure (secondary).
- Existing Everflow plans: issues #4 and #5.

Update this file when a P0/P1 gap ships or when a competitor’s public posture changes in a way that affects sequencing.
