"""character_trophies (патч 9, блок 2): стакающийся счётчик по градации.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_trophies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trophy_id", sa.String(32), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "character_id", "trophy_id", name="uq_character_trophies_character_trophy"
        ),
    )
    op.create_index(
        "ix_character_trophies_character_id", "character_trophies", ["character_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_character_trophies_character_id", table_name="character_trophies")
    op.drop_table("character_trophies")
