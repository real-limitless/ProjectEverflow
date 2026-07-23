"""Encrypted AI provider credentials (user or project scope)."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

OwnerType = Literal["user", "project"]
ProviderId = Literal["openrouter", "openai", "anthropic", "xai", "custom"]

KNOWN_PROVIDERS = ("openrouter", "openai", "anthropic", "xai", "custom")


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    __table_args__ = (
        UniqueConstraint(
            "owner_type",
            "owner_id",
            "provider",
            name="uq_provider_owner_provider",
        ),
    )

    id: Mapped[UUID] = mapped_column(GUID, primary_key=True, default=uuid4)
    owner_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    owner_id: Mapped[UUID] = mapped_column(GUID, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Fernet token (ascii); nonce reserved for future AES-GCM
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    secret_nonce: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # Comma-separated scopes: chat,embed,ocr,* — empty means *
    scopes: Mapped[str] = mapped_column(String(120), nullable=False, default="*")
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
