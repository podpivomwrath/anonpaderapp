"""Журнал золота и самоцветов (2026-10-21): последние операции игрока."""
import sqlalchemy as sa
from alembic import op

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wallet_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("balance", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("note", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wallet_log_character_id", "wallet_log", ["character_id"])


def downgrade():
    op.drop_index("ix_wallet_log_character_id", "wallet_log")
    op.drop_table("wallet_log")
