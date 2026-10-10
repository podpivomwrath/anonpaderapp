"""Разломы: случайные данжи на карте и счётчик их появления."""
import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("ring", sa.Integer(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("state", sa.String(16), nullable=False, server_default="free"),
        sa.Column("members", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("wait_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("spawned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rifts_status", "rifts", ["status"])
    op.create_table(
        "rift_meter",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("explorations", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("rift_meter")
    op.drop_index("ix_rifts_status", "rifts")
    op.drop_table("rifts")
