"""Травничество (2026-10-21): трава на клетках, сумка травника, уровень."""
import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "herb_patches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("herb_id", sa.String(32), nullable=False),
        sa.Column("spawned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("x", "y", name="uq_herb_patches_cell"),
    )
    op.create_table(
        "character_herbs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("herb_id", sa.String(32), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "herb_id", name="uq_character_herbs_char_herb"),
    )
    op.create_index("ix_character_herbs_character_id", "character_herbs", ["character_id"])
    op.add_column("characters", sa.Column("herbalism_level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("characters", sa.Column("herbalism_xp", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("characters", "herbalism_xp")
    op.drop_column("characters", "herbalism_level")
    op.drop_index("ix_character_herbs_character_id", "character_herbs")
    op.drop_table("character_herbs")
    op.drop_table("herb_patches")
