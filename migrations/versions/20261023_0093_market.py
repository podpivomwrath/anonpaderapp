"""Рынок (2026-10-23): заявки, сделки, ящик купленного."""
import sqlalchemy as sa
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "market_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("good", sa.String(64), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("qty_total", sa.Integer(), nullable=False),
        sa.Column("qty_left", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_market_orders_character_id", "market_orders", ["character_id"])
    op.create_index("ix_market_orders_status", "market_orders", ["status"])
    op.create_index("ix_market_orders_expires_at", "market_orders", ["expires_at"])
    op.create_index("ix_market_orders_book", "market_orders", ["good", "side", "status", "price"])
    op.create_table(
        "market_trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("good", sa.String(64), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("buyer_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_market_trades_good", "market_trades", ["good"])
    op.create_index("ix_market_trades_buyer_id", "market_trades", ["buyer_id"])
    op.create_index("ix_market_trades_seller_id", "market_trades", ["seller_id"])
    op.create_index("ix_market_trades_created_at", "market_trades", ["created_at"])
    op.create_table(
        "market_inbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("good", sa.String(64), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_market_inbox_character_id", "market_inbox", ["character_id"])


def downgrade():
    op.drop_table("market_inbox")
    op.drop_table("market_trades")
    op.drop_table("market_orders")
