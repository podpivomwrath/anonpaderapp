"""PvP: уровень и подкласс участников на момент боя (2026-10-21)."""
import sqlalchemy as sa
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pvp_battles", sa.Column("participants", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("pvp_battles", "participants")
