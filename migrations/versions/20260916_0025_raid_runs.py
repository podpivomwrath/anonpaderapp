"""Durable raid key receipts and restart recovery."""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "raid_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("leader_character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raid_id", sa.String(32), nullable=False),
        sa.Column("members", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_raid_runs_status", "raid_runs", ["status"])


def downgrade():
    op.drop_table("raid_runs")
