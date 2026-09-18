"""Fishing: lakes, bag, records, fishing level, lifetime mob kills."""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    # Садок: стак по (вид + градация) суммарным весом, не отдельные хвосты.
    op.create_table(
        "character_fish",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fish_id", sa.String(32), nullable=False),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("total_grams", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "fish_id", "grade", name="uq_character_fish_char_fish_grade"),
    )
    op.create_index("ix_character_fish_character_id", "character_fish", ["character_id"])

    # Рекорды по видам. Они же источник общего топа по весу, отдельной
    # «серверной» таблицы не нужно — ORDER BY weight_grams DESC.
    op.create_table(
        "character_fish_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fish_id", sa.String(32), nullable=False),
        sa.Column("weight_grams", sa.Integer(), nullable=False),
        sa.Column("caught_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("character_id", "fish_id", name="uq_character_fish_records_char_fish"),
    )
    op.create_index("ix_character_fish_records_character_id", "character_fish_records", ["character_id"])
    op.create_index("ix_character_fish_records_weight_grams", "character_fish_records", ["weight_grams"])

    # Уровень рыбалки и состояние заброса. server_default обязателен: у всех
    # действующих персонажей строки уже есть, и без него они получили бы NULL
    # там, где код ждёт число (то же правило, что в миграции премиума).
    op.add_column("characters", sa.Column("fishing_level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("characters", sa.Column("fishing_xp", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("characters", sa.Column("fishing_cast_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("characters", sa.Column("fishing_bite_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("characters", sa.Column("fishing_pending_fish", sa.String(32), nullable=True))
    op.add_column("characters", sa.Column("fishing_pending_grams", sa.Integer(), nullable=True))

    # Счётчик убийств. Пересчитать задним числом нечем: истории боёв с мобами
    # в базе нет (pvp_battles пишет только PvP). Стартует с нуля у всех —
    # осознанное решение, а не упущение.
    op.add_column("characters", sa.Column("mobs_killed", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("characters", "mobs_killed")
    op.drop_column("characters", "fishing_pending_grams")
    op.drop_column("characters", "fishing_pending_fish")
    op.drop_column("characters", "fishing_bite_at")
    op.drop_column("characters", "fishing_cast_at")
    op.drop_column("characters", "fishing_xp")
    op.drop_column("characters", "fishing_level")
    op.drop_table("character_fish_records")
    op.drop_table("character_fish")
