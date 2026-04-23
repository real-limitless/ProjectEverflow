from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify
from django.conf import settings

class User(AbstractUser):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('contributor', 'Contributor'),
        ('admin', 'Administrator'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='contributor')
    teams = models.ManyToManyField('Team', related_name='member_users', blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    email_notifications = models.BooleanField(default=True)
    dark_mode = models.BooleanField(default=False)
    default_llm_model = models.CharField(max_length=500, blank=True, null=True, help_text='Default LLM model for this user (e.g., openai/gpt-4, anthropic/claude-3)')

class Team(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    organization = models.ForeignKey('Organization', on_delete=models.SET_NULL, related_name='teams', null=True, blank=True)
    members = models.ManyToManyField(User, related_name='user_teams', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Organization(models.Model):
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_organizations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        base_slug = slugify(self.slug or self.name) or 'organization'
        slug = base_slug
        index = 1
        while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            index += 1
            slug = f"{base_slug}-{index}"
        self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Administrator'),
        ('member', 'Member'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organization_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'user')
        ordering = ['organization__name', 'user__username']

    def __str__(self):
        return f"{self.user.username} in {self.organization.name} ({self.role})"

class Project(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_development', 'In Development'),
        ('awaiting_approval', 'Awaiting Approval'),
        ('published', 'Published'),
    ]
    WORKSPACE_IMAGE_CHOICES = [
        ('fedora:43', 'Fedora 43'),
        ('registry.access.redhat.com/ubi9/ubi', 'UBI 9'),
    ]
    WORKSPACE_MODE_CHOICES = [
        ('personal', 'Personal'),
        ('shared', 'Shared'),
    ]
    CREATION_METHOD_CHOICES = [
        ('blank', 'Blank Project'),
        ('clone', 'Clone Repository'),
        ('chat', 'AI-Assisted Planning'),
        ('template', 'Use Template'),
    ]
    PROVISIONING_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    system_prompt = models.TextField(blank=True, help_text="Custom system prompt for AI assistant in this project")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects')
    contributors = models.ManyToManyField(User, related_name='contributed_projects', blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='projects', null=True, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, related_name='projects', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    progress = models.IntegerField(default=0)  # 0-100
    
    # Workspace configuration
    workspace_image = models.CharField(max_length=100, choices=WORKSPACE_IMAGE_CHOICES, default='fedora:43', help_text="Container image for AI workspace")
    workspace_size = models.CharField(max_length=20, default='standard', help_text="Resource tier for workspace container")
    workspace_mode = models.CharField(max_length=20, choices=WORKSPACE_MODE_CHOICES, default='personal', help_text="Personal or shared workspace mode")
    
    # Project initialization
    creation_method = models.CharField(max_length=20, choices=CREATION_METHOD_CHOICES, default='blank', help_text="How this project was created")
    git_repo_url = models.CharField(max_length=500, blank=True, help_text="Git repository URL for cloned projects")
    branch = models.CharField(max_length=255, blank=True, default='main', help_text="Git branch name for cloned projects")
    template = models.ForeignKey('ProjectTemplate', on_delete=models.SET_NULL, null=True, blank=True, related_name='projects_using')
    provisioning_status = models.CharField(max_length=20, choices=PROVISIONING_STATUS_CHOICES, default='pending', help_text="Status of workspace provisioning")
    
    # Logging configuration
    log_retention_days = models.IntegerField(default=30, help_text="Number of days to retain provisioning logs (0 = keep forever)")
    
    # Agent framework configuration
    agent_framework = models.CharField(max_length=50, choices=[('langgraph', 'LangGraph')], default='langgraph', help_text="Agent framework for AI chat in this project")
    allowed_commands = models.JSONField(default=list, help_text="List of allowed shell commands for workspace tools")
    command_timeout = models.IntegerField(default=60, help_text="Timeout in seconds for tool command execution")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Environment(models.Model):
    TYPE_CHOICES = [
        ('production', 'Production'),
        ('development', 'Development'),
        ('staging', 'Staging'),
        ('demo', 'Demo'),
        ('custom', 'Custom'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='environments')
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    environment_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='development')
    workspace_image = models.CharField(max_length=100, choices=Project.WORKSPACE_IMAGE_CHOICES, default='fedora:43')
    workspace_size = models.CharField(max_length=20, default='standard')
    workspace_mode = models.CharField(max_length=20, choices=Project.WORKSPACE_MODE_CHOICES, default='shared')
    domain = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_environments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('project', 'slug')
        ordering = ['project__name', 'name']

    def save(self, *args, **kwargs):
        base_slug = slugify(self.slug or self.name) or 'environment'
        slug = base_slug
        index = 1
        while Environment.objects.filter(project=self.project, slug=slug).exclude(pk=self.pk).exists():
            index += 1
            slug = f"{base_slug}-{index}"
        self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project.name} / {self.name}"


class App(models.Model):
    SOURCE_CHOICES = [
        ('compose', 'Compose'),
        ('container', 'Container Image'),
        ('repository', 'Repository'),
        ('custom', 'Custom'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name='apps')
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='compose')
    repository_url = models.CharField(max_length=500, blank=True)
    compose_path = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    config = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_apps')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('environment', 'slug')
        ordering = ['environment__name', 'name']

    def save(self, *args, **kwargs):
        base_slug = slugify(self.slug or self.name) or 'app'
        slug = base_slug
        index = 1
        while App.objects.filter(environment=self.environment, slug=slug).exclude(pk=self.pk).exists():
            index += 1
            slug = f"{base_slug}-{index}"
        self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.environment.name} / {self.name}"


class WorkspaceResourceTier(models.Model):
    """Admin-managed resource tiers for workspace containers (t-shirt sizing)"""
    name = models.CharField(max_length=100, help_text="Display name (e.g., 'Light', 'Standard', 'Heavy')")
    slug = models.SlugField(max_length=100, unique=True, help_text="Unique identifier for API usage")
    cpu_limit = models.CharField(max_length=20, help_text="CPU limit (e.g., '1.0', '2.0', '4.0')")
    memory_limit = models.CharField(max_length=20, help_text="Memory limit (e.g., '2g', '4g', '8g')")
    is_default = models.BooleanField(default=False, help_text="Set as default tier for new projects")
    is_active = models.BooleanField(default=True, help_text="Available for selection")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_tiers')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['cpu_limit', 'memory_limit']
        verbose_name = "Workspace Resource Tier"
        verbose_name_plural = "Workspace Resource Tiers"

    def save(self, *args, **kwargs):
        # Ensure only one default tier
        if self.is_default:
            WorkspaceResourceTier.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.cpu_limit} CPU, {self.memory_limit} RAM)"


class ProjectPod(models.Model):
    STATUS_CHOICES = [
        ('creating', 'Creating'),
        ('running', 'Running'),
        ('stopped', 'Stopped'),
        ('error', 'Error'),
    ]

    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='pod')
    environment = models.ForeignKey(Environment, on_delete=models.SET_NULL, related_name='pods', null=True, blank=True)
    pod_name = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='creating')
    config = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pod for {self.project.name}"


class ProjectService(models.Model):
    SERVICE_CHOICES = [
        ('backend', 'Backend Service'),
        ('frontend', 'Frontend Service'),
        ('tooling', 'Tool Runner'),
        ('ai-workspace', 'AI Workspace'),
        ('custom', 'Custom Service'),
    ]

    pod = models.ForeignKey(ProjectPod, on_delete=models.CASCADE, related_name='services')
    app = models.ForeignKey(App, on_delete=models.SET_NULL, related_name='services', null=True, blank=True)
    name = models.CharField(max_length=255)
    service_type = models.CharField(max_length=20, choices=SERVICE_CHOICES, default='custom')
    image = models.CharField(max_length=255)
    container_name = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=50, default='stopped')
    ports = models.JSONField(default=list, blank=True)
    environment = models.JSONField(default=dict, blank=True)
    config = models.JSONField(default=dict, blank=True, help_text="Service-specific configuration like image_digest, resource_limits, etc.")
    autostart = models.BooleanField(default=False, help_text="Auto-start this service when workspace starts")
    cpu_limit = models.CharField(max_length=20, blank=True, null=True, help_text="CPU limit (e.g., '1.5' or '2')")
    memory_limit = models.CharField(max_length=20, blank=True, null=True, help_text="Memory limit (e.g., '512M' or '2G')")
    last_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('pod', 'name')

    def __str__(self):
        return f"{self.name} ({self.pod.project.name})"


class Deployment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('rolled_back', 'Rolled Back'),
    ]
    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('push', 'On Push'),
        ('rollback', 'Rollback'),
    ]

    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name='deployments')
    app = models.ForeignKey(App, on_delete=models.CASCADE, related_name='deployments')
    version = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')
    deployed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='deployments')
    source_ref = models.CharField(max_length=255, blank=True)
    compose_path = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)
    config_snapshot = models.JSONField(default=dict, blank=True)
    service_snapshot = models.JSONField(default=dict, blank=True)
    rollback_of = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='rollback_deployments')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.app.name} {self.version} ({self.status})"


class ProvisioningLog(models.Model):
    """Tracks step-by-step provisioning logs for project creation and container setup."""
    LEVEL_CHOICES = [
        ('debug', 'Debug'),
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='provisioning_logs')
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default='info')
    step_name = models.CharField(max_length=100, blank=True, help_text="Step identifier (e.g., 'clone_repo', 'provision_services')")
    message = models.TextField(help_text="Human-readable log message")
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional structured data (service names, errors, etc.)")

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['project', 'timestamp']),
            models.Index(fields=['project', 'level']),
        ]

    def __str__(self):
        return f"[{self.level.upper()}] {self.project.name}: {self.message[:50]}"


class ProjectTool(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tools')
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    entrypoint = models.CharField(max_length=500, help_text="Command to run inside the tool container")
    runtime_image = models.CharField(max_length=255, blank=True, help_text="Container image to run the tool in")
    args_schema = models.JSONField(default=dict, blank=True)
    environment = models.JSONField(default=dict, blank=True)
    timeout_seconds = models.IntegerField(default=300)
    is_active = models.BooleanField(default=True)
    workspace_tool = models.BooleanField(default=False, help_text="Execute in workspace container via podman exec")
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='created_tools')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('project', 'slug')
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            index = 1
            while ProjectTool.objects.filter(project=self.project, slug=slug).exclude(pk=self.pk).exists():
                index += 1
                slug = f"{base_slug}-{index}"
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.project.name})"


class ToolExecution(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
    ]

    tool = models.ForeignKey(ProjectTool, on_delete=models.CASCADE, related_name='executions')
    session = models.ForeignKey('ChatSession', on_delete=models.SET_NULL, null=True, blank=True, related_name='tool_executions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    input_payload = models.JSONField(default=dict, blank=True)
    output_payload = models.JSONField(default=dict, blank=True)
    logs = models.TextField(blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Execution of {self.tool.name} ({self.status})"

class ProjectTemplate(models.Model):
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=100)
    framework = models.CharField(max_length=100)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='intermediate')
    tags = models.JSONField(default=list, blank=True)  # List of tags
    file_structure = models.JSONField(default=dict, blank=True, help_text="Template file structure: {files: {path: {content, executable}}, directories: []}")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class LLMProvider(models.Model):
    """Multi-level LLM provider configuration with encrypted API keys for cost allocation"""
    SCOPE_CHOICES = [
        ('system', 'System-wide'),
        ('team', 'Team-level'),
        ('project', 'Project-level'),
        ('user', 'User-level'),
    ]
    
    PROVIDER_TYPE_CHOICES = [
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic'),
        ('openrouter', 'OpenRouter'),
        ('ollama', 'Ollama'),
        ('vllm', 'vLLM'),
        ('litemaas', 'LiteMaaS'),
        ('custom', 'Custom Provider'),
    ]
    
    # Scope configuration
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, help_text="Configuration level: system, team, project, or user")
    scope_team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True, related_name='llm_providers', help_text="Team for team-scoped providers")
    scope_project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='llm_providers', help_text="Project for project-scoped providers")
    scope_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='llm_providers', help_text="User for user-scoped providers")
    
    # Provider configuration
    provider_type = models.CharField(max_length=50, choices=PROVIDER_TYPE_CHOICES, help_text="Type of LLM provider")
    instance_name = models.CharField(max_length=200, help_text="User-friendly name for this provider instance (e.g., 'My OpenRouter', 'Team vLLM')")
    api_key = models.TextField(blank=True, help_text="Encrypted API key for the provider (encrypted via Fernet)")
    base_url = models.URLField(max_length=500, blank=True, null=True, help_text="Custom base URL for API endpoint (for vLLM, custom providers)")
    
    # Model discovery and pricing
    available_models = models.JSONField(default=list, blank=True, help_text="Cached list of available models with pricing: [{id, name, pricing: {prompt, completion}, context_length}]")
    pricing_data = models.JSONField(default=dict, blank=True, help_text="Additional provider-level pricing configuration")
    last_discovery = models.DateTimeField(null=True, blank=True, help_text="Last time models were discovered from provider API")
    
    # Function calling support
    supports_function_calling = models.BooleanField(default=False, help_text="Whether this provider supports native function/tool calling")
    
    # Status and metadata
    is_active = models.BooleanField(default=True, help_text="Whether this provider is available for use")
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_llm_providers', help_text="Admin who created this provider")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['scope', 'instance_name']
        indexes = [
            models.Index(fields=['scope', 'is_active']),
            models.Index(fields=['scope_team', 'is_active']),
            models.Index(fields=['scope_project', 'is_active']),
            models.Index(fields=['scope_user', 'is_active']),
        ]
    
    def __str__(self):
        scope_label = self.get_scope_label()
        return f"[{scope_label}] {self.instance_name} ({self.provider_type})"
    
    def get_scope_label(self):
        """Return human-readable scope label"""
        if self.scope == 'system':
            return 'System'
        elif self.scope == 'team' and self.scope_team:
            return f'Team: {self.scope_team.name}'
        elif self.scope == 'project' and self.scope_project:
            return f'Project: {self.scope_project.name}'
        elif self.scope == 'user' and self.scope_user:
            return f'User: {self.scope_user.username}'
        return self.scope
    
    def set_api_key(self, plain_key: str):
        """Encrypt and store API key"""
        from cryptography.fernet import Fernet
        if not settings.FIELD_ENCRYPTION_KEY:
            raise ValueError("FIELD_ENCRYPTION_KEY not configured")
        cipher = Fernet(settings.FIELD_ENCRYPTION_KEY.encode())
        self.api_key = cipher.encrypt(plain_key.encode()).decode()
    
    def get_api_key(self) -> str:
        """Decrypt and return API key"""
        from cryptography.fernet import Fernet, InvalidToken
        if not self.api_key:
            return ''
        if not settings.FIELD_ENCRYPTION_KEY:
            raise ValueError("FIELD_ENCRYPTION_KEY not configured")
        
        try:
            cipher = Fernet(settings.FIELD_ENCRYPTION_KEY.encode())
            return cipher.decrypt(self.api_key.encode()).decode()
        except InvalidToken:
            # Encryption key changed - API key needs to be re-saved
            raise ValueError(
                f"Failed to decrypt API key for provider '{self.instance_name}'. "
                "The encryption key may have changed. Please re-enter your API key in Settings."
            )

    def clean(self):
        """Validate that scope matches scope_* field"""
        from django.core.exceptions import ValidationError
        if self.scope == 'team' and not self.scope_team:
            raise ValidationError("Team-scoped provider must have scope_team set")
        if self.scope == 'project' and not self.scope_project:
            raise ValidationError("Project-scoped provider must have scope_project set")
        if self.scope == 'user' and not self.scope_user:
            raise ValidationError("User-scoped provider must have scope_user set")
        if self.scope == 'system' and (self.scope_team or self.scope_project or self.scope_user):
            raise ValidationError("System-scoped provider cannot have scope_team, scope_project, or scope_user set")


class ChangeRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('changes_requested', 'Changes Requested'),
        ('rejected', 'Rejected'),
    ]
    CHANGE_TYPE_CHOICES = [
        ('feature', 'Feature'),
        ('bug_fix', 'Bug Fix'),
        ('enhancement', 'Enhancement'),
        ('documentation', 'Documentation'),
        ('refactor', 'Refactor'),
        ('other', 'Other'),
    ]
    title = models.CharField(max_length=255)
    description = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='change_requests')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='authored_requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES, default='feature')
    diff_summary = models.JSONField(blank=True, null=True)  # e.g., {'files_changed': 5, 'lines_added': 100, 'lines_removed': 20}
    approvals_required = models.IntegerField(default=3)  # Number of approvals needed
    target_branch = models.CharField(max_length=255, default='main')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.project.name}"

class Approval(models.Model):
    change_request = models.ForeignKey(ChangeRequest, on_delete=models.CASCADE, related_name='approval_records')
    approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_approvals')
    approved = models.BooleanField(default=False)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['change_request', 'approver']

    def __str__(self):
        return f"{self.approver.username} - {self.change_request.title} ({'Approved' if self.approved else 'Pending'})"

class ComplianceCheck(models.Model):
    CATEGORY_CHOICES = [
        ('security', 'Security'),
        ('code_quality', 'Code Quality'),
        ('performance', 'Performance'),
        ('compliance', 'Compliance'),
        ('custom', 'Custom'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    name = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    ai_prompt = models.TextField()  # Instructions for AI validation
    is_active = models.BooleanField(default=True)

class ComplianceTemplate(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    checks = models.ManyToManyField(ComplianceCheck, related_name='templates')
    is_active = models.BooleanField(default=True)

class ProjectAssignment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    template = models.ForeignKey(ComplianceTemplate, on_delete=models.CASCADE, blank=True, null=True)
    custom_checks = models.ManyToManyField(ComplianceCheck, blank=True)
    last_run = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, default='not_run')  # e.g., 'pass', 'fail'
    violations = models.IntegerField(default=0)


class Discussion(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='discussions')
    category = models.CharField(max_length=100, default='General')
    replies = models.IntegerField(default=0)
    views = models.IntegerField(default=0)
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-last_activity']

    def __str__(self):
        return self.title


class DiscussionReply(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='discussion_replies')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='discussion_replies')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.author.username} on {self.discussion.title}"


class MarketplaceItem(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    emoji = models.CharField(max_length=10, blank=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marketplace_items')
    category = models.CharField(max_length=50)
    likes = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default='available')  # available, deprecated, etc.
    gradient = models.CharField(max_length=200, blank=True)  # CSS gradient for UI
    tags = models.JSONField(default=list, blank=True)  # List of tags
    demo_url = models.URLField(blank=True)
    documentation_url = models.URLField(blank=True)
    is_featured = models.BooleanField(default=False)
    downloads = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_featured', '-likes', '-created_at']

    def __str__(self):
        return self.name


class MarketplaceCategory(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.label


# Chatbot Models
class ChatbotPersona(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=50, default='User')
    category = models.CharField(max_length=50, default='General')
    system_prompt = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    # Default LLM settings
    default_llm_id = models.CharField(max_length=100, null=True, blank=True)
    default_temperature = models.FloatField(default=0.7)
    default_max_tokens = models.IntegerField(default=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ChatbotTemplate(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    system_prompt = models.TextField()
    user_prompt_template = models.TextField()
    variables = models.JSONField(default=list)  # List of variable definitions
    category = models.CharField(max_length=50, default='General')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ChatSession(models.Model):
    MODE_CHOICES = [
        ('ask', 'Ask'),
        ('plan', 'Plan'),
        ('agent', 'Agent'),
        ('persona', 'Persona'),
        ('deep', 'Deep'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='chat_sessions', null=True, blank=True)
    persona = models.ForeignKey(ChatbotPersona, on_delete=models.SET_NULL, null=True, blank=True)
    template = models.ForeignKey(ChatbotTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=200)
    
    # LLM configuration - updated to use provider system
    provider = models.ForeignKey(LLMProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name='chat_sessions', help_text="Selected LLM provider for this session")
    selected_model = models.CharField(max_length=200, blank=True, help_text="Model ID from the provider (e.g., 'openai/gpt-4', 'anthropic/claude-3-opus')")
    llm_id = models.CharField(max_length=100, null=True, blank=True, help_text="DEPRECATED: Legacy LLM ID, migrating to provider system")
    
    temperature = models.FloatField(default=0.7, help_text="Temperature for LLM generation (0.0 to 2.0)")
    started_by_persona = models.BooleanField(default=False, help_text="Whether this session was started by selecting a persona")
    subject = models.CharField(max_length=255, blank=True, null=True, help_text="Brief summary of the conversation")
    is_active = models.BooleanField(default=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='ask')
    enabled_tools = models.ManyToManyField(ProjectTool, related_name='chat_sessions', blank=True)
    agent_iterations = models.IntegerField(default=0, help_text="Number of agent loop iterations in this session")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username}: {self.title}"


class ChatMessage(models.Model):
    MESSAGE_TYPES = [
        ('user', 'User Message'),
        ('assistant', 'Assistant Message'),
        ('system', 'System Message'),
    ]

    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default='user')
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)  # Store additional data like tokens used, etc.
    
    # Cost tracking and billing
    used_by_provider = models.ForeignKey(LLMProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name='chat_messages', help_text="Provider used for this message (for cost allocation)")
    prompt_tokens = models.IntegerField(null=True, blank=True, help_text="Number of tokens in the prompt")
    completion_tokens = models.IntegerField(null=True, blank=True, help_text="Number of tokens in the completion")
    total_tokens = models.IntegerField(null=True, blank=True, help_text="Total tokens used (prompt + completion)")
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True, help_text="Estimated cost in USD for this message")
    
    # Agent framework fields
    reasoning = models.TextField(blank=True, null=True, help_text="Agent's reasoning/thinking process")
    tool_calls = models.JSONField(default=list, blank=True, help_text="List of tool calls made by agent")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['used_by_provider', 'created_at']),
            models.Index(fields=['session', 'created_at']),
        ]

    def __str__(self):
        return f"{self.session.title}: {self.message_type} - {self.content[:50]}"


class Issue(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    CATEGORY_CHOICES = [
        ('bug', 'Bug'),
        ('feature_request', 'Feature Request'),
        ('question', 'Question'),
        ('enhancement', 'Enhancement'),
        ('documentation', 'Documentation'),
        ('other', 'Other'),
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='issues')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='authored_issues')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    votes = models.IntegerField(default=0)
    views = models.IntegerField(default=0)
    is_bookmarked = models.BooleanField(default=False)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_issues')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_activity']

    def __str__(self):
        return f"{self.title} - {self.project.name}"


class IssueReply(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='issue_replies')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.author.username} on {self.issue.title}"


class Workflow(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('archived', 'Archived'),
    ]
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='workflows')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='authored_workflows')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    nodes = models.JSONField(default=list)  # ReactFlow nodes data
    edges = models.JSONField(default=list)  # ReactFlow edges data
    settings = models.JSONField(default=dict)  # Workflow settings and configuration
    last_run = models.DateTimeField(blank=True, null=True)
    run_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.name} - {self.project.name}"


class WorkflowExecution(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name='executions')
    triggered_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workflow_executions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    execution_data = models.JSONField(default=dict)  # Execution results and logs
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.workflow.name} execution - {self.status}"