"""Мастерский рецепт (2026-10-23): перстень и постоянная прибавка эликсира."""
import sqlalchemy as sa
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("ring_id", sa.String(16), nullable=True))
    op.add_column("characters", sa.Column("perm_stat_pct", sa.Float(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("characters", "perm_stat_pct")
    op.drop_column("characters", "ring_id")
