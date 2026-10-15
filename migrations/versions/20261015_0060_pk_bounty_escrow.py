"""Награда за голову - залог (2026-10-15): уже назначенные награды были
обещанием и не списывались. Списываем сейчас, сколько есть в кошельке (не
больше награды), - это и становится залогом. Иначе при сходе меток игрок
получил бы «возврат» золота, которое у него не забирали."""
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        WITH esc AS (
            SELECT c.id, LEAST(c.pk_bounty, GREATEST(w.farm_currency, 0)) AS amount
            FROM characters c JOIN wallets w ON w.character_id = c.id
            WHERE c.pk_bounty > 0
        ), charged AS (
            UPDATE wallets w SET farm_currency = w.farm_currency - esc.amount
            FROM esc WHERE w.character_id = esc.id
        )
        UPDATE characters c SET pk_bounty = esc.amount FROM esc WHERE c.id = esc.id
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE wallets w SET farm_currency = w.farm_currency + c.pk_bounty
        FROM characters c WHERE w.character_id = c.id AND c.pk_bounty > 0
        """
    )
