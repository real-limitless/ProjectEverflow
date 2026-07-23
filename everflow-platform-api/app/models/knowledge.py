"""Project knowledge canvases (markdown knowledge documents)."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class KnowledgeCanvas(Base):
    """Markdown knowledge document scoped to a project (studio Knowledge panel)."""

    __tablename__ = "knowledge_canvases"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # created | upload | ocr | web
    origin: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    # ready | uploading | ocr | chunking | embedding | indexed | stale | error
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    chunks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
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

    project: Mapped["Project"] = relationship("Project", back_populates="knowledge_canvases")
