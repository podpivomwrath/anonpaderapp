"""Служебные предметы удалены из игры (2026-10-23, владелец).

Служебная редкость стояла в файле редкостей после легендарной, и Метка
Хранителя «поднимала» легендарный дроп до неё - с мобов падали «Служебный
жезл» и прочие. Тестовое «Перо Хранителя» ушло вместе с ними: удаляются все
вещи служебной редкости или с флагом admin_only, затем сам флаг.
"""
import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

SERVICE = "select id from items where rarity = 'admin' or admin_only"


def upgrade():
    op.execute(f"update items set socketed_gem_id = null where socketed_gem_id in ({SERVICE})")
    # inventory и guild_items уходят каскадом, история улучшений - SET NULL.
    op.execute(f"delete from inventory where item_id in ({SERVICE})")
    op.execute(f"delete from items where id in ({SERVICE})")
    op.drop_column("items", "admin_only")


def downgrade():
    op.add_column("items", sa.Column("admin_only", sa.Boolean(), nullable=False, server_default=sa.false()))
