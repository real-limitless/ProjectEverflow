"""Bot bus: runs, run nodes, audited events, scoped memory."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.org import Seat, Team
    from app.models.project import Project
    from app.models.room import Channel
    from app.models.user import User


class OrgRun(Base):
    __tablename__ = "org_runs"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_channels.id", ondelete="SET NULL"), nullable=True
    )
    thread_id: Mapped[UUID | None] = mapped_column(GUID, nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    sentence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="compiled")
    compiled_graph: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="runs")
    channel: Mapped["Channel | None"] = relationship("Channel")
    nodes: Mapped[list["OrgRunNode"]] = relationship(
        "OrgRunNode", back_populates="run", cascade="all, delete-orphan"
    )


class OrgRunNode(Base):
    __tablename__ = "org_run_nodes"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("org_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seat_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_seats.id", ondelete="SET NULL"), nullable=True
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="waiting")
    brief: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    depends_on: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)

    run: Mapped["OrgRun"] = relationship("OrgRun", back_populates="nodes")
    seat: Mapped["Seat | None"] = relationship("Seat")


class BusEvent(Base):
    __tablename__ = "org_bus_events"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("org_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verb: Mapped[str] = mapped_column(String(40), nullable=False)
    from_seat_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_seats.id", ondelete="SET NULL"), nullable=True
    )
    to_seat_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_seats.id", ondelete="SET NULL"), nullable=True
    )
    to_team_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_teams.id", ondelete="SET NULL"), nullable=True
    )
    to_channel_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_channels.id", ondelete="SET NULL"), nullable=True
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    project: Mapped["Project"] = relationship("Project", back_populates="bus_events")
    from_seat: Mapped["Seat | None"] = relationship("Seat", foreign_keys=[from_seat_id])
    to_seat: Mapped["Seat | None"] = relationship("Seat", foreign_keys=[to_seat_id])
    to_team: Mapped["Team | None"] = relationship("Team", foreign_keys=[to_team_id])


class MemoryBlock(Base):
    __tablename__ = "org_memory_blocks"
    __table_args__ = (
        UniqueConstraint("project_id", "scope", "scope_id", "name", name="uq_org_memory_block"),
    )

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(24), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
