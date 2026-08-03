"""Пепельный ларец: история открытий (патч 24).

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_lootboxes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("reward_summary", sa.String(256), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_character_lootboxes_character_id", "character_lootboxes", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_character_lootboxes_character_id", table_name="character_lootboxes")
    op.drop_table("character_lootboxes")
