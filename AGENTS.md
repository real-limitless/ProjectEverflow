# Enterprise AI Application Platform — Agent Documentation Hub

This repository now uses a modular documentation suite under `docs/agents/`. The goal of this top-level guide is to summarize the platform and point you to the deep dives for every area of the product. If you spot a mismatch between this file and the sub-documents, update the relevant file under `docs/agents/` first and then refresh the pointers here.

> **Tip:** Start with [`docs/agents/index.md`](docs/agents/index.md) for the canonical overview, architecture, and core concepts.

---

## How to Navigate the Modular Docs

1. Open [`docs/agents/index.md`](docs/agents/index.md) for the project overview, architecture, and core concepts.
2. Jump to the focused guides listed below for detailed specs, workflows, and UI breakdowns.
3. When editing documentation, mirror the structure already established in `docs/agents/` to keep this hub aligned with the modular files.

### Section Map

| Topic | Description | File |
| --- | --- | --- |
| Project Overview, Architecture, Core Concepts | High-level goals, stack, and domain definitions | [`docs/agents/index.md`](docs/agents/index.md) |
| Application Structure & Pages | All routed experiences plus development-only demos | [`docs/agents/pages.md`](docs/agents/pages.md) |
| Advanced Features | Visual workflow builder, AI tooling, PR enhancements, space-optimized headers, page headers | [`docs/agents/features.md`](docs/agents/features.md) |
| Webtop Development Environment | Per-project containerized workspaces, orchestrator abstraction, lifecycle management | [`docs/agents/webtop.md`](docs/agents/webtop.md) |
| Key Components | UI primitives, dashboard/editor/project modules | [`docs/agents/components.md`](docs/agents/components.md) |
| Data Models | JSON data sources powering mock content | [`docs/agents/data-models.md`](docs/agents/data-models.md) |
| Workflows & Roles | Join, PR approval, compliance flows, and role matrix | [`docs/agents/workflows.md`](docs/agents/workflows.md) |
| PatternFly Integration | PatternFly, Shadcn, and custom component references | [`docs/agents/ui-integration.md`](docs/agents/ui-integration.md) |
| Routing | Frontend routes plus backend API endpoints | [`docs/agents/routing.md`](docs/agents/routing.md) |
| State Management | React Context, hooks, React Query, and data sources | [`docs/agents/state-management.md`](docs/agents/state-management.md) |
| Future Enhancements | Backlog of aspirational features | [`docs/agents/future-enhancements.md`](docs/agents/future-enhancements.md) |
| Development Guidelines | Code style, component patterns, testing, API guidance | [`docs/agents/development-guidelines.md`](docs/agents/development-guidelines.md) |
| Deployment | Build, preview, and hosting notes | [`docs/agents/deployment.md`](docs/agents/deployment.md) |
| Support, Glossary, Contact | Reference material and contributor info | [`docs/agents/support.md`](docs/agents/support.md) |

---

## Executive Summary

### Project Overview
This is an enterprise-grade collaborative AI application development platform enabling teams to build, review, and deploy AI-powered applications with built-in safety, compliance, and approval workflows. The product ships with a modern React + TypeScript frontend, a Django REST API backend, visual workflow builders, issue tracking, enhanced pull request management, and space-optimized editing experiences.

### Architecture Snapshot
- **Frontend**: React 18.3.1, Vite, PatternFly components, Tailwind semantic tokens
- **Backend**: Django 4.x + Django REST Framework, SQLite (dev) / PostgreSQL (prod)
- **Key Libraries**: ReactFlow, TanStack Query, React Hook Form + Zod, Recharts, Lucide
- **Container Orchestration**: Podman-based workspace management with orchestrator abstraction
- **API Surface**: `/api/users/`, `/api/projects/`, `/api/change-requests/`, `/api/compliance-checks/`, `/api/compliance-templates/`, `/api/project-assignments/`, `/api/workspace-tiers/`, `/api/project-services/`, `/api/llm-config/`

### Core Concepts
- **Projects** track ownership, contributors, status, and completion progress.
- **Teams & Workspaces** let all members discover projects and request to join.
- **Change Requests** (PRs) require multi-approver workflows with diff summaries.
- **Safety & Compliance** bundles checks into templates that run on commits, builds, and PR creation.

For the full text of these sections, follow the links in the table above.

---

## Keeping This File in Sync

- When adding a brand-new section, create or update the appropriate file in `docs/agents/` and add a link to the table here.
- If you rename files under `docs/agents/`, update every reference in this hub and in the `index.md` table of contents.
- The detailed documents each include a `Back to Index` link so readers can always return to [`docs/agents/index.md`](docs/agents/index.md).
- If you make a change that changes any of these files inside `doc/` make sure to update the corresponding markdown documentation.

---

*Last Updated: 2025-12-06 (matches `docs/agents/index.md`)*
