"""Organization invites and git credentials.

Revision ID: 015
Revises: 014
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, Sequence[str], None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_invites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by", sa.String(length=36), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["accepted_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_org_invite_token_hash"),
    )
    op.create_index(
        op.f("ix_organization_invites_organization_id"),
        "organization_invites",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_invites_token_hash"),
        "organization_invites",
        ["token_hash"],
        unique=False,
    )

    op.create_table(
        "git_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_type", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
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
    )
    op.create_index(
        op.f("ix_git_credentials_owner_type"),
        "git_credentials",
        ["owner_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_git_credentials_owner_id"),
        "git_credentials",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_git_credentials_provider"),
        "git_credentials",
        ["provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_git_credentials_provider"), table_name="git_credentials")
    op.drop_index(op.f("ix_git_credentials_owner_id"), table_name="git_credentials")
    op.drop_index(op.f("ix_git_credentials_owner_type"), table_name="git_credentials")
    op.drop_table("git_credentials")
    op.drop_index(
        op.f("ix_organization_invites_token_hash"), table_name="organization_invites"
    )
    op.drop_index(
        op.f("ix_organization_invites_organization_id"),
        table_name="organization_invites",
    )
    op.drop_table("organization_invites")
