"""Текущий вложенный экран персонажа (патч 37): клавиатура — свойство экрана.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "characters",
        sa.Column("screen", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("characters", "screen")
