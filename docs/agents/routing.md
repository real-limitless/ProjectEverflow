## Routing

**Main Routes**:
- `/login` - User authentication
- `/` - Main dashboard (home page)
- `/my-teamspace` - Browse all team projects
- `/my-applications` - My owned/contributed projects
- `/approval-queue` - PR review system
- `/safety-compliance` - Compliance check library
- `/marketplace` - Published applications
- `/enterprise-chatbot` - AI chatbot
- `/collaboration-hub` - Real-time collaboration
- `/notifications` - Notifications center
- `/settings` - User settings & LLM provider management
- `/support` - Support page
- `/about` - About page

**Admin Routes**:
- `/admin/workspace-settings` - Workspace tier configuration
- `/admin/llm-usage` - LLM usage analytics & reporting

**Teamspace Routes**:
- `/my-teamspace/view/:appName` - View project details
- `/my-teamspace/join/:appName` - Request to join project
- `/my-teamspace/fork/:appName` - Fork project
- `/my-teamspace/create` - Create new team project

**Application Management Routes**:
- `/my-applications/create` - Create new application
- `/my-applications/edit/:appName` - Edit application
- `/my-applications/run/:appName` - Preview/run application

**Discussion Routes**:
- `/create-discussion` - Create new discussion
- `/view-discussion/:id` - View discussion details

**Team Management Routes**:
- `/create-team` - Create new team
- `/teams/view/:teamId` - View team details
- `/teams/join/:teamId` - Join a team

**Error Routes**:
- `*` - Not found (404) page

**Backend API Routes**:

*Authentication*:
- `POST /api/auth/login/` - JWT token authentication
- `POST /api/auth/refresh/` - JWT token refresh

*User Management*:
- `GET/POST /api/users/` - User CRUD operations
- `GET/PATCH /api/users/me/` - Current user profile

*Team Management*:
- `GET/POST /api/teams/` - Team CRUD operations
- `POST /api/teams/:id/add_member/` - Add member to team
- `POST /api/teams/:id/remove_member/` - Remove member from team

*Project Management*:
- `GET/POST /api/projects/` - Project CRUD operations
- `GET /api/projects/my_projects/` - User's projects
- `POST /api/projects/:id/ensure_webtop/` - Provision/ensure webtop workspace
- `POST /api/projects/:id/ensure_workspace/` - Provision/ensure AI workspace container
- `POST /api/projects/:id/update_workspace_image/` - Update workspace to latest image
- `POST /api/projects/:id/reset_workspace/` - Reset workspace volume to clean state
- `GET/POST /api/project-templates/` - Project template management

*Change Requests*:
- `GET/POST /api/change-requests/` - Change request CRUD
- `POST /api/change-requests/:id/approve/` - Approve a change request
- `POST /api/change-requests/:id/request_changes/` - Request changes on PR

*Compliance*:
- `GET/POST /api/compliance-checks/` - Compliance check library
- `GET/POST /api/compliance-templates/` - Template management
- `GET/POST /api/project-assignments/` - Project compliance assignments

*Discussions*:
- `GET/POST /api/discussions/` - Discussion CRUD
- `POST /api/discussions/:id/increment_views/` - Track views
- `POST /api/discussions/:id/toggle_pin/` - Pin/unpin discussion
- `POST /api/discussions/:id/toggle_lock/` - Lock/unlock discussion
- `GET/POST /api/discussion-replies/` - Discussion replies

*Marketplace*:
- `GET/POST /api/marketplace-items/` - Marketplace items
- `POST /api/marketplace-items/:id/like/` - Like an item
- `POST /api/marketplace-items/:id/increment_downloads/` - Track downloads
- `GET /api/marketplace-categories/` - Marketplace categories

*Chatbot*:
- `GET/POST /api/chatbot-personas/` - Chatbot personas
- `GET/POST /api/chatbot-templates/` - Prompt templates
- `GET/POST /api/chat-sessions/` - Chat sessions
- `POST /api/chat-sessions/:id/send_message/` - Send message and get AI response
- `POST /api/chat-sessions/:id/summarize/` - Generate conversation summary
- `GET/POST /api/chat-messages/` - Chat messages

*Issues*:
- `GET/POST /api/issues/` - Issue CRUD
- `POST /api/issues/:id/vote/` - Vote for an issue
- `POST /api/issues/:id/bookmark/` - Bookmark/unbookmark issue
- `POST /api/issues/:id/view/` - Track issue views
- `GET/POST /api/issue-replies/` - Issue replies

*Workflows*:
- `GET/POST /api/workflows/` - Workflow CRUD
- `POST /api/workflows/:id/execute/` - Execute a workflow
- `GET/POST /api/workflow-executions/` - Workflow execution history

*Podman/Container Management*:
- `GET /api/project-pods/` - Project pods (containers)
- `POST /api/project-pods/ensure/` - Ensure pod exists
- `GET /api/project-services/` - Project services with live status sync
- `POST /api/project-services/:id/start/` - Start a stopped service
- `POST /api/project-services/:id/stop/` - Stop a running service
- `POST /api/project-services/:id/restart/` - Restart a service
- `POST /api/project-services/:id/kill/` - Forcefully kill a service
- `GET /api/project-services/:id/logs/` - Retrieve service logs (with tail/since params)
- `DELETE /api/project-services/:id/delete/` - Delete a service
- `GET/POST /api/project-tools/` - Project tools
- `POST /api/project-tools/:id/execute/` - Execute a tool
- `GET /api/tool-executions/` - Tool execution history

*Workspace Management*:
- `GET/POST /api/workspace-tiers/` - Workspace resource tier management (admin)
- `GET /api/workspace-tiers/:slug/` - Get specific tier by slug

*Workspace File System*:
- `GET /api/projects/:id/workspace/files/tree/` - Get file tree structure
- `GET /api/projects/:id/workspace/files/read/:filepath` - Read file contents
- `POST /api/projects/:id/workspace/files/create/` - Create new file
- `PUT /api/projects/:id/workspace/files/update/:filepath` - Update file contents
- `DELETE /api/projects/:id/workspace/files/delete/:filepath` - Delete file

*Proxy Services*:
- `/api/projects/:id/webtop-proxy/:path` - Authenticated proxy to webtop container
- `/api/projects/:id/preview-proxy/:path` - Authenticated proxy to preview services

*LLM Configuration*:
- `GET/POST /api/llm-config/` - LLM configuration management
- `GET /api/llm-config/available_models/` - List available LLM models
- `POST /api/llm-config/test_connection/` - Test LLM connection

*LLM Provider Management*:
- `GET/POST /api/llm-providers/` - LLM provider CRUD (hierarchical access control)
- `GET /api/llm-providers/:id/` - Get provider details
- `PATCH /api/llm-providers/:id/` - Update provider
- `DELETE /api/llm-providers/:id/` - Delete provider
- `POST /api/llm-providers/:id/discover_models/` - Trigger model discovery
- `POST /api/llm-providers/:id/test_connection/` - Validate API key
- `GET /api/llm-providers/available_models/` - Get models for project context

*LLM Usage Statistics*:
- `GET /api/llm-usage-stats/scope_stats/` - Get usage stats by scope (system/team/project/user)
- `GET /api/llm-usage-stats/daily_trends/` - Get daily cost trends
- `GET /api/llm-usage-stats/user_stats/` - Get current user's usage stats
- `GET /api/llm-usage-stats/provider_stats/` - Get provider-specific usage stats (admin)

[Back to Index](./index.md)
