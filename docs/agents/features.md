## Advanced Features

### 1. Visual Workflow Builder
**Component**: `WorkflowTab.tsx`
**Library**: ReactFlow (@xyflow/react v12.9.2)

**Features**:
- Drag-and-drop node-based workflow designer
- Multiple node types: Trigger, Action, Condition, Database, AI Model, Code, API, Email
- Visual pipeline creation for CI/CD, automation, and AI workflows
- Real-time workflow execution status
- Workflow templates and examples
- Export/import workflow configurations

**Node Types**:
- **Trigger**: Start workflows on events (webhooks, schedules, manual)
- **Action**: Perform operations (file operations, notifications)
- **Condition**: Branch logic based on data or conditions
- **Database**: CRUD operations on data sources
- **AI Model**: Integrate with AI APIs for processing
- **Code**: Execute custom JavaScript/Python code
- **API**: Make HTTP requests to external services
- **Email**: Send automated notifications

### 2. Issue Tracking System
**Component**: `IssuesTab.tsx`

**Features**:
- Create and manage project issues
- Categorize by type (Bug, Feature, Enhancement, etc.)
- Status tracking (Open, In Progress, Resolved, Closed)
- Voting system for issue prioritization
- Bookmark important issues
- Search and filter capabilities
- Integration with project workflow

### 3. Enhanced Pull Request Management
**Component**: `PullRequestsTab.tsx`

**Features**:
- Advanced PR filtering and search
- Approval progress tracking
- Diff summary with file changes and line counts
- Review comments and feedback
- Branch and target branch management
- Integration with compliance checks

### 4. Space-Optimized Headers
**Components**: `collapsible-page-header.tsx`, `compact-page-header.tsx`

**Features**:
- **Auto-Hide**: Saves 40-50% vertical space by hiding on scroll
- **Manual Compact**: User-controlled compact mode saving 30-35% space
- Smooth animations and professional UX
- Floating "Show Header" button when collapsed
- Configurable scroll thresholds and behavior

### 5. Page Headers
**Component**: `PageHeader.tsx`
**Usage**: All main application pages

**Features**:
- Consistent header layout across all main pages
- Icon + title + description structure
- Action buttons for primary page functions
- Responsive design with flex layouts
- Reusable component ensuring visual consistency

**Props**:
- `title`: string - Main page title
- `description`: string - Subtitle/description text
- `icon`: ReactNode - Icon component (e.g., Lucide icons)
- `actions?`: ReactNode - Action buttons or elements
- `className?`: string - Additional CSS classes

**Examples**:
- **Dashboard**: "Dashboard" with LayoutDashboard icon, "Overview of your projects and activities"
- **Organizations**: "Organizations" with a hierarchy icon, "Manage organizations, projects, environments, apps, and deployments"
- **My Projects**: "My Projects" with Package icon, "Projects you own or contribute to, grouped around the organization hierarchy"
- **My Teamspace**: "My Teamspace" with FolderTree icon, "Browse accessible organizations and jump into nested project routes"
- **Marketplace**: "Marketplace" with Store icon, "Discover and integrate AI tools..."
- **Settings**: "Settings" with Settings icon, "Manage your account and preferences"

### 6. AI Integration & MCP Support
**Features**:
- Multiple AI model support with configurable parameters
- Model Context Protocol (MCP) server integration
- Streaming responses for real-time interaction
- Custom prompt templates and personas
- Parameter tuning (temperature, max tokens, etc.)
- LiteMaaS API integration for OpenAI-compatible LLM endpoints
- Workspace context injection into chat sessions
- Tool execution integration with chat agents

### 7. Container Orchestration & Workspace Management
**Components**: `WebtopTab.tsx`, `ContainerLogsTab.tsx`, `WorkspaceOrchestration.tsx`

**Features**:
- Per-project containerized development environments
- Podman-based container management with orchestrator abstraction
- Multiple workspace options:
  - **Webtop**: Full Linux desktop (Fedora KDE) accessible via browser
  - **AI Workspace**: Custom container for AI development
- Workspace lifecycle management (start, stop, restart, kill)
- Real-time container logs with tail control and auto-refresh
- Persistent workspace volumes
- Workspace file system API for direct file access
- Resource tier management (t-shirt sizing for CPU/memory limits)
- Workspace initialization methods:
  - Blank project
  - Git repository cloning
  - AI-assisted planning
  - Template-based initialization
- Authenticated proxy access to workspace services
- WebSocket support for real-time terminal access

**Key Capabilities**:
- No host port conflicts - services accessed via backend proxy
- Isolated per-project namespaces
- Workspace volume reset and backup
- Image updates without data loss
- Multi-service orchestration per project

[Back to Index](./index.md)
