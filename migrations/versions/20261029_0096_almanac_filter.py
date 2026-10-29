"""Альманах: какой тир травы подсказывать (2026-10-29, просьба игрока).
NULL - любую траву, которую персонаж различает."""
import sqlalchemy as sa
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_craft_gear", sa.Column("herb_tier", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("character_craft_gear", "herb_tier")
