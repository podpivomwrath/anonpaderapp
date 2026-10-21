"""Журнал ресурсов игрока (2026-10-21)."""
import sqlalchemy as sa
from alembic import op

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "resource_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("ref", sa.String(80), nullable=False),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resource_log_character_id", "resource_log", ["character_id"])
    op.create_index("ix_resource_log_created_at", "resource_log", ["created_at"])


def downgrade():
    op.drop_index("ix_resource_log_created_at", "resource_log")
    op.drop_index("ix_resource_log_character_id", "resource_log")
    op.drop_table("resource_log")
