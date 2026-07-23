"""Project-scoped HTTP tool definitions (Tools panel)."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class ProjectHttpTool(Base):
    """Registered HTTP action agents can call via Everflow MCP / Tools panel."""

    __tablename__ = "project_http_tools"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="GET")
    url_template: Mapped[str] = mapped_column(String(2000), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    project: Mapped["Project"] = relationship("Project", back_populates="http_tools")
