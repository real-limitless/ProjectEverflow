"""SQLAlchemy declarative base and shared mixins."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid4] = mapped_column(  # type: ignore[valid-type]
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
