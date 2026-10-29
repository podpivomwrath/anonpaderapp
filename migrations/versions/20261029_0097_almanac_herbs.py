"""Альманах: какие травы подсказывать - галочками по траве (2026-10-29,
владелец). NULL - вся трава, которую персонаж различает; пустая строка -
никакая (альманах молчит); иначе id трав через запятую. herb_tier остаётся
для старых строк: выбранный тир читается как его травы."""
import sqlalchemy as sa
from alembic import op

revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_craft_gear", sa.Column("herb_ids", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("character_craft_gear", "herb_ids")
