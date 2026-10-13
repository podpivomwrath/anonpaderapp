"""Ежедневное задание хранит свою цель: уровень, выросший днём, её не поднимает."""
import sqlalchemy as sa
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_dailies", sa.Column("target", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("character_dailies", "target")
