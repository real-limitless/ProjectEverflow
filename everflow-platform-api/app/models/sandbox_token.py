"""Project-scoped access tokens for sandbox MCP / machine clients."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base

# Public token prefix so we can detect scheme without DB lookup ambiguity.
TOKEN_PREFIX = "ef_sbox_"


class SandboxAccessToken(Base):
    __tablename__ = "sandbox_access_tokens"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        GUID,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    # First chars of raw token for UI/debug (not secret).
    prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    # e.g. ["knowledge:rw", "agents:rw", "project:read"]
    scopes: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True, default=list)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
