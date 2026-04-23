from rest_framework import serializers
from .models import User, Team, Organization, OrganizationMembership, Project, Environment, App, Deployment, ProjectTemplate, ChangeRequest, Approval, ComplianceCheck, ComplianceTemplate, ProjectAssignment, Discussion, DiscussionReply, MarketplaceItem, MarketplaceCategory, ChatbotPersona, ChatbotTemplate, ChatSession, ChatMessage, Issue, IssueReply, Workflow, WorkflowExecution, LLMProvider
from .models import ProjectPod, ProjectService, ProjectTool, ToolExecution, WorkspaceResourceTier

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'bio', 'avatar', 'teams', 'email_notifications', 'dark_mode', 'default_llm_model']
        read_only_fields = ['id', 'username', 'role', 'teams']  # Users can't change these directly


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    organization = serializers.PrimaryKeyRelatedField(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(source='organization', queryset=Organization.objects.all(), write_only=True, required=False)
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(source='user', queryset=User.objects.all(), write_only=True, required=False)

    class Meta:
        model = OrganizationMembership
        fields = [
            'id',
            'organization',
            'organization_id',
            'organization_name',
            'user',
            'user_id',
            'role',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'organization_name', 'user', 'created_at', 'updated_at']


class OrganizationSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    memberships = OrganizationMembershipSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()
    project_count = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'owner',
            'memberships',
            'member_count',
            'project_count',
            'user_role',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'owner', 'memberships', 'member_count', 'project_count', 'user_role', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_project_count(self, obj):
        return obj.projects.count()

    def get_user_role(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        membership = obj.memberships.filter(user=request.user).first()
        if membership:
            return membership.role
        if obj.owner_id == request.user.id:
            return 'owner'
        return None

class TeamSerializer(serializers.ModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(source='organization', queryset=Organization.objects.all(), write_only=True, required=False, allow_null=True)
    members = UserSerializer(many=True, read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = ['id', 'name', 'description', 'organization', 'organization_id', 'members', 'member_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        return obj.members.count()

class ProjectSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    contributors = UserSerializer(many=True, read_only=True)
    team = TeamSerializer(read_only=True)
    organization = OrganizationSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(source='organization', queryset=Organization.objects.all(), write_only=True, required=False, allow_null=True)

    class Meta:
        model = Project
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'provisioning_status']

    def to_representation(self, instance):
        """Customize output to include full owner details"""
        data = super().to_representation(instance)
        data['owner'] = UserSerializer(instance.owner).data
        return data


class EnvironmentSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(source='project', queryset=Project.objects.all(), write_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    organization_id = serializers.IntegerField(source='project.organization_id', read_only=True)
    created_by = UserSerializer(read_only=True)
    app_count = serializers.SerializerMethodField()

    class Meta:
        model = Environment
        fields = [
            'id',
            'project',
            'project_id',
            'project_name',
            'organization_id',
            'name',
            'slug',
            'description',
            'environment_type',
            'workspace_image',
            'workspace_size',
            'workspace_mode',
            'domain',
            'is_primary',
            'created_by',
            'app_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'project', 'project_name', 'organization_id', 'created_by', 'app_count', 'created_at', 'updated_at']

    def get_app_count(self, obj):
        return obj.apps.count()


class AppSerializer(serializers.ModelSerializer):
    environment = serializers.PrimaryKeyRelatedField(read_only=True)
    environment_id = serializers.PrimaryKeyRelatedField(source='environment', queryset=Environment.objects.all(), write_only=True)
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    project_id = serializers.IntegerField(source='environment.project_id', read_only=True)
    created_by = UserSerializer(read_only=True)
    service_count = serializers.SerializerMethodField()
    latest_deployment = serializers.SerializerMethodField()

    class Meta:
        model = App
        fields = [
            'id',
            'environment',
            'environment_id',
            'environment_name',
            'project_id',
            'name',
            'slug',
            'description',
            'source_type',
            'repository_url',
            'compose_path',
            'status',
            'config',
            'created_by',
            'service_count',
            'latest_deployment',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'environment', 'environment_name', 'project_id', 'created_by', 'service_count', 'latest_deployment', 'created_at', 'updated_at']

    def get_service_count(self, obj):
        return obj.services.count()

    def get_latest_deployment(self, obj):
        latest = obj.deployments.order_by('-created_at').first()
        if not latest:
            return None
        return {
            'id': latest.id,
            'version': latest.version,
            'status': latest.status,
            'created_at': latest.created_at,
        }


class DeploymentSerializer(serializers.ModelSerializer):
    environment = serializers.PrimaryKeyRelatedField(read_only=True)
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    app = serializers.PrimaryKeyRelatedField(read_only=True)
    app_id = serializers.PrimaryKeyRelatedField(source='app', queryset=App.objects.all(), write_only=True)
    app_name = serializers.CharField(source='app.name', read_only=True)
    deployed_by = UserSerializer(read_only=True)
    rollback_of = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Deployment
        fields = [
            'id',
            'environment',
            'environment_name',
            'app',
            'app_id',
            'app_name',
            'version',
            'status',
            'trigger_type',
            'deployed_by',
            'source_ref',
            'compose_path',
            'notes',
            'config_snapshot',
            'service_snapshot',
            'rollback_of',
            'started_at',
            'completed_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'environment', 'environment_name', 'app', 'app_name', 'deployed_by', 'rollback_of', 'created_at', 'updated_at']


class ProjectServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectService
        fields = '__all__'
        read_only_fields = ['id', 'pod', 'created_at', 'updated_at']
        extra_kwargs = {
            'container_name': {'required': False, 'allow_blank': True},
        }


class ProjectPodSerializer(serializers.ModelSerializer):
    services = ProjectServiceSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectPod
        fields = ['id', 'project', 'environment', 'pod_name', 'status', 'config', 'last_synced_at', 'created_at', 'updated_at', 'services']
        read_only_fields = ['id', 'project', 'pod_name', 'created_at', 'updated_at', 'services']


class ProjectToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectTool
        fields = ['id', 'project', 'name', 'slug', 'description', 'entrypoint', 'runtime_image', 'args_schema', 'environment', 'timeout_seconds', 'is_active', 'workspace_tool', 'created_by', 'created_at', 'updated_at']
        read_only_fields = ['id', 'slug', 'created_by', 'created_at', 'updated_at']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class WorkspaceResourceTierSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = WorkspaceResourceTier
        fields = ['id', 'name', 'slug', 'cpu_limit', 'memory_limit', 'is_default', 'is_active', 'display_name', 'created_by', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def get_display_name(self, obj):
        return f"{obj.name} ({obj.cpu_limit} CPU, {obj.memory_limit} RAM)"

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['created_by'] = request.user
        return super().create(validated_data)


class ToolExecutionSerializer(serializers.ModelSerializer):
    tool = ProjectToolSerializer(read_only=True)

    class Meta:
        model = ToolExecution
        fields = ['id', 'tool', 'session', 'status', 'input_payload', 'output_payload', 'logs', 'exit_code', 'started_at', 'completed_at']
        read_only_fields = ['id', 'status', 'logs', 'exit_code', 'started_at', 'completed_at', 'tool', 'session']

class ProjectTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectTemplate
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

class ApprovalSerializer(serializers.ModelSerializer):
    approver = UserSerializer(read_only=True)

    class Meta:
        model = Approval
        fields = ['id', 'approver', 'approved', 'comments', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class ChangeRequestSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    project = ProjectSerializer(read_only=True)
    approvals = ApprovalSerializer(source='approval_records', many=True, read_only=True)
    approval_count = serializers.SerializerMethodField()
    is_approved = serializers.SerializerMethodField()

    class Meta:
        model = ChangeRequest
        fields = ['id', 'title', 'description', 'project', 'author', 'status', 'change_type', 'diff_summary', 'approvals_required', 'approvals', 'approval_count', 'is_approved', 'target_branch', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_approval_count(self, obj):
        return obj.approval_records.filter(approved=True).count()

    def get_is_approved(self, obj):
        return obj.approval_records.filter(approved=True).count() >= obj.approvals_required

class ComplianceCheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceCheck
        fields = '__all__'

class ComplianceTemplateSerializer(serializers.ModelSerializer):
    checks = ComplianceCheckSerializer(many=True, read_only=True)
    projects_using_count = serializers.SerializerMethodField()

    class Meta:
        model = ComplianceTemplate
        fields = '__all__'

    def get_projects_using_count(self, obj):
        return obj.projectassignment_set.count()

class ProjectAssignmentSerializer(serializers.ModelSerializer):
    project = ProjectSerializer(read_only=True)
    template = ComplianceTemplateSerializer(read_only=True)

    class Meta:
        model = ProjectAssignment
        fields = '__all__'


class DiscussionSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = Discussion
        fields = '__all__'


class DiscussionReplySerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    discussion = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = DiscussionReply
        fields = '__all__'


class MarketplaceItemSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)

    class Meta:
        model = MarketplaceItem
        fields = '__all__'


# Chatbot Serializers
class ChatbotPersonaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatbotPersona
        fields = '__all__'


class ChatbotTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatbotTemplate
        fields = '__all__'


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = '__all__'


class ChatSessionSerializer(serializers.ModelSerializer):
    persona_name = serializers.CharField(source='persona.name', read_only=True, required=False)
    template_name = serializers.CharField(source='template.name', read_only=True, required=False)
    message_count = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    enabled_tools = ProjectToolSerializer(many=True, read_only=True)
    enabled_tool_ids = serializers.PrimaryKeyRelatedField(
        source='enabled_tools', queryset=ProjectTool.objects.all(), many=True, required=False, write_only=True
    )

    class Meta:
        model = ChatSession
        fields = [
            'id',
            'project',
            'persona',
            'template',
            'title',
            'llm_id',
            'temperature',
            'started_by_persona',
            'subject',
            'is_active',
            'mode',
            'enabled_tools',
            'enabled_tool_ids',
            'created_at',
            'updated_at',
            'persona_name',
            'template_name',
            'message_count',
            'last_message_preview',
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at', 'message_count', 'last_message_preview', 'persona_name', 'template_name', 'enabled_tools']

    def validate_persona(self, value):
        if value is not None:
            # Handle both ID (int) and object cases
            if hasattr(value, 'id'):
                # It's already a ChatbotPersona object
                persona_id = value.id
            else:
                # It's an ID
                persona_id = value

            if not ChatbotPersona.objects.filter(id=persona_id).exists():
                raise serializers.ValidationError("Selected persona does not exist.")
        return value

    def get_message_count(self, obj):
        return obj.messages.count()

    def get_last_message_preview(self, obj):
        last_message = obj.messages.order_by('-created_at').first()
        if not last_message:
            return ''
        content = last_message.content or ''
        return content[:200]

    def validate_template(self, value):
        if value is not None:
            # Handle both ID (int) and object cases
            if hasattr(value, 'id'):
                # It's already a ChatbotTemplate object
                template_id = value.id
            else:
                # It's an ID
                template_id = value
            
            if not ChatbotTemplate.objects.filter(id=template_id).exists():
                raise serializers.ValidationError("Selected template does not exist.")
        return value

    def get_message_count(self, obj):
        return obj.messages.count()

    def get_last_message_preview(self, obj):
        last_message = obj.messages.filter(message_type='user').last()
        if last_message:
            return last_message.content[:100] + ('...' if len(last_message.content) > 100 else '')
        return ''


class MarketplaceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceCategory
        fields = '__all__'


class IssueSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    project = ProjectSerializer(read_only=True)
    assigned_to = UserSerializer(read_only=True)
    replies_count = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = ['id', 'title', 'description', 'project', 'author', 'status', 'category', 'votes', 'views', 'is_bookmarked', 'assigned_to', 'replies_count', 'created_at', 'updated_at', 'last_activity']
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_activity']

    def get_replies_count(self, obj):
        return obj.replies.count()


class IssueReplySerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = IssueReply
        fields = ['id', 'issue', 'author', 'content', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class WorkflowSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    project = ProjectSerializer(read_only=True)

    class Meta:
        model = Workflow
        fields = ['id', 'name', 'description', 'project', 'author', 'status', 'nodes', 'edges', 'settings', 'last_run', 'run_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at', 'author', 'last_run', 'run_count']


class WorkflowExecutionSerializer(serializers.ModelSerializer):
    workflow = WorkflowSerializer(read_only=True)
    triggered_by = UserSerializer(read_only=True)

    class Meta:
        model = WorkflowExecution
        fields = ['id', 'workflow', 'triggered_by', 'status', 'execution_data', 'started_at', 'completed_at', 'error_message']
        read_only_fields = ['id', 'started_at']


class LLMProviderSerializer(serializers.ModelSerializer):
    """Serializer for LLMProvider with API key masking"""
    api_key_masked = serializers.SerializerMethodField()
    scope_label = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    
    # Write-only field for setting API key
    api_key_plain = serializers.CharField(write_only=True, required=False, allow_blank=True)
    
    class Meta:
        model = LLMProvider
        fields = [
            'id', 'scope', 'scope_team', 'scope_project', 'scope_user',
            'provider_type', 'instance_name', 'api_key_masked', 'api_key_plain',
            'base_url', 'available_models', 'pricing_data', 'last_discovery',
            'supports_function_calling', 'is_active', 'created_by', 'created_by_username', 'created_at', 'updated_at',
            'scope_label'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'last_discovery', 'api_key_masked', 'scope_label']
        extra_kwargs = {
            'api_key': {'write_only': True},  # Never expose encrypted key
        }
    
    def get_api_key_masked(self, obj):
        """Return masked API key (show last 4 characters)"""
        if not obj.api_key:
            return None
        try:
            plain_key = obj.get_api_key()
            if len(plain_key) > 4:
                return '*' * (len(plain_key) - 4) + plain_key[-4:]
            return '****'
        except Exception:
            return '****'
    
    def get_scope_label(self, obj):
        """Return human-readable scope label"""
        return obj.get_scope_label()
    
    def create(self, validated_data):
        """Handle API key encryption on create"""
        api_key_plain = validated_data.pop('api_key_plain', None)
        instance = super().create(validated_data)
        
        if api_key_plain:
            instance.set_api_key(api_key_plain)
            instance.save()
        
        return instance
    
    def update(self, instance, validated_data):
        """Handle API key encryption on update"""
        api_key_plain = validated_data.pop('api_key_plain', None)
        instance = super().update(instance, validated_data)
        
        if api_key_plain:
            instance.set_api_key(api_key_plain)
            instance.save()
        
        return instance
    
    def validate(self, data):
        """Validate scope consistency and required fields"""
        scope = data.get('scope', getattr(self.instance, 'scope', None))
        
        # For updates, check existing instance values if not in data
        scope_team = data.get('scope_team', getattr(self.instance, 'scope_team', None))
        scope_project = data.get('scope_project', getattr(self.instance, 'scope_project', None))
        scope_user = data.get('scope_user', getattr(self.instance, 'scope_user', None))
        
        if scope == 'team' and not scope_team:
            raise serializers.ValidationError("Team-scoped provider must have scope_team set")
        if scope == 'project' and not scope_project:
            raise serializers.ValidationError("Project-scoped provider must have scope_project set")
        if scope == 'user' and not scope_user:
            raise serializers.ValidationError("User-scoped provider must have scope_user set")
        if scope == 'system' and (scope_team or scope_project or scope_user):
            raise serializers.ValidationError("System-scoped provider cannot have scope_team, scope_project, or scope_user set")
        
        # Validate base_url is provided
        base_url = data.get('base_url', getattr(self.instance, 'base_url', None))
        if not base_url:
            raise serializers.ValidationError("base_url is required")
        
        return data