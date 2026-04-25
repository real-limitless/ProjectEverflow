from django.db import models
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from asgiref.sync import sync_to_async, async_to_sync
import os
import asyncio
import aiohttp
import json
import random
import logging
import threading
from .workspace_initializer import initialize_project_workspace, WorkspaceInitializer
from .deployment_runner import run_deployment
from .llm_config import get_llm_manager
from .podman_orchestrator import PodmanOrchestrator
from .compose_parser import load_compose_from_text, build_service_specs
from .git_connection_discovery import GitProviderDiscoveryError, list_connection_repositories, list_repository_branches, test_connection_credential
from .git_source_normalization import GitRepositoryNormalizationError, normalize_public_git_repository_input
from .source_discovery import SourceDiscoveryError, get_source_discovery_payload
from .models import (
    User,
    Team,
    Organization,
    OrganizationMembership,
    OrganizationGitConnection,
    PersonalGitConnection,
    Project,
    Environment,
    App,
    AppSourceSettings,
    Deployment,
    ProjectTemplate,
    ChangeRequest,
    Approval,
    ComplianceCheck,
    ComplianceTemplate,
    ProjectAssignment,
    Discussion,
    DiscussionReply,
    MarketplaceItem,
    MarketplaceCategory,
    ChatbotPersona,
    ChatbotTemplate,
    ChatSession,
    ChatMessage,
    Issue,
    IssueReply,
    Workflow,
    WorkflowExecution,
    ProjectTool,
    ToolExecution,
    ProjectPod,
    ProjectService,
    WorkspaceResourceTier,
    LLMProvider,
)
from .serializers import (
    UserSerializer,
    TeamSerializer,
    OrganizationSerializer,
    OrganizationMembershipSerializer,
    OrganizationGitConnectionSerializer,
    PersonalGitConnectionSerializer,
    ProjectSerializer,
    EnvironmentSerializer,
    AppSerializer,
    AppSourceSettingsSerializer,
    DeploymentSerializer,
    ProjectTemplateSerializer,
    ChangeRequestSerializer,
    ApprovalSerializer,
    ComplianceCheckSerializer,
    ComplianceTemplateSerializer,
    ProjectAssignmentSerializer,
    DiscussionSerializer,
    DiscussionReplySerializer,
    MarketplaceItemSerializer,
    MarketplaceCategorySerializer,
    ChatbotPersonaSerializer,
    ChatbotTemplateSerializer,
    ChatSessionSerializer,
    ChatMessageSerializer,
    IssueSerializer,
    IssueReplySerializer,
    WorkflowSerializer,
    WorkflowExecutionSerializer,
    ProjectToolSerializer,
    ToolExecutionSerializer,
    ProjectPodSerializer,
    ProjectServiceSerializer,
    WorkspaceResourceTierSerializer,
    LLMProviderSerializer,
)
from .podman_manager import PodmanManager, ToolExecutionError, PodmanError
from .podman_orchestrator import PodmanOrchestrator
from .orchestrator import OrchestratorError, ServiceSpec


ORGANIZATION_ROLE_ORDER = {
    'member': 1,
    'admin': 2,
    'owner': 3,
}


def user_is_global_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or user.role == 'admin'))


def get_accessible_projects_queryset(user):
    if not user or not user.is_authenticated:
        return Project.objects.none()
    if user_is_global_admin(user):
        return Project.objects.all()

    user_teams = Team.objects.filter(members=user)
    return Project.objects.filter(
        models.Q(owner=user) |
        models.Q(contributors=user) |
        models.Q(team__in=user_teams) |
        models.Q(organization__memberships__user=user)
    ).distinct()


def user_has_organization_access(user, organization: Organization, minimum_role: str = 'member') -> bool:
    if not organization:
        return False
    if user_is_global_admin(user):
        return True

    membership = organization.memberships.filter(user=user).first()
    if not membership:
        return False

    return ORGANIZATION_ROLE_ORDER.get(membership.role, 0) >= ORGANIZATION_ROLE_ORDER.get(minimum_role, 0)


def user_can_manage_project(user, project: Project) -> bool:
    if not user or not user.is_authenticated or not project:
        return False
    if user_is_global_admin(user):
        return True

    owner_id = project.owner.id if hasattr(project.owner, 'id') else project.owner_id
    if owner_id == user.id:
        return True
    if project.contributors.filter(id=user.id).exists():
        return True
    if project.team and project.team.members.filter(id=user.id).exists():
        return True
    if project.organization and user_has_organization_access(user, project.organization, minimum_role='admin'):
        return True
    return False


def user_has_project_access(user, project: Project) -> bool:
    if not project:
        return False
    if user_can_manage_project(user, project):
        return True
    if project.organization and user_has_organization_access(user, project.organization):
        return True
    return False


def build_service_container_name(project_id: int, service_name: str) -> str:
    normalized_name = ''.join(
        character.lower() if character.isalnum() else '-'
        for character in (service_name or 'service')
    ).strip('-') or 'service'
    base_name = f"proj-{project_id}-{normalized_name}"[:255]
    container_name = base_name
    suffix = 2

    while ProjectService.objects.filter(container_name=container_name).exists():
        suffix_text = f"-{suffix}"
        container_name = f"{base_name[:255 - len(suffix_text)]}{suffix_text}"
        suffix += 1

    return container_name

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only see their own profile
        return User.objects.filter(id=self.request.user.id)

    def get_object(self):
        # Always return the current user's profile
        return self.request.user

    @action(detail=False, methods=['get', 'patch'])
    def me(self, request):
        """Get or update current user profile"""
        if request.method == 'GET':
            serializer = self.get_serializer(self.get_object())
            return Response(serializer.data)
        elif request.method == 'PATCH':
            serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Organization.objects.select_related('owner').prefetch_related('memberships__user')
        if user_is_global_admin(self.request.user):
            return queryset
        return queryset.filter(
            models.Q(owner=self.request.user) |
            models.Q(memberships__user=self.request.user)
        ).distinct()

    def perform_create(self, serializer):
        if not user_is_global_admin(self.request.user):
            raise PermissionDenied("Only administrators can create organizations")

        organization = serializer.save(owner=self.request.user)
        OrganizationMembership.objects.get_or_create(
            organization=organization,
            user=self.request.user,
            defaults={'role': 'owner'},
        )

    def perform_update(self, serializer):
        organization = self.get_object()
        if not user_has_organization_access(self.request.user, organization, minimum_role='admin'):
            raise PermissionDenied("You do not have permission to manage this organization")
        serializer.save()

    def perform_destroy(self, instance):
        if not user_has_organization_access(self.request.user, instance, minimum_role='owner'):
            raise PermissionDenied("Only organization owners or global administrators can delete organizations")
        instance.delete()

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        organization = self.get_object()
        serializer = OrganizationMembershipSerializer(
            organization.memberships.select_related('user'),
            many=True,
            context={'request': request},
        )
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def projects(self, request, pk=None):
        organization = self.get_object()
        queryset = get_accessible_projects_queryset(request.user).filter(organization=organization)
        serializer = ProjectSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        organization = self.get_object()
        if not user_has_organization_access(request.user, organization, minimum_role='admin'):
            raise PermissionDenied("You do not have permission to manage this organization")

        user_id = request.data.get('user_id')
        role = request.data.get('role', 'member')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        if role not in {'admin', 'member'}:
            return Response({'error': 'role must be one of: admin, member'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            member = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        membership, created = OrganizationMembership.objects.get_or_create(
            organization=organization,
            user=member,
            defaults={'role': role},
        )
        if not created and membership.role != role:
            membership.role = role
            membership.save(update_fields=['role', 'updated_at'])

        serializer = OrganizationMembershipSerializer(membership, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        organization = self.get_object()
        if not user_has_organization_access(request.user, organization, minimum_role='admin'):
            raise PermissionDenied("You do not have permission to manage this organization")

        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        membership = organization.memberships.filter(user_id=user_id).first()
        if not membership:
            return Response({'error': 'Membership not found'}, status=status.HTTP_404_NOT_FOUND)
        if membership.role == 'owner':
            return Response({'error': 'Organization owner cannot be removed'}, status=status.HTTP_400_BAD_REQUEST)

        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizationMembershipViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrganizationMembership.objects.all()
    serializer_class = OrganizationMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = OrganizationMembership.objects.select_related('organization', 'user')
        if not user_is_global_admin(self.request.user):
            queryset = queryset.filter(
                models.Q(organization__owner=self.request.user) |
                models.Q(organization__memberships__user=self.request.user)
            ).distinct()

        organization_id = self.request.query_params.get('organization')
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        return queryset


class OrganizationGitConnectionViewSet(viewsets.ModelViewSet):
    queryset = OrganizationGitConnection.objects.all()
    serializer_class = OrganizationGitConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = OrganizationGitConnection.objects.select_related('organization', 'created_by')
        if not user_is_global_admin(self.request.user):
            queryset = queryset.filter(
                models.Q(organization__owner=self.request.user) |
                models.Q(organization__memberships__user=self.request.user)
            ).distinct()

        organization_id = self.request.query_params.get('organization')
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        return queryset

    def perform_create(self, serializer):
        organization = serializer.validated_data.get('organization')
        if not organization:
            raise ValidationError({'organization_id': 'This field is required.'})
        if not user_has_organization_access(self.request.user, organization, minimum_role='admin'):
            raise PermissionDenied('You do not have permission to manage organization Git connections')
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        organization = serializer.validated_data.get('organization', instance.organization)
        if organization != instance.organization:
            raise ValidationError({'organization_id': 'Changing the owning organization is not supported.'})
        if not user_has_organization_access(self.request.user, instance.organization, minimum_role='admin'):
            raise PermissionDenied('You do not have permission to manage organization Git connections')
        serializer.save()

    def perform_destroy(self, instance):
        if not user_has_organization_access(self.request.user, instance.organization, minimum_role='admin'):
            raise PermissionDenied('You do not have permission to manage organization Git connections')
        instance.delete()

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        connection = self.get_object()
        if not user_has_organization_access(request.user, connection.organization, minimum_role='admin'):
            raise PermissionDenied('You do not have permission to test organization Git connections')

        result = test_connection_credential(connection)

        connection.last_tested_at = timezone.now()
        connection.last_test_status = result['status'] if result['status'] in {'succeeded', 'failed'} else 'unknown'
        connection.save(update_fields=['last_tested_at', 'last_test_status', 'updated_at'])
        serializer = self.get_serializer(connection)
        return Response(
            {
                'status': result['status'],
                'message': result['message'],
                'username': result.get('username'),
                'connection': serializer.data,
            }
        )

    @action(detail=True, methods=['get'])
    def repositories(self, request, pk=None):
        connection = self.get_object()
        if not user_has_organization_access(request.user, connection.organization, minimum_role='member'):
            raise PermissionDenied('You do not have permission to use organization Git connections')

        search = request.query_params.get('search')
        try:
            repositories = list_connection_repositories(connection, search=search)
        except GitProviderDiscoveryError as exc:
            raise ValidationError({'detail': str(exc)}) from exc

        connection.repository_cache = repositories
        connection.save(update_fields=['repository_cache', 'updated_at'])

        return Response(
            {
                'repositories': repositories,
                'count': len(repositories),
            }
        )

    @action(detail=True, methods=['get'])
    def branches(self, request, pk=None):
        connection = self.get_object()
        if not user_has_organization_access(request.user, connection.organization, minimum_role='member'):
            raise PermissionDenied('You do not have permission to use organization Git connections')

        repository_identifier = request.query_params.get('repository', '')
        try:
            payload = list_repository_branches(connection, repository_identifier)
        except GitProviderDiscoveryError as exc:
            raise ValidationError({'detail': str(exc)}) from exc

        return Response(
            {
                **payload,
                'count': len(payload['branches']),
            }
        )


class PersonalGitConnectionViewSet(viewsets.ModelViewSet):
    queryset = PersonalGitConnection.objects.all()
    serializer_class = PersonalGitConnectionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PersonalGitConnection.objects.select_related('user').filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.user_id != self.request.user.id:
            raise PermissionDenied('You do not have permission to manage this personal Git connection')
        serializer.save()

    def perform_destroy(self, instance):
        if instance.user_id != self.request.user.id:
            raise PermissionDenied('You do not have permission to manage this personal Git connection')
        instance.delete()

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        connection = self.get_object()
        if connection.user_id != request.user.id:
            raise PermissionDenied('You do not have permission to test this personal Git connection')

        result = test_connection_credential(connection)

        connection.last_tested_at = timezone.now()
        connection.last_test_status = result['status'] if result['status'] in {'succeeded', 'failed'} else 'unknown'
        connection.save(update_fields=['last_tested_at', 'last_test_status', 'updated_at'])
        serializer = self.get_serializer(connection)
        return Response(
            {
                'status': result['status'],
                'message': result['message'],
                'username': result.get('username'),
                'connection': serializer.data,
            }
        )

    @action(detail=True, methods=['get'])
    def repositories(self, request, pk=None):
        connection = self.get_object()
        if connection.user_id != request.user.id:
            raise PermissionDenied('You do not have permission to use this personal Git connection')

        search = request.query_params.get('search')
        try:
            repositories = list_connection_repositories(connection, search=search)
        except GitProviderDiscoveryError as exc:
            raise ValidationError({'detail': str(exc)}) from exc

        connection.repository_cache = repositories
        connection.save(update_fields=['repository_cache', 'updated_at'])

        return Response(
            {
                'repositories': repositories,
                'count': len(repositories),
            }
        )

    @action(detail=True, methods=['get'])
    def branches(self, request, pk=None):
        connection = self.get_object()
        if connection.user_id != request.user.id:
            raise PermissionDenied('You do not have permission to use this personal Git connection')

        repository_identifier = request.query_params.get('repository', '')
        try:
            payload = list_repository_branches(connection, repository_identifier)
        except GitProviderDiscoveryError as exc:
            raise ValidationError({'detail': str(exc)}) from exc

        return Response(
            {
                **payload,
                'count': len(payload['branches']),
            }
        )

class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Allow all authenticated users to see all teams in the workspace
        # This enables team discovery and joining functionality
        queryset = Team.objects.all()
        organization_id = self.request.query_params.get('organization')
        if organization_id:
            queryset = queryset.filter(organization_id=organization_id)
        return queryset

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        """Add a member to the team"""
        team = self.get_object()
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=400)

        try:
            user = User.objects.get(id=user_id)
            team.members.add(user)
            return Response({'message': f'User {user.username} added to team'})
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

    @action(detail=True, methods=['post'])
    def remove_member(self, request, pk=None):
        """Remove a member from the team"""
        team = self.get_object()
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=400)

        try:
            user = User.objects.get(id=user_id)
            team.members.remove(user)
            return Response({'message': f'User {user.username} removed from team'})
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    logger = logging.getLogger(__name__)

    def get_queryset(self):
        return get_accessible_projects_queryset(self.request.user)

    def create(self, request, *args, **kwargs):
        """Create project and automatically provision workspace for clone method."""
        data = request.data.copy()

        if data.get('creation_method') == 'clone' and data.get('git_repo_url'):
            provider_hint = data.pop('git_provider_hint', None)
            if isinstance(provider_hint, list):
                provider_hint = provider_hint[0] if provider_hint else None
            if provider_hint == 'other':
                provider_hint = None

            try:
                normalized_repository = normalize_public_git_repository_input(
                    data.get('git_repo_url'),
                    provider_hint=provider_hint,
                )
            except GitRepositoryNormalizationError as exc:
                raise ValidationError({'git_repo_url': str(exc)}) from exc

            data['git_repo_url'] = normalized_repository.clone_url

        # Extract connection fields before passing to serializer (not model fields on Project)
        connection_scope = data.pop('connection_scope', None)
        if isinstance(connection_scope, list):
            connection_scope = connection_scope[0] if connection_scope else None
        connection_id = data.pop('connection_id', None)
        if isinstance(connection_id, list):
            connection_id = connection_id[0] if connection_id else None
        if connection_id:
            try:
                connection_id = int(connection_id)
            except (TypeError, ValueError):
                connection_id = None

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        organization = serializer.validated_data.get('organization')
        owner = serializer.validated_data.get('owner', request.user)

        if organization and not user_has_organization_access(request.user, organization, minimum_role='admin'):
            raise PermissionDenied("You do not have permission to create projects in this organization")
        if owner != request.user and not user_is_global_admin(request.user):
            raise PermissionDenied("Only administrators can assign another user as project owner")

        project = serializer.save(owner=owner)
        # Default provisioning status
        project.provisioning_status = 'pending'
        project.save(update_fields=['provisioning_status'])

        # Resolve credential from the optional saved connection
        clone_credential: str | None = None
        if connection_id and connection_scope and data.get('creation_method') == 'clone':
            try:
                if connection_scope == 'organization':
                    from .models import OrganizationGitConnection
                    git_conn = OrganizationGitConnection.objects.get(pk=connection_id)
                    if git_conn.organization == organization or user_has_organization_access(request.user, git_conn.organization, minimum_role='member'):
                        clone_credential = git_conn.get_credential()
                elif connection_scope == 'personal':
                    from .models import PersonalGitConnection
                    git_conn = PersonalGitConnection.objects.get(pk=connection_id, user=request.user)
                    clone_credential = git_conn.get_credential()
            except Exception:  # noqa: BLE001
                clone_credential = None

        # Trigger workspace provisioning for clone method
        if project.creation_method == 'clone' and project.git_repo_url:
            project.provisioning_status = 'in_progress'
            project.save(update_fields=['provisioning_status'])

            try:
                orchestrator = PodmanOrchestrator()
                user_id = request.user.id

                # Provision workspace volume and container
                orchestrator.ensure_workspace_service(project.id, user_id=user_id)

                # Initialize workspace with git clone (credential passed securely, never logged)
                initialize_project_workspace(project, clone_credential=clone_credential)

                project.provisioning_status = 'completed'
                project.save(update_fields=['provisioning_status'])

            except Exception as exc:
                project.provisioning_status = 'failed'
                project.save(update_fields=['provisioning_status'])
                self.logger.error("Failed to provision workspace for project %s: %s", project.id, exc)

        # Re-serialize to include updated provisioning_status
        output_serializer = self.get_serializer(project)
        headers = self.get_success_headers(output_serializer.data)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @action(detail=False, methods=['get'])
    def my_projects(self, request):
        """Get projects where user is owner or contributor"""
        queryset = Project.objects.filter(
            models.Q(owner=request.user) |
            models.Q(contributors=request.user)
        ).distinct()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_update(self, serializer):
        project = self.get_object()
        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied("You do not have permission to manage this project")

        organization = serializer.validated_data.get('organization', project.organization)
        if organization and not user_has_organization_access(self.request.user, organization, minimum_role='admin'):
            raise PermissionDenied("You do not have permission to move this project into the selected organization")
        serializer.save()

    def perform_destroy(self, instance):
        if not user_can_manage_project(self.request.user, instance):
            raise PermissionDenied("You do not have permission to delete this project")
        instance.delete()
    
    @action(detail=True, methods=['get'])
    def provisioning_status(self, request, pk=None):
        """Get current provisioning status for this project."""
        project = self.get_object()
        return Response({
            'status': project.provisioning_status,
            'creation_method': project.creation_method,
            'git_repo_url': project.git_repo_url,
            'branch': project.branch,
        })
    
    @action(detail=True, methods=['post'])
    def ensure_webtop(self, request, pk=None):
        """Provision or ensure webtop service is running for this project."""
        project = self.get_object()  # get_object() already checks access via get_queryset()
        
        orchestrator = PodmanOrchestrator()
        
        try:
            # Ensure workspace volume
            workspace_volume = orchestrator.ensure_volume(project.id, 'workspace')
            
            # Define webtop service spec
            # Selkies expects SUBFOLDER to correctly route HTTP/WebSocket under a subpath
            spec = ServiceSpec(
                name='webtop',
                service_type='tooling',
                image='lscr.io/linuxserver/webtop:amd64-el-xfce',
                ports=['3000:3000'],  # TEMPORARILY expose port for direct testing
                environment={
                    'PUID': '1000',
                    'PGID': '1000',
                    'TZ': 'UTC',
                    'TITLE': f'{project.name} Workspace',
                    # Configure subfolder so Selkies serves and upgrades WS at the proxy path
                    # Must match X-Forwarded-Prefix with trailing slash
                    'SUBFOLDER': f'/api/projects/{project.id}/webtop-proxy/',
                },
                volumes=[
                    {
                        'type': 'volume',
                        'source': workspace_volume,
                        'target': '/config',
                        'readonly': False,
                    },
                    {
                        'type': 'volume',
                        'source': workspace_volume,
                        'target': '/workspace',
                        'readonly': False,
                    }
                ]
            )
            
            service_status = orchestrator.ensure_service(project.id, spec)
            
            return Response({
                'status': 'success',
                'service': {
                    'name': 'webtop',
                    'container_name': service_status.container_name,
                    'status': service_status.status,
                    'started_at': service_status.started_at,
                    'proxy_url': f'/api/projects/{project.id}/webtop-proxy/',
                },
                'workspace_volume': workspace_volume,
            })
        except OrchestratorError as exc:
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def ensure_workspace(self, request, pk=None):
        """Provision or ensure AI workspace service is running for this project."""
        project = self.get_object()
        user_id = request.user.id
        
        orchestrator = PodmanOrchestrator()
        
        try:
            service_status = orchestrator.ensure_workspace_service(project.id, user_id=user_id)
            
            # Check if compose services need to be provisioned
            # Only provision if workspace was just created or if no services exist yet
            pod = project.pod
            if pod:
                self.logger.info(f"Project {project.id} has pod {pod.id}, checking for compose services")
                # Check if compose services have been provisioned
                compose_services_exist = ProjectService.objects.filter(
                    pod=pod
                ).exclude(service_type='ai-workspace').exists()
                
                self.logger.info(f"Project {project.id}: compose_services_exist={compose_services_exist}")
                
                if not compose_services_exist:
                    # Try to provision compose services from workspace volume
                    try:
                        volume_name = f"proj-{project.id}-workspace"
                        initializer = WorkspaceInitializer(volume_name, project_id=project.id)
                        self.logger.info(f"Attempting to provision compose services for project {project.id}")
                        initializer.provision_compose_services(project)
                        self.logger.info(f"Compose service provisioning completed for project {project.id}")
                    except Exception as compose_exc:
                        # Don't fail the entire request if compose provisioning fails
                        self.logger.warning(f"Failed to provision compose services for project {project.id}: {compose_exc}", exc_info=True)
                else:
                    self.logger.info(f"Project {project.id} already has compose services, skipping provisioning")
            else:
                self.logger.warning(f"Project {project.id} has no pod after ensure_workspace_service")
            
            return Response({
                'status': 'success',
                'service': {
                    'name': service_status.container_name.split('-')[-1],
                    'container_name': service_status.container_name,
                    'status': service_status.status,
                    'started_at': service_status.started_at,
                },
                'workspace_config': {
                    'image': project.workspace_image,
                    'size': project.workspace_size,
                    'mode': project.workspace_mode,
                },
            })
        except OrchestratorError as exc:
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def update_workspace_image(self, request, pk=None):
        """Update workspace container to latest image version."""
        project = self.get_object()
        
        orchestrator = PodmanOrchestrator()
        
        try:
            service_status = orchestrator.update_workspace_image(project.id)
            
            return Response({
                'status': 'success',
                'message': 'Workspace image updated. Container stopped. Click Start to use new image.',
                'service': {
                    'container_name': service_status.container_name,
                    'status': service_status.status,
                },
            })
        except OrchestratorError as exc:
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def reset_workspace(self, request, pk=None):
        """Reset workspace volume to clean state."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to reset this workspace")
        
        orchestrator = PodmanOrchestrator()
        
        try:
            orchestrator.reset_workspace_volume(project.id)
            
            return Response({
                'status': 'success',
                'message': 'Workspace volume has been reset to clean state',
            })
        except OrchestratorError as exc:
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def workspace_files(self, request, pk=None):
        """Debug endpoint: List files in workspace volume."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to access this workspace")
        
        try:
            volume_name = f"proj-{project.id}-workspace"
            orchestrator = PodmanOrchestrator()
            
            # List all files in workspace
            result = orchestrator._run(
                ['run', '--rm',
                 '-v', f'{volume_name}:/workspace:ro',
                 'alpine:latest',
                 'sh', '-c', 'ls -la /workspace && echo "---" && find /workspace -maxdepth 2 -type f'],
                capture_output=True,
                check=False
            )
            
            return Response({
                'volume': volume_name,
                'files': result.stdout if result.stdout else 'No output',
                'error': result.stderr if result.stderr else None,
            })
        except Exception as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def provision_services(self, request, pk=None):
        """Manually trigger compose service provisioning."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to provision services")
        
        try:
            volume_name = f"proj-{project.id}-workspace"
            initializer = WorkspaceInitializer(volume_name, project_id=project.id)
            
            self.logger.info(f"Manually triggering compose service provisioning for project {project.id}")
            initializer.provision_compose_services(project)
            
            return Response({
                'status': 'success',
                'message': 'Service provisioning completed. Check provisioning logs for details.',
            })
        except Exception as exc:
            self.logger.error(f"Error provisioning services for project {project.id}: {exc}")
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def stop_workspace(self, request, pk=None):
        """Stop the workspace container."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to stop workspace")
        
        try:
            pod = project.pod
            if not pod:
                return Response(
                    {'error': 'No workspace found for this project'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            workspace_service = pod.services.filter(service_type='ai-workspace').first()
            if not workspace_service:
                return Response(
                    {'error': 'Workspace service not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            orchestrator = PodmanOrchestrator()
            orchestrator.stop_container(workspace_service.container_name)
            
            workspace_service.status = 'stopped'
            workspace_service.save(update_fields=['status'])
            
            self.logger.info(f"Stopped workspace for project {project.id}")
            return Response({'status': 'success', 'message': 'Workspace stopped'})
            
        except Exception as exc:
            self.logger.error(f"Error stopping workspace for project {project.id}: {exc}")
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def restart_workspace(self, request, pk=None):
        """Restart the workspace container."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to restart workspace")
        
        try:
            pod = project.pod
            if not pod:
                return Response(
                    {'error': 'No workspace found for this project'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            workspace_service = pod.services.filter(service_type='ai-workspace').first()
            if not workspace_service:
                return Response(
                    {'error': 'Workspace service not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            orchestrator = PodmanOrchestrator()
            orchestrator.stop_container(workspace_service.container_name)
            orchestrator.start_container(workspace_service.container_name)
            
            workspace_service.status = 'running'
            workspace_service.last_started_at = timezone.now()
            workspace_service.save(update_fields=['status', 'last_started_at'])
            
            self.logger.info(f"Restarted workspace for project {project.id}")
            return Response({'status': 'success', 'message': 'Workspace restarted'})
            
        except Exception as exc:
            self.logger.error(f"Error restarting workspace for project {project.id}: {exc}")
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def delete_service(self, request, pk=None):
        """Delete a specific service container."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to delete services")
        
        service_id = request.data.get('service_id')
        if not service_id:
            return Response(
                {'error': 'service_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = ProjectService.objects.get(id=service_id, pod__project=project)
            
            # Prevent deletion of workspace service
            if service.service_type == 'ai-workspace':
                return Response(
                    {'error': 'Cannot delete workspace service. Use workspace controls instead.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            orchestrator = PodmanOrchestrator()
            try:
                orchestrator.remove_container(service.container_name, force=True)
            except Exception as remove_exc:
                self.logger.warning(f"Error removing container {service.container_name}: {remove_exc}")
            
            service.delete()
            
            self.logger.info(f"Deleted service {service.name} for project {project.id}")
            return Response({'status': 'success', 'message': f'Service {service.name} deleted'})
            
        except ProjectService.DoesNotExist:
            return Response(
                {'error': 'Service not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as exc:
            self.logger.error(f"Error deleting service for project {project.id}: {exc}")
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def start_all_services(self, request, pk=None):
        """Start all stopped services."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to start services")
        
        try:
            pod = project.pod
            if not pod:
                return Response(
                    {'error': 'No workspace found for this project'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            stopped_services = pod.services.filter(status='stopped').exclude(service_type='ai-workspace')
            orchestrator = PodmanOrchestrator()
            started = []
            errors = []
            
            for service in stopped_services:
                try:
                    orchestrator.start_container(service.container_name)
                    service.status = 'running'
                    service.last_started_at = timezone.now()
                    service.save(update_fields=['status', 'last_started_at'])
                    started.append(service.name)
                except Exception as start_exc:
                    errors.append({'service': service.name, 'error': str(start_exc)})
            
            self.logger.info(f"Started {len(started)} services for project {project.id}")
            return Response({
                'status': 'success',
                'started': started,
                'errors': errors,
                'message': f'Started {len(started)} service(s)'
            })
            
        except Exception as exc:
            self.logger.error(f"Error starting all services for project {project.id}: {exc}")
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def stop_all_services(self, request, pk=None):
        """Stop all running services (except workspace)."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to stop services")
        
        try:
            pod = project.pod
            if not pod:
                return Response(
                    {'error': 'No workspace found for this project'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            running_services = pod.services.filter(status='running').exclude(service_type='ai-workspace')
            orchestrator = PodmanOrchestrator()
            stopped = []
            errors = []
            
            for service in running_services:
                try:
                    orchestrator.stop_container(service.container_name)
                    service.status = 'stopped'
                    service.save(update_fields=['status'])
                    stopped.append(service.name)
                except Exception as stop_exc:
                    errors.append({'service': service.name, 'error': str(stop_exc)})
            
            self.logger.info(f"Stopped {len(stopped)} services for project {project.id}")
            return Response({
                'status': 'success',
                'stopped': stopped,
                'errors': errors,
                'message': f'Stopped {len(stopped)} service(s)'
            })
            
        except Exception as exc:
            self.logger.error(f"Error stopping all services for project {project.id}: {exc}")
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def start_service(self, request, pk=None):
        """Start a specific stopped service."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to start services")
        
        service_id = request.data.get('service_id')
        if not service_id:
            return Response(
                {'error': 'service_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = ProjectService.objects.get(id=service_id, pod__project=project)
            
            # Check dependencies if configured
            dependencies = service.config.get('depends_on', [])
            if dependencies:
                pod = service.pod
                for dep_name in dependencies:
                    dep_service = pod.services.filter(name=dep_name).first()
                    if dep_service and dep_service.status != 'running':
                        return Response(
                            {'error': f'Cannot start {service.name}: dependency {dep_name} is not running'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
            
            orchestrator = PodmanOrchestrator()
            orchestrator.start_container(service.container_name)
            
            service.status = 'running'
            service.last_started_at = timezone.now()
            service.save(update_fields=['status', 'last_started_at'])
            
            self.logger.info(f"Started service {service.name} for project {project.id}")
            return Response({'status': 'success', 'message': f'Service {service.name} started'})
            
        except ProjectService.DoesNotExist:
            return Response(
                {'error': 'Service not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as exc:
            self.logger.error(f"Error starting service for project {project.id}: {exc}")
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            return Response({
                'status': 'success',
                'message': 'Workspace reset. Volume reinitialized according to project creation method.',
            })
        except OrchestratorError as exc:
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def check_containers(self, request, pk=None):
        """Check health of project containers and detect missing services."""
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to view this project's containers")
        
        orchestrator = PodmanOrchestrator()
        
        try:
            # Get all services for this project
            from .models import ProjectPod, ProjectService
            
            try:
                pod = ProjectPod.objects.get(project=project)
                services = ProjectService.objects.filter(pod=pod)
            except ProjectPod.DoesNotExist:
                return Response({
                    'status': 'no_pod',
                    'healthy': False,
                    'message': 'No pod exists for this project',
                    'services': [],
                    'missing_services': [],
                })
            
            if not services.exists():
                return Response({
                    'status': 'no_services',
                    'healthy': False,
                    'message': 'No services defined for this project',
                    'services': [],
                    'missing_services': [],
                })
            
            # Check each service
            service_status = []
            missing_services = []
            
            for service in services:
                try:
                    container_status = orchestrator.check_service_status(project.id, service.name)
                    if container_status:
                        service_status.append({
                            'name': service.name,
                            'status': container_status.get('status', 'unknown'),
                            'exists': True,
                        })
                    else:
                        missing_services.append(service.name)
                        service_status.append({
                            'name': service.name,
                            'status': 'missing',
                            'exists': False,
                        })
                except Exception as exc:
                    self.logger.warning(f"Failed to check service {service.name}: {exc}")
                    missing_services.append(service.name)
                    service_status.append({
                        'name': service.name,
                        'status': 'error',
                        'exists': False,
                        'error': str(exc),
                    })
            
            healthy = len(missing_services) == 0
            
            return Response({
                'status': 'healthy' if healthy else 'degraded',
                'healthy': healthy,
                'message': 'All containers running' if healthy else f'{len(missing_services)} container(s) missing',
                'services': service_status,
                'missing_services': missing_services,
            })
            
        except Exception as exc:
            self.logger.error(f"Error checking containers for project {project.id}: {exc}")
            return Response(
                {'error': str(exc), 'error_type': 'check_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def container_stats(self, request, pk=None):
        """
        GET /api/projects/{project_id}/container_stats/
        Get CPU, memory usage, and port details for workspace container.
        """
        project = self.get_object()
        self.check_object_permissions(request, project)
        
        try:
            # Get ai-workspace service
            workspace_service = project.pod.services.filter(service_type='ai-workspace').first()
            if not workspace_service:
                return Response({
                    'error': 'Workspace not provisioned',
                }, status=status.HTTP_404_NOT_FOUND)
            
            if workspace_service.status != 'running':
                return Response({
                    'status': workspace_service.status,
                    'running': False,
                    'cpu_percent': 0,
                    'memory_mb': 0,
                    'memory_limit_mb': 0,
                    'ports': workspace_service.ports or [],
                })
            
            # Get live stats from podman stats using JSON format
            orchestrator = PodmanOrchestrator()
            try:
                result = orchestrator._run(
                    ['stats', '--no-stream', '--format', 'json', workspace_service.container_name],
                    capture_output=True,
                    check=False
                )
                
                stats_data = {
                    'status': 'running',
                    'running': True,
                    'cpu_percent': 0,
                    'memory_mb': 0,
                    'memory_limit_mb': 0,
                    'ports': workspace_service.ports or [],
                    'container_name': workspace_service.container_name,
                }
                
                # Parse JSON output
                if result.stdout:
                    try:
                        import json as json_module
                        stats = json_module.loads(result.stdout)
                        if stats and len(stats) > 0:
                            stat = stats[0]  # First (and only) container
                            
                            # CPU percentage (already a string like "12.34%")
                            cpu_str = stat.get('cpu_percent', '0%').rstrip('%')
                            try:
                                stats_data['cpu_percent'] = float(cpu_str) if cpu_str else 0
                            except ValueError:
                                stats_data['cpu_percent'] = 0
                            
                            # Memory usage (format: "123.4MB / 2GB")
                            mem_usage = stat.get('mem_usage', '0B / 0B')
                            if '/' in mem_usage:
                                usage_str, limit_str = mem_usage.split('/')
                                usage_str = usage_str.strip().upper()  # Normalize to uppercase
                                limit_str = limit_str.strip().upper()
                                
                                # Parse usage
                                try:
                                    if 'GB' in usage_str:
                                        stats_data['memory_mb'] = float(usage_str.replace('GB', '').strip()) * 1024
                                    elif 'MB' in usage_str:
                                        stats_data['memory_mb'] = float(usage_str.replace('MB', '').strip())
                                    elif 'KB' in usage_str or 'K' in usage_str:
                                        # Handle both KB and k suffix
                                        val = usage_str.replace('KB', '').replace('K', '').strip()
                                        stats_data['memory_mb'] = float(val) / 1024
                                    elif 'B' in usage_str:
                                        stats_data['memory_mb'] = float(usage_str.replace('B', '').strip()) / (1024 * 1024)
                                except (ValueError, AttributeError) as e:
                                    self.logger.debug(f"Could not parse memory usage '{usage_str}': {e}")
                                
                                # Parse limit
                                try:
                                    if 'GB' in limit_str:
                                        stats_data['memory_limit_mb'] = float(limit_str.replace('GB', '').strip()) * 1024
                                    elif 'MB' in limit_str:
                                        stats_data['memory_limit_mb'] = float(limit_str.replace('MB', '').strip())
                                    elif 'KB' in limit_str or 'K' in limit_str:
                                        val = limit_str.replace('KB', '').replace('K', '').strip()
                                        stats_data['memory_limit_mb'] = float(val) / 1024
                                    elif 'B' in limit_str:
                                        stats_data['memory_limit_mb'] = float(limit_str.replace('B', '').strip()) / (1024 * 1024)
                                except (ValueError, AttributeError) as e:
                                    self.logger.debug(f"Could not parse memory limit '{limit_str}': {e}")
                    except Exception as parse_err:
                        self.logger.warning(f"Failed to parse stats JSON for {workspace_service.container_name}: {parse_err}")
                
                return Response(stats_data)
                
            except Exception as e:
                self.logger.warning(f"Failed to get stats for {workspace_service.container_name}: {e}")
                return Response({
                    'status': 'running',
                    'running': True,
                    'cpu_percent': 0,
                    'memory_mb': 0,
                    'memory_limit_mb': 0,
                    'ports': workspace_service.ports or [],
                    'container_name': workspace_service.container_name,
                })
        
        except Exception as exc:
            self.logger.error(f"Error getting container stats for project {project.id}: {exc}")
            return Response(
                {'error': str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def reprovision(self, request, pk=None):
        """
        Delete and recreate all services from compose file.
        Query param: ?wipe_volumes=true to also delete workspace volume.
        """
        project = self.get_object()
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to reprovision this project")
        
        wipe_volumes = request.query_params.get('wipe_volumes', 'false').lower() == 'true'
        
        orchestrator = PodmanOrchestrator()
        
        try:
            from .models import ProjectPod, ProjectService
            
            # 1. Stop and delete all services
            try:
                pod = ProjectPod.objects.get(project=project)
                services = ProjectService.objects.filter(pod=pod)
                
                for service in services:
                    try:
                        orchestrator.stop_service(project.id, service.name)
                        self.logger.info(f"Stopped service: {service.name}")
                    except Exception as exc:
                        self.logger.warning(f"Failed to stop service {service.name}: {exc}")
                
                # Delete pod
                try:
                    orchestrator.delete_pod(project.id)
                    self.logger.info(f"Deleted pod for project {project.id}")
                except Exception as exc:
                    self.logger.warning(f"Failed to delete pod: {exc}")
                
                # Delete service records from DB
                services.delete()
                pod.delete()
                
            except ProjectPod.DoesNotExist:
                self.logger.info(f"No existing pod for project {project.id}")
            
            # 2. Optionally wipe workspace volume
            if wipe_volumes:
                try:
                    volume_name = f"proj-{project.id}-workspace"
                    orchestrator._run_command(['volume', 'rm', '-f', volume_name])
                    self.logger.info(f"Deleted workspace volume: {volume_name}")
                except Exception as exc:
                    self.logger.warning(f"Failed to delete workspace volume: {exc}")
            
            # 3. Recreate pod and reprovision services
            project.provisioning_status = 'in_progress'
            project.save(update_fields=['provisioning_status'])
            
            try:
                # Ensure pod exists
                orchestrator.ensure_workspace_service(project.id, user_id=request.user.id)
                
                # If volumes were wiped, reinitialize workspace
                if wipe_volumes:
                    initialize_project_workspace(project)
                else:
                    # Just reprovision services from compose file
                    volume_name = f"proj-{project.id}-workspace"
                    initializer = WorkspaceInitializer(volume_name, project_id=project.id)
                    initializer.provision_compose_services(project)
                
                project.provisioning_status = 'completed'
                project.save(update_fields=['provisioning_status'])
                
                return Response({
                    'status': 'success',
                    'message': f"Project reprovisioned successfully {'with clean volumes' if wipe_volumes else ''}",
                    'volumes_wiped': wipe_volumes,
                })
                
            except Exception as exc:
                project.provisioning_status = 'failed'
                project.save(update_fields=['provisioning_status'])
                raise exc
            
        except Exception as exc:
            self.logger.error(f"Error reprovisioning project {project.id}: {exc}")
            return Response(
                {'error': str(exc), 'error_type': 'reprovision_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='workspace/clone-from-source')
    def clone_workspace_from_source(self, request, pk=None):
        """
        Clone a git repository directly into the project workspace volume.
        Clears existing workspace content first. The workspace container does not
        need to be running — cloning uses a temporary alpine/git container.
        """
        project = self.get_object()

        if not user_has_project_access(request.user, project):
            raise PermissionDenied("You do not have permission to manage this project's workspace")

        git_url = request.data.get('git_url', '').strip()
        branch = request.data.get('branch', '').strip() or None
        connection_scope = request.data.get('connection_scope', '').strip() or None
        connection_id_raw = request.data.get('connection_id', None)
        connection_id = None
        if connection_id_raw:
            try:
                connection_id = int(connection_id_raw)
            except (TypeError, ValueError):
                connection_id = None

        if not git_url:
            return Response({'error': 'git_url is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize the URL
        try:
            normalized_repository = normalize_public_git_repository_input(git_url)
            git_url = normalized_repository.clone_url
        except GitRepositoryNormalizationError:
            pass  # Use the URL as-is (may be a private or self-hosted repo)

        # Resolve PAT from an optional saved connection
        clone_credential = None
        if connection_id and connection_scope:
            try:
                if connection_scope == 'organization':
                    org = project.organization
                    git_conn = OrganizationGitConnection.objects.get(pk=connection_id)
                    if git_conn.organization == org or user_has_organization_access(request.user, git_conn.organization, minimum_role='member'):
                        clone_credential = git_conn.get_credential()
                elif connection_scope == 'personal':
                    git_conn = PersonalGitConnection.objects.get(pk=connection_id, user=request.user)
                    clone_credential = git_conn.get_credential()
            except Exception:  # noqa: BLE001
                clone_credential = None

        volume_name = f"proj-{project.id}-workspace"
        initializer = WorkspaceInitializer(volume_name, project_id=project.id)
        podman_bin = os.getenv('PODMAN_BIN', 'podman')

        try:
            # Ensure the volume exists before clearing
            initializer._ensure_volume_exists()

            # Clear existing workspace content so the clone lands cleanly
            clear_cmd = 'find /workspace -mindepth 1 -delete 2>/dev/null || true'
            try:
                initializer._run_command([
                    podman_bin, 'run', '--rm',
                    '-v', f'{volume_name}:/workspace',
                    '--entrypoint', '/bin/sh',
                    'alpine:latest',
                    '-c', clear_cmd,
                ])
            except Exception as clear_exc:
                self.logger.warning(f"Could not clear workspace before clone: {clear_exc}")

            # Clone the repository into the volume
            initializer.init_from_clone(git_url, branch, credential=clone_credential)

            return Response({'status': 'success', 'message': 'Repository cloned successfully into workspace'})

        except Exception as exc:
            self.logger.error(f"clone_workspace_from_source failed for project {project.id}: {exc}")
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProjectTemplateViewSet(viewsets.ModelViewSet):
    queryset = ProjectTemplate.objects.filter(is_active=True)
    serializer_class = ProjectTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

class ChangeRequestViewSet(viewsets.ModelViewSet):
    queryset = ChangeRequest.objects.all()
    serializer_class = ChangeRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can see change requests for projects they own or contribute to
        user_projects = Project.objects.filter(
            models.Q(owner=self.request.user) | models.Q(contributors=self.request.user)
        )
        return ChangeRequest.objects.filter(project__in=user_projects)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Approve a change request"""
        change_request = self.get_object()

        # Check if user can approve (must be contributor or owner of project)
        if request.user not in change_request.project.contributors.all() and request.user != change_request.project.owner:
            return Response({'error': 'You do not have permission to approve this change request'}, status=403)

        # Check if user already approved
        approval, created = Approval.objects.get_or_create(
            change_request=change_request,
            approver=request.user,
            defaults={'approved': True}
        )

        if not created and not approval.approved:
            approval.approved = True
            approval.save()

        return Response({'message': 'Change request approved'})

    @action(detail=True, methods=['post'])
    def request_changes(self, request, pk=None):
        """Request changes on a change request"""
        change_request = self.get_object()

        # Check if user can review (must be contributor or owner of project)
        if request.user not in change_request.project.contributors.all() and request.user != change_request.project.owner:
            return Response({'error': 'You do not have permission to review this change request'}, status=403)

        approval, created = Approval.objects.get_or_create(
            change_request=change_request,
            approver=request.user,
            defaults={'approved': False}
        )

        if not created:
            approval.approved = False
            approval.comments = request.data.get('comments', '')
            approval.save()

        return Response({'message': 'Changes requested'})

class ComplianceCheckViewSet(viewsets.ModelViewSet):
    queryset = ComplianceCheck.objects.all()
    serializer_class = ComplianceCheckSerializer
    permission_classes = [permissions.IsAuthenticated]

class ComplianceTemplateViewSet(viewsets.ModelViewSet):
    queryset = ComplianceTemplate.objects.all()
    serializer_class = ComplianceTemplateSerializer
    permission_classes = [permissions.IsAuthenticated]

class ProjectAssignmentViewSet(viewsets.ModelViewSet):
    queryset = ProjectAssignment.objects.all()
    serializer_class = ProjectAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]


class DiscussionViewSet(viewsets.ModelViewSet):
    queryset = Discussion.objects.all()
    serializer_class = DiscussionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=['post'])
    def increment_views(self, request, pk=None):
        discussion = self.get_object()
        discussion.views += 1
        discussion.save()
        return Response({'views': discussion.views})

    @action(detail=True, methods=['post'])
    def toggle_pin(self, request, pk=None):
        discussion = self.get_object()
        discussion.is_pinned = not discussion.is_pinned
        discussion.save()
        return Response({'is_pinned': discussion.is_pinned})

    @action(detail=True, methods=['post'])
    def toggle_lock(self, request, pk=None):
        discussion = self.get_object()
        discussion.is_locked = not discussion.is_locked
        discussion.save()
        return Response({'is_locked': discussion.is_locked})


class DiscussionReplyViewSet(viewsets.ModelViewSet):
    queryset = DiscussionReply.objects.all()
    serializer_class = DiscussionReplySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
        # Update discussion reply count and last activity
        discussion = serializer.validated_data['discussion']
        discussion.replies += 1
        discussion.save()

    def get_queryset(self):
        queryset = DiscussionReply.objects.all()
        discussion_id = self.request.query_params.get('discussion', None)
        if discussion_id is not None:
            queryset = queryset.filter(discussion_id=discussion_id)
        return queryset


class MarketplaceItemViewSet(viewsets.ModelViewSet):
    queryset = MarketplaceItem.objects.all()
    serializer_class = MarketplaceItemSerializer

    def get_permissions(self):
        """
        Allow public read access but require authentication for write operations
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'like', 'increment_downloads']:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.AllowAny]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        item = self.get_object()
        item.likes += 1
        item.save()
        return Response({'likes': item.likes})

    @action(detail=True, methods=['post'])
    def increment_downloads(self, request, pk=None):
        item = self.get_object()
        item.downloads += 1
        item.save()
        return Response({'downloads': item.downloads})

    def get_queryset(self):
        queryset = MarketplaceItem.objects.all()
        category = self.request.query_params.get('category', None)
        search = self.request.query_params.get('search', None)
        featured = self.request.query_params.get('featured', None)

        if category and category != 'all':
            queryset = queryset.filter(category=category)
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) |
                models.Q(description__icontains=search) |
                models.Q(author__username__icontains=search)
            )
        if featured:
            queryset = queryset.filter(is_featured=True)

        return queryset


class MarketplaceCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MarketplaceCategory.objects.all()
    serializer_class = MarketplaceCategorySerializer
    permission_classes = [permissions.AllowAny]  # Categories are public


# Chatbot ViewSets
class ChatbotPersonaViewSet(viewsets.ModelViewSet):
    queryset = ChatbotPersona.objects.all()
    serializer_class = ChatbotPersonaSerializer
    permission_classes = [permissions.AllowAny]  # Personas are public

    def get_queryset(self):
        queryset = ChatbotPersona.objects.filter(is_active=True)
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category=category)
        return queryset


class ChatbotTemplateViewSet(viewsets.ModelViewSet):
    queryset = ChatbotTemplate.objects.all()
    serializer_class = ChatbotTemplateSerializer
    permission_classes = [permissions.AllowAny]  # Templates are public

    def get_queryset(self):
        queryset = ChatbotTemplate.objects.filter(is_active=True)
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category=category)
        return queryset


class ChatMessageViewSet(viewsets.ModelViewSet):
    queryset = ChatMessage.objects.all()
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        session_id = self.request.query_params.get('session', None)
        if session_id:
            return ChatMessage.objects.filter(session_id=session_id, session__user=self.request.user)
        return ChatMessage.objects.filter(session__user=self.request.user)

    def perform_create(self, serializer):
        serializer.save()

    def update(self, request, *args, **kwargs):
        """Update a chat message"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        # Check ownership
        if instance.session.user != request.user:
            return Response({'error': 'Unauthorized'}, status=403)
        
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Optionally delete all messages after this one if requested
        if request.data.get('clear_after', False):
            ChatMessage.objects.filter(
                session=instance.session,
                created_at__gt=instance.created_at
            ).delete()
        
        return Response(serializer.data)


class IssueViewSet(viewsets.ModelViewSet):
    queryset = Issue.objects.all()
    serializer_class = IssueSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_id = self.request.query_params.get('project', None)
        if project_id:
            # Allow users to see issues for projects they have access to
            return Issue.objects.filter(
                models.Q(project_id=project_id) & 
                (models.Q(project__owner=self.request.user) | 
                 models.Q(project__contributors=self.request.user))
            )
        # Return issues for projects the user has access to
        return Issue.objects.filter(
            models.Q(project__owner=self.request.user) | 
            models.Q(project__contributors=self.request.user)
        )

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=['post'])
    def vote(self, request, pk=None):
        """Vote for an issue"""
        issue = self.get_object()
        issue.votes += 1
        issue.save()
        return Response({'votes': issue.votes})

    @action(detail=True, methods=['post'])
    def bookmark(self, request, pk=None):
        """Bookmark/unbookmark an issue"""
        issue = self.get_object()
        issue.is_bookmarked = not issue.is_bookmarked
        issue.save()
        return Response({'is_bookmarked': issue.is_bookmarked})

    @action(detail=True, methods=['post'])
    def view(self, request, pk=None):
        """Increment view count"""
        issue = self.get_object()
        issue.views += 1
        issue.save()
        return Response({'views': issue.views})


class IssueReplyViewSet(viewsets.ModelViewSet):
    queryset = IssueReply.objects.all()
    serializer_class = IssueReplySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        issue_id = self.request.query_params.get('issue', None)
        if issue_id:
            return IssueReply.objects.filter(issue_id=issue_id)
        return IssueReply.objects.all()

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class WorkflowViewSet(viewsets.ModelViewSet):
    queryset = Workflow.objects.all()
    serializer_class = WorkflowSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_id = self.request.query_params.get('project', None)
        if project_id:
            # Allow users to see workflows for projects they have access to
            return Workflow.objects.filter(
                models.Q(project_id=project_id) & 
                (models.Q(project__owner=self.request.user) | 
                 models.Q(project__contributors=self.request.user))
            )
        # Return workflows for projects the user has access to
        return Workflow.objects.filter(
            models.Q(project__owner=self.request.user) | 
            models.Q(project__contributors=self.request.user)
        )

    def perform_create(self, serializer):
        serializer.save(author=self.request.user, project_id=self.request.data.get('project'))

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        """Execute a workflow"""
        workflow = self.get_object()
        # Create execution record
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            triggered_by=request.user,
            status='running'
        )
        # Here you would trigger the actual workflow execution
        # For now, we'll just mark it as completed
        execution.status = 'completed'
        execution.completed_at = models.functions.Now()
        execution.save()
        
        workflow.last_run = models.functions.Now()
        workflow.run_count += 1
        workflow.save()
        
        return Response(WorkflowExecutionSerializer(execution).data)


class WorkflowExecutionViewSet(viewsets.ModelViewSet):
    queryset = WorkflowExecution.objects.all()
    serializer_class = WorkflowExecutionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        workflow_id = self.request.query_params.get('workflow', None)
        if workflow_id:
            return WorkflowExecution.objects.filter(workflow_id=workflow_id)
        # Return executions for workflows the user has access to
        return WorkflowExecution.objects.filter(
            models.Q(workflow__project__owner=self.request.user) | 
            models.Q(workflow__project__contributors=self.request.user)
        )


class EnvironmentViewSet(viewsets.ModelViewSet):
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Environment.objects.select_related('project', 'project__organization', 'created_by')
        if not user_is_global_admin(self.request.user):
            queryset = queryset.filter(project__in=get_accessible_projects_queryset(self.request.user))

        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied("You do not have permission to create environments for this project")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        project = serializer.validated_data.get('project', self.get_object().project)
        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied("You do not have permission to manage this environment")
        serializer.save()

    def perform_destroy(self, instance):
        if not user_can_manage_project(self.request.user, instance.project):
            raise PermissionDenied("You do not have permission to delete this environment")
        instance.delete()


class AppViewSet(viewsets.ModelViewSet):
    queryset = App.objects.all()
    serializer_class = AppSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = App.objects.select_related('environment', 'environment__project', 'created_by', 'source_settings', 'source_settings__organization_connection', 'source_settings__personal_connection')
        if not user_is_global_admin(self.request.user):
            queryset = queryset.filter(environment__project__in=get_accessible_projects_queryset(self.request.user))

        environment_id = self.request.query_params.get('environment')
        if environment_id:
            queryset = queryset.filter(environment_id=environment_id)
        return queryset

    def perform_create(self, serializer):
        environment = serializer.validated_data['environment']
        if not user_can_manage_project(self.request.user, environment.project):
            raise PermissionDenied("You do not have permission to create apps in this environment")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        environment = serializer.validated_data.get('environment', self.get_object().environment)
        if not user_can_manage_project(self.request.user, environment.project):
            raise PermissionDenied("You do not have permission to manage this app")
        serializer.save()

    def perform_destroy(self, instance):
        if not user_can_manage_project(self.request.user, instance.environment.project):
            raise PermissionDenied("You do not have permission to delete this app")
        instance.delete()

    def _build_source_settings_defaults(self, app):
        deployment_settings = (app.config or {}).get('deploymentSettings', {})
        source_provider = deployment_settings.get('providerType', 'github')
        requested_source_kind = deployment_settings.get('sourceKind')

        if source_provider == 'docker-registry':
            source_kind = 'container-image'
        elif source_provider == 'raw-compose':
            source_kind = 'raw-dockerfile' if requested_source_kind == 'raw-dockerfile' or deployment_settings.get('buildContextPath') else 'raw-compose'
        else:
            source_kind = 'git-repository'

        if source_kind == 'git-repository':
            source_location = deployment_settings.get('sourceLocation') or deployment_settings.get('sourceReference') or app.repository_url or ''
            source_ref = deployment_settings.get('sourceRef', 'main')
            normalized_watch_paths_default = 'src/**'
            normalized_submodules_enabled = bool(deployment_settings.get('submodulesEnabled'))
            normalized_trigger_type = deployment_settings.get('triggerType', 'manual')
        elif source_kind == 'container-image':
            source_location = deployment_settings.get('sourceLocation') or deployment_settings.get('sourceReference') or app.repository_url or ''
            source_ref = deployment_settings.get('sourceRef') or 'latest'
            normalized_watch_paths_default = []
            normalized_submodules_enabled = False
            normalized_trigger_type = deployment_settings.get('triggerType', 'manual')
            if normalized_trigger_type == 'push':
                normalized_trigger_type = 'manual'
        else:
            source_location = deployment_settings.get('sourceLocation') or deployment_settings.get('sourceReference') or app.compose_path or ''
            source_ref = ''
            normalized_watch_paths_default = []
            normalized_submodules_enabled = False
            normalized_trigger_type = deployment_settings.get('triggerType', 'manual')
            if normalized_trigger_type == 'push':
                normalized_trigger_type = 'manual'

        watch_paths = deployment_settings.get('watchPaths', 'src/**')
        if normalized_watch_paths_default == []:
            watch_paths = []
        if isinstance(watch_paths, str):
            watch_paths = [path.strip() for path in watch_paths.splitlines() if path.strip()]
        elif not isinstance(watch_paths, list):
            watch_paths = []

        return {
            'source_provider': source_provider,
            'source_kind': source_kind,
            'source_location': source_location,
            'build_context_path': deployment_settings.get('buildContextPath', ''),
            'source_ref': source_ref,
            'watch_paths': watch_paths,
            'trigger_type': normalized_trigger_type,
            'auto_deploy_enabled': bool(deployment_settings.get('autoDeployEnabled')),
            'submodules_enabled': normalized_submodules_enabled,
            'schedule': deployment_settings.get('schedule', '0 */6 * * *'),
            'created_by': app.created_by,
        }

    @action(detail=True, methods=['get'])
    def source_discovery(self, request, pk=None):
        app = self.get_object()

        provider = (request.query_params.get('provider') or '').strip()
        source_kind = (request.query_params.get('source_kind') or '').strip()
        if not provider:
            raise ValidationError({'provider': 'A source provider is required.'})
        if not source_kind:
            raise ValidationError({'source_kind': 'A source kind is required.'})

        try:
            payload = get_source_discovery_payload(
                provider,
                source_kind,
                search=request.query_params.get('search'),
                repository=request.query_params.get('repository'),
            )
        except SourceDiscoveryError as exc:
            raise ValidationError({'detail': str(exc)}) from exc

        return Response(payload)

    @action(detail=True, methods=['get', 'patch'])
    def source_settings(self, request, pk=None):
        app = self.get_object()
        source_settings, _ = AppSourceSettings.objects.get_or_create(
            app=app,
            defaults=self._build_source_settings_defaults(app),
        )

        if request.method == 'GET':
            serializer = AppSourceSettingsSerializer(source_settings, context={'request': request, 'app': app})
            return Response(serializer.data)

        if not user_can_manage_project(request.user, app.environment.project):
            raise PermissionDenied('You do not have permission to manage this app source configuration')

        serializer = AppSourceSettingsSerializer(
            source_settings,
            data=request.data,
            partial=True,
            context={'request': request, 'app': app},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=source_settings.created_by or request.user)

        response_serializer = AppSourceSettingsSerializer(source_settings, context={'request': request, 'app': app})
        return Response(response_serializer.data)


class DeploymentViewSet(viewsets.ModelViewSet):
    queryset = Deployment.objects.all()
    serializer_class = DeploymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Deployment.objects.select_related('environment', 'app', 'deployed_by', 'app__environment__project')
        if not user_is_global_admin(self.request.user):
            queryset = queryset.filter(environment__project__in=get_accessible_projects_queryset(self.request.user))

        environment_id = self.request.query_params.get('environment')
        if environment_id:
            queryset = queryset.filter(environment_id=environment_id)

        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(app_id=app_id)
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app = serializer.validated_data['app']
        if not user_can_manage_project(request.user, app.environment.project):
            raise PermissionDenied("You do not have permission to deploy this app")

        deployment = serializer.save(deployed_by=request.user, environment=app.environment)

        # Kick off the real deployment (clone + provision) in a background daemon thread
        thread = threading.Thread(
            target=run_deployment,
            args=(deployment.id,),
            daemon=True,
            name=f"deploy-{deployment.id}",
        )
        thread.start()

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_202_ACCEPTED, headers=headers)

    def perform_create(self, serializer):
        # Kept for completeness; actual creation now happens in create().
        app = serializer.validated_data['app']
        if not user_can_manage_project(self.request.user, app.environment.project):
            raise PermissionDenied("You do not have permission to deploy this app")
        serializer.save(deployed_by=self.request.user, environment=app.environment)

    def perform_update(self, serializer):
        deployment = self.get_object()
        app = serializer.validated_data.get('app', deployment.app)
        if not user_can_manage_project(self.request.user, app.environment.project):
            raise PermissionDenied("You do not have permission to manage this deployment")
        serializer.save(environment=app.environment)

    def perform_destroy(self, instance):
        if not user_can_manage_project(self.request.user, instance.environment.project):
            raise PermissionDenied("You do not have permission to delete this deployment")
        instance.delete()

    @action(detail=True, methods=['post'])
    def rollback(self, request, pk=None):
        deployment = self.get_object()
        if not user_can_manage_project(request.user, deployment.environment.project):
            raise PermissionDenied("You do not have permission to roll back this deployment")

        rollback_deployment = Deployment.objects.create(
            environment=deployment.environment,
            app=deployment.app,
            version=deployment.version,
            status='rolled_back',
            trigger_type='rollback',
            deployed_by=request.user,
            source_ref=deployment.source_ref,
            compose_path=deployment.compose_path,
            notes=request.data.get('notes', ''),
            config_snapshot=deployment.config_snapshot,
            service_snapshot=deployment.service_snapshot,
            rollback_of=deployment,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        serializer = self.get_serializer(rollback_deployment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ProjectPodViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProjectPodSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ProjectPod.objects.filter(project__in=get_accessible_projects_queryset(self.request.user))
        environment_id = self.request.query_params.get('environment')
        if environment_id:
            queryset = queryset.filter(environment_id=environment_id)
        return queryset

    @action(detail=False, methods=['post'])
    def ensure(self, request):
        project_id = request.data.get('project')
        if not project_id:
            return Response({'error': 'project is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')

        manager = PodmanManager(project)
        try:
            pod = manager.ensure_pod()
        except PodmanError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = self.get_serializer(pod)
        return Response(serializer.data)


class ProjectServiceViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectServiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ProjectService.objects.filter(
            pod__project__in=get_accessible_projects_queryset(self.request.user)
        ).distinct()
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(pod__project_id=project_id)

        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(app_id=app_id)
        
        # Filter by service_type if provided
        service_type = self.request.query_params.get('service_type')
        if service_type:
            queryset = queryset.filter(service_type=service_type)
        
        return queryset
    
    def list(self, request, *args, **kwargs):
        """List services with live status and port sync from compose file."""
        queryset = list(self.get_queryset())  # Evaluate queryset to list

        # --- Auto-sync: create ProjectService records from compose file if not yet in DB ---
        project_id_param = request.query_params.get('project')
        app_id_param = request.query_params.get('app')

        if project_id_param:
            try:
                target_project = Project.objects.get(pk=int(project_id_param))
                volume_name = f"proj-{target_project.id}-workspace"

                target_app = None
                if app_id_param:
                    try:
                        target_app = App.objects.get(pk=int(app_id_param), environment__project=target_project)
                    except App.DoesNotExist:
                        pass

                # 1. Try reading compose file from workspace volume
                compose_text = None
                try:
                    workspace_init = WorkspaceInitializer(volume_name)
                    compose_text = workspace_init._read_compose_file()
                except Exception:
                    pass

                # 2. Fall back to raw-compose stored in AppSourceSettings.source_location
                if not compose_text and target_app:
                    try:
                        source_settings = AppSourceSettings.objects.get(app=target_app)
                        if source_settings.source_kind == 'raw-compose' and source_settings.source_location:
                            compose_text = source_settings.source_location
                    except AppSourceSettings.DoesNotExist:
                        pass

                if compose_text:
                    try:
                        compose_data = load_compose_from_text(compose_text)
                        orch_tmp = PodmanOrchestrator()
                        limits = orch_tmp._get_resource_limits(target_project.workspace_size)
                        specs, _ = build_service_specs(
                            compose=compose_data,
                            project_id=target_project.id,
                            workspace_volume=volume_name,
                            network_name=f"proj-{target_project.id}-net",
                            default_cpu=limits.get('cpu', '1.0'),
                            default_mem=limits.get('memory', '2g'),
                        )

                        existing_names = {s.name for s in queryset}

                        # Ensure a pod record exists for this project
                        pod_defaults = {'pod_name': f'proj-{target_project.id}-pod', 'status': 'stopped'}
                        if target_app:
                            pod_defaults['environment'] = target_app.environment
                        else:
                            first_env = Environment.objects.filter(project=target_project).first()
                            if first_env:
                                pod_defaults['environment'] = first_env
                        pod, _ = ProjectPod.objects.get_or_create(project=target_project, defaults=pod_defaults)

                        new_services = []
                        for spec in specs:
                            if spec.name in existing_names:
                                continue
                            container_name = build_service_container_name(target_project.id, spec.name)
                            # Strip workspace volume auto-mount from stored config
                            config_volumes = [v for v in (spec.volumes or []) if v.get('source') != volume_name]
                            svc, _ = ProjectService.objects.get_or_create(
                                pod=pod,
                                name=spec.name,
                                defaults=dict(
                                    app=target_app,
                                    service_type=spec.service_type or 'custom',
                                    image=spec.image or '',
                                    container_name=container_name,
                                    status='stopped',
                                    ports=spec.ports or [],
                                    environment=spec.environment or {},
                                    config={'depends_on': spec.depends_on, 'volumes': config_volumes},
                                    cpu_limit=spec.cpu_limit,
                                    memory_limit=spec.memory_limit,
                                    autostart=spec.autostart,
                                ),
                            )
                            new_services.append(svc)

                        queryset.extend(new_services)
                    except Exception as sync_exc:
                        logging.debug(f"Could not auto-sync compose services for project {target_project.id}: {sync_exc}")
            except (ValueError, Project.DoesNotExist):
                pass
        # --- End auto-sync ---

        # Group services by project for efficient compose file reading
        services_by_project = {}
        for service in queryset:
            project_id = service.pod.project_id
            if project_id not in services_by_project:
                services_by_project[project_id] = []
            services_by_project[project_id].append(service)
        
        orchestrator = PodmanOrchestrator()
        
        for project_id, services in services_by_project.items():
            project = services[0].pod.project
            volume_name = f"proj-{project_id}-workspace"
            
            # Try to read compose file and extract current ports
            compose_ports = {}
            try:
                initializer = WorkspaceInitializer(volume_name)
                compose_text = initializer._read_compose_file()
                if compose_text:
                    compose_data = load_compose_from_text(compose_text)
                    specs, _ = build_service_specs(
                        compose=compose_data,
                        project_id=project_id,
                        workspace_volume=volume_name,
                        network_name=f"proj-{project_id}-net",
                        default_cpu="1.0",
                        default_mem="2g",
                    )
                    for spec in specs:
                        compose_ports[spec.name] = spec.ports
            except Exception as e:
                logging.debug(f"Could not read compose file for project {project_id}: {e}")
            
            # Sync status and ports for each service
            for service in services:
                # Sync status
                try:
                    live_status = orchestrator.get_service_status(project_id, service.name)
                    if live_status.status != service.status:
                        service.status = live_status.status
                        if live_status.status == 'running' and live_status.started_at:
                            service.last_started_at = live_status.started_at
                        service.save(update_fields=['status', 'last_started_at'])
                except OrchestratorError:
                    if service.status != 'stopped':
                        service.status = 'stopped'
                        service.save(update_fields=['status'])
                
                # Sync ports from compose file if different
                if service.name in compose_ports:
                    live_ports = compose_ports[service.name]
                    if service.ports != live_ports:
                        logging.info(f"Updating ports for service {service.name}: {service.ports} -> {live_ports}")
                        service.ports = live_ports
                        service.save(update_fields=['ports'])
        
        # Re-serialize with updated data
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        app = serializer.validated_data.get('app')
        if not app:
            raise ValidationError({'app': 'An application is required to create a service.'})

        project = app.environment.project
        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied('You do not have permission to create services for this project')

        pod, _ = ProjectPod.objects.get_or_create(
            project=project,
            defaults={
                'environment': app.environment,
                'pod_name': f'proj-{project.id}-pod',
                'status': 'stopped',
            },
        )

        if app.environment_id and pod.environment_id != app.environment_id:
            pod.environment = app.environment
            pod.save(update_fields=['environment'])

        container_name = serializer.validated_data.get('container_name') or build_service_container_name(
            project.id,
            serializer.validated_data.get('name', ''),
        )
        serializer.save(pod=pod, container_name=container_name)

    def perform_update(self, serializer):
        service = self.get_object()
        project = service.pod.project

        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied('You do not have permission to update services for this project')

        app = serializer.validated_data.get('app', service.app)
        if app and app.environment.project_id != project.id:
            raise ValidationError({'app': 'The selected application must belong to the same project as this service.'})

        serializer.save()

        if app and service.pod.environment_id != app.environment_id:
            service.pod.environment = app.environment
            service.pod.save(update_fields=['environment'])

    def perform_destroy(self, instance):
        project = instance.pod.project
        if not user_can_manage_project(self.request.user, project):
            raise PermissionDenied('You do not have permission to delete services for this project')
        instance.delete()
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a stopped service."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        logging.info(f"User {request.user.id} attempting to start service '{service.name}' for project {project.id}")
        orchestrator = PodmanOrchestrator()
        
        try:
            service_status = orchestrator.start_service(project.id, service.name)
            return Response({
                'status': 'success',
                'service': {
                    'name': service.name,
                    'container_name': service_status.container_name,
                    'status': service_status.status,
                    'started_at': service_status.started_at,
                }
            })
        except OrchestratorError as exc:
            logging.error(f"User {request.user.id} failed to start service '{service.name}' for project {project.id}: {str(exc)}", exc_info=True)
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """Stop a running service."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        logging.info(f"User {request.user.id} attempting to stop service '{service.name}' for project {project.id}")
        orchestrator = PodmanOrchestrator()
        
        try:
            service_status = orchestrator.stop_service(project.id, service.name)
            return Response({
                'status': 'success',
                'service': {
                    'name': service.name,
                    'container_name': service_status.container_name,
                    'status': service_status.status,
                }
            })
        except OrchestratorError as exc:
            logging.error(f"User {request.user.id} failed to stop service '{service.name}' for project {project.id}: {str(exc)}", exc_info=True)
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """Restart a service."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        logging.info(f"User {request.user.id} attempting to restart service '{service.name}' for project {project.id}")
        orchestrator = PodmanOrchestrator()
        
        try:
            service_status = orchestrator.restart_service(project.id, service.name)
            return Response({
                'status': 'success',
                'service': {
                    'name': service.name,
                    'container_name': service_status.container_name,
                    'status': service_status.status,
                    'started_at': service_status.started_at,
                }
            })
        except OrchestratorError as exc:
            logging.error(f"User {request.user.id} failed to restart service '{service.name}' for project {project.id}: {str(exc)}", exc_info=True)
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def kill(self, request, pk=None):
        """Forcefully kill a service."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        logging.info(f"User {request.user.id} attempting to kill service '{service.name}' for project {project.id}")
        orchestrator = PodmanOrchestrator()
        
        try:
            service_status = orchestrator.kill_service(project.id, service.name)
            return Response({
                'status': 'success',
                'service': {
                    'name': service.name,
                    'container_name': service_status.container_name,
                    'status': service_status.status,
                }
            })
        except OrchestratorError as exc:
            logging.error(f"User {request.user.id} failed to kill service '{service.name}' for project {project.id}: {str(exc)}", exc_info=True)
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def recreate(self, request, pk=None):
        """Recreate an orphaned container (DB record exists but container is missing)."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        logging.info(f"User {request.user.id} recreating service '{service.name}' for project {project.id}")
        orchestrator = PodmanOrchestrator()
        
        try:
            container_name = service.container_name or orchestrator._generate_container_name(project.id, service.name)
            
            # Force remove the old container if it exists
            if orchestrator._container_exists(container_name):
                try:
                    orchestrator._run(['rm', '-f', container_name], timeout=30)
                except OrchestratorError:
                    pass
            
            # Try to read compose file to get the full service spec
            volume_name = f"proj-{project.id}-workspace"
            service_spec = None
            
            try:
                initializer = WorkspaceInitializer(volume_name)
                compose_text = initializer._read_compose_file()
                if compose_text:
                    compose_data = load_compose_from_text(compose_text)
                    specs, _ = build_service_specs(
                        compose=compose_data,
                        project_id=project.id,
                        workspace_volume=volume_name,
                        network_name=f"proj-{project.id}-net",
                        default_cpu="1.0",
                        default_mem="2g",
                    )
                    for spec in specs:
                        if spec.name == service.name:
                            service_spec = spec
                            break
            except Exception as e:
                logging.warning(f"Could not read compose file for recreate: {e}")
            
            if service_spec:
                # Recreate from compose spec
                orchestrator.ensure_service(project.id, service_spec)
            elif service.service_type == 'ai-workspace':
                # Recreate workspace service
                orchestrator.ensure_workspace_service(project.id, user_id=request.user.id)
            else:
                # Fallback: reconstruct ServiceSpec from the DB record
                logging.info(f"Reconstructing ServiceSpec from DB for service '{service.name}'")
                from .orchestrator import ServiceSpec as _ServiceSpec
                fallback_spec = _ServiceSpec(
                    name=service.name,
                    service_type=service.service_type,
                    image=service.image,
                    ports=service.ports or [],
                    environment=service.environment or {},
                    volumes=[{
                        'type': 'volume',
                        'source': volume_name,
                        'target': '/workspace',
                        'readonly': False,
                    }],
                    cpu_limit=service.cpu_limit,
                    memory_limit=service.memory_limit,
                    network=f"proj-{project.id}-net",
                    autostart=service.autostart,
                    workdir=(service.config or {}).get('workdir'),
                    labels=(service.config or {}).get('labels', {}),
                    depends_on=(service.config or {}).get('depends_on', []),
                )
                orchestrator.ensure_service(project.id, fallback_spec)
            
            # Refresh service from DB
            service.refresh_from_db()
            
            return Response({
                'status': 'success',
                'message': f"Service '{service.name}' recreated successfully",
                'service': {
                    'id': service.id,
                    'name': service.name,
                    'container_name': service.container_name,
                    'status': service.status,
                },
            })
        except Exception as exc:
            logging.error(f"Failed to recreate service '{service.name}': {exc}", exc_info=True)
            return Response(
                {'error': str(exc), 'error_type': 'recreate_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def logs(self, request, pk=None):
        """Retrieve service logs."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        # Parse query parameters
        tail = int(request.query_params.get('tail', 1000))
        since = request.query_params.get('since', None)
        
        orchestrator = PodmanOrchestrator()
        
        try:
            log_entry = orchestrator.get_service_logs(project.id, service.name, tail=tail, since=since)
            return Response({
                'status': 'success',
                'logs': log_entry.logs,
                'truncated': log_entry.truncated,
                'service': {
                    'name': service.name,
                    'container_name': service.container_name,
                }
            })
        except OrchestratorError as exc:
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['delete'])
    def delete(self, request, pk=None):
        """Delete a service."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        logging.info(f"User {request.user.id} attempting to delete service '{service.name}' for project {project.id}")
        orchestrator = PodmanOrchestrator()
        
        try:
            orchestrator.delete_service(project.id, service.name)
            return Response({'status': 'success'})
        except OrchestratorError as exc:
            logging.error(f"User {request.user.id} failed to delete service '{service.name}' for project {project.id}: {str(exc)}", exc_info=True)
            return Response(
                {'error': str(exc), 'error_type': 'orchestrator_error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def stats(self, request, pk=None):
        """Get live container stats (CPU, memory, disk) for a service."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        try:
            import subprocess
            import json
            
            # Use podman stats to get live container metrics
            binary = os.getenv('PODMAN_BIN', 'podman')
            result = subprocess.run(
                [binary, 'stats', service.container_name, '--format=json', '--no-stream'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                try:
                    stats_data = json.loads(result.stdout)
                    if isinstance(stats_data, list) and len(stats_data) > 0:
                        stats = stats_data[0]
                        return Response({
                            'status': 'success',
                            'cpu_percent': stats.get('CPU', '0%').rstrip('%'),
                            'memory_used': stats.get('MemUsage', '0B'),
                            'memory_percent': stats.get('MemPerc', '0%').rstrip('%'),
                            'block_input': stats.get('BlockInput', '0B'),
                            'block_output': stats.get('BlockOutput', '0B'),
                            'net_input': stats.get('NetInput', '0B'),
                            'net_output': stats.get('NetOutput', '0B'),
                            'pids': stats.get('PIDs', 0),
                            'container_name': service.container_name,
                        })
                except json.JSONDecodeError:
                    pass
            
            return Response({
                'status': 'error',
                'message': 'Could not retrieve container stats'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except subprocess.TimeoutExpired:
            return Response({
                'status': 'error',
                'message': 'Container stats request timed out'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except Exception as e:
            logging.error(f"Failed to get stats for service {service.name}: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def top(self, request, pk=None):
        """Get live process list for a running container (htop-style)."""
        service = self.get_object()
        project = service.pod.project
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        try:
            import subprocess
            
            binary = os.getenv('PODMAN_BIN', 'podman')
            result = subprocess.run(
                [binary, 'top', service.container_name, '-eo', 'pid,user,pcpu,pmem,args'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                processes = []
                if len(lines) > 1:
                    # First line is the header
                    for line in lines[1:]:
                        parts = line.split(None, 4)
                        if len(parts) >= 4:
                            processes.append({
                                'pid': parts[0],
                                'user': parts[1],
                                'cpu': parts[2],
                                'mem': parts[3],
                                'command': parts[4] if len(parts) > 4 else '',
                            })
                
                return Response({
                    'status': 'success',
                    'container_name': service.container_name,
                    'processes': processes,
                })
            else:
                return Response({
                    'status': 'error',
                    'message': result.stderr or 'Container may not be running'
                }, status=status.HTTP_400_BAD_REQUEST)
        except subprocess.TimeoutExpired:
            return Response({
                'status': 'error',
                'message': 'Process list request timed out'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except Exception as e:
            logging.error(f"Failed to get process list for service {service.name}: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def sync_check(self, request):
        """Check for orphaned containers - DB records without actual Podman containers."""
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({'error': 'project_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if not user_has_project_access(request.user, project):
            raise PermissionDenied('You do not have access to this project')
        
        try:
            import subprocess
            import json
            
            binary = os.getenv('PODMAN_BIN', 'podman')
            
            # Get all Podman containers
            result = subprocess.run(
                [binary, 'ps', '--all', '--format=json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                return Response({
                    'status': 'error',
                    'message': 'Failed to query Podman containers'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            try:
                containers_data = json.loads(result.stdout)
            except json.JSONDecodeError:
                containers_data = []
            
            # Build set of actual container names
            actual_containers = {c['Names'][0] if c.get('Names') else '' for c in containers_data if c.get('Names')}
            
            # Get DB records for this project's services
            services = ProjectService.objects.filter(pod__project=project)
            
            orphaned = []
            synced = []
            
            for service in services:
                if service.container_name in actual_containers:
                    synced.append({
                        'id': service.id,
                        'name': service.name,
                        'container_name': service.container_name,
                        'status': 'synced'
                    })
                else:
                    orphaned.append({
                        'id': service.id,
                        'name': service.name,
                        'container_name': service.container_name,
                        'status': 'orphaned'
                    })
            
            return Response({
                'status': 'success',
                'synced_count': len(synced),
                'orphaned_count': len(orphaned),
                'synced': synced,
                'orphaned': orphaned,
            })
        except subprocess.TimeoutExpired:
            return Response({
                'status': 'error',
                'message': 'Sync check timed out'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except Exception as e:
            logging.error(f"Failed to sync check for project {project_id}: {str(e)}")
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProjectToolViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectToolSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ProjectTool.objects.filter(
            models.Q(project__owner=self.request.user) |
            models.Q(project__contributors=self.request.user)
        )
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        return queryset

    def perform_create(self, serializer):
        project = serializer.validated_data.get('project')
        if not user_has_project_access(self.request.user, project):
            raise PermissionDenied('You do not have access to this project')
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        project = serializer.instance.project
        if not user_has_project_access(self.request.user, project):
            raise PermissionDenied('You do not have access to this project')
        serializer.save()

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        tool = self.get_object()
        payload = request.data.get('arguments', {})
        manager = PodmanManager(tool.project)
        execution = ToolExecution.objects.create(
            tool=tool,
            session=None,
            input_payload=payload,
            status='running'
        )
        try:
            result = manager.run_tool(tool, payload)
            execution.status = 'succeeded'
            execution.output_payload = result
            execution.logs = (result.get('stdout') or '') + (result.get('stderr') or '')
            execution.exit_code = 0
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'output_payload', 'logs', 'exit_code', 'completed_at'])
            return Response({'output': result})
        except ToolExecutionError as exc:
            execution.status = 'failed'
            execution.logs = str(exc)
            execution.exit_code = 1
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'logs', 'exit_code', 'completed_at'])
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ToolExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ToolExecutionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ToolExecution.objects.filter(
            models.Q(tool__project__owner=self.request.user) |
            models.Q(tool__project__contributors=self.request.user)
        )


# Chatbot ViewSets

async def get_workspace_context(project):
    """
    Gather workspace context information for injection into LLM system prompts.
    Returns a formatted string with workspace configuration, resources, and structure.
    """
    if not project:
        return None
    
    from asgiref.sync import sync_to_async
    
    try:
        # Get workspace configuration
        workspace_config = await sync_to_async(lambda: project.workspace_config)()
        workspace_size = await sync_to_async(lambda: project.workspace_size)()
        workspace_image = await sync_to_async(lambda: project.workspace_image)()
        
        if not workspace_config:
            return None  # No workspace configured for this project
        
        # Get resource tier information
        workspace_tier_id = await sync_to_async(lambda: project.workspace_tier_id)()
        tier_info = ""
        if workspace_tier_id:
            try:
                tier = await sync_to_async(WorkspaceResourceTier.objects.get)(id=workspace_tier_id)
                tier_info = (
                    f"\nResource Tier: {tier.name}\n"
                    f"  - CPU: {tier.cpu_request} (limit: {tier.cpu_limit})\n"
                    f"  - Memory: {tier.memory_request} (limit: {tier.memory_limit})\n"
                    f"  - Storage: {tier.storage_limit}"
                )
            except:
                pass
        
        # Get available tools
        tools = await sync_to_async(lambda: list(project.tools.filter(is_active=True).values('name', 'slug', 'description')))()
        tools_info = ""
        if tools:
            tools_list = ", ".join([f"{t['name']} ({t['slug']})" for t in tools])
            tools_info = f"\nAvailable Tools: {tools_list}"
        
        # Build workspace context string
        context_parts = [
            f"Workspace Configuration:\n"
            f"  - Image: {workspace_image or 'default'}\n"
            f"  - Size Mode: {workspace_size or 'standard'}"
        ]
        
        if tier_info:
            context_parts.append(tier_info)
        
        if tools_info:
            context_parts.append(tools_info)
        
        context_parts.append(
            "\nYou have access to a development workspace container. "
            "You can use the available tools to execute commands, manage files, and control the workspace."
        )
        
        return "\n".join(context_parts)
    
    except Exception as e:
        print(f"Error gathering workspace context: {e}")
        return None


class ChatSessionViewSet(viewsets.ModelViewSet):
    queryset = ChatSession.objects.all()
    serializer_class = ChatSessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        session = serializer.save(user=self.request.user)
        
        # If session was started by persona, send initial AI greeting
        if session.started_by_persona and session.persona:
            import asyncio
            try:
                initial_message = f"Hello! I'm {session.persona.name}. How can I help you today?"
                # use LLM to generate a more personalized greeting using the persona's system prompt
            
                ChatMessage.objects.create(
                    session=session,
                    message_type='assistant',
                    content=initial_message
                )
            except Exception as e:
                print(f"Failed to create initial persona message: {e}")
        
        # If session was started by template, send initial AI message with template
        elif session.template:
            import asyncio
            try:
                template = session.template
                initial_message = template.user_prompt_template or f"Hello! I'm ready to help with {template.name}."
                ChatMessage.objects.create(
                    session=session,
                    message_type='assistant',
                    content=initial_message
                )
            except Exception as e:
                print(f"Failed to create initial template message: {e}")

    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Send a message to the chat session and get AI response"""
        
        try:
            session = self.get_object()
            message_content = request.data.get('message')
            llm_id = request.data.get('llm_id')
            temperature = request.data.get('temperature')
            mode = request.data.get('mode')
            persona_id = request.data.get('persona')
            enabled_tools = request.data.get('enabled_tools')
            
            if not message_content:
                return Response({'error': 'Message content is required'}, status=400)
            
            # Update session with provided settings
            if llm_id:
                session.llm_id = llm_id
            if temperature is not None:
                session.temperature = temperature
            if mode and mode in dict(ChatSession.MODE_CHOICES):
                session.mode = mode
            if persona_id:
                session.persona_id = persona_id
            if enabled_tools is not None:
                if not session.project:
                    return Response({'error': 'Project context is required to enable tools'}, status=400)
                tools_qs = ProjectTool.objects.filter(id__in=enabled_tools, project=session.project, is_active=True)
                session.enabled_tools.set(tools_qs)
            session.save()
            
            # Save user message
            user_message = ChatMessage.objects.create(
                session=session,
                message_type='user',
                content=message_content
            )
        except Exception as e:
            print(f"Error saving user message: {e}")
            return Response({'ai_message': str(e)}, status=500)
            
        # Get AI response - handle agent mode differently
        try:
            if session.mode == 'agent' and session.project and session.project.agent_framework == 'langgraph':
                # Use LangGraph agent
                ai_response = async_to_sync(self._run_langgraph_agent)(session, message_content)

                # Save AI message with agent data
                ai_message = ChatMessage.objects.create(
                    session=session,
                    message_type='assistant',
                    content=ai_response.get('content', ''),
                    reasoning=ai_response.get('reasoning', ''),
                    tool_calls=ai_response.get('tool_calls', []),
                    metadata={'todos': ai_response.get('todos', [])}
                )

                # Update session iteration count
                session.agent_iterations += ai_response.get('iterations', 0)
                session.save(update_fields=['agent_iterations'])
            else:
                # Use traditional response generation
                ai_response = async_to_sync(self._aget_ai_response)(session, message_content)

                processed_tool_output = self._process_tool_call(session, ai_response)
                final_response = processed_tool_output or ai_response

                # Save AI message
                ai_message = ChatMessage.objects.create(
                    session=session,
                    message_type='assistant',
                    content=final_response
                )
            
            # Store token usage and cost data if available
            if hasattr(session, '_last_response_tokens'):
                token_data = session._last_response_tokens
                ai_message.prompt_tokens = token_data.get('prompt_tokens')
                ai_message.completion_tokens = token_data.get('completion_tokens')
                ai_message.total_tokens = token_data.get('total_tokens')
                ai_message.estimated_cost = token_data.get('estimated_cost')
                ai_message.used_by_provider = token_data.get('provider')
                ai_message.save()
                
                # Clean up temp data
                delattr(session, '_last_response_tokens')
            
            return Response({
                'user_message': ChatMessageSerializer(user_message).data,
                'ai_message': ChatMessageSerializer(ai_message).data
            })
        except Exception as e:
            print(f"Error generating AI response: {e}")
            return Response({'ai_message': str(e)}, status=500)

    async def _run_langgraph_agent(self, session, user_message):
        """Run LangGraph agent for the session."""
        from api.frameworks.langgraph import create_agent, run_agent_stream

        # Get workspace container
        container_name = f"proj-pod-{session.project.id}-workspace-shared"

        # Create agent (wrap synchronous call in sync_to_async)
        graph = await sync_to_async(create_agent)(session, container_name)

        # Collect results
        reasoning_parts = []
        tool_calls = []
        final_content = ""
        iterations = 0
        todos = []

        # Run agent and collect events
        async for event in run_agent_stream(graph, user_message, session.id):
            if event['type'] == 'thinking':
                reasoning_parts.append(event['content'])
            elif event['type'] == 'tool_start':
                tool_calls.append({
                    'id': f"call_{len(tool_calls)}",
                    'name': event['name'],
                    'arguments': event['args'],
                    'status': 'running'
                })
            elif event['type'] == 'tool_end':
                # Update last tool call with result
                if tool_calls:
                    tool_calls[-1]['status'] = 'completed'
                    tool_calls[-1]['output'] = event['output']
            elif event['type'] == 'todos_update':
                todos = event['todos']
            elif event['type'] == 'final':
                final_content = event['content']
                iterations += 1

        return {
            'content': final_content,
            'reasoning': '\n'.join(reasoning_parts),
            'tool_calls': tool_calls,
            'iterations': iterations,
            'todos': todos
        }

    def _process_tool_call(self, session, ai_response):
        """Inspect AI response for tool call instructions and execute when needed."""
        if not session.project:
            return None

        import re
        
        # Try to extract JSON from the response (it might be embedded in text)
        json_match = re.search(r'\{.*\}', ai_response)
        if not json_match:
            return None
            
        try:
            payload = json.loads(json_match.group())
        except (TypeError, ValueError):
            return None

        if not isinstance(payload, dict) or 'tool' not in payload:
            return None

        tool_slug = payload.get('tool')
        arguments = payload.get('arguments', {})
        if not tool_slug:
            return None

        tool = session.enabled_tools.filter(slug=tool_slug, is_active=True).first()
        if not tool:
            return f"Requested tool '{tool_slug}' is not available."

        execution = ToolExecution.objects.create(
            tool=tool,
            session=session,
            input_payload=arguments or {},
            status='running'
        )

        manager = PodmanManager(session.project)
        try:
            result = manager.run_tool(tool, arguments)
            logs = (result.get('stdout') or '') + (result.get('stderr') or '')
            execution.status = 'succeeded'
            execution.output_payload = result
            execution.logs = logs
            execution.exit_code = 0
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'output_payload', 'logs', 'exit_code', 'completed_at'])
            output = result.get('stdout') or 'Tool executed successfully with no output.'
            return f"Tool `{tool.name}` output:\n{output}"
        except ToolExecutionError as exc:
            execution.status = 'failed'
            execution.logs = str(exc)
            execution.exit_code = 1
            execution.completed_at = timezone.now()
            execution.save(update_fields=['status', 'logs', 'exit_code', 'completed_at'])
            return f"Tool `{tool.name}` failed: {exc}"

    async def _aget_ai_response(self, session, user_message):
        """Generate AI response using hierarchical provider resolution"""
        from asgiref.sync import sync_to_async
        
        # Get persona, template, project, and enabled tools
        persona = await sync_to_async(lambda: session.persona)()
        template = await sync_to_async(lambda: session.template)()
        project = await sync_to_async(lambda: session.project)()
        enabled_tools = await sync_to_async(lambda: list(session.enabled_tools.filter(is_active=True).values('name', 'slug', 'description', 'args_schema')))()
        
        # Build system prompt
        system_prompt_parts = []
        if persona and persona.system_prompt:
            system_prompt_parts.append(persona.system_prompt)
        elif template and template.system_prompt:
            system_prompt_parts.append(template.system_prompt)
        
        # Add project-specific system prompt if available
        if project and project.system_prompt:
            system_prompt_parts.append(f"Project Context: {project.name}\n{project.system_prompt}")
        
        # Add workspace context if project has workspace configured
        if project:
            workspace_context = await get_workspace_context(project)
            if workspace_context:
                system_prompt_parts.append(f"Workspace Context:\n{workspace_context}")
        
        # Mode-specific guidance
        mode_instructions = {
            'ask': 'Answer user questions directly using the provided project context.',
            'plan': 'Break work into actionable steps, highlight dependencies, and confirm before executing tools.',
            'agent': 'Act autonomously: decide when to call tools to complete the request, narrate your reasoning briefly.',
            'persona': 'Adopt the selected persona tone and constraints when replying.',
        }
        mode_text = mode_instructions.get(session.mode)
        if mode_text:
            system_prompt_parts.append(f"Chat Mode: {session.mode.upper()} - {mode_text}")

        # Tool availability instructions
        if enabled_tools:
            tool_doc = json.dumps(enabled_tools, indent=2)
            system_prompt_parts.append(
                "Available project tools:\n"
                + tool_doc + "\n\n"
                + "To use a tool, respond with ONLY a JSON object in this exact format:\n"
                + '{"tool": "tool-slug", "arguments": {...}}'
            )
            
            # Special instructions for execute-command tool
            execute_tool = next((t for t in enabled_tools if t['slug'] == 'execute-command'), None)
            if execute_tool:
                system_prompt_parts.append("""
You have access to execute commands in project containers. Use the execute-command tool to run commands within /workspace.

Available containers: frontend, backend, database, services

To execute a command, respond with ONLY this JSON:
{"tool": "execute-command", "arguments": {"command": "ls -la /workspace", "container": "backend"}}

Examples:
- List files: {"tool": "execute-command", "arguments": {"command": "ls -la /workspace/src"}}
- Read file: {"tool": "execute-command", "arguments": {"command": "cat /workspace/package.json"}}
- Run Python script: {"tool": "execute-command", "arguments": {"command": "python /workspace/script.py", "container": "backend"}}
- Execute SQL: {"tool": "execute-command", "arguments": {"command": "psql -d mydb -c 'SELECT * FROM users;'", "container": "database"}}

Commands are restricted to safe operations and /workspace directory only. For complex multi-step tasks, break them down and execute one command at a time.

IMPORTANT: When using tools, respond with ONLY the JSON object, no other text or explanation.
""")
        
        system_prompt = "\n\n".join(system_prompt_parts)
        
        try:
            # Resolve provider hierarchy: user → project → team → system
            provider = await sync_to_async(self._resolve_provider_hierarchy)(session)
            
            if not provider:
                print(f"WARNING: No LLM provider found for user {session.user.username}. Please configure an LLM provider in Settings.")
                # Fallback to legacy llm_config system
                llm_manager = get_llm_manager()
                if session.llm_id:
                    llm_config = llm_manager.get_llm_config(session.llm_id)
                else:
                    llm_config = llm_manager.get_llm_config()
                
                if session.temperature is not None:
                    llm_config.temperature = session.temperature
                
                return await self._call_litemaas_api(llm_config, user_message, system_prompt, None, None)
            
            print(f"Using provider: {provider.instance_name} ({provider.provider_type})")
            # Use new provider system
            response = await self._call_provider_api(provider, session, user_message, system_prompt)
            return response.get('content', '')
            
        except Exception as e:
            print(f"AI response error: {e}")
            import traceback
            traceback.print_exc()
            return await self._get_fallback_response(session, user_message, system_prompt, str(e))
    
    def _resolve_provider_hierarchy(self, session):
        """Resolve which provider to use based on hierarchy: user → project → team → system"""
        # Ensure we access related objects synchronously or wrap in sync_to_async if called from async context
        # Since this method is called from both sync (stream generator) and async contexts, we handle it carefully.
        # But wait - this is a sync method. The caller should manage async/sync context. 
        # The issue is accessing session.user inside async _generate_summary -> sync _resolve_provider_hierarchy
        # without prefetching or sync_to_async.
        
        # Access relationships safely
        user = session.user
        project = session.project
        
        # If session has a provider set, use it
        if session.provider:
            return session.provider
        
        # If session has selected_model, find provider that has this model
        if session.selected_model:
            # Try user-level providers first
            for provider in LLMProvider.objects.filter(scope='user', scope_user=user, is_active=True):
                if any(model.get('id') == session.selected_model for model in provider.available_models):
                    return provider
            
            # Try project-level providers
            if project:
                for provider in LLMProvider.objects.filter(scope='project', scope_project=project, is_active=True):
                    if any(model.get('id') == session.selected_model for model in provider.available_models):
                        return provider
                
                # Try team-level providers
                if project.team:
                    for provider in LLMProvider.objects.filter(scope='team', scope_team=project.team, is_active=True):
                        if any(model.get('id') == session.selected_model for model in provider.available_models):
                            return provider
            
            # Try system-level providers
            for provider in LLMProvider.objects.filter(scope='system', is_active=True):
                if any(model.get('id') == session.selected_model for model in provider.available_models):
                    return provider
        
        # NEW: Check user's default_llm_model if no specific model selected
        if user.default_llm_model:
            # Try user-level providers first
            for provider in LLMProvider.objects.filter(scope='user', scope_user=user, is_active=True):
                if any(model.get('id') == user.default_llm_model for model in provider.available_models):
                    print(f"Using user's default model: {user.default_llm_model} from user provider {provider.instance_name}")
                    session.selected_model = user.default_llm_model
                    return provider
            
            # Try project-level providers
            if project:
                for provider in LLMProvider.objects.filter(scope='project', scope_project=project, is_active=True):
                    if any(model.get('id') == user.default_llm_model for model in provider.available_models):
                        print(f"Using user's default model: {user.default_llm_model} from project provider {provider.instance_name}")
                        session.selected_model = user.default_llm_model
                        return provider
                
                # Try team-level providers
                if project.team:
                    for provider in LLMProvider.objects.filter(scope='team', scope_team=project.team, is_active=True):
                        if any(model.get('id') == user.default_llm_model for model in provider.available_models):
                            print(f"Using user's default model: {user.default_llm_model} from team provider {provider.instance_name}")
                            session.selected_model = user.default_llm_model
                            return provider
            
            # Try system-level providers
            for provider in LLMProvider.objects.filter(scope='system', is_active=True):
                if any(model.get('id') == user.default_llm_model for model in provider.available_models):
                    print(f"Using user's default model: {user.default_llm_model} from system provider {provider.instance_name}")
                    session.selected_model = user.default_llm_model
                    return provider
        
        # No specific model selected and no default, use first available provider in hierarchy
        # User-level
        provider = LLMProvider.objects.filter(
            scope='user',
            scope_user=user,
            is_active=True
        ).first()
        if provider:
            return provider
        
        # Project-level
        if project:
            provider = LLMProvider.objects.filter(
                scope='project',
                scope_project=project,
                is_active=True
            ).first()
            if provider:
                return provider
            
            # Team-level
            if project.team:
                provider = LLMProvider.objects.filter(
                    scope='team',
                    scope_team=project.team,
                    is_active=True
                ).first()
                if provider:
                    return provider
        
        # System-level (fallback)
        return LLMProvider.objects.filter(
            scope='system',
            is_active=True
        ).first()
    
    async def _call_provider_api(self, provider, session, user_message, system_prompt, tools=None, max_tokens=None):
        """Make API call using the resolved provider with cost tracking and optional tool support"""
        import aiohttp
        from asgiref.sync import sync_to_async
        
        try:
            # Get API key and configuration
            try:
                api_key = provider.get_api_key() if provider.api_key else None
            except ValueError as decrypt_error:
                # Decryption failed - encryption key changed
                raise ValueError(
                    f"Cannot decrypt API key for provider '{provider.instance_name}'. "
                    "The encryption key may have changed. Please go to Settings and "
                    "re-enter your API key for this provider."
                ) from decrypt_error
            
            base_url = provider.base_url
            
            # Validate base_url exists
            if not base_url:
                raise ValueError(
                    f"Provider '{provider.instance_name}' has no base_url configured. "
                    "Please edit the provider in Settings and add a base URL."
                )
            
            # Determine model to use
            model = session.selected_model
            if not model and provider.available_models:
                # Use first available model as default
                model = provider.available_models[0].get('id') if provider.available_models else None
            
            if not model:
                raise ValueError(f"No model specified for provider {provider.instance_name}")
            
            # Get temperature from session or default
            temperature = session.temperature if session.temperature is not None else 0.7
            # max_tokens: None = unlimited (let model use its own default)
            
            # Build URL based on provider type
            if provider.provider_type in ['openai', 'openrouter', 'litemaas', 'vllm', 'custom']:
                url = f"{base_url.rstrip('/')}/chat/completions"
            elif provider.provider_type == 'anthropic':
                url = f"{base_url.rstrip('/')}/v1/messages"
            else:
                raise ValueError(f"Unsupported provider type: {provider.provider_type}")
            
            # Build headers
            headers = {"Content-Type": "application/json"}
            if api_key:
                if provider.provider_type == 'anthropic':
                    headers["x-api-key"] = api_key
                    headers["anthropic-version"] = "2023-06-01"
                else:
                    headers["Authorization"] = f"Bearer {api_key}"
            
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_message})
            
            # Build request data
            data = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            if max_tokens:
                data["max_tokens"] = int(max_tokens)
            
            # Add tools if provider supports function calling and tools are provided
            if provider.supports_function_calling and tools:
                if provider.provider_type == 'anthropic':
                    # Anthropic uses 'tools' parameter
                    data["tools"] = tools
                else:
                    # OpenAI-compatible providers use 'tools' or 'functions'
                    data["tools"] = tools
                    data["tool_choice"] = "auto"
            
            print(f"Making request to {provider.provider_type}: {url}")
            print(f"Model: {model}")
            if tools and provider.supports_function_calling:
                print(f"Using native tool calling with {len(tools)} tools")
            
            # Make the async HTTP request
            async with aiohttp.ClientSession() as http_session:
                async with http_session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Extract response content and token usage
                        content = None
                        usage_data = result.get('usage', {})
                        tool_calls = []
                        
                        if provider.provider_type == 'anthropic':
                            content = result.get('content', [{}])[0].get('text')
                            # Extract tool calls from Anthropic response
                            for content_block in result.get('content', []):
                                if content_block.get('type') == 'tool_use':
                                    tool_calls.append({
                                        'id': content_block.get('id'),
                                        'type': 'tool_call',
                                        'name': content_block.get('name'),
                                        'args': content_block.get('input', {})
                                    })
                        else:
                            # OpenAI-compatible response
                            if 'choices' in result and len(result['choices']) > 0:
                                choice = result['choices'][0]
                                message = choice.get('message', {})
                                content = message.get('content', '')
                                
                                # Extract tool calls if present
                                if 'tool_calls' in message:
                                    tool_calls = []
                                    for tc in message['tool_calls']:
                                        # Convert OpenAI format to LangChain ToolCall format
                                        import json
                                        try:
                                            args = json.loads(tc['function']['arguments'])
                                        except (json.JSONDecodeError, KeyError):
                                            args = {}
                                        
                                        tool_calls.append({
                                            'id': tc.get('id'),
                                            'type': 'tool_call',
                                            'name': tc['function']['name'],
                                            'args': args
                                        })
                                else:
                                    tool_calls = []
                        
                        # Ensure content is a string
                        if isinstance(content, (list, dict)):
                            content = str(content)
                        elif not isinstance(content, str):
                            content = str(content) if content is not None else ''
                        
                        # Extract token counts
                        prompt_tokens = usage_data.get('prompt_tokens', 0)
                        completion_tokens = usage_data.get('completion_tokens', 0)
                        total_tokens = usage_data.get('total_tokens', prompt_tokens + completion_tokens)
                        
                        # Calculate cost
                        from .cost_calculator import CostCalculator
                        estimated_cost = None
                        if prompt_tokens and completion_tokens:
                            pricing = CostCalculator.get_model_pricing(provider, model)
                            if pricing:
                                estimated_cost = CostCalculator.calculate_message_cost(
                                    prompt_tokens,
                                    completion_tokens,
                                    pricing
                                )
                        
                        # Store usage data in session for later use when saving message
                        await sync_to_async(setattr)(session, '_last_response_tokens', {
                            'prompt_tokens': prompt_tokens,
                            'completion_tokens': completion_tokens,
                            'total_tokens': total_tokens,
                            'estimated_cost': float(estimated_cost) if estimated_cost else None,
                            'provider': provider,
                            'model': model
                        })
                        
                        # Return both content and tool_calls
                        return {
                            'content': content or '',
                            'tool_calls': tool_calls
                        }
                    else:
                        error_text = await response.text()
                        raise ValueError(f"API request failed with status {response.status}: {error_text}")
                        
        except Exception as e:
            print(f"Provider API error: {e}")
            raise e
    
    async def _call_litemaas_api(self, llm_config, user_message, system_prompt):
        """Make a direct API call to LiteMaaS (OpenAI-compatible)"""
        import aiohttp
        import json
        
        try:
            base_url = getattr(llm_config, 'resolved_base_url', None) or os.getenv('LITEMAAS_BASE_URL')
            api_key = getattr(llm_config, 'api_key', None) or os.getenv('LITEMAAS_API_KEY')
            model = getattr(llm_config, 'model', 'gpt-3.5-turbo')
            max_tokens = getattr(llm_config, 'max_tokens', None)  # None = unlimited
            temperature = getattr(llm_config, 'temperature', 0.7)
            
            if not base_url:
                raise ValueError("No base URL configured for LiteMaaS")
            if not api_key:
                raise ValueError("No API key configured for LiteMaaS")
            
            # Prepare the request
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_message})
            
            data = {
                "model": model,
                "messages": messages,
                "temperature": temperature
            }
            if max_tokens:
                data["max_tokens"] = int(max_tokens)
            
            print(f"Making request to LiteMaaS: {url}")
            print(f"Model: {model}")
            
            # Make the async HTTP request
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if 'choices' in result and len(result['choices']) > 0:
                            return result['choices'][0]['message']['content']
                        else:
                            raise ValueError("No response content in API result")
                    else:
                        error_text = await response.text()
                        raise ValueError(f"API request failed with status {response.status}: {error_text}")
                        
        except Exception as e:
            print(f"LiteMaaS API error: {e}")
            raise e
    
    async def _get_fallback_response(self, session, user_message, system_prompt, error_message=None):
        """Generate a fallback response when LLM API is not available"""
        from asgiref.sync import sync_to_async
        
        persona = await sync_to_async(lambda: session.persona)()
        persona_name = persona.name if persona else "AI Assistant"
        
        # If there's a specific error message, show it
        if error_message:
            if "decrypt API key" in error_message or "encryption key" in error_message:
                response = (
                    f"⚠️ **API Key Decryption Error**\n\n"
                    f"I'm {persona_name}, but I cannot process your request because the API key decryption failed.\n\n"
                    f"**Error:** {error_message}\n\n"
                    f"**To fix this:**\n"
                    f"1. Go to Settings → LLM Provider Management\n"
                    f"2. Find the affected provider\n"
                    f"3. Click Edit and re-enter your API key\n"
                    f"4. Save the provider\n\n"
                    f"This happens when the encryption key changes. Re-entering your API key will fix it."
                )
            else:
                response = (
                    f"⚠️ **LLM API Error**\n\n"
                    f"I'm {persona_name}, but I encountered an error processing your request.\n\n"
                    f"**Error:** {error_message}\n\n"
                    f"Please check your LLM provider configuration in Settings."
                )
        else:
            # Return a helpful message explaining the issue
            response = (
                f"⚠️ **LLM Provider Not Configured**\n\n"
                f"I'm {persona_name}, but I cannot process your request because no LLM provider is configured.\n\n"
                f"**To fix this:**\n"
                f"1. Go to Settings\n"
                f"2. Add an LLM Provider (OpenRouter, OpenAI, Anthropic, etc.)\n"
                f"3. Enter your API key\n"
                f"4. Discover and enable models\n"
                f"5. Set a default model in Preferences\n\n"
                f"Once configured, I'll be able to respond to: \"{user_message[:50]}{'...' if len(user_message) > 50 else ''}\""
            )
        
        return response
    
    @action(detail=True, methods=['post'])
    def summarize(self, request, pk=None):
        """Generate a summary of the conversation for the session subject"""
        logger = logging.getLogger(__name__)
        session = self.get_object()
        
        # Get all messages in the session
        messages = session.messages.order_by('created_at')
        if not messages.exists():
            return Response({'subject': session.title or 'Empty conversation'}, status=200)
        
        # Build conversation text for summarization
        conversation_text = ""
        for message in messages:
            role = "User" if message.message_type == 'user' else "Assistant"
            conversation_text += f"{role}: {message.content}\n"
        
        # Use LLM to generate summary
        try:
            summary = async_to_sync(self._generate_summary)(session, conversation_text)
            
            # Update session subject
            session.subject = summary
            session.save()
            
            logger.info(f"[Summarize] Session {session.id}: Generated summary: {summary}")
            return Response({'subject': summary})
        except Exception as e:
            logger.error(f"[Summarize] Session {session.id}: Error generating summary: {e}")
            import traceback
            traceback.print_exc()
            # Fallback: use first user message as subject
            first_user_message = messages.filter(message_type='user').first()
            fallback_subject = first_user_message.content[:100] + "..." if first_user_message else "Conversation"
            session.subject = fallback_subject
            session.save()
            return Response({'subject': fallback_subject})
    
    async def _generate_summary(self, session, conversation_text):
        """Generate a one-sentence summary using the LLM"""
        from asgiref.sync import sync_to_async
        logger = logging.getLogger(__name__)
        
        prompt = f"Please provide a 5 word summary of this conversation (Make it a subject line of a conversation history):\n\n{conversation_text}\n\nSummary:"
        
        # Resolve provider needs to happen in sync context to access DB relations safely
        # Wrap the whole resolution logic
        provider = await sync_to_async(self._resolve_provider_hierarchy)(session)
        
        if provider:
            try:
                logger.info(f"[Summarize] Using provider {provider.name} ({provider.provider_type})")
                return await self._call_provider_summary(provider, prompt)
            except Exception as e:
                logger.warning(f"[Summarize] Provider summary failed: {e}, trying fallback")
        
        # Fallback to LLM manager config
        try:
            llm_manager = get_llm_manager()
            if session.llm_id:
                llm_config = llm_manager.get_llm_config(session.llm_id)
            else:
                llm_config = llm_manager.get_llm_config()
            
            if llm_config:
                llm_config.temperature = 0.1
                return await self._call_litemaas_summary(llm_config, prompt)
        except Exception as e:
            logger.error(f"[Summarize] Fallback summarization error: {e}")
        
        # Final fallback
        return "Conversation summary"
    
    async def _call_provider_summary(self, provider, prompt):
        """Call the provider API for summarization"""
        import aiohttp
        
        api_key = provider.get_api_key() if provider.api_key else None
        base_url = provider.base_url
        
        if not base_url or not api_key:
            raise ValueError(f"Provider {provider.name} misconfigured")
        
        if provider.provider_type in ['openai', 'openrouter', 'litemaas', 'vllm', 'custom']:
            url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            raise ValueError(f"Unsupported provider type: {provider.provider_type}")
        
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        model = provider.available_models[0]['id'] if provider.available_models else "gpt-3.5-turbo"
        
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100,
            "temperature": 0.1
        }
        
        async with aiohttp.ClientSession() as aio_session:
            async with aio_session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result['choices'][0]['message']['content'].strip()
                else:
                    raise ValueError(f"API error: {response.status}")
    
    async def _call_litemaas_summary(self, llm_config, prompt):
        """Make a direct API call to LiteMaaS for summarization"""
        import aiohttp
        import json
        
        try:
            base_url = getattr(llm_config, 'resolved_base_url', None) or os.getenv('LITEMAAS_BASE_URL')
            api_key = getattr(llm_config, 'api_key', None) or os.getenv('LITEMAAS_API_KEY')
            model = getattr(llm_config, 'model', 'gpt-3.5-turbo')
            
            if not base_url or not api_key:
                raise ValueError("LiteMaaS configuration incomplete")
            
            url = f"{base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.1
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result['choices'][0]['message']['content'].strip()
                    else:
                        raise ValueError(f"LiteMaaS API error: {response.status}")
                        
        except Exception as e:
            print(f"LiteMaaS summarization error: {e}")
            return "Conversation summary"

    @action(detail=True, methods=['post'])
    def stream(self, request, pk=None, project_id=None):
        """Stream a chat message response using Server-Sent Events (SSE)"""
        from django.http import StreamingHttpResponse
        import json
        
        try:
            session = self.get_object()
            message_content = request.data.get('message')
            llm_id = request.data.get('llm_id')
            temperature = request.data.get('temperature', 0.7)
            max_tokens = request.data.get('max_tokens') or None  # None = unlimited (model default)
            mode = request.data.get('mode', 'ask')
            persona_id = request.data.get('persona_id')
            enabled_tools = request.data.get('enabled_tool_ids', [])
            context_files = request.data.get('context_files', [])  # NEW: Accept context files
            
            if not message_content:
                return Response({'error': 'Message content is required'}, status=400)
            
            # Update session with provided settings
            if llm_id:
                session.llm_id = llm_id
            if temperature is not None:
                session.temperature = temperature
            if mode and mode in dict(ChatSession.MODE_CHOICES):
                session.mode = mode
            if persona_id:
                session.persona_id = persona_id
            if enabled_tools:
                if not session.project:
                    return Response({'error': 'Project context required'}, status=400)
                # Filter out non-numeric tool IDs (e.g. LangGraph workspace tool names like 'read_file')
                numeric_tool_ids = []
                for tid in enabled_tools:
                    try:
                        numeric_tool_ids.append(int(tid))
                    except (ValueError, TypeError):
                        pass
                if numeric_tool_ids:
                    tools_qs = ProjectTool.objects.filter(id__in=numeric_tool_ids, project=session.project, is_active=True)
                    session.enabled_tools.set(tools_qs)
            session.save()
            
            # Save user message
            user_message = ChatMessage.objects.create(
                session=session,
                message_type='user',
                content=message_content
            )
            
            # Generator function for SSE streaming (using synchronous requests for proper streaming)
            def event_generator():
                import requests
                
                try:
                    # Get AI response components
                    system_prompt = self._build_system_prompt(session, message_content, context_files)
                    
                    # Resolve provider using hierarchy
                    provider = self._resolve_provider_hierarchy(session)
                    
                    if not provider:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'No LLM provider configured'})}\n\n"
                        return
                    
                    full_content = ""
                    reasoning = ""
                    
                    # Stream the response
                    try:
                        api_key = provider.get_api_key() if provider.api_key else None
                        base_url = provider.base_url
                        
                        if not base_url or not api_key:
                            yield f"data: {json.dumps({'type': 'error', 'message': 'Provider misconfigured'})}\n\n"
                            return
                        
                        # Build URL and headers
                        if provider.provider_type in ['openai', 'openrouter', 'litemaas', 'vllm', 'custom']:
                            url = f"{base_url.rstrip('/')}/chat/completions"
                        elif provider.provider_type == 'anthropic':
                            url = f"{base_url.rstrip('/')}/v1/messages"
                        else:
                            yield f"data: {json.dumps({'type': 'error', 'message': f'Unsupported provider: {provider.provider_type}'})}\n\n"
                            return
                        
                        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                        
                        # Build messages
                        messages = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": message_content}
                        ]
                        
                        data = {
                            "model": session.selected_model or provider.available_models[0]['id'] if provider.available_models else "gpt-3.5-turbo",
                            "messages": messages,
                            "temperature": session.temperature or temperature,
                            "stream": True
                        }
                        if max_tokens:
                            data["max_tokens"] = int(max_tokens)
                        
                        # Use synchronous requests with streaming for proper SSE
                        with requests.post(url, headers=headers, json=data, stream=True, timeout=120) as resp:
                            if resp.status_code == 200:
                                # Iterate over response lines as they arrive
                                for line in resp.iter_lines(decode_unicode=True):
                                    if line and line.startswith('data: '):
                                        line_data = line[6:].strip()
                                        if line_data == '[DONE]':
                                            break
                                        try:
                                            event_data = json.loads(line_data)
                                            if event_data.get('choices'):
                                                delta = event_data['choices'][0].get('delta', {})
                                                # Handle text content
                                                chunk = delta.get('content', '')
                                                if chunk:
                                                    full_content += chunk
                                                    yield f"data: {json.dumps({'type': 'text_chunk', 'content': chunk})}\n\n"
                                                # Handle reasoning (for models that support it)
                                                if 'reasoning_content' in delta:
                                                    reasoning_chunk = delta.get('reasoning_content', '')
                                                    if reasoning_chunk:
                                                        reasoning += reasoning_chunk
                                                        yield f"data: {json.dumps({'type': 'reasoning', 'content': reasoning_chunk})}\n\n"
                                        except json.JSONDecodeError:
                                            pass
                            else:
                                error_text = resp.text[:500] if resp.text else f'Status {resp.status_code}'
                                yield f"data: {json.dumps({'type': 'error', 'message': f'API error: {error_text}'})}\n\n"
                                return
                        
                        # Save AI message with reasoning if available
                        if full_content:
                            msg_data = {'reasoning': reasoning} if reasoning else {}
                            ChatMessage.objects.create(
                                session=session,
                                message_type='assistant',
                                content=full_content,
                                metadata=msg_data
                            )
                        
                        # Signal completion
                        yield f"data: {json.dumps({'type': 'complete', 'content': full_content})}\n\n"
                        
                    except requests.exceptions.Timeout:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Request timed out after 120 seconds'})}\n\n"
                    except requests.exceptions.RequestException as e:
                        print(f"Stream request error: {e}")
                        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                    except Exception as e:
                        print(f"Stream error: {e}")
                        import traceback
                        traceback.print_exc()
                        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                    
                except Exception as e:
                    print(f"SSE generator error: {e}")
                    import traceback
                    traceback.print_exc()
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            
            return StreamingHttpResponse(
                event_generator(),
                content_type='text/event-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'X-Accel-Buffering': 'no',
                }
            )
        except Exception as e:
            print(f"Stream endpoint error: {e}")
            return Response({'error': str(e)}, status=500)

    def _build_system_prompt(self, session, user_message, context_files=None):
        """Build system prompt from persona, template, and project context"""
        system_prompt_parts = []
        
        if session.persona and session.persona.system_prompt:
            system_prompt_parts.append(session.persona.system_prompt)
        elif session.template and session.template.system_prompt:
            system_prompt_parts.append(session.template.system_prompt)
        
        if session.project and session.project.system_prompt:
            system_prompt_parts.append(f"Project: {session.project.name}\n{session.project.system_prompt}")
        
        mode_guidance = {
            'ask': 'Answer directly and concisely.',
            'plan': 'Break the request into steps and highlight dependencies.',
            'agent': 'Act autonomously and use tools when beneficial.',
            'persona': 'Adopt the selected persona tone.',
        }
        
        if session.mode in mode_guidance:
            system_prompt_parts.append(f"Mode: {mode_guidance[session.mode]}")
        
        # Add context files if provided
        if context_files:
            files_context = "## Context Files:\n\n"
            for file_info in context_files:
                if isinstance(file_info, dict):
                    path = file_info.get('path', 'unknown')
                    content = file_info.get('content', '')
                    files_context += f"### {path}\n```\n{content}\n```\n\n"
                elif isinstance(file_info, str):
                    files_context += f"### {file_info}\n"
            system_prompt_parts.append(files_context)
        
        return "\n\n".join(system_prompt_parts) if system_prompt_parts else "You are a helpful assistant."

    @action(detail=True, methods=['get'])
    def available_tools(self, request, pk=None, **kwargs):
        """Get available tools for this session's project"""
        try:
            session = self.get_object()
            
            if not session.project:
                return Response({'tools': []})
            
            # Get the workspace container name using PodmanManager
            container_name = f"workspace-{session.project.id}"  # Default fallback
            try:
                from api.podman_manager import PodmanManager
                manager = PodmanManager(session.project)
                found_container = manager._get_workspace_container_name()
                if found_container:
                    container_name = found_container
            except Exception as e:
                logger.warning(f"Failed to resolve workspace container name via PodmanManager: {e}")
            
            # Import tools function
            from api.frameworks.langgraph.tools import get_workspace_tools
            
            # Get tools from the framework
            tools_list = get_workspace_tools(session.project, container_name)
            
            # Convert langchain tools to JSON schema for frontend
            tools_data = []
            for tool in tools_list:
                tool_data = {
                    'id': tool.name,
                    'name': tool.name,
                    'description': tool.description or '',
                    'enabled': False,  # Track separately in session
                }
                
                # Try to extract parameters from tool schema if available
                if hasattr(tool, 'args_schema') and tool.args_schema:
                    try:
                        schema = tool.args_schema
                        if hasattr(schema, 'model_fields'):
                            params = []
                            for field_name, field_info in schema.model_fields.items():
                                params.append({
                                    'name': field_name,
                                    'type': str(field_info.annotation).__name__ if hasattr(field_info, 'annotation') else 'str',
                                    'description': field_info.description or '',
                                    'required': field_info.is_required() if hasattr(field_info, 'is_required') else True,
                                })
                            tool_data['params'] = params
                    except Exception:
                        tool_data['params'] = []
                
                tools_data.append(tool_data)
            
            return Response({'tools': tools_data})
        
        except Exception as e:
            import traceback
            import logging
            logging.getLogger(__name__).error(f"Error getting tools: {e}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=400)


class WorkspaceResourceTierViewSet(viewsets.ModelViewSet):
    """ViewSet for managing workspace resource tiers (t-shirt sizing)"""
    queryset = WorkspaceResourceTier.objects.all()
    serializer_class = WorkspaceResourceTierSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'slug'
    
    def get_queryset(self):
        """Return only active tiers for non-admin users"""
        if self.request.user.is_staff:
            return WorkspaceResourceTier.objects.all()
        return WorkspaceResourceTier.objects.filter(is_active=True)
    
    def create(self, request, *args, **kwargs):
        """Only admins can create tiers"""
        if not request.user.is_staff:
            raise PermissionDenied("Only administrators can create workspace tiers")
        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        """Only admins can update tiers"""
        if not request.user.is_staff:
            raise PermissionDenied("Only administrators can update workspace tiers")
        return super().update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Only admins can delete tiers"""
        if not request.user.is_staff:
            raise PermissionDenied("Only administrators can delete workspace tiers")
        return super().destroy(request, *args, **kwargs)


class LLMProviderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing LLM providers with hierarchical scope access"""
    queryset = LLMProvider.objects.all()
    serializer_class = LLMProviderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Return providers accessible to the user based on hierarchy"""
        user = self.request.user
        
        # Build query for all accessible providers
        query = models.Q()
        
        # System-level providers (visible to all)
        query |= models.Q(scope='system', is_active=True)
        
        # User's own providers
        query |= models.Q(scope='user', scope_user=user, is_active=True)
        
        # Team-level providers (from user's teams)
        user_teams = Team.objects.filter(members=user)
        query |= models.Q(scope='team', scope_team__in=user_teams, is_active=True)
        
        # Project-level providers (from projects user owns or contributes to)
        user_projects = Project.objects.filter(
            models.Q(owner=user) | models.Q(contributors=user)
        )
        query |= models.Q(scope='project', scope_project__in=user_projects, is_active=True)
        
        return LLMProvider.objects.filter(query).distinct().order_by('scope', 'instance_name')
    
    def check_permission_for_scope(self, scope, scope_id=None):
        """Check if user has permission to manage provider at given scope"""
        user = self.request.user
        
        # System scope requires admin/staff
        if scope == 'system':
            if not (user.is_staff or user.role == 'admin'):
                raise PermissionDenied("Only administrators can manage system-level providers")
            return True
        
        # Team scope requires admin + team membership
        if scope == 'team':
            if not (user.role == 'admin' or user.is_staff):
                raise PermissionDenied("Only administrators can manage team providers")
            if scope_id:
                team = Team.objects.filter(id=scope_id, members=user).first()
                if not team:
                    raise PermissionDenied("You must be a member of this team")
            return True
        
        # Project scope requires admin + project access
        if scope == 'project':
            if not (user.role == 'admin' or user.is_staff):
                raise PermissionDenied("Only administrators can manage project providers")
            if scope_id:
                project = Project.objects.filter(id=scope_id).first()
                if not project or not user_has_project_access(user, project):
                    raise PermissionDenied("You must have access to this project")
            return True
        
        # User scope - users can only manage their own
        if scope == 'user':
            if scope_id and scope_id != user.id:
                raise PermissionDenied("You can only manage your own providers")
            return True
        
        return False
    
    def perform_create(self, serializer):
        """Create provider with permission checks"""
        scope = serializer.validated_data.get('scope')
        scope_team = serializer.validated_data.get('scope_team')
        scope_project = serializer.validated_data.get('scope_project')
        scope_user = serializer.validated_data.get('scope_user')
        
        scope_id = None
        if scope_team:
            scope_id = scope_team.id
        elif scope_project:
            scope_id = scope_project.id
        elif scope_user:
            scope_id = scope_user.id
        
        self.check_permission_for_scope(scope, scope_id)
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        """Update provider with permission checks"""
        instance = self.get_object()
        self.check_permission_for_scope(instance.scope, self._get_scope_id(instance))
        serializer.save()
    
    def perform_destroy(self, instance):
        """Delete provider with permission checks"""
        self.check_permission_for_scope(instance.scope, self._get_scope_id(instance))
        instance.delete()
    
    def _get_scope_id(self, instance):
        """Helper to get scope ID from instance"""
        if instance.scope_team:
            return instance.scope_team.id
        elif instance.scope_project:
            return instance.scope_project.id
        elif instance.scope_user:
            return instance.scope_user.id
        return None
    
    @action(detail=True, methods=['post'])
    def discover_models(self, request, pk=None):
        """Manually trigger model discovery for a provider"""
        provider = self.get_object()
        self.check_permission_for_scope(provider.scope, self._get_scope_id(provider))
        
        from .llm_discovery import LLMDiscoveryService
        from datetime import datetime
        
        try:
            # Run async discovery in sync context
            api_key = provider.get_api_key() if provider.api_key else None
            models = asyncio.run(LLMDiscoveryService.discover_models(
                provider.provider_type,
                api_key,
                provider.base_url
            ))
            
            provider.available_models = models
            provider.last_discovery = datetime.now()
            provider.save()
            
            return Response({
                'success': True,
                'message': f'Discovered {len(models)} models',
                'models': models
            })
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test connection to provider"""
        provider = self.get_object()
        
        from .llm_discovery import LLMDiscoveryService
        
        try:
            api_key = provider.get_api_key() if provider.api_key else None
            result = asyncio.run(LLMDiscoveryService.test_connection(
                provider.provider_type,
                api_key,
                provider.base_url
            ))
            
            return Response(result)
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def available_models(self, request):
        """Get all available models from accessible providers with scope context"""
        project_id = request.query_params.get('project_id')
        
        # Get providers accessible to user
        providers = self.get_queryset()
        
        # Filter by project context if provided
        if project_id:
            try:
                project = Project.objects.get(id=project_id)
                if not user_has_project_access(request.user, project):
                    raise PermissionDenied("You don't have access to this project")
                
                # Include project and team providers
                if project.team:
                    providers = providers.filter(
                        models.Q(scope='system') |
                        models.Q(scope='user', scope_user=request.user) |
                        models.Q(scope='team', scope_team=project.team) |
                        models.Q(scope='project', scope_project=project)
                    )
                else:
                    providers = providers.filter(
                        models.Q(scope='system') |
                        models.Q(scope='user', scope_user=request.user) |
                        models.Q(scope='project', scope_project=project)
                    )
            except Project.DoesNotExist:
                pass
        
        # Build response grouped by provider
        response_data = {
            'providers': []
        }
        
        for provider in providers:
            if provider.available_models:
                response_data['providers'].append({
                    'provider_id': provider.id,
                    'instance_name': provider.instance_name,
                    'provider_type': provider.provider_type,
                    'scope': provider.scope,
                    'scope_label': provider.get_scope_label(),
                    'models': provider.available_models
                })
        
        return Response(response_data)


class LLMUsageStatsViewSet(viewsets.ViewSet):
    """ViewSet for LLM usage statistics and cost reporting"""
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def scope_stats(self, request):
        """Get usage statistics for a scope"""
        from .cost_calculator import CostCalculator
        from datetime import datetime, timedelta
        
        scope = request.query_params.get('scope', 'user')
        scope_id = request.query_params.get('scope_id')
        days = int(request.query_params.get('days', 30))
        
        # Permission checks
        user = request.user
        if scope == 'system':
            if not (user.is_staff or user.role == 'admin'):
                raise PermissionDenied("Only administrators can view system stats")
        elif scope == 'team' and scope_id:
            team = Team.objects.filter(id=scope_id, members=user).first()
            if not team:
                raise PermissionDenied("You must be a member of this team")
        elif scope == 'project' and scope_id:
            project = Project.objects.filter(id=scope_id).first()
            if not project or not user_has_project_access(user, project):
                raise PermissionDenied("You must have access to this project")
        elif scope == 'user':
            scope_id = user.id
        
        start_date = datetime.now() - timedelta(days=days)
        
        stats = CostCalculator.get_scope_usage_stats(
            scope,
            int(scope_id) if scope_id else None,
            start_date,
            None
        )
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def daily_trends(self, request):
        """Get daily usage trends for charting"""
        from .cost_calculator import CostCalculator
        
        scope = request.query_params.get('scope', 'user')
        scope_id = request.query_params.get('scope_id')
        days = int(request.query_params.get('days', 30))
        
        # Permission checks (same as scope_stats)
        user = request.user
        if scope == 'system':
            if not (user.is_staff or user.role == 'admin'):
                raise PermissionDenied("Only administrators can view system stats")
        elif scope == 'team' and scope_id:
            team = Team.objects.filter(id=scope_id, members=user).first()
            if not team:
                raise PermissionDenied("You must be a member of this team")
        elif scope == 'project' and scope_id:
            project = Project.objects.filter(id=scope_id).first()
            if not project or not user_has_project_access(user, project):
                raise PermissionDenied("You must have access to this project")
        elif scope == 'user':
            scope_id = user.id
        
        trends = CostCalculator.get_daily_usage_trends(
            scope,
            int(scope_id) if scope_id else None,
            days
        )
        
        return Response({'trends': trends})
    
    @action(detail=False, methods=['get'])
    def user_stats(self, request):
        """Get usage statistics for current user"""
        from .cost_calculator import CostCalculator
        from datetime import datetime, timedelta
        
        days = int(request.query_params.get('days', 30))
        start_date = datetime.now() - timedelta(days=days)
        
        stats = CostCalculator.get_user_usage_stats(
            request.user.id,
            start_date,
            None
        )
        
        return Response(stats)
    
    @action(detail=False, methods=['get'])
    def provider_stats(self, request):
        """Get usage statistics for a specific provider"""
        from .cost_calculator import CostCalculator
        from datetime import datetime, timedelta
        
        provider_id = request.query_params.get('provider_id')
        days = int(request.query_params.get('days', 30))
        
        if not provider_id:
            return Response({'error': 'provider_id required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user has access to this provider
        try:
            provider = LLMProvider.objects.get(id=provider_id)
            # Check if provider is in user's accessible list
            accessible_providers = LLMProviderViewSet().get_queryset()
            accessible_providers.request = request
            if not accessible_providers.filter(id=provider_id).exists():
                raise PermissionDenied("You don't have access to this provider")
        except LLMProvider.DoesNotExist:
            return Response({'error': 'Provider not found'}, status=status.HTTP_404_NOT_FOUND)
        
        start_date = datetime.now() - timedelta(days=days)
        
        stats = CostCalculator.get_provider_usage_stats(
            int(provider_id),
            start_date,
            None
        )
        
        return Response(stats)