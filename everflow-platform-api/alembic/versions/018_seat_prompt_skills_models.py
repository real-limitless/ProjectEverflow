"""Seat prompt, skills, and preferred models.

Revision ID: 018
Revises: 017
Create Date: 2026-09-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, Sequence[str], None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_seats",
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column("project_seats", sa.Column("skills", sa.JSON(), nullable=True))
    op.add_column("project_seats", sa.Column("preferred_models", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_seats", "preferred_models")
    op.drop_column("project_seats", "skills")
    op.drop_column("project_seats", "prompt")
