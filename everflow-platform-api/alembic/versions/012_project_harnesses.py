"""Add projects.harnesses JSON column for sandbox bootstrap selection.

Revision ID: 012
Revises: 011
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, Sequence[str], None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("harnesses", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "harnesses")
