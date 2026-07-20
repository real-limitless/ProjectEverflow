"""Project model scoped to an organization."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.organization import Organization


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
