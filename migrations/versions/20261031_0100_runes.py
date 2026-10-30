"""Руны (2026-10-31): сумка, мастерство, слоты и поля на персонаже."""
import sqlalchemy as sa
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_runes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rune_id", sa.String(24), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "rune_id", name="uq_character_rune"),
    )
    op.create_index("ix_character_runes_character_id", "character_runes", ["character_id"])
    op.create_table(
        "character_rune_mastery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rune_id", sa.String(24), nullable=False),
        sa.Column("absorbed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "rune_id", name="uq_character_rune_mastery"),
    )
    op.create_index("ix_character_rune_mastery_character_id", "character_rune_mastery", ["character_id"])
    op.create_table(
        "character_rune_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("slot", sa.String(48), nullable=False),
        sa.Column("rune_id", sa.String(24), nullable=False),
        sa.UniqueConstraint("character_id", "kind", "slot", name="uq_character_rune_slot"),
    )
    op.create_index("ix_character_rune_slots_character_id", "character_rune_slots", ["character_id"])
    op.add_column("characters", sa.Column("rune_hero_slots", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("characters", sa.Column("rune_skill_slots", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("characters", sa.Column("rune_effects", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("characters", "rune_effects")
    op.drop_column("characters", "rune_skill_slots")
    op.drop_column("characters", "rune_hero_slots")
    op.drop_table("character_rune_slots")
    op.drop_table("character_rune_mastery")
    op.drop_table("character_runes")
