"""ORM models. Import all models so metadata is complete for Alembic."""

# User first — shares fastapi-users metadata; org/project FKs reference user.id
from app.models.user import OAuthAccount, User
from app.models.organization import Organization, OrganizationMember
from app.models.project import Project
from app.models.preview import PreviewEndpoint
from app.models.provider_credential import ProviderCredential
from app.models.knowledge import KnowledgeCanvas
from app.models.agent import ProjectAgent
from app.models.sandbox_token import SandboxAccessToken
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

__all__ = [
    "User",
    "OAuthAccount",
    "Organization",
    "OrganizationMember",
    "Project",
    "PreviewEndpoint",
    "ProviderCredential",
    "KnowledgeCanvas",
    "ProjectAgent",
    "SandboxAccessToken",
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
]
