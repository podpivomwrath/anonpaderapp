"""Из какой гильдии ушёл (2026-10-31): возврат в ту же - через неделю,
бывшие согильдийцы 48 часов не дерутся в открытом PvP. Без внешнего ключа:
распущенная гильдия удаляется, а память об уходе нужна."""
import sqlalchemy as sa
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("guild_left_id", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("characters", "guild_left_id")
