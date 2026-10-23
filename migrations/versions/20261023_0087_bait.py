"""Прикормка (2026-10-23): до какого времени у персонажа клюёт быстрее."""
import sqlalchemy as sa
from alembic import op

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("bait_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("characters", "bait_until")
