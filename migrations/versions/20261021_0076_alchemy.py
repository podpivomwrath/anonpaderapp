"""Алхимия (2026-10-21): уровень и работа в доме (варка, позже готовка)."""
import sqlalchemy as sa
from alembic import op

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("alchemy_level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("characters", sa.Column("alchemy_xp", sa.BigInteger(), nullable=False, server_default="0"))
    op.add_column("characters", sa.Column("house_work", sa.String(64), nullable=True))
    op.add_column("characters", sa.Column("house_work_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("characters", "house_work_until")
    op.drop_column("characters", "house_work")
    op.drop_column("characters", "alchemy_xp")
    op.drop_column("characters", "alchemy_level")
