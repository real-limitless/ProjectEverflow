from django.contrib import admin
from .models import User, Team, Project, ChangeRequest, Approval, ComplianceCheck, ComplianceTemplate, ProjectAssignment, Discussion, DiscussionReply, MarketplaceItem, MarketplaceCategory, ChatbotPersona, ChatbotTemplate, ChatSession, ChatMessage, Issue, IssueReply, Workflow, WorkflowExecution, ProjectTool, ProjectPod, ProjectService, ToolExecution, LLMProvider

# Register your models here.

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active', 'is_staff', 'teams')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    filter_horizontal = ('teams',)
    readonly_fields = ('date_joined', 'last_login')

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_at', 'member_count')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('name', 'description')
    filter_horizontal = ('members',)
    readonly_fields = ('created_at', 'updated_at')

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = 'Members'

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'team', 'status', 'progress', 'created_at')
    list_filter = ('status', 'team', 'created_at', 'updated_at')
    search_fields = ('name', 'description', 'owner__username')
    filter_horizontal = ('contributors',)
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('status', 'progress')

@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'author', 'status', 'change_type', 'created_at')
    list_filter = ('status', 'change_type', 'created_at', 'project')
    search_fields = ('title', 'description', 'author__username', 'project__name')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Approval)
class ApprovalAdmin(admin.ModelAdmin):
    list_display = ('change_request', 'approver', 'approved', 'created_at')
    list_filter = ('approved', 'created_at', 'updated_at')
    search_fields = ('change_request__title', 'approver__username', 'comments')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(ComplianceCheck)
class ComplianceCheckAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'severity')
    list_filter = ('category', 'severity')
    search_fields = ('name', 'description')

@admin.register(ComplianceTemplate)
class ComplianceTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'check_count')
    search_fields = ('name', 'description')
    filter_horizontal = ('checks',)

    def check_count(self, obj):
        return obj.checks.count()
    check_count.short_description = 'Checks'

@admin.register(ProjectAssignment)
class ProjectAssignmentAdmin(admin.ModelAdmin):
    list_display = ('project', 'template', 'last_run', 'status', 'violations')
    list_filter = ('status', 'last_run')
    search_fields = ('project__name', 'template__name')
    filter_horizontal = ('custom_checks',)

@admin.register(MarketplaceCategory)
class MarketplaceCategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'label', 'icon', 'order')
    list_filter = ('order',)
    search_fields = ('id', 'label', 'description')
    ordering = ('order', 'label')
    list_editable = ('order',)

@admin.register(MarketplaceItem)
class MarketplaceItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'author', 'status', 'likes', 'created_at')
    list_filter = ('status', 'category', 'created_at', 'author')
    search_fields = ('name', 'description', 'author__username', 'author__first_name', 'author__last_name')
    readonly_fields = ('created_at', 'updated_at', 'likes')
    list_editable = ('status',)
    ordering = ('-created_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('author')


@admin.register(ChatbotPersona)
class ChatbotPersonaAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'icon', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'category')
    list_editable = ('is_active',)
    ordering = ('category', 'name')


@admin.register(ChatbotTemplate)
class ChatbotTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'created_at')
    list_filter = ('category', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'category')
    list_editable = ('is_active',)
    ordering = ('category', 'name')


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'persona', 'template', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at', 'persona', 'template')
    search_fields = ('title', 'user__username', 'user__first_name', 'user__last_name')
    readonly_fields = ('created_at', 'updated_at')
    list_editable = ('is_active',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'message_type', 'content_preview', 'created_at')
    list_filter = ('message_type', 'created_at', 'session__user')
    search_fields = ('content', 'session__title', 'session__user__username')
    readonly_fields = ('created_at',)

    def content_preview(self, obj):
        return obj.content[:100] + ('...' if len(obj.content) > 100 else '')
    content_preview.short_description = 'Content Preview'


@admin.register(Discussion)
class DiscussionAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'category', 'replies', 'views', 'is_pinned', 'is_locked', 'created_at')
    list_filter = ('category', 'is_pinned', 'is_locked', 'created_at', 'author')
    search_fields = ('title', 'content', 'author__username', 'author__first_name', 'author__last_name')
    readonly_fields = ('created_at', 'updated_at', 'last_activity', 'replies', 'views')
    list_editable = ('is_pinned', 'is_locked')
    ordering = ('-is_pinned', '-last_activity')


@admin.register(DiscussionReply)
class DiscussionReplyAdmin(admin.ModelAdmin):
    list_display = ('discussion', 'author', 'content_preview', 'created_at')
    list_filter = ('created_at', 'author', 'discussion__category')
    search_fields = ('content', 'author__username', 'discussion__title')
    readonly_fields = ('created_at', 'updated_at')

    def content_preview(self, obj):
        return obj.content[:100] + ('...' if len(obj.content) > 100 else '')
    content_preview.short_description = 'Content Preview'


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'author', 'status', 'category', 'votes', 'views', 'assigned_to', 'created_at')
    list_filter = ('status', 'category', 'created_at', 'project', 'author', 'assigned_to')
    search_fields = ('title', 'description', 'author__username', 'project__name', 'assigned_to__username')
    readonly_fields = ('created_at', 'updated_at', 'last_activity', 'votes', 'views')
    list_editable = ('status', 'assigned_to')
    ordering = ('-last_activity',)


@admin.register(IssueReply)
class IssueReplyAdmin(admin.ModelAdmin):
    list_display = ('issue', 'author', 'content_preview', 'created_at')
    list_filter = ('created_at', 'author', 'issue__project', 'issue__status')
    search_fields = ('content', 'author__username', 'issue__title')
    readonly_fields = ('created_at', 'updated_at')

    def content_preview(self, obj):
        return obj.content[:100] + ('...' if len(obj.content) > 100 else '')
    content_preview.short_description = 'Content Preview'


@admin.register(Workflow)
class WorkflowAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'author', 'status', 'run_count', 'last_run', 'created_at')
    list_filter = ('status', 'created_at', 'project', 'author')
    search_fields = ('name', 'description', 'author__username', 'project__name')
    readonly_fields = ('created_at', 'updated_at', 'run_count', 'last_run')
    list_editable = ('status',)
    ordering = ('-updated_at',)


@admin.register(WorkflowExecution)
class WorkflowExecutionAdmin(admin.ModelAdmin):
    list_display = ('workflow', 'triggered_by', 'status', 'started_at', 'completed_at')
    list_filter = ('status', 'started_at', 'workflow__project', 'triggered_by')
    search_fields = ('workflow__name', 'triggered_by__username', 'error_message')
    readonly_fields = ('started_at', 'completed_at')
    ordering = ('-started_at',)


@admin.register(ProjectTool)
class ProjectToolAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'slug', 'is_active', 'runtime_image', 'timeout_seconds', 'created_at')
    list_filter = ('is_active', 'project')
    search_fields = ('name', 'slug', 'project__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProjectPod)
class ProjectPodAdmin(admin.ModelAdmin):
    list_display = ('project', 'pod_name', 'status', 'last_synced_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('project__name', 'pod_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProjectService)
class ProjectServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'pod', 'service_type', 'status', 'image', 'last_started_at')
    list_filter = ('service_type', 'status')
    search_fields = ('name', 'pod__project__name', 'container_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ToolExecution)
class ToolExecutionAdmin(admin.ModelAdmin):
    list_display = ('tool', 'session', 'status', 'started_at', 'completed_at', 'exit_code')
    list_filter = ('status', 'tool__project')
    search_fields = ('tool__name', 'session__title')
    readonly_fields = ('started_at',)


@admin.register(LLMProvider)
class LLMProviderAdmin(admin.ModelAdmin):
    list_display = ('instance_name', 'provider_type', 'scope', 'get_scope_label', 'is_active', 'last_discovery', 'created_at')
    list_filter = ('scope', 'provider_type', 'is_active', 'created_at')
    search_fields = ('instance_name', 'provider_type')
    readonly_fields = ('created_at', 'updated_at', 'last_discovery')
    fieldsets = (
        ('Scope Configuration', {
            'fields': ('scope', 'scope_team', 'scope_project', 'scope_user')
        }),
        ('Provider Settings', {
            'fields': ('provider_type', 'instance_name', 'api_key', 'base_url')
        }),
        ('Model Discovery', {
            'fields': ('available_models', 'pricing_data', 'last_discovery')
        }),
        ('Status', {
            'fields': ('is_active', 'created_by', 'created_at', 'updated_at')
        }),
    )
    
    def get_scope_label(self, obj):
        return obj.get_scope_label()
    get_scope_label.short_description = 'Scope Details'