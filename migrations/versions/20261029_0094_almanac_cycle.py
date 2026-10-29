"""Альманах травника на зарядке (2026-10-29): начало цикла «час работает,
час заряжается»."""
import sqlalchemy as sa
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_craft_gear", sa.Column("cycle_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("character_craft_gear", "cycle_at")
