# Enterprise AI Application Platform - Agent Documentation

> This index is referenced by [`AGENTS.md`](../../AGENTS.md); keep the section ordering and headings in sync when updating.

## Sections
- [Pages](./pages.md)
- [Advanced Features](./features.md)
- [Webtop Development Environment](./webtop.md)
- [Key Components](./components.md)
- [Data Models](./data-models.md)
- [Workflows & Roles](./workflows.md)
- [PatternFly Integration](./ui-integration.md)
- [Routing](./routing.md)
- [State Management](./state-management.md)
- [Future Enhancements](./future-enhancements.md)
- [Development Guidelines](./development-guidelines.md)
- [Deployment](./deployment.md)
- [Support, Glossary & Contact](./support.md)

## Project Overview

This is an enterprise-grade collaborative AI application development platform that enables teams to build, review, and deploy AI-powered applications with built-in safety, compliance, and approval workflows. The platform features a modern React frontend with TypeScript, a Django REST API backend, visual workflow builders, issue tracking, enhanced pull request management, and space-optimized user interfaces.

## Architecture

### Technology Stack
- **Frontend Framework**: React 18.3.1 with TypeScript
- **Backend Framework**: Django REST Framework with SQLite
- **Build Tool**: Vite
- **UI Framework**: PatternFly React Components (v6.3.1)
- **Styling**: Tailwind CSS with custom design tokens
- **UI Components**: Shadcn/ui + PatternFly
- **Routing**: React Router v6
- **State Management**: React hooks and context
- **Forms**: React Hook Form with Zod validation
- **Data Visualization**: Recharts, PatternFly Charts (Victory)
- **Workflow Visualization**: ReactFlow (@xyflow/react v12.9.2)
- **Icons**: Lucide React, PatternFly Icons
- **Query Management**: TanStack React Query v5.83.0

### Design System
All styling uses semantic tokens from `src/index.css` and `tailwind.config.ts`. Colors are HSL-based and support light/dark modes:
- `--background`, `--foreground`
- `--primary`, `--primary-foreground`
- `--secondary`, `--secondary-foreground`
- `--muted`, `--muted-foreground`
- `--accent`, `--destructive`, `--border`, etc.

### Backend Architecture
- **Framework**: Django 4.x with Django REST Framework
- **Database**: SQLite (development), PostgreSQL (production)
- **Authentication**: JWT authentication via `djangorestframework-simplejwt`
- **API**: RESTful API with ViewSets and Routers
- **Container Orchestration**: Podman-based container management with orchestrator abstraction layer
- **Models**:
  - `User`: Extended Django User with roles (owner, contributor, admin)
  - `Team`: Team/workspace management with members
  - `Project`: AI applications with status, progress, workspace configuration, and relationships
  - `ProjectTemplate`: Templates for creating new projects
  - `ChangeRequest`: Pull requests with approvals and diff summaries
  - `ComplianceCheck`: Automated compliance validation rules
  - `ComplianceTemplate`: Groups of compliance checks
  - `ProjectAssignment`: Links projects to compliance templates/checks
  - `Discussion` / `DiscussionReply`: Discussion forum functionality
  - `MarketplaceItem` / `MarketplaceCategory`: Marketplace for sharing tools
  - `ChatbotPersona` / `ChatbotTemplate`: AI chatbot configuration
  - `ChatSession` / `ChatMessage`: Chat history and messages
  - `Issue` / `IssueReply`: Issue tracking system
  - `Workflow` / `WorkflowExecution`: Visual workflow automation
  - `ProjectPod` / `ProjectService`: Container orchestration and service management
  - `ProjectTool` / `ToolExecution`: Custom tool integration and execution
  - `WorkspaceResourceTier`: T-shirt sizing for workspace container resources (CPU, memory limits)

**API Endpoints**:
- `/api/auth/login/` - JWT authentication
- `/api/auth/refresh/` - JWT token refresh
- `/api/users/` - User management
- `/api/teams/` - Team management
- `/api/projects/` - Project CRUD operations with workspace management actions
- `/api/project-templates/` - Project templates
- `/api/change-requests/` - Pull request management
- `/api/compliance-checks/` - Compliance check library
- `/api/compliance-templates/` - Check template management
- `/api/project-assignments/` - Project compliance assignments
- `/api/discussions/` - Discussion forum
- `/api/discussion-replies/` - Discussion replies
- `/api/marketplace-items/` - Marketplace items
- `/api/marketplace-categories/` - Marketplace categories
- `/api/chatbot-personas/` - Chatbot personas
- `/api/chatbot-templates/` - Prompt templates
- `/api/chat-sessions/` - Chat sessions with AI integration
- `/api/chat-messages/` - Chat messages
- `/api/issues/` - Issue tracking
- `/api/issue-replies/` - Issue replies
- `/api/workflows/` - Workflow management
- `/api/workflow-executions/` - Workflow execution history
- `/api/project-pods/` - Container pod management
- `/api/project-services/` - Container services with lifecycle controls (start/stop/restart/kill)
- `/api/project-tools/` - Custom tools
- `/api/tool-executions/` - Tool execution history
- `/api/workspace-tiers/` - Workspace resource tier management (admin)
- `/api/llm-config/` - LLM configuration and model management
- `/api/projects/{id}/webtop-proxy/{path}` - Authenticated proxy to webtop container
- `/api/projects/{id}/preview-proxy/{path}` - Authenticated proxy to preview services
- `/api/projects/{id}/workspace/files/` - Workspace file system operations (tree, read, create, update, delete)

---

## Core Concepts

### 1. Projects
Projects are AI applications being developed by team members. Each project has:
- **Owner**: The creator of the project
- **Contributors**: Team members actively working on the project
- **Status**: Draft, In Development, Awaiting Approval, Published
- **Progress**: Completion percentage (0-100%)

### 2. Teams & Workspaces
- Users belong to teams/workspaces
- Team members can discover and join projects
- All projects within a team are visible to all team members
- Joining a project requires approval from the project owner

### 3. Change Requests (Pull Requests)
- Contributors submit code changes as PRs
- PRs require approval from multiple contributors (e.g., 3 approvals)
- Only project owners and contributors can review PRs
- Contributors cannot approve their own PRs

### 4. Safety & Compliance
- Administrators create and manage compliance checks
- Checks are grouped into templates (e.g., HIPAA, SOC2)
- Templates are assigned to projects
- Checks run automatically on commit, build, and PR creation

---

*Last Updated: 2025-12-06*
