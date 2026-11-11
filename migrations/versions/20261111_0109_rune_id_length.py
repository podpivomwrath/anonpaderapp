"""Руны-навыки (2026-11-11): id руны-навыка - это id навыка, а он бывает
длиннее 24 знаков («blood_knight_lifesteal_strike»). На проде колонки уже
расширены вручную при выкатке - здесь та же правка для остальных баз."""
import sqlalchemy as sa
from alembic import op

revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None

TABLES = ("character_runes", "character_rune_mastery", "character_rune_slots")


def upgrade():
    for table in TABLES:
        op.alter_column(table, "rune_id", type_=sa.String(64), existing_type=sa.String(24))


def downgrade():
    for table in TABLES:
        op.alter_column(table, "rune_id", type_=sa.String(24), existing_type=sa.String(64))
