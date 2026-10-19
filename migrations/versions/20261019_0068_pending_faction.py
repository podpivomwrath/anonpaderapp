"""Смена фракции, купленная в бою, срабатывает после боя (2026-10-19)."""
import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("pending_faction", sa.String(16), nullable=True))


def downgrade():
    op.drop_column("characters", "pending_faction")
