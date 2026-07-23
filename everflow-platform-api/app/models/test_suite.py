"""Project-scoped test suites and cases (studio Tests panel)."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.project import Project


class TestSuite(Base):
    """Named collection of shell-backed test cases for a project."""

    __tablename__ = "test_suites"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    project: Mapped["Project"] = relationship("Project", back_populates="test_suites")
    cases: Mapped[list["TestCase"]] = relationship(
        "TestCase",
        back_populates="suite",
        cascade="all, delete-orphan",
        order_by="TestCase.created_at",
    )


class TestCase(Base):
    """Single shell command assertion within a test suite."""

    __tablename__ = "test_cases"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    suite_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("test_suites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # unit | e2e | smoke
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="unit")
    command: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # passed | failed | skipped | None (pending)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    suite: Mapped["TestSuite"] = relationship("TestSuite", back_populates="cases")
