"""Пепельная донка (2026-10-23): авторыбалка из магазина - куплена ли и
стоит ли сейчас у воды."""
import sqlalchemy as sa
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("has_donka", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("characters", sa.Column("fishing_auto", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("characters", "fishing_auto")
    op.drop_column("characters", "has_donka")
