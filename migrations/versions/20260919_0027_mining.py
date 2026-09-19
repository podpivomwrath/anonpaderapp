"""Mining: ore inventory, shared mine veins, mining level and dig state."""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    # Руда в инвентаре: стак по (вид + градация) ШТУКАМИ. Потолка нет.
    op.create_table(
        "character_ore",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ore_id", sa.String(32), nullable=False),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("character_id", "ore_id", "grade", name="uq_character_ore_char_ore_grade"),
    )
    op.create_index("ix_character_ore_character_id", "character_ore", ["character_id"])

    # Состояние МИРА: сколько руды лежит в каждом статичном руднике. Строки
    # заводятся лениво при первом обращении — сидировать 27 штук в миграции
    # незачем, иначе каждый новый рудник в контенте требовал бы миграции.
    op.create_table(
        "mine_veins",
        sa.Column("mine_id", sa.String(48), primary_key=True),
        sa.Column("ore_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # Уровень горного дела и состояние добычи. server_default обязателен:
    # строки действующих персонажей уже существуют.
    op.add_column("characters", sa.Column("mining_level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("characters", sa.Column("mining_xp", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("characters", sa.Column("mining_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("characters", sa.Column("mining_mine_id", sa.String(48), nullable=True))


def downgrade():
    op.drop_column("characters", "mining_mine_id")
    op.drop_column("characters", "mining_ends_at")
    op.drop_column("characters", "mining_xp")
    op.drop_column("characters", "mining_level")
    op.drop_table("mine_veins")
    op.drop_table("character_ore")
