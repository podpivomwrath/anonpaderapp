"""characters.pvp_wins/pvp_losses + pvp_battles (патч 22: открытое PvP).

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "characters", sa.Column("pvp_wins", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "characters", sa.Column("pvp_losses", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_index(
        "ix_characters_pvp_wins", "characters", [sa.text("pvp_wins DESC")]
    )
    op.create_table(
        "pvp_battles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("battle_type", sa.String(16), nullable=False),
        sa.Column("participant_ids", sa.JSON(), nullable=False),
        sa.Column("winner_ids", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("pvp_battles")
    op.drop_index("ix_characters_pvp_wins", table_name="characters")
    op.drop_column("characters", "pvp_losses")
    op.drop_column("characters", "pvp_wins")
