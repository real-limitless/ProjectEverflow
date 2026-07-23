"""Add provider_credentials table for encrypted AI provider keys.

Revision ID: 005
Revises: 004
Create Date: 2026-07-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, Sequence[str], None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

GUID = sa.String(36)


def upgrade() -> None:
    op.create_table(
        "provider_credentials",
        sa.Column("id", GUID, nullable=False),
        sa.Column("owner_type", sa.String(length=16), nullable=False),
        sa.Column("owner_id", GUID, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_nonce", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("key_last4", sa.String(length=8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_type",
            "owner_id",
            "provider",
            name="uq_provider_owner_provider",
        ),
    )
    op.create_index(
        op.f("ix_provider_credentials_owner_type"),
        "provider_credentials",
        ["owner_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_credentials_owner_id"),
        "provider_credentials",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_provider_credentials_provider"),
        "provider_credentials",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_provider_credentials_provider"), table_name="provider_credentials")
    op.drop_index(op.f("ix_provider_credentials_owner_id"), table_name="provider_credentials")
    op.drop_index(op.f("ix_provider_credentials_owner_type"), table_name="provider_credentials")
    op.drop_table("provider_credentials")
