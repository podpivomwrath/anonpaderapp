"""character_consumables (патч 16: лавка эликсиров и зелий).

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_consumables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("elixir_id", sa.String(32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "elixir_id", name="uq_character_consumables_character_elixir"),
    )
    op.create_index(
        "ix_character_consumables_character_id", "character_consumables", ["character_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_character_consumables_character_id", table_name="character_consumables")
    op.drop_table("character_consumables")
