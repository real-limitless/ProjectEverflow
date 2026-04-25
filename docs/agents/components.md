## Key Components

### UI Components (`src/components/ui/`)
Shadcn/ui components customized with design system tokens:
- `PageHeader.tsx` - Consistent page header component
- `accordion.tsx`, `alert-dialog.tsx`, `alert.tsx`, `aspect-ratio.tsx`
- `avatar.tsx`, `badge.tsx`, `breadcrumb.tsx`, `button.tsx`
- `calendar.tsx`, `card.tsx`, `carousel.tsx`, `chart.tsx`
- `checkbox.tsx`, `collapsible.tsx`, `command.tsx`, `context-menu.tsx`
- `dialog.tsx`, `drawer.tsx`, `dropdown-menu.tsx`, `form.tsx`
- `hover-card.tsx`, `input-otp.tsx`, `input.tsx`, `label.tsx`
- `menubar.tsx`, `navigation-menu.tsx`, `pagination.tsx`, `popover.tsx`
- `progress.tsx`, `radio-group.tsx`, `resizable.tsx`, `scroll-area.tsx`
- `select.tsx`, `separator.tsx`, `sheet.tsx`, `sidebar.tsx`
- `skeleton.tsx`, `slider.tsx`, `sonner.tsx`, `switch.tsx`
- `table.tsx`, `tabs.tsx`, `textarea.tsx`, `toast.tsx`, `toaster.tsx`
- `toggle-group.tsx`, `toggle.tsx`, `tooltip.tsx`
- `collapsible-page-header.tsx` - Auto-hide header on scroll
- `compact-page-header.tsx` - Manual compact header toggle
- `use-toast.ts` (hook)

### Dashboard Components (`src/components/dashboard/`)
- `DashboardHeader.tsx` - Top navigation bar
- `DashboardSidebar.tsx` - Side navigation menu
- `MetricsCards.tsx` - KPI metric cards
- `AnalyticsChart.tsx` - Data visualization charts
- `DataTable.tsx` - Data tables with sorting/filtering

### Editor Components (`src/components/editor/`)
- `CodeEditor.tsx` - Code editing interface
- `FileTree.tsx` - File/folder navigation
- `GitDiffViewer.tsx` - View code diffs

### Project Components (`src/components/project/`)
- `AIEditorTab.tsx` - AI-assisted code editing tab
- `ContainerLogsTab.tsx` - Container log viewer with tail control and auto-refresh
- `FileManagerTab.tsx` - File system operations tab
- `IssuesTab.tsx` - Issue tracking and discussion system
- `ProjectCreationWizard.tsx` - Wizard for creating new projects
- `ProjectDetailsTab.tsx` - Project configuration tab
- `PullRequestsTab.tsx` - Pull request management and code review
- `RepositoryGitTab.tsx` - Git operations and version control tab
- `SafetyComplianceTab.tsx` - Safety and compliance settings tab
- `WebtopTab.tsx` - Webtop workspace viewer with lifecycle controls
- `WorkflowTab.tsx` - Visual workflow builder with ReactFlow integration
- `WorkspaceOrchestration.tsx` - Workspace service orchestration interface

### Project Creation Components (`src/components/project/creation/`)
- `AIPlanningChat.tsx` - AI-assisted project planning chat interface
- `BlankProjectForm.tsx` - Form for creating blank projects
- `CloneRepositoryForm.tsx` - Form for cloning repositories
- `TemplateSelector.tsx` - Template selection for new projects

### Chatbot Components (`src/components/chatbot/`)
- `ChatHistory.tsx` - Conversation history display
- `ChatInterface.tsx` - Main chat UI
- `EditTemplateDialog.tsx` - Template editing dialog
- `ModelSettings.tsx` - AI model configuration settings
- `PersonaSelector.tsx` - Chatbot persona selection
- `PersonaSettingsModal.tsx` - Persona configuration modal
- `TemplateManager.tsx` - Prompt template management
- `TemplateVariableDialog.tsx` - Template variable configuration

### Other Components (`src/components/`)
- `AuthGuard.tsx` - Route protection component for authentication
- `CreateWorkflowDialog.tsx` - Dialog for creating new workflows

[Back to Index](./index.md)
