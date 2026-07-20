"""User and OAuth account models for fastapi-users."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)
from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.organization import OrganizationMember


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, Base):
    # Table name must stay "oauth_account" if customized carefully;
    # default fastapi-users name is fine; FK targets "user.id".
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    # fastapi-users OAuthAccount FK expects table name "user" (singular).
    pass

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

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount",
        lazy="joined",
        cascade="all, delete-orphan",
    )
    memberships: Mapped[list["OrganizationMember"]] = relationship(
        "OrganizationMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )


# Re-export UUID type for type hints in routers
UserId = UUID
