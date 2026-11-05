"""Древние руины культа (2026-11-05): забеги и участники с мешками."""
import sqlalchemy as sa
from alembic import op

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ruin_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(8), nullable=False, server_default="active"),
        sa.Column("outcome", sa.String(12), nullable=True),
        sa.Column("leader_id", sa.Integer(), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("layout", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("pos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prev_pos", sa.Integer(), nullable=True),
        sa.Column("visited", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("cleared", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("phase", sa.String(8), nullable=False, server_default="walk"),
        sa.Column("pending", sa.JSON(), nullable=True),
        sa.Column("vote", sa.JSON(), nullable=True),
        sa.Column("deepest", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_action_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ruin_runs_status", "ruin_runs", ["status"])
    op.create_table(
        "ruin_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("ruin_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("hp", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("hp_before", sa.Integer(), nullable=True),
        sa.Column("dead", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("consumables_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bag", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("left_reason", sa.String(12), nullable=True),
    )
    op.create_index("ix_ruin_members_run_id", "ruin_members", ["run_id"])
    op.create_index("ix_ruin_members_character_id", "ruin_members", ["character_id"])
    op.create_index("ix_ruin_members_active", "ruin_members", ["active"])


def downgrade():
    op.drop_table("ruin_members")
    op.drop_table("ruin_runs")
