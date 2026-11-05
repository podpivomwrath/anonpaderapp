"""Руины культа, этапы 2-4 (2026-11-05): дары, выбор дара, состояние забега."""
import sqlalchemy as sa
from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ruin_runs", sa.Column("gifts", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("ruin_runs", sa.Column("offer", sa.JSON(), nullable=True))
    op.add_column("ruin_runs", sa.Column("extra", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("ruin_runs", "extra")
    op.drop_column("ruin_runs", "offer")
    op.drop_column("ruin_runs", "gifts")
