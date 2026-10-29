"""Альманах: на какую траву уже указал (2026-10-29, владелец) - id кустов
herb_patches через запятую. Второй раз на тот же куст не указывает."""
import sqlalchemy as sa
from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_craft_gear", sa.Column("hinted", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("character_craft_gear", "hinted")
