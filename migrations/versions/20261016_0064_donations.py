"""Учёт донатов (2026-10-16): таблица и донаты, принятые до запуска ЮKassa
(список владельца; vk_id сверены с проды по именам VK)."""
import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

#: (vk_id, имя VK, персонаж на момент записи, рублей)
EARLIER = [
    (245009805, "Вячеслав Чайка", "Кайр", 2000),
    (450240819, "Степа Яровенко", "Гостус", 500),
    (553069569, "Тальхарп-Шуудан-Малал Движуха-Энвилоуп-Изгоев", "Мор", 2000),
    (537117757, "Сергей Артеменко", "Нежа", 2000),
    (812238761, "Николай Васильев", "Мич", 100),
    (178169665, "Сергей Хромых", "Archon", 500),
    (167900580, "Никита Гора", "EGERb", 400),
    (343930529, "Никита Молчанов", "Чача", 1500),
    (84430623, "Михаил Сачнёв", "Бубылда", 5000),
    (841301021, "Алексей Фаиров", "Алексио", 5000),
]


def upgrade():
    table = op.create_table(
        "donations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vk_id", sa.BigInteger(), nullable=True),
        sa.Column("donor", sa.String(160), nullable=False),
        sa.Column("character_name", sa.String(64), nullable=True),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("gems", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("payment_id", sa.String(64), nullable=True, unique=True),
        sa.Column("note", sa.String(256), nullable=True),
        sa.Column("added_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_donations_vk_id", "donations", ["vk_id"])
    op.bulk_insert(table, [
        {"vk_id": vk, "donor": donor, "character_name": char, "amount_rub": rub, "source": "manual",
         "note": "до запуска ЮKassa (список владельца)"}
        for vk, donor, char, rub in EARLIER
    ])


def downgrade():
    op.drop_index("ix_donations_vk_id", table_name="donations")
    op.drop_table("donations")
