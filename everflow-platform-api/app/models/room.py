"""Project room: channels, messages, threads."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.bus import OrgRun
    from app.models.org import Seat
    from app.models.project import Project
    from app.models.user import User


class Channel(Base):
    __tablename__ = "project_channels"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_project_channel_slug"),)

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_teams.id", ondelete="SET NULL"), nullable=True
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="channel")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="channels")
    messages: Mapped[list["ChannelMessage"]] = relationship(
        "ChannelMessage", back_populates="channel", cascade="all, delete-orphan"
    )


class ChannelMessage(Base):
    __tablename__ = "project_channel_messages"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    channel_id: Mapped[UUID] = mapped_column(
        GUID, ForeignKey("project_channels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_channel_messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    author_user_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    author_seat_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("project_seats.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="message")
    mentions: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(
        GUID, ForeignKey("org_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    channel: Mapped["Channel"] = relationship("Channel", back_populates="messages")
    author_user: Mapped["User | None"] = relationship("User")
    author_seat: Mapped["Seat | None"] = relationship("Seat")
    run: Mapped["OrgRun | None"] = relationship("OrgRun", foreign_keys=[run_id])
