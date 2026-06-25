# Everflow: The AI-Native, Multi-Orchestrator Vibe Coding Platform

**Tagline**: "From vibe prompt to production — securely, on your infrastructure, with your rules."

**Version**: 0.1.0 (Vibe Plan)  
**Date**: May 20, 2026  
**Inspired by**: Dokploy + Coolify + Portainer + v0.dev/Lovable + OpenClaw + Selkies + GitKraken + Claude Code/Gemini CLI + n8n + CrewAI/LangGraph + Mem0

---

## 1. Vision & Mission

Everflow is the **ultimate self-hosted developer platform** that combines:

- **PaaS power** (Dokploy/Coolify style deployments with Docker, Podman, OpenShift, vSphere, etc.)
- **AI-first development** (vibe coding like Lovable/v0 + full agentic system with Main/Subagents, Skills, RAG & Code Indexing like advanced Claude Code/Grok Build)
- **Visual automation & CI/CD** (n8n-style workflows triggered by Git commits, deployments, metrics, etc. — powered by agents)
- **Team collaboration portal** with org-level everything
- **Marketplace** for sharing/forking AI-enhanced apps **and workflows**
- **Ironclad safety** via organizational guardrails on ALL AI interactions **and workflow executions**
- **Data sovereignty** by design: Run everything on your nodes, in your regions, with private networking

**Core Promise**:
- Attach any machine (laptop, server, cluster) with one command.
- Build apps by chatting ("vibe code").
- Deploy anywhere with one click.
- AI agents that respect *your* organization's laws and limits.
- Live desktop control for complex tasks.
- Seamless routing across hybrid/multi-cloud setups.

---

## 2. Core Features (Dokploy Parity + Massive Upgrades)

### 2.1 PaaS & Deployment (Dokploy Core + More)
- **Applications**: Deploy from Git, Docker image, Docker Compose, Nixpacks, Buildpacks, or **AI-generated code**.
- **Multi-Orchestrator Support**:
  - Docker (Swarm + Compose)
  - Podman (rootless + Compose)
  - OpenShift / Kubernetes (full operator support)
  - vSphere / VMs (via govmomi or similar)
  - Future: Nomad, ECS, etc. via plugins
- **Environments**: dev / staging / prod per project (with promotion pipelines)
- **Databases**: One-click Postgres, MySQL, Mongo, Redis, etc. + custom + external connection strings. **S3 backups** with scheduling & retention.
- **Monitoring & Logs**: Real-time CPU/Mem/Disk/Net + container logs + distributed tracing (optional OpenTelemetry).
- **Terminal Access**: Web terminal into any running container/pod.
- **Scheduled Jobs & Cron**: Built-in or via compose.
- **Templates**: 100+ one-click open-source apps (Plausible, Supabase, etc.) + community.
- **CI/CD**: Visual pipeline editor + `.everflow.yml` + Git webhooks + preview deployments.
- **Backups**: Volume + DB + full app state to S3-compatible (MinIO, AWS, Wasabi, etc.). Point-in-time restore.
- **Scaling**: Horizontal (replicas) + vertical. Auto-scaling hooks.

### 2.2 Node & Infrastructure Management (Portainer-Style + Better)
- **One-command attach**:
  ```bash
  curl -sSL https://everflow.dev/install.sh | sh
  everflow attach --org myorg --token xxxxx
  ```
  Works on Linux/macOS/Windows (WSL), laptops, bare metal, VMs, K8s clusters.
- **Node Dashboard**: Health, metrics, capabilities (orchestrator type, resources), tags (e.g., "eu-west-prod", "gpu-enabled").
- **Local Dev Magic**: Attach your laptop → run apps locally with live reload, but managed centrally. Port forwarding + optional Tailscale/WireGuard mesh.
- **Multi-Node Orchestration**: Apps can span nodes. everflow-router handles discovery & routing.

### 2.3 AI-Powered Development Studio (The Killer Feature)
- **Vibe Coding Editor** (Lovable + v0.dev + Bolt.new on steroids):
  - Chat interface: "Build me a beautiful SaaS dashboard with auth and Stripe"
  - Generates full-stack app (Next.js, Tailwind, shadcn, tRPC, etc.)
  - **Live Preview**: Instant sandbox (WebContainers or isolated Docker preview)
  - One-click "Deploy to Everflow" → chooses env/node, sets up routing, DB, etc.
  - Iterative: "Make the sidebar purple and add dark mode toggle"
  - Screenshot import (like v0)
- **Agentic AI Workspace** (`everflow-ai-workspace`):
  - Like **Gemini CLI / Claude Code / Grok Build** but in browser + desktop.
  - Add **MCP servers** (tool providers) and custom tools.
  - Multi-LLM support: Attach your keys (OpenAI, Anthropic, Grok/xAI, Groq, local Ollama, etc.)
  - **Live Webtop** (Selkies-powered):
    - Full Linux desktop in browser (GPU-accelerated WebRTC)
    - **OpenClaw-style LLM Desktop Agent**: LLM can see screen, move mouse, type, open apps, configure GUIs.
    - Perfect for "set up this legacy Java app's config panel" or complex installs.
  - User chooses execution location: Specific node, AI-workspace cluster, or local laptop.
- **Git Management** (GitKraken + VS Code Web + File Manager):
  - Browse all repos (connected GitHub/GitLab/Gitea or internal Gitea instance)
  - Visual commit graph, blame, diff
  - **Web IDE**: Monaco + full VS Code features (or embedded code-server/Theia)
  - File manager with drag-drop, search, AI "explain this file" / "refactor this function"
- **Marketplace**:
  - Publish your apps (with AI prompt history, compose files, guardrail templates)
  - Others can **Run / Install / Fork / Edit with AI**
  - AI-assisted customization: "Fork this and make it use Postgres + add user roles"
  - Revenue share? (future, optional)

### 2.4 Organizational Safety & Guardrails (Unique Differentiator)
- **Org-Level AI Policy Engine** (the biggest thing):
  - Define policies in YAML/JSON UI:
    ```yaml
    guardrails:
      max_turns_per_conversation: 50
      allowed_tools: ["file_read", "docker_deploy", "web_search_approved"]
      forbidden_topics: ["crypto_trading", "personal_data_export"]
      pre_tool_hooks:
        - name: "require_approval_for_prod"
          condition: "target_env == 'prod'"
      post_tool_hooks:
        - name: "log_and_sanitize"
      conversation_filters:
        - type: "pii_detection"
        - action: "redact"
      output_sanitization: true
    ```
  - Enforced at **every layer**:
    - Vibe coding prompts
    - Agent tool/MCP calls (pre & post)
    - Marketplace AI edits
    - Webtop desktop actions
    - Chatbots/agents users build
  - **Audit Log**: Every AI decision, tool call, with policy evaluation reason.
  - **Human-in-the-loop**: Require approval for high-risk actions (prod deploys, external API calls).
  - Works even if user uses their own keys — policies are enforced server-side before/after LLM calls.

### 2.5 Networking & Routing (`everflow-router`)
- **Smart Global Router** (Cloudflare Workers + Traefik/HAProxy hybrid):
  - Apps register their location (node IP + internal port/service name)
  - Domain/DNS points to router (or any node)
  - Router intelligently proxies to the correct node (even if app is on node1 but DNS resolves to node2)
  - Supports:
    - Path-based routing
    - Header-based (A/B testing)
    - Geographic (if nodes tagged by region)
    - WebSocket, gRPC, TCP passthrough
  - Auto TLS (Let's Encrypt + custom certs)
  - Can be deployed as lightweight sidecar on any node or dedicated edge cluster.
- **Private Networking**: WireGuard mesh between nodes + platform for zero-trust.

### 2.6 Data Sovereignty & Security
- Everything runs on **your infrastructure**.
- Secrets: Encrypted at rest (Vault or built-in KMS), never leave nodes unencrypted.
- Air-gapped support: Nodes can operate offline with periodic sync.
- Compliance: SOC2-ready logging, GDPR data residency (choose EU nodes only), HIPAA (future).
- RBAC + SSO (OIDC/SAML) + SCIM for teams.
- Audit everything.

### 2.7 Workflows & Automation Studio (n8n on Steroids)

**The missing piece that turns Everflow into a complete DevOps + AI automation platform.**

- **Visual Workflow Builder** (n8n-level experience):
  - Drag-and-drop canvas powered by **React Flow**
  - 50+ pre-built nodes with beautiful icons and configuration panels
  - Real-time execution preview, breakpoints, variable live inspector
  - Version history + diff view for workflows (like Git for automations)

- **Powerful Triggers** (Git-first):
  - Git push / PR opened / PR merged / Tag created / Commit message matches regex
  - Webhook (GitHub, GitLab, custom, or any external system)
  - Schedule (cron expressions with timezone support)
  - App lifecycle events (deployment started/succeeded/failed, scaling, backup completed)
  - Metric/alert thresholds (CPU > 80% for 5min → trigger incident workflow)
  - Manual trigger + AI-initiated ("Claude, run the production release workflow")

- **Action Nodes** (extensive library):
  - **Infrastructure**: Deploy App, Scale Replicas, Restart Service, Run Shell/Command on any Edge node(s), Provision Database
  - **CI/CD**: Build & Test, Promote to next environment, Blue/Green deploy, Canary, Rollback
  - **Notifications & Comms**: Slack/Discord/Teams/Email/PagerDuty with rich templates + variables
  - **AI-Powered** (guardrail-aware): Call Agent with custom prompt, Auto code review, Generate release notes/changelog, Root cause analysis from logs
  - **Data & Backup**: Trigger S3 backup, Point-in-time restore, Run DB migrations
  - **Control Flow**: If/Else, Switch, Parallel branches, Loop (forEach, while), Wait for human approval, Delay
  - **Integrations**: HTTP Request, Call MCP Tool, Execute another Workflow, Update Git (create PR, commit file)
  - **Custom**: Run JavaScript/Python snippet, Call external API with auth

- **Execution Engine**:
  - Distributed execution across **everflow-edge** (for shell/node commands) and **everflow-ai-workspace** (for AI-heavy steps)
  - Full step-by-step logs, input/output inspection, retry individual failed steps
  - Variables & secrets injection (respecting org vault)
  - Approval gates with email/Slack links + audit trail
  - Execution history searchable by trigger, app, user, status
  - Webhook callbacks for external systems

- **Deep Git Integration**:
  - Every workflow is linked to one or more Git repositories/branches
  - Workflows can read commit data, changed files, PR metadata
  - Bidirectional: Workflows can create commits, open PRs, add comments

- **AI Co-Pilot for Workflows**:
  - Natural language → full workflow: "When I push to main, run tests, deploy to staging, notify team, and if successful promote to prod with approval"
  - "Add a security scan step using our internal tool"
  - Auto-suggest optimizations or missing guardrail checks

- **Marketplace for Workflows**:
  - Publish reusable workflows (e.g. "Enterprise Release Pipeline with Approvals + Rollback + Post-Deploy AI Summary")
  - One-click import + AI customization ("Adapt this for my team's Slack channel")
  - Versioned and forkable like apps

- **Security & Guardrails** (non-negotiable):
  - All AI nodes and external calls go through the **org guardrails engine**
  - RBAC: Only authorized roles can create, edit, or trigger workflows
  - Secrets never exposed in logs or UI
  - Full immutable audit log of every execution and decision
  - "Dry run" mode + simulation before enabling

This feature makes Everflow the **single pane of glass** for development, deployment, **and full automation** — replacing n8n + Jenkins + custom scripts in one beautiful, secure, AI-augmented interface.

### 2.8 Agentic AI System (Main Agents • Subagents • Skills • RAG • Code Indexing)

**The brain of Everflow** — a full agentic AI platform with hierarchical agents, composable skills, powerful RAG, and deep code understanding.

#### Main Agents & Subagents (Hierarchical Agentic Architecture)
- **Main Agents** (persistent, long-lived):
  - Examples: "Lead Developer Agent", "DevOps Commander", "Security & Compliance Sentinel", "Product Strategist Agent", "Incident Response Lead"
  - Maintain conversation history, long-term goals, project memory, and team context across days/weeks.
  - Can spawn, delegate to, and supervise **Subagents**.
  - Exposed in the UI as always-available teammates you can chat with or assign tasks to.

- **Subagents** (task-specific, spawnable):
  - Examples: "Code Reviewer Subagent", "RAG Researcher", "Deployment Executor", "Desktop Operator (via Selkies webtop)", "Changelog Generator", "Test Writer", "Security Scanner"
  - Created on-demand by Main Agents for parallel execution.
  - Short lifespan but can persist state back to the Main Agent.
  - Support **multi-agent collaboration** (e.g., Main Agent asks 3 subagents to work in parallel on different parts of a task).

- **Agent Lifecycle**:
  - Create / Customize / Clone agents via natural language or UI.
  - Assign agents to Projects, Environments, or specific Workflows.
  - Agents can be published to the Marketplace (with their skills, memory, and guardrail profiles).

#### Skills System (Composable Capabilities)
- **Skills** are first-class, reusable, versioned building blocks (think "tools" but richer and more structured).
- Built-in skills: `git_operations`, `deploy_to_environment`, `run_command_on_edge`, `query_codebase_rag`, `control_webtop_mouse_keyboard`, `analyze_logs`, `generate_code`, `send_notification`, `call_mcp_server`, `execute_workflow`.
- Custom skills: Users (or AI) can create new skills by describing them or writing small functions (sandboxed JS/Python).
- Skills support:
  - Input/output schemas
  - Guardrail hooks (pre/post execution)
  - Versioning + rollback
  - Marketplace sharing ("Team's Internal Deploy Skill v2.3")
- Main Agents and Subagents are composed of **skill sets** (e.g., "Frontend Dev Agent" = code_generation + git + review + deploy skills).

#### RAG & Knowledge Management
- **Unified Knowledge Base** per Organization + per Project.
- Sources: Connected Git repos, uploaded docs/PDFs, issues, design files, previous agent conversations, workflow executions, monitoring data.
- **Hybrid Search**: Semantic (embeddings) + keyword + structural (call graphs, dependencies via tree-sitter).

#### Code Indexing (The Killer RAG Feature)
- **Automatic Background Indexing**:
  - Every connected Git repository is continuously indexed.
  - Uses **tree-sitter** for accurate AST parsing (supports 20+ languages).
  - Generates embeddings (configurable: OpenAI, Voyage, local nomic-embed, etc.).
  - Stores in **pgvector** (already in our stack) with metadata (file path, function name, commit SHA, author, last modified).
- **Incremental & Smart Updates**:
  - On every commit/push → only changed files/functions are re-indexed.
  - Supports branch-aware indexing (main vs feature branches).
- **Powerful Query Capabilities** (used by agents and users):
  - "Find all functions that call `processPayment` and were changed in the last month"
  - "Show me similar code to this authentication logic"
  - "What files would be impacted if I change this interface?"
  - "Explain the architecture of the auth module with diagrams"
- **RAG in Practice**:
  - Agents use code RAG for accurate, context-aware responses (massively reduces hallucinations).
  - Vibe Coding Studio uses it for "refactor this function using patterns from our codebase".
  - Workflow AI nodes can query the codebase before taking actions.

#### Other Core Agentic Features
- **Memory**: Short-term (conversation) + Long-term (project knowledge, user preferences) via Mem0 or custom vector + graph memory.
- **Planning & Reflection**: Agents can create multi-step plans, execute them, reflect on results, and iterate (ReAct + Plan-and-Execute + Reflexion patterns).
- **Tool Use & MCP**: Full support for adding external MCP servers + custom tools. All tool calls go through guardrails.
- **Human-in-the-Loop**: Configurable checkpoints where agents pause and ask for approval/feedback.
- **Multi-Modal**: Future support for vision (analyzing screenshots from the Selkies webtop) and voice.
- **Observability**: Full trace of every agent thought, tool call, delegation, and RAG retrieval (visible in UI with "Why did the agent do X?").

#### Integration Across Everflow
- **Vibe Coding Studio**: Agents act as pair programmers with full codebase knowledge.
- **Workflow Studio**: AI nodes can spawn Main Agents or Subagents for complex steps.
- **everflow-ai-workspace**: Primary runtime for all agents (with user choice of execution location: platform, dedicated node, or local).
- **Marketplace**: Share complete agents ("My Team's Senior Backend Agent"), skill packs, and indexed knowledge bases.
- **Guardrails**: Applied at every layer — prompt, tool call, delegation, RAG retrieval, final output.

This agentic layer makes Everflow feel like having a **full AI engineering team** that knows your codebase, follows your processes, and never forgets context.

### 2.9 Advanced Competitive Features (Differentiators)

These features make Everflow significantly more powerful and harder to replicate than Dokploy, Coolify, Portainer, or any combination of tools.

1. **Self-Healing Deployments**  
   When a deployment fails, an intelligent agent automatically:
   - Rolls back to the last stable version
   - Analyzes logs + code diff + recent changes
   - Uses Code RAG to understand context
   - Proposes a fix (or multiple options)
   - Creates a draft PR with explanation
   - Notifies the team with a clear summary

2. **AI Code Review Agent**  
   Every Pull Request automatically receives a high-quality, context-aware code review from your organization's **"Lead Developer Agent"**:
   - Full understanding of the codebase via RAG
   - Checks for security issues, performance problems, style violations, and architectural drift
   - Suggests improvements with code examples from your own repo
   - Posts directly as a PR comment (or blocks merge based on policy)

3. **Compliance Mode** (SOC2 / GDPR / HIPAA Ready)  
   One-click generation of full compliance reports including:
   - Complete audit trails of all deployments, agent actions, and data access
   - Evidence export (logs, approvals, policy violations, access history)
   - Configurable policy templates
   - Automated evidence collection from workflows and agents

4. **One-Click Full Org Disaster Recovery**  
   - Snapshot the entire organization (apps, environments, workflows, agents, skills, knowledge bases, secrets metadata)
   - Restore to a completely new cluster or new Everflow instance in minutes
   - Supports cross-cloud / cross-region recovery
   - Point-in-time restore with full lineage

5. **Agent + Skill Revenue Marketplace**  
   - Users can publish and sell custom agents and skill packs
   - Built-in versioning, reviews, and usage analytics
   - Optional platform revenue share (configurable per organization)
   - Enterprise licensing options for internal-only or public agents

6. **Secrets & Policy Scanner**  
   - Continuously scans all connected Git repositories and running containers
   - Detects hardcoded secrets, API keys, and sensitive data
   - Enforces organization policy violations (e.g., "no AWS keys in code")
   - Auto-remediation suggestions + one-click fixes
   - Integrates with guardrails for blocking risky deployments

These features turn Everflow from a "good self-hosted PaaS" into a **complete AI-powered DevOps + Engineering platform** that teams will actually want to standardize on.

---

## 3. Architecture

### High-Level Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        everflow-platform                         │
│   (FastAPI Backend + PatternFly v6 React UI)                    │
│   - Auth (OAuth + JWT), Orgs, Projects, Guardrails UI           │
│   - Vibe Coding Studio + Agent Studio                           │
│   - n8n-style Workflow Canvas (React Flow)                      │
│   - Git IDE + File Manager + Code RAG Search                    │
│   - Monitoring + Compliance Dashboard                           │
│   - Marketplace (Apps + Agents + Skills + Workflows)            │
└──────────────────────┬──────────────────────────────────────────┘
                       │ gRPC / REST / WebSocket (mTLS + JWT)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│   everflow-router (Traefik + Custom Controller)                 │
│   - Dynamic service discovery & intelligent routing             │
│   - Auto SSL, load balancing, WebSocket support                 │
└──────────────────────┬──────────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ everflow-edge │ │ everflow-edge │ │ everflow-edge │
│   (Node 1)    │ │   (Node 2)    │ │   (Node 3)    │
│ - Docker      │ │ - Podman      │ │ - OpenShift   │
│ - Podman      │ │ - K8s         │ │ - vSphere     │
│ - Metrics     │ │ - Workloads   │ │ - GPU         │
│ - Local Dev   │ │               │ │               │
└───────────────┘ └───────────────┘ └───────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              everflow-ai-workspace (pluggable)                   │
│   - Hierarchical Agent Runtime (Main Agents + Subagents)        │
│   - Skills Engine + RAG + Code Indexing (pgvector + tree-sitter)│
│   - MCP tool servers + Custom Tools                             │
│   - Selkies Webtop + OpenClaw-style Desktop Agent               │
│   - Guardrails Enforcement Engine                               │
│   - Can run on: Platform node, dedicated AI node, or user laptop│
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Example (Vibe Code → Deploy)
1. User in **everflow-platform** chats: "Build a Trello clone with real-time collab"
2. **everflow-ai-workspace** (with guardrails) generates code using chosen LLM.
3. Live preview in sandbox / webtop.
4. User approves → "Deploy to prod (eu-west nodes)"
5. Platform creates App record → sends deploy job to **everflow-edge** on tagged nodes.
6. Edge builds (if needed) and runs via chosen orchestrator.
7. App registers with **everflow-router**.
8. Router updates Traefik config → traffic flows seamlessly.
9. All AI actions logged + policy-checked.

---

## 4. Recommended Tech Stack (Vibe-Coding Friendly + Production Ready)

### Platform Split Architecture (as requested)

**everflow-platform-api** (Backend)
- **Framework**: FastAPI (Python 3.12+)
- **ORM + Migrations**: SQLAlchemy 2.0 + Alembic
- **Database**: PostgreSQL + pgvector (for embeddings & RAG)
- **Auth**: `fastapi-users` + OAuth2 (GitHub, Google, GitLab, Microsoft, custom OIDC) + JWT
- **Real-time**: FastAPI WebSockets + Redis (for pub/sub)
- **Task Queue**: Celery or ARQ (for background jobs, indexing, long-running agent tasks)
- **API Docs**: Automatic OpenAPI + Swagger/ReDoc

**everflow-platform-ui** (Frontend)
- **Framework**: React 19 + Vite
- **Design System**: **PatternFly v6** (as requested — enterprise-grade, accessible, excellent for complex dashboards)
- **State Management**: TanStack Query + Zustand
- **Routing**: TanStack Router or React Router
- **Real-time**: WebSocket client + React hooks
- **Workflow Canvas**: React Flow (already planned)
- **Agent Canvas / Studio**: Custom + React Flow where needed

### Other Layers (unchanged)

| Layer                        | Recommendation                                      | Why |
|-----------------------------|-----------------------------------------------------|-----|
| **Edge Agent**              | Go 1.23+ (or Rust)                                  | Lightweight, excellent Docker/Podman/K8s/vSphere clients |
| **Router**                  | Traefik v3 + custom Go controller                   | Battle-tested dynamic routing |
| **AI Runtime**              | Python (FastAPI) + LangGraph / CrewAI / AutoGen     | Best agentic frameworks + easy integration with platform API |
| **Web IDE**                 | Monaco Editor + code-server / Theia                 | VS Code experience in browser |
| **Webtop**                  | Selkies (WebRTC) + custom agent                     | Low-latency desktop streaming |
| **Desktop Agent**           | OpenClaw-inspired (screenshot + actions)            | LLM computer use |
| **Guardrails**              | Custom engine + Llama Guard / NeMo Guardrails       | Flexible policy enforcement |
| **Orchestration Abstraction** | Custom SDK layer (Go) wrapping Docker SDK, Podman, client-go, govmomi | Unified API |
| **Secrets**                 | HashiCorp Vault or built-in (age + KMS)             | Enterprise grade |
| **Marketplace**             | S3 + metadata in Postgres                           | Easy publish/fork + revenue features |

**Monorepo Structure** (pnpm workspaces + Turborepo):
```
/everflow
├── everflow-platform-api/      # FastAPI + SQLAlchemy + Alembic
├── everflow-platform-ui/       # PatternFly v6 React + Vite
├── everflow-edge/              # Go agent
├── everflow-router/            # Go + Traefik config controller
├── everflow-ai-workspace/      # Python (LangGraph + FastAPI) + Selkies
├── shared/                     # Common types (Pydantic models, OpenAPI schemas)
├── docs/
├── scripts/                    # install.sh, attach.sh, etc.
└── turbo.json
```

---

## 5. Data Models (Prisma-inspired)

```prisma
model Organization {
  id          String   @id @default(cuid())
  name        String
  slug        String   @unique
  guardrails  Json     // Full policy YAML/JSON
  aiKeys      Json     // Encrypted per-provider keys
  createdAt   DateTime @default(now())
  members     OrganizationMember[]
  projects    Project[]
  nodes       Node[]
}

model Project {
  id             String   @id @default(cuid())
  name           String
  organization   Organization @relation(...)
  environments   Environment[]
  marketplaceItem MarketplaceItem?
}

model Environment {
  id        String   @id
  name      String   // dev | staging | prod
  project   Project  @relation(...)
  targetNodes String[] // node IDs or tags
  apps      Application[]
}

model Application {
  id            String
  name          String
  type          String   // web | worker | db | compose
  source        Json     // git | docker | ai-generated
  buildConfig   Json
  envVars       Json
  volumes       Json
  replicas      Int      @default(1)
  status        String
  nodeId        String?
  environment   Environment @relation(...)
  deployments   Deployment[]
}

model Node {
  id           String
  name         String
  organization Organization @relation(...)
  capabilities Json     // {docker: true, podman: true, k8s: true, gpu: true, ...}
  lastSeen     DateTime
  metrics      Json
  token        String   @unique
}

model Deployment {
  id        String
  app       Application @relation(...)
  status    String
  logs      String?
  createdAt DateTime
}

model MarketplaceItem {
  id          String
  name        String
  description String
  promptUsed  String?  // Original vibe prompt
  compose     Json
  guardrails  Json?
  publishedBy Organization
  forks       Int      @default(0)
}

// NEW: n8n-style Workflows
model Workflow {
  id            String   @id @default(cuid())
  name          String
  description   String?
  organization  Organization @relation(...)
  project       Project? @relation(...)
  definition    Json     // { nodes: [...], edges: [...] , config }
  isActive      Boolean  @default(true)
  version       Int      @default(1)
  createdBy     String
  executions    WorkflowExecution[]
  createdAt     DateTime @default(now())
}

model WorkflowExecution {
  id          String
  workflow    Workflow @relation(...)
  status      String   // running, success, failed, cancelled, waiting_approval
  triggerData Json
  variables   Json
  startedAt   DateTime
  finishedAt  DateTime?
  steps       WorkflowStepExecution[]
}

model WorkflowStepExecution {
  id          String
  execution   WorkflowExecution @relation(...)
  nodeId      String
  nodeType    String
  status      String
  input       Json?
  output      Json?
  error       String?
  durationMs  Int?
  startedAt   DateTime
}

// NEW: Agentic AI System
model Agent {
  id              String   @id @default(cuid())
  name            String
  type            String   // "main" | "sub"
  description     String?
  organization    Organization @relation(...)
  project         Project? @relation(...)
  skills          Json     // Array of skill IDs + config
  memory          Json?    // Long-term memory summary + vector refs
  guardrails      Json?    // Agent-specific policy overrides
  isActive        Boolean  @default(true)
  createdAt       DateTime @default(now())
  lastUsedAt      DateTime?
}

model Skill {
  id            String   @id @default(cuid())
  name          String
  description   String
  organization  Organization @relation(...)
  code          String?    // Sandboxed function or reference
  inputSchema   Json
  outputSchema  Json
  version       Int        @default(1)
  isPublic      Boolean    @default(false)
  createdAt     DateTime   @default(now())
}

model KnowledgeBase {
  id            String   @id @default(cuid())
  name          String
  organization  Organization @relation(...)
  project       Project? @relation(...)
  sources       Json       // Git repos, uploaded files, etc.
  vectorStore   String     // "pgvector" | external
  lastIndexedAt DateTime?
  createdAt     DateTime   @default(now())
}

model CodeIndex {
  id          String   @id @default(cuid())
  repoUrl     String
  branch      String
  filePath    String
  functionName String?
  embedding   Unsupported("vector(1536)") // pgvector
  metadata    Json     // AST info, commit SHA, author, etc.
  knowledgeBase KnowledgeBase @relation(...)
  indexedAt   DateTime @default(now())
}
```

---

## 6. Key Workflows & User Stories

1. **New Team Onboarding**
   - Create org → Invite members → Define guardrails → Attach first node (laptop or server)

2. **Vibe Code → Prod in < 10 minutes**
   - Open Vibe Studio → Prompt → Preview → "Deploy to staging" → Done (router auto-configures domain)

3. **Attach Local Machine for Dev**
   - `everflow attach --local` → Apps run on laptop, appear in dashboard, live sync with central git

4. **Complex Task with Desktop Agent**
   - In AI Workspace: "Configure the new ERP system's admin panel" → Opens Selkies webtop → LLM clicks through GUI → Done

5. **Marketplace Fork + AI Edit**
   - Browse marketplace → Fork "Plausible Analytics" → "Change branding to my company and add custom event tracking" → AI does it → Deploy

6. **Guardrail in Action**
   - User tries to make agent "export all customer data to my personal S3" → Pre-tool hook blocks + requires org admin approval + logs it

7. **DevOps Automation with n8n-style Workflows**
   - DevOps engineer opens Workflow Studio → Creates visual pipeline triggered on `git push to main` → Runs tests on GPU edge nodes → Deploys to staging → Posts AI-generated summary to Slack → Waits for approval → Promotes to prod with automatic rollback on failure. All while org guardrails enforce approval for production deploys and scan every AI step.

8. **Agentic Development with Main + Subagents + Code RAG**
   - Developer chats with "Lead Developer Agent": "Refactor the payment module to support new currency and update all tests". The Main Agent spawns a Code Reviewer Subagent + RAG Researcher Subagent (which queries the full indexed codebase) + Test Writer Subagent. They collaborate in parallel, the Main Agent reviews results, proposes changes via PR, and asks for human approval before merging. All steps are fully auditable and respect org guardrails.

7. **Git-Triggered Smart Pipeline (n8n-style)**
   - Push to `main` → Workflow triggers → Run tests on any available edge node → If green → Deploy to staging + run AI code review → On approval → Promote to prod + notify Slack + trigger backup + publish changelog to marketplace

---

## 7. Security & Sovereignty Architecture

- **Zero-Trust Networking**: All inter-component comms via mTLS + short-lived JWTs. Nodes only accept connections from platform/router.
- **Secret Management**: Never stored in plaintext. Platform uses envelope encryption; nodes decrypt only at runtime.
- **Guardrails as Code**: Policies versioned in Git, applied at runtime.
- **Audit Everything**: Immutable logs of all AI decisions, deployments, node actions.
- **Sovereignty Modes**:
  - Fully air-gapped (periodic USB sync)
  - Private cloud only (no external LLM calls unless approved)
  - Hybrid (local LLMs preferred)

---

## 8. Vibe Coding Roadmap (How We'll Build This Together)

### Phase 0: Bootstrap (This Week)
- [x] This plan
- [ ] Monorepo + shared types
- [ ] Basic everflow-platform (Next.js + auth + org dashboard)
- [ ] everflow-edge skeleton (Go, registers node)
- [ ] Simple router (Traefik + hello world)

### Phase 1: Dokploy Parity + Basic Workflows (2-3 weeks)
- Multi-orchestrator deploy (Docker/Podman first)
- Git deploy + buildpacks
- Logs, monitoring, terminal
- Traefik routing + auto SSL
- DB + S3 backups
- **Basic n8n-style workflow canvas** + Git webhook trigger + Deploy action (MVP)

### Phase 2: AI Core + Full Agentic System + Workflow AI Nodes (3-4 weeks)
- LLM integration + multi-provider keys
- Vibe Coding Studio (prompt → preview)
- Basic guardrails engine
- **everflow-ai-workspace** with Main Agents + Subagents + Skills system
- **Code Indexing + RAG** (tree-sitter + pgvector) across all repos
- **AI-powered workflow nodes** (code review, changelog, incident responder) with guardrail enforcement
- Agent Studio UI for creating/customizing agents and skills

### Phase 3: Advanced Magic + Competitive Differentiators (4-6 weeks)
- Selkies webtop + OpenClaw agent
- Full Git web IDE + file manager
- Marketplace (publish/fork/AI-edit **and workflows + agents + skills**)
- K8s/vSphere adapters
- Full guardrails + audit
- **Self-Healing Deployments** + **AI Code Review Agent**
- **Compliance Mode** + **One-Click Org Disaster Recovery**
- **Secrets & Policy Scanner**
- **Agent + Skill Revenue Marketplace** foundation

### Phase 4: Polish & Launch (Ongoing)
- CLI tool
- One-command everything
- Templates gallery
- Community marketplace
- Performance & scale testing

---

## 9. How to Start Vibe Coding Right Now

1. **Clone / Initialize**
   ```bash
   git clone https://github.com/yourname/everflow   # (we'll create it)
   cd everflow
   pnpm install
   ```

2. **Run Platform Locally**
   ```bash
   cd everflow-platform
   pnpm dev
   ```

3. **I (Grok) will generate**:
   - Next.js starter with beautiful dashboard
   - Go edge agent with attach command
   - Guardrails engine prototype
   - Selkies + agent integration snippets
   - etc.

**Just say the word**: "Generate the Next.js platform skeleton" or "Build the Go edge agent" or "Create the guardrails policy engine" and we'll vibe code it live.

---

## 10. Open Questions / Future Polish

- Pricing model? (Self-hosted free core, optional hosted AI credits?)
- Marketplace monetization (optional)
- Mobile app? (React Native or PWA)
- Plugin system for custom orchestrators/tools
- Federation (multiple Everflow instances talking to each other)

---

**This is the plan. Now let's build the future of developer platforms.**

**Ready to start coding?** Tell me which component to tackle first — I'll generate production-ready code, Dockerfiles, install scripts, everything.

Let's make Everflow the most loved self-hosted platform in 2026. 🚀

---

*Generated with ❤️ by Grok — built by xAI*