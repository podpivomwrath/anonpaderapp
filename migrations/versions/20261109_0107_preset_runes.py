"""Раскладка рун в пресете (2026-11-09, репорт 340)."""
import sqlalchemy as sa
from alembic import op

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_buff_presets", sa.Column("runes", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("character_buff_presets", "runes")
