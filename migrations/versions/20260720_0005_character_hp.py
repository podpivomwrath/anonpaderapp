"""character current_hp (персистентное HP между боями)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NULL = полное HP; восстанавливается отдыхом (8-12с) и авто-респавном
    op.add_column("characters", sa.Column("current_hp", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("characters", "current_hp")
