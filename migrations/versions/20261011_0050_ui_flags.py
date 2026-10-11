"""Мини-апп: что игрок уже видел (вступление, тур, подсказки) и звук."""
import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("ui_flags", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("characters", "ui_flags")
