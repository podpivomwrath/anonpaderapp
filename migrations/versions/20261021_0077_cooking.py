"""Кулинария (2026-10-21): уровень, блюда в инвентаре, бафф от еды."""
import sqlalchemy as sa
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_food",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dish_id", sa.String(32), nullable=False),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "dish_id", "grade", name="uq_character_food"),
    )
    op.create_index("ix_character_food_character_id", "character_food", ["character_id"])
    op.add_column("characters", sa.Column("cooking_level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("characters", sa.Column("cooking_xp", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("characters", sa.Column("food_dish", sa.String(32), nullable=True))
    op.add_column("characters", sa.Column("food_grade", sa.String(16), nullable=True))
    op.add_column("characters", sa.Column("food_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for col in ("food_until", "food_grade", "food_dish", "cooking_xp", "cooking_level"):
        op.drop_column("characters", col)
    op.drop_index("ix_character_food_character_id", "character_food")
    op.drop_table("character_food")
