"""Сопротивления (2026-11-02): у кованых вещей - одно случайное сопротивление
(crit | dodge | dot), уже скованным выдаётся броском прямо здесь; у персонажа -
Перстень Несгоревшего."""
import sqlalchemy as sa
from alembic import op

revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("items", sa.Column("craft_resist", sa.String(8), nullable=True))
    op.add_column("characters", sa.Column("resist_ring", sa.Boolean(), nullable=False, server_default="false"))
    op.execute(
        "UPDATE items SET craft_resist = (ARRAY['crit', 'dodge', 'dot'])[1 + floor(random() * 3)::int] "
        "WHERE craft_spec IS NOT NULL"
    )


def downgrade():
    op.drop_column("characters", "resist_ring")
    op.drop_column("items", "craft_resist")
