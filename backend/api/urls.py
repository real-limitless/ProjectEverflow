from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from .llm_views import LLMConfigViewSet
from .workspace_file_views import WorkspaceFileViewSet
from .git_views import GitViewSet
from .proxy_views import webtop_proxy_view
from .preview_proxy_views import preview_proxy_view
from .service_proxy_views import service_proxy_view
from .subdomain_proxy import service_proxy_auth_view
from . import copilot_proxy_views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'organizations', views.OrganizationViewSet, basename='organizations')
router.register(r'organization-memberships', views.OrganizationMembershipViewSet, basename='organization-memberships')
router.register(r'teams', views.TeamViewSet)
router.register(r'projects', views.ProjectViewSet)
router.register(r'environments', views.EnvironmentViewSet, basename='environments')
router.register(r'apps', views.AppViewSet, basename='apps')
router.register(r'deployments', views.DeploymentViewSet, basename='deployments')
router.register(r'project-templates', views.ProjectTemplateViewSet)
router.register(r'change-requests', views.ChangeRequestViewSet)
router.register(r'compliance-checks', views.ComplianceCheckViewSet)
router.register(r'compliance-templates', views.ComplianceTemplateViewSet)
router.register(r'project-assignments', views.ProjectAssignmentViewSet)
router.register(r'discussions', views.DiscussionViewSet)
router.register(r'discussion-replies', views.DiscussionReplyViewSet)
router.register(r'marketplace-items', views.MarketplaceItemViewSet)
router.register(r'marketplace-categories', views.MarketplaceCategoryViewSet)
router.register(r'chatbot-personas', views.ChatbotPersonaViewSet)
router.register(r'chatbot-templates', views.ChatbotTemplateViewSet)
router.register(r'chat-sessions', views.ChatSessionViewSet)
router.register(r'chat-messages', views.ChatMessageViewSet)
router.register(r'issues', views.IssueViewSet)
router.register(r'issue-replies', views.IssueReplyViewSet)
router.register(r'workflows', views.WorkflowViewSet)
router.register(r'workflow-executions', views.WorkflowExecutionViewSet)
router.register(r'project-pods', views.ProjectPodViewSet, basename='project-pods')
router.register(r'project-services', views.ProjectServiceViewSet, basename='project-services')
router.register(r'project-tools', views.ProjectToolViewSet, basename='project-tools')
router.register(r'tool-executions', views.ToolExecutionViewSet, basename='tool-executions')
router.register(r'workspace-tiers', views.WorkspaceResourceTierViewSet, basename='workspace-tiers')
router.register(r'llm-config', LLMConfigViewSet, basename='llm-config')
router.register(r'llm-providers', views.LLMProviderViewSet, basename='llm-providers')
router.register(r'llm-usage-stats', views.LLMUsageStatsViewSet, basename='llm-usage-stats')

urlpatterns = [
    path('', include(router.urls)),
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('service-proxy-auth/', service_proxy_auth_view, name='service-proxy-auth'),
    re_path(r'^projects/(?P<project_id>\d+)/webtop-proxy/(?P<path>.*)$', webtop_proxy_view, name='webtop-proxy'),
    re_path(r'^projects/(?P<project_id>\d+)/preview-proxy/(?P<path>.*)$', preview_proxy_view, name='preview-proxy'),
    re_path(r'^projects/(?P<project_id>\d+)/service-proxy/(?P<service_id>\d+)/(?P<port>\d+)/(?P<path>.*)$', service_proxy_view, name='service-proxy'),
    # Workspace file system API
    re_path(r'^projects/(?P<project_id>\d+)/workspace/files/tree/$', WorkspaceFileViewSet.as_view({'get': 'get_file_tree'}), name='workspace-files-tree'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/files/git-status/$', WorkspaceFileViewSet.as_view({'get': 'get_git_status'}), name='workspace-files-git-status'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/files/read/(?P<filepath>.+)$', WorkspaceFileViewSet.as_view({'get': 'read_file'}), name='workspace-files-read'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/files/create/$', WorkspaceFileViewSet.as_view({'post': 'create_file'}), name='workspace-files-create'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/files/update/(?P<filepath>.+)$', WorkspaceFileViewSet.as_view({'put': 'update_file'}), name='workspace-files-update'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/files/delete/(?P<filepath>.+)$', WorkspaceFileViewSet.as_view({'delete': 'delete_file'}), name='workspace-files-delete'),
    # File analysis endpoint (quick/deep)
    re_path(r'^projects/(?P<project_id>\d+)/workspace/files/analyze/$', WorkspaceFileViewSet.as_view({'post': 'analyze_file'}), name='workspace-files-analyze'),
    # Git operations API
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/branches/$', GitViewSet.as_view({'get': 'branches'}), name='git-branches'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/commits/$', GitViewSet.as_view({'get': 'commits'}), name='git-commits'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/remote-status/$', GitViewSet.as_view({'get': 'remote_status'}), name='git-remote-status'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/pull/$', GitViewSet.as_view({'post': 'pull'}), name='git-pull'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/push/$', GitViewSet.as_view({'post': 'push'}), name='git-push'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/fetch/$', GitViewSet.as_view({'post': 'fetch'}), name='git-fetch'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/checkout/$', GitViewSet.as_view({'post': 'checkout'}), name='git-checkout'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/commit/$', GitViewSet.as_view({'post': 'commit'}), name='git-commit'),
    re_path(r'^projects/(?P<project_id>\d+)/workspace/git/rebase/$', GitViewSet.as_view({'post': 'rebase'}), name='git-rebase'),
    # Chat streaming endpoint
    re_path(r'^projects/(?P<project_id>\d+)/chat-sessions/(?P<pk>\d+)/stream/$', views.ChatSessionViewSet.as_view({'post': 'stream'}), name='chat-session-stream'),
    # Chat available tools endpoint
    re_path(r'^projects/(?P<project_id>\d+)/chat-sessions/(?P<pk>\d+)/available_tools/$', views.ChatSessionViewSet.as_view({'get': 'available_tools'}), name='chat-session-available-tools'),
    # Copilot Mode proxy endpoints
    re_path(r'^projects/(?P<project_id>\d+)/copilot/health/$', copilot_proxy_views.CopilotProxyView.as_view(), {'endpoint': 'health'}, name='copilot-health'),
    re_path(r'^projects/(?P<project_id>\d+)/copilot/tools/$', copilot_proxy_views.CopilotProxyView.as_view(), {'endpoint': 'tools'}, name='copilot-tools'),
    re_path(r'^projects/(?P<project_id>\d+)/copilot/chat/$', copilot_proxy_views.CopilotProxyView.as_view(), {'endpoint': 'chat'}, name='copilot-chat'),
    re_path(r'^projects/(?P<project_id>\d+)/copilot/chat/stream/$', copilot_proxy_views.CopilotProxyView.as_view(), {'endpoint': 'chat/stream'}, name='copilot-chat-stream'),
]