"""Пепельная донка (2026-10-23): работает час с постановки, а не «пока игрок
активен» - отметка активности продлевала её бесконечно."""
import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("donka_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("characters", "donka_until")
