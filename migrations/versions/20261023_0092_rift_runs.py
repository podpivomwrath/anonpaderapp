"""Заходы в разломы (2026-10-23): исход каждого захода, чтобы видеть
поражения - раньше погибшая группа следа не оставляла."""
import sqlalchemy as sa
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rift_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rift_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("ring", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("blood", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("members", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_rift_runs_rift_id", "rift_runs", ["rift_id"])
    op.create_index("ix_rift_runs_outcome", "rift_runs", ["outcome"])


def downgrade():
    op.drop_table("rift_runs")
