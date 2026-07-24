"""Encrypted git remote credentials (PAT) — user, org, or project scope."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

OwnerType = Literal["user", "org", "project"]
GitProvider = Literal["github", "gitlab", "bitbucket", "custom"]


class GitCredential(Base):
    __tablename__ = "git_credentials"

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    owner_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    owner_id: Mapped[UUID] = mapped_column(GUID, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="github")
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    secret_nonce: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    scopes: Mapped[str] = mapped_column(String(120), nullable=False, default="repo")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    key_last4: Mapped[str | None] = mapped_column(String(8), nullable=True)
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
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
