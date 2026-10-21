"""Дом за самоцветы (2026-10-21): печь и алхимический стол в родном городе."""
import sqlalchemy as sa
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("has_house", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("characters", "has_house")
