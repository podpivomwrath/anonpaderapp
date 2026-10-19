"""Турбоишак бежит по клеткам, а не перескакивает (2026-10-19)."""
import sqlalchemy as sa
from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("turbo_ishak_days", sa.Column("from_x", sa.Integer(), nullable=True))
    op.add_column("turbo_ishak_days", sa.Column("from_y", sa.Integer(), nullable=True))
    op.add_column("turbo_ishak_days", sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("turbo_ishak_days", "run_started_at")
    op.drop_column("turbo_ishak_days", "from_y")
    op.drop_column("turbo_ishak_days", "from_x")
