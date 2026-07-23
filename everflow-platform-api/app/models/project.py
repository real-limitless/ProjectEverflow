"""Project model scoped to an organization."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.agent import ProjectAgent
    from app.models.deploy import DeployNode, DeploySshKey
    from app.models.http_tool import ProjectHttpTool
    from app.models.knowledge import KnowledgeCanvas
    from app.models.organization import Organization
    from app.models.test_suite import TestSuite
    from app.models.workflow import Workflow


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_org_project_slug"),)

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Catalog of attached git remotes (cloned into sandbox workspace after provision).
    # List of dicts: id, label, url, branch, provider, local_path, clone_status, clone_error
    repos: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True, default=list)

    # Enabled sandbox harness ids (strings) or {id, label?, enabled?} dicts.
    # Applied on provision / bootstrap when the user changes Project Settings → Harnesses.
    harnesses: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True, default=list)

    # microsandbox lifecycle (provisioned via internal sandbox-agent)
    sandbox_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sandbox_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    sandbox_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sandbox_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sandbox_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    knowledge_canvases: Mapped[list["KnowledgeCanvas"]] = relationship(
        "KnowledgeCanvas",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    agents: Mapped[list["ProjectAgent"]] = relationship(
        "ProjectAgent",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    workflows: Mapped[list["Workflow"]] = relationship(
        "Workflow",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    test_suites: Mapped[list["TestSuite"]] = relationship(
        "TestSuite",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    http_tools: Mapped[list["ProjectHttpTool"]] = relationship(
        "ProjectHttpTool",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    deploy_ssh_keys: Mapped[list["DeploySshKey"]] = relationship(
        "DeploySshKey",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    deploy_nodes: Mapped[list["DeployNode"]] = relationship(
        "DeployNode",
        back_populates="project",
        cascade="all, delete-orphan",
    )
