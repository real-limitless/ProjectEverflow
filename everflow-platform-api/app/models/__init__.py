"""ORM models. Import all models so metadata is complete for Alembic."""

# User first — shares fastapi-users metadata; org/project FKs reference user.id
from app.models.user import OAuthAccount, User
from app.models.organization import Organization, OrganizationInvite, OrganizationMember
from app.models.project import Project
from app.models.preview import PreviewEndpoint
from app.models.provider_credential import ProviderCredential
from app.models.git_credential import GitCredential
from app.models.knowledge import (
    AgentCollectionGrant,
    KnowledgeCanvas,
    KnowledgeCanvasVersion,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeEvalQuestion,
    KnowledgeEvalSet,
    KnowledgeLink,
    KnowledgeMindMap,
)
from app.models.agent import ProjectAgent
from app.models.sandbox_token import SandboxAccessToken
from app.models.ai_usage import AiUsageEvent
from app.models.workflow import (
    Workflow,
    WorkflowCredential,
    WorkflowDataTable,
    WorkflowDataTableRow,
    WorkflowRun,
)
from app.models.test_suite import TestCase, TestSuite
from app.models.http_tool import ProjectHttpTool
from app.models.deploy import DeployNode, DeployRoute, DeployRun, DeploySshKey
from app.models.org import Seat, Team
from app.models.room import Channel, ChannelMessage
from app.models.bus import BusEvent, MemoryBlock, OrgRun, OrgRunNode

__all__ = [
    "User",
    "OAuthAccount",
    "Organization",
    "OrganizationMember",
    "OrganizationInvite",
    "Project",
    "PreviewEndpoint",
    "ProviderCredential",
    "GitCredential",
    "KnowledgeCanvas",
    "KnowledgeCollection",
    "AgentCollectionGrant",
    "KnowledgeChunk",
    "KnowledgeCanvasVersion",
    "KnowledgeLink",
    "KnowledgeMindMap",
    "KnowledgeEvalSet",
    "KnowledgeEvalQuestion",
    "ProjectAgent",
    "SandboxAccessToken",
    "AiUsageEvent",
    "Workflow",
    "WorkflowRun",
    "WorkflowCredential",
    "WorkflowDataTable",
    "WorkflowDataTableRow",
    "TestSuite",
    "TestCase",
    "ProjectHttpTool",
    "DeploySshKey",
    "DeployNode",
    "DeployRoute",
    "DeployRun",
    "Team",
    "Seat",
    "Channel",
    "ChannelMessage",
    "OrgRun",
    "OrgRunNode",
    "BusEvent",
    "MemoryBlock",
]
