"""Питомцы (2026-11-12): кто каким владеет, кто в слоте, ворон за сезон PvP
и Пепельный дракон - одна строка на весь мир."""

import sqlalchemy as sa
from alembic import op

revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_pets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("character_id", sa.Integer, sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pet_id", sa.String(24), nullable=False),
        sa.Column("obtained_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("character_id", "pet_id", name="uq_character_pets_char_pet"),
    )
    op.create_index("ix_character_pets_character_id", "character_pets", ["character_id"])
    op.add_column("characters", sa.Column("pet_id", sa.String(24), nullable=True))
    op.add_column("pvp_season_results",
                  sa.Column("raven", sa.Boolean, server_default=sa.false(), nullable=False))
    op.create_table(
        "ash_dragon",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("awakened_by", sa.Integer, sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("awakened_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("ash_dragon")
    op.drop_column("pvp_season_results", "raven")
    op.drop_column("characters", "pet_id")
    op.drop_index("ix_character_pets_character_id", "character_pets")
    op.drop_table("character_pets")
