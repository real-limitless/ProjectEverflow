## Application Structure

### Pages

#### 1. **Login** (`/login`)
**File**: `src/pages/Login.tsx`

**Purpose**: User authentication page for accessing the Everflow AI Platform using PatternFly's LoginPage component.

**Features**:
- Full-screen login page with background image
- Username and password authentication with validation
- Remember me functionality
- Social media login buttons (Google, GitHub, Dropbox, Facebook, GitLab)
- Footer links (Terms of Use, Help, Privacy Policy)
- Loading states during authentication
- Mock authentication using JSON data
- Responsive design with PatternFly styling

**Data Source**: `src/data/loginData.json`

**Components Used**:
- PatternFly LoginPage - Main page wrapper with background
- PatternFly LoginForm - Form component with validation
- PatternFly LoginFooterItem - Footer navigation links
- PatternFly icons for social media buttons
- React state management for form handling

**Demo Credentials**:
- **Admin**: admin / admin123
- **Developer**: developer / dev123
- **Manager**: manager / mgr123

**Authentication Flow**:
1. User enters credentials in the PatternFly LoginForm
2. Form validation occurs on submit
3. Credentials checked against mock data
4. On success: user data stored in localStorage, redirect to dashboard
5. On failure: error message displayed with helper text

**Social Media Integration**:
- Placeholder buttons for OAuth providers
- Accessible with proper ARIA labels
- Ready for integration with actual authentication services

**Footer Links**:
- Terms of Use
- Help documentation
- Privacy Policy
- Sign up messaging (points to administrator contact)
- Forgot credentials link

---

#### 2. **Dashboard** (`/`)
**File**: `src/pages/Dashboard.tsx`

Main overview page showing:
- Metrics cards (active projects, team members, pending approvals)
- Analytics charts (project trends, activity)
- Recent activity feed
- Quick actions

**Components**:
- `DashboardHeader.tsx` - Header with user info and actions
- `DashboardSidebar.tsx` - Navigation menu
- `MetricsCards.tsx` - KPI cards
- `AnalyticsChart.tsx` - Data visualizations
- `DataTable.tsx` - Recent activity table

---

#### 3. **Organizations** (`/organizations`)
**Files**:
- `src/pages/Organizations.tsx`
- `src/pages/organizations/OrganizationsOverview.tsx`
- `src/pages/organizations/OrganizationDetail.tsx`
- `src/pages/organizations/ProjectDetail.tsx`
- `src/pages/organizations/EnvironmentDetail.tsx`
- `src/pages/organizations/AppDetail.tsx`

**Purpose**: Primary workspace shell for the Dokploy-style hierarchy: Organization → Project → Environment → App → Deployment.

**Features**:
- PatternFly Tree View for hierarchy navigation
- Route-driven detail panes using nested React Router routes
- Creation flows for organizations, projects, environments, apps, and deployment records
- Summary cards for organization and project health
- Deployment history with rollback action at the app route level

**Route Structure**:
- `/organizations` - Overview of accessible organizations
- `/organizations/:orgId` - Organization summary and project list
- `/organizations/:orgId/projects/:projectId` - Project detail and environments
- `/organizations/:orgId/projects/:projectId/environments/:environmentId` - Environment detail and apps
- `/organizations/:orgId/projects/:projectId/environments/:environmentId/apps/:appId` - App detail and deployments

**Workflow**:
1. User selects an organization from the hierarchy tree
2. User drills into a project, environment, and app through nested routes
3. Deployment history and rollback are handled within the app detail route

---

#### 4. **My Teamspace** (`/my-teamspace`)
**File**: `src/pages/MyTeamspace.tsx`

**Purpose**: Organization-first directory page for discovering accessible organizations and jumping into the nested hierarchy.

**Features**:
- Aggregated organization cards with project previews
- Filters for organization role, search text, and sort order
- Stats for organizations, accessible projects, owned projects, and admin roles
- Deep links into `/organizations/:orgId` and `/organizations/:orgId/projects/:projectId`
- Legacy standalone project callout for projects not yet attached to an organization

**Data Sources**:
- `getOrganizations()`
- `getProjects()`
- `getCurrentUser()`

**Workflow**:
1. User browses organizations they can access
2. User opens an organization or a specific project route
3. User continues into environments and apps through the hierarchy shell

---

#### 5. **My Projects** (`/my-applications`)
**File**: `src/pages/MyApplications.tsx`

**Purpose**: Project-centric view of the work a user owns or contributes to, grouped by organization.

**Features**:
- Groups projects by organization name
- Filters by ownership role, project status, search text, and sort order
- Stats for owned, contributing, awaiting approval, and published projects
- Deep links into organization and project detail routes
- Fallback handling for projects that are still independent of an organization

**Data Sources**:
- `getMyProjects()`
- `getCurrentUser()`

**Workflow**:
1. User filters to the projects they care about
2. User opens the relevant project route inside the organization hierarchy
3. User manages deployments, environments, and downstream tooling from the project path

---

#### 6. **Approval Queue** (`/approval-queue`)
**File**: `src/pages/ApprovalQueue.tsx`

**Purpose**: Review and approve pull requests (code changes) for projects where user is owner or contributor.

**Data Source**: `src/data/changeRequests.json`

**Change Request Structure**: See the JSON file for complete data structure and examples.

**Features**:
- Filter by:
  - Project
  - Change type (Feature, Bug Fix, Enhancement, Documentation)
  - Status (All, Pending Review, Approved, Changes Requested, Rejected)
- Approval progress indicator (e.g., "2 of 3 required approvals")
- Diff summary (files changed, lines added/removed)
- Actions:
  - Approve (if user is owner/contributor and hasn't approved yet)
  - Request Changes
  - Reject
  - View Full Diff
  - View Project

**Approval Rules**:
- Requires N contributor approvals before merge (e.g., 3)
- Contributors cannot approve their own PRs
- Once required approvals are met, PR can be merged
- Only visible to project owners and contributors

**Workflow**:
1. Contributor submits code changes (PR)
2. PR appears in Approval Queue for all project members
3. Owners/Contributors review changes
4. Each approves or requests changes
5. Once 3 approvals received → Ready to merge
6. Changes are merged into main/target branch

---

#### 7. **Safety & Compliance** (`/safety-compliance`)
**File**: `src/pages/SafetyCompliance.tsx`

**Purpose**: Administrator check library for creating, browsing, and assigning compliance checks to projects.

**Data Source**: `src/data/complianceChecks.json`

**Data Structure**: See the JSON file for complete compliance check, template, and project assignment structures and examples.

**Features**:

**Tab 1: Check Library**
- Browse all available compliance checks
- Filter by category (Security, Code Quality, Performance, Compliance, Custom)
- Search checks by name
- View check details:
  - Name, description, category, severity
  - AI validation prompt/rules
  - Usage count (how many projects use this check)
- Admin actions:
  - Create new check
  - Edit existing check
  - Delete check
  - View check usage

**Tab 2: Compliance Templates**
- Create/manage groups of checks
- Templates include:
  - Name (e.g., "HIPAA Compliance", "SOC2 Compliance")
  - Description
  - List of checks included
  - Projects currently using the template
- Actions:
  - Create template
  - Edit template
  - Delete template
  - Assign template to projects
  - View template usage

**Tab 3: Project Assignments**
- Table showing which checks/templates are assigned to which projects
- Columns:
  - Project name
  - Assigned templates
  - Assigned custom checks
  - Last check run date/time
  - Last check status (Pass/Fail)
  - Number of violations
- Actions:
  - Assign checks to project
  - Assign templates to project
  - View check history
  - Run checks manually

**Check Execution Model**:
Checks run automatically when:
- Code is committed
- Build is executed
- PR is created
- Manual trigger by admin

**Admin Workflow**:
1. Create individual compliance checks (SQL injection, XSS, etc.)
2. Group checks into templates (HIPAA, SOC2, PCI-DSS)
3. Assign templates to projects
4. Checks run automatically on commit/build/PR
5. View results in Project Assignments tab
6. Address violations before approval

---

#### 8. **Edit Application** (`/my-applications/edit/:appName`)
**File**: `src/pages/EditApplication.tsx`

**Purpose**: Comprehensive application editing interface with AI assistance, file management, collaborative features, and space-optimized headers.

**New Features**:
- **Header Mode Toggle**: Three header modes for space optimization:
  - **Auto-Hide Header** (`CollapsiblePageHeader`): Automatically hides on scroll down, shows on scroll up
  - **Manual Compact Header** (`CompactPageHeader`): Toggle between full and compact modes manually
  - **Original Header**: Classic static header layout
- **Space Savings**: Auto-hide saves ~150-200px (40-50% more vertical space), Manual compact saves ~100-120px (30-35% more space)

**Components**:
- `CollapsiblePageHeader.tsx` - Auto-hide header component
- `CompactPageHeader.tsx` - Manual toggle header component
- `IssuesTab.tsx` - Issue tracking and discussion
- `PullRequestsTab.tsx` - Pull request management
- `WorkflowTab.tsx` - Visual workflow builder with ReactFlow
- `CodeEditor.tsx` - Code editing interface
- `FileTree.tsx` - File/folder navigation
- `GitDiffViewer.tsx` - Code diff visualization

**Tabs**:
1. **AI Editor** - AI-assisted code editing with MCP server integration
2. **Application Details** - Form-based editing with validation
3. **File Manager** - File system operations and management
4. **Repository & Git** - Git operations and history
5. **Issues** - Issue tracking and collaboration
6. **Pull Requests** - Code review and merging
7. **Workflow** - Visual workflow design and automation

**AI Integration**:
- Multiple AI model support (GPT-4, Claude, etc.)
- Configurable parameters (temperature, max tokens, etc.)
- MCP (Model Context Protocol) server integration
- Streaming responses
- Custom prompt templates

---

### Additional Pages

#### **About** (`/about`)
**File**: `src/pages/About.tsx`
About page with project information and credits.

#### **Support** (`/support`)
**File**: `src/pages/Support.tsx`
Support and help resources.

#### **Create Discussion** (`/create-discussion`)
**File**: `src/pages/CreateDiscussion.tsx`
Interface for creating new discussion threads.

#### **View Discussion** (`/view-discussion/:id`)
**File**: `src/pages/ViewDiscussion.tsx`
View and participate in discussion threads.

#### **Create Workspace Project** (`/my-teamspace/create`)
**File**: `src/pages/CreateWorkspaceProject.tsx`
Legacy create route for project creation. It still supports blank projects, repository cloning, AI-assisted planning, and template-based creation, but the primary hierarchy entry point is now the Organizations page.

#### **View Application** (`/my-teamspace/view/:appName`)
**File**: `src/pages/ViewApplication.tsx`
Legacy compatibility page from the pre-organization Teamspace model.

#### **Join Application** (`/my-teamspace/join/:appName`)
**File**: `src/pages/JoinApplication.tsx`
Legacy compatibility page from the pre-organization Teamspace model.

#### **Fork Application** (`/my-teamspace/fork/:appName`)
**File**: `src/pages/ForkApplication.tsx`
Legacy compatibility page for copying an existing project outside the new hierarchy shell.

#### **Create Application** (`/my-applications/create`)
**File**: `src/pages/CreateApplication.tsx`
Legacy standalone create route that remains available alongside the organization-first hierarchy.

#### **Application Preview** (`/my-applications/run/:appName`)
**File**: `src/pages/ApplicationPreview.tsx`
Legacy preview route retained for older project/application flows.

#### **Create Team** (`/create-team`)
**File**: `src/pages/CreateTeam.tsx`
Create a new team for collaboration.

#### **View Team** (`/teams/view/:teamId`)
**File**: `src/pages/ViewTeam.tsx`
View details of a specific team.

#### **Join Team** (`/teams/join/:teamId`)
**File**: `src/pages/JoinTeam.tsx`
Request to join a team.

#### **Create Workflow** (Internal)
**File**: `src/pages/CreateWorkflow.tsx`
Create new workflows for projects.

#### **Index** (`/`)
**File**: `src/pages/Index.tsx`
Alternative landing page (not currently routed - Dashboard is the main landing page).

#### **Not Found** (`*`)
**File**: `src/pages/NotFound.tsx`
404 error page for unmatched routes.

---

#### **Header Demo** (Development Only)
**File**: `src/pages/HeaderDemo.tsx`

**Purpose**: Demonstration and testing page for the new header components.

**Features**:
- Live examples of `CollapsiblePageHeader` and `CompactPageHeader`
- Interactive demos with scroll testing
- Code examples and usage documentation
- Performance metrics and testing instructions

**Components**:
- `collapsible-page-header.tsx` - Auto-hide header demo
- `compact-page-header.tsx` - Manual compact header demo

**Note**: This page is not routed in production and is used for development/testing purposes only.

#### **Marketplace** (`/marketplace`)
**File**: `src/pages/Marketplace.tsx`
Browse and discover published applications from the community.

#### **Enterprise Chatbot** (`/enterprise-chatbot`)
**File**: `src/pages/EnterpriseChatbot.tsx`
AI-powered chatbot interface with persona selection and template management.

**Components**:
- `PersonaSelector.tsx` - Choose chatbot personality
- `ChatInterface.tsx` - Main chat UI
- `ChatHistory.tsx` - Conversation history
- `TemplateManager.tsx` - Manage prompt templates
- `EditTemplateDialog.tsx` - Template editing dialog
- `TemplateVariableDialog.tsx` - Template variable management
- `ModelSettings.tsx` - Configure AI model settings
- `PersonaSettingsModal.tsx` - Persona configuration modal

#### **Collaboration Hub** (`/collaboration-hub`)
**File**: `src/pages/CollaborationHub.tsx`
Real-time collaboration features (whiteboard, video chat, shared editing).

#### **Notifications** (`/notifications`)
**File**: `src/pages/Notifications.tsx`
System notifications, alerts, and activity updates.

#### **Settings** (`/settings`)
**File**: `src/pages/Settings.tsx`
User preferences, account settings, integrations.

#### **Admin Workspace Settings** (`/admin/workspace-settings`)
**File**: `src/pages/AdminWorkspaceSettings.tsx`

**Purpose**: Administrator interface for managing workspace resource tiers (t-shirt sizing for container resources).

**Features**:
- View all workspace resource tiers
- Create new tiers with custom CPU and memory limits
- Edit existing tier configurations
- Delete unused tiers
- Set default tier for new projects
- Activate/deactivate tiers for user selection

**Data Fields**:
- `name`: Display name (e.g., "Light", "Standard", "Heavy")
- `slug`: Unique identifier for API usage
- `cpu_limit`: CPU limit (e.g., "1.0", "2.0", "4.0")
- `memory_limit`: Memory limit (e.g., "2g", "4g", "8g")
- `is_default`: Whether this is the default tier for new projects
- `is_active`: Whether this tier is available for selection

**API Integration**:
- Uses TanStack Query for data fetching and mutations
- Real-time updates with query invalidation
- Toast notifications for user feedback

**Admin Workflow**:
1. Navigate to Admin Workspace Settings
2. View list of existing resource tiers
3. Create new tier with specific CPU/memory limits
4. Activate/deactivate tiers as needed
5. Set default tier for new projects
6. Users see available tiers when creating projects

**Note**: This page requires admin permissions and is only accessible to administrators.

---

[Back to Index](./index.md)
