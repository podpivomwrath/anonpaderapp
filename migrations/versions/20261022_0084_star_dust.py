"""Звёздная пыль (2026-10-22): разбор уникальной вещи даёт 1 пыль."""
import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("star_dust", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("characters", "star_dust")
