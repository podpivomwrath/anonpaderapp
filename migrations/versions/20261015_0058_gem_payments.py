"""Покупки самоцветов через ЮKassa."""
import sqlalchemy as sa
from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gem_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vk_id", sa.BigInteger(), nullable=False),
        sa.Column("pack_id", sa.String(16), nullable=False),
        sa.Column("gems", sa.Integer(), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("yk_payment_id", sa.String(64), nullable=True, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("credited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_gem_payments_character_id", "gem_payments", ["character_id"])
    op.create_index("ix_gem_payments_vk_id", "gem_payments", ["vk_id"])


def downgrade():
    op.drop_table("gem_payments")
