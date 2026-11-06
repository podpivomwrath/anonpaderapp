"""Клеймо Хранителя (2026-11-06): премиум для 60 уровня.

Ключи Монолита до 4 и слот пресета переезжают с Метки на Клеймо. Метки,
активные сейчас, держат их до конца своего срока: legacy_perks_until = premium_until.
"""
import sqlalchemy as sa
from alembic import op

revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("brand_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("characters", sa.Column("brand_warn_sent", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("characters", sa.Column("brand_expire_notified", sa.Boolean(), nullable=False,
                                          server_default=sa.false()))
    op.add_column("characters", sa.Column("legacy_perks_until", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE characters SET legacy_perks_until = premium_until WHERE premium_until > now()")


def downgrade():
    op.drop_column("characters", "legacy_perks_until")
    op.drop_column("characters", "brand_expire_notified")
    op.drop_column("characters", "brand_warn_sent")
    op.drop_column("characters", "brand_until")
