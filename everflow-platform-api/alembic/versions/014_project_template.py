"""Project template_id and preview_device.

Revision ID: 014
Revises: 013
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, Sequence[str], None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("template_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("preview_device", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("preview_device")
        batch.drop_column("template_id")
