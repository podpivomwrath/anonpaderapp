"""Журнал передач между игроками."""
import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transfer_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("from_character_id", sa.Integer(),
                  sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_character_id", sa.Integer(),
                  sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ref", sa.String(64), nullable=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transfer_log_from_character_id", "transfer_log", ["from_character_id"])
    op.create_index("ix_transfer_log_to_character_id", "transfer_log", ["to_character_id"])
    op.create_index("ix_transfer_log_created_at", "transfer_log", ["created_at"])


def downgrade():
    op.drop_table("transfer_log")
