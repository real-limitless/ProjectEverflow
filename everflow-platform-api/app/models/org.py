"""Project teams and seats (org chart control plane)."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class Team(Base):
    """Named roster you can @mention (`@eng`, `@qa`)."""

    __tablename__ = "project_teams"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_project_team_slug"),)

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    mention: Mapped[str] = mapped_column(String(80), nullable=False)
    lane: Mapped[str] = mapped_column(String(32), nullable=False, default="line")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    conductor_seat_id: Mapped[UUID | None] = mapped_column(GUID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="teams")
    seats: Mapped[list["Seat"]] = relationship(
        "Seat", back_populates="team", foreign_keys="Seat.team_id"
    )


class Seat(Base):
    """Human or bot seat on the org chart. Bot seats bind to one OpenCode session."""

    __tablename__ = "project_seats"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_project_seat_slug"),)

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="bot")
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False, default="specialist")
    lane: Mapped[str] = mapped_column(String(32), nullable=False, default="line")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reports_to_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_seats.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_slug: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_conductor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opencode_session_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    worktree_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    budget_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    permission: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    tools: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="idle")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="seats")
    team: Mapped["Team | None"] = relationship(
        "Team", back_populates="seats", foreign_keys=[team_id]
    )
    owner: Mapped["User | None"] = relationship("User")
    reports_to: Mapped["Seat | None"] = relationship(
        "Seat", remote_side="Seat.id", foreign_keys=[reports_to_id]
    )
