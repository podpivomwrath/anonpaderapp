"""Руны-навыки (2026-11-10): выбор развилки ступени III у каждого навыка."""
import sqlalchemy as sa
from alembic import op

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("skill_forks", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("characters", "skill_forks")
