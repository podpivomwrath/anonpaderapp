"""Турбоишак (2026-10-19): имя маунта от игрока и ишак дня."""
import sqlalchemy as sa
from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_mounts", sa.Column("nickname", sa.String(24), nullable=True))
    op.create_table(
        "turbo_ishak_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.String(10), nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="planned"),
        sa.Column("spawn_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_move_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("x", sa.Integer(), nullable=True),
        sa.Column("y", sa.Integer(), nullable=True),
        sa.Column("caught_by", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("caught_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("turbo_ishak_days")
    op.drop_column("character_mounts", "nickname")
