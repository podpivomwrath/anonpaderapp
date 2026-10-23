"""Ремесленные инструменты (2026-10-23): character_craft_gear и сила пряностей
в действующем баффе еды (characters.food_boost)."""
import sqlalchemy as sa
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_craft_gear",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_id", sa.String(16), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "tool_id", name="uq_craft_gear_char_tool"),
    )
    op.create_index("ix_character_craft_gear_character_id", "character_craft_gear", ["character_id"])
    op.add_column("characters", sa.Column("food_boost", sa.Float(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("characters", "food_boost")
    op.drop_index("ix_character_craft_gear_character_id", "character_craft_gear")
    op.drop_table("character_craft_gear")
