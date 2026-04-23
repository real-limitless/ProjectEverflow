## Data Models

### Frontend Data Models
Data models are defined in the corresponding JSON files in `src/data/`. See the JSON files for complete data structures and examples:

- **Login Data**: `src/data/loginData.json`
- **Projects**: `src/data/teamProjects.json`
- **Change Requests**: `src/data/changeRequests.json`
- **Compliance Checks**: `src/data/complianceChecks.json`
- **Dashboard Metrics**: `src/data/dashboardMetrics.json`
- **Marketplace Tools**: `src/data/marketplaceTools.json`
- **Workflows**: `src/data/workflows.json`
- **Chatbot Data**: `src/data/chatbotPersonas.json`, `src/data/chatbotTemplates.json`, `src/data/chatSessions.json`
- **Notifications**: `src/data/notifications.json`
- **Collaboration Data**: `src/data/collaborationData.json`
- **User Settings**: `src/data/userSettings.json`
- **Support Options**: `src/data/supportData.json`
- **Application Form Data**: `src/data/applicationFormData.json`
- **Navigation Menu**: `src/data/navigationData.json`
- **About Page**: `src/data/aboutData.json`
- **Edit Application Defaults**: `src/data/editApplicationData.json`
- **Page Content**: `src/data/pageContent.json`

### Backend Data Models
Django models are defined in `backend/api/models.py`. Key models include:

**Core Models**:
- **User**: Extended Django User with role (owner/contributor/admin), teams, bio, avatar, preferences
- **Team**: Team/workspace management with members, description, timestamps
- **Project**: AI applications with owner, contributors, team, status, progress, workspace configuration
- **ProjectTemplate**: Templates for project creation with file structure, language, framework, difficulty

**Workspace & Container Models**:
- **WorkspaceResourceTier**: T-shirt sizing for container resources (name, slug, CPU/memory limits, default flag)
- **ProjectPod**: Container pod for project namespace (project, pod_name, status, config)
- **ProjectService**: Container services (pod, name, type, image, container_name, status, ports, environment, config)
- **ProjectTool**: Custom tools for projects (project, name, slug, description, entrypoint, runtime_image, args_schema)
- **ToolExecution**: Tool execution history (tool, session, status, input/output payload, logs, exit_code)

**Compliance & Safety Models**:
- **ComplianceCheck**: Validation rules (name, description, category, severity, AI prompt)
- **ComplianceTemplate**: Groups of checks (name, description, checks)
- **ProjectAssignment**: Links projects to compliance templates/checks (project, template, custom_checks, status, violations)

**Collaboration Models**:
- **ChangeRequest**: Pull requests with approvals (title, description, project, author, status, change_type, diff_summary, approvals_required)
- **Approval**: PR approval records (change_request, approver, approved, comments)
- **Discussion** / **DiscussionReply**: Forum discussions with category, replies, views, pinned/locked flags
- **Issue** / **IssueReply**: Issue tracking (title, description, project, author, status, category, votes, views)

**AI & Chatbot Models**:
- **ChatbotPersona**: AI assistant personalities (name, description, icon, category, system_prompt, default_llm_id, temperature, max_tokens)
- **ChatbotTemplate**: Prompt templates (name, description, system_prompt, user_prompt_template, variables, category)
- **ChatSession**: Chat sessions (user, project, persona, template, title, llm_id, temperature, mode, enabled_tools)
- **ChatMessage**: Chat messages (session, message_type, content, metadata)

**Workflow Models**:
- **Workflow**: Visual workflow automation (name, description, project, author, status, nodes, edges, settings)
- **WorkflowExecution**: Workflow execution history (workflow, triggered_by, status, execution_data, started_at, completed_at)

**Marketplace Models**:
- **MarketplaceItem**: Published tools/applications (name, description, author, category, likes, status, gradient, tags, downloads)
- **MarketplaceCategory**: Marketplace categories (id, label, icon, description, order)

[Back to Index](./index.md)
