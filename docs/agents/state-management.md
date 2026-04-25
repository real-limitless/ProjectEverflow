## State Management

### State Management Strategies

**Local Component State**:
- React `useState` and `useReducer` for component-level state
- Form state managed by React Hook Form with Zod validation
- UI state (modals, dropdowns, tabs) in local component state

**Server State**:
- **TanStack React Query (v5.83.0)**: Primary tool for server state management
  - Query caching and automatic refetching
  - Optimistic updates and mutation handling
  - Background data synchronization
  - Query invalidation on mutations
- **API Client**: Centralized in `src/lib/api.ts`
  - Type-safe API functions for all backend endpoints
  - Axios-based HTTP client with interceptors
  - JWT authentication token management
  - Error handling and response transformations

**Custom Hooks**:
- `use-toast.ts`: Toast notification system with shadcn/ui integration
- `use-mobile.tsx`: Responsive breakpoint detection and mobile device handling

**URL State**:
- React Router for routing and navigation
- Query parameters for filters, search, pagination
- URL params for resource IDs (project IDs, discussion IDs, etc.)

**Theme & Preferences**:
- Dark/light mode via CSS custom properties
- User preferences stored in localStorage
- Semantic tokens for consistent theming

**Data Sources**:
- **Primary**: Django REST API (`/api/*` endpoints)
- **Development/Mock**: JSON files in `src/data/` directory
- **Hybrid**: Some components use mock data during development, switch to API in production

### API Integration (`src/lib/api.ts`)

The API client provides type-safe functions for all backend operations:

**Authentication**:
- `login(username, password)` - JWT token authentication
- `refreshToken(token)` - Token refresh
- Token storage in localStorage with automatic injection in requests

**Projects**:
- `getProjects()` - List all accessible projects
- `createProject(data)` - Create new project
- `updateProject(id, data)` - Update project
- `deleteProject(id)` - Delete project
- `ensureWebtop(projectId)` - Provision webtop workspace
- `ensureWorkspace(projectId)` - Provision AI workspace
- `updateWorkspaceImage(projectId)` - Update workspace container image
- `resetWorkspace(projectId)` - Reset workspace to clean state

**Services & Containers**:
- `getProjectServices(projectId)` - List project services
- `startService(serviceId)` - Start service
- `stopService(serviceId)` - Stop service
- `restartService(serviceId)` - Restart service
- `killService(serviceId)` - Kill service
- `getServiceLogs(serviceId, params)` - Retrieve logs

**Workspace Files**:
- `getWorkspaceFileTree(projectId)` - Get file tree
- `readWorkspaceFile(projectId, filepath)` - Read file
- `createWorkspaceFile(projectId, data)` - Create file
- `updateWorkspaceFile(projectId, filepath, data)` - Update file
- `deleteWorkspaceFile(projectId, filepath)` - Delete file

**Chat & AI**:
- `getChatSessions()` - List chat sessions
- `createChatSession(data)` - Create session
- `sendMessage(sessionId, message, settings)` - Send message to AI
- `summarizeChatSession(sessionId)` - Generate conversation summary

**Compliance & Safety**:
- `getComplianceChecks()` - List checks
- `getComplianceTemplates()` - List templates
- `getProjectAssignments()` - List project assignments

**Change Requests**:
- `getChangeRequests()` - List PRs
- `approveChangeRequest(id)` - Approve PR
- `requestChanges(id, comments)` - Request changes

**Workspace Tiers** (Admin):
- `getWorkspaceTiers()` - List resource tiers
- `createWorkspaceTier(data)` - Create tier
- `updateWorkspaceTier(id, data)` - Update tier
- `deleteWorkspaceTier(id)` - Delete tier

### Query Keys Convention

TanStack Query uses consistent query keys for caching:
- `['projects']` - All projects list
- `['projects', id]` - Single project
- `['project-services', projectId]` - Services for project
- `['chat-sessions']` - Chat sessions
- `['chat-messages', sessionId]` - Messages for session
- `['workspace-tiers']` - Workspace resource tiers
- `['compliance-checks']` - Compliance checks
- `['change-requests']` - Change requests

Mutations automatically invalidate related queries for consistency.

[Back to Index](./index.md)
