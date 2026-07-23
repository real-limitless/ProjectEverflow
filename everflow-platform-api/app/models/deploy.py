"""Deploy nodes, SSH keys, routes, and run stubs."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class DeploySshKey(Base):
    """Project SSH keypair; private key stored Fernet-encrypted."""

    __tablename__ = "deploy_ssh_keys"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)
    private_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(GUID, nullable=True, index=True)
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

    project: Mapped["Project"] = relationship("Project", back_populates="deploy_ssh_keys")


class DeployNode(Base):
    """Remote host that can receive podman/docker-compose deploys over SSH."""

    __tablename__ = "deploy_nodes"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    ssh_user: Mapped[str] = mapped_column(String(128), nullable=False, default="everflow")
    tags: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True, default=list)
    # unknown | online | offline
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    created_by: Mapped[UUID | None] = mapped_column(GUID, nullable=True, index=True)
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

    project: Mapped["Project"] = relationship("Project", back_populates="deploy_nodes")
    routes: Mapped[list["DeployRoute"]] = relationship(
        "DeployRoute",
        back_populates="node",
        cascade="all, delete-orphan",
    )


class DeployRoute(Base):
    """Host-header / path → service mapping on a deploy node."""

    __tablename__ = "deploy_routes"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    node_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("deploy_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host_header: Mapped[str] = mapped_column(String(255), nullable=False)
    service_name: Mapped[str] = mapped_column(String(200), nullable=False)
    service_port: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    path_prefix: Mapped[str] = mapped_column(String(512), nullable=False, default="/")
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

    node: Mapped["DeployNode"] = relationship("DeployNode", back_populates="routes")


class DeployRun(Base):
    """Optional stub record for deploy attempts (SSH execute not wired yet)."""

    __tablename__ = "deploy_runs"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[UUID | None] = mapped_column(
        GUID,
        ForeignKey("deploy_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    compose_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="up")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="stub")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
