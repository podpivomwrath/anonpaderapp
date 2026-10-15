"""Торговля, этапы 2-3 (2026-10-16): срочные заказы, события в пути, итоги
недели фракций, доля налога с переводов первому поставщику."""
import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("trade_carts", sa.Column("event", sa.String(16), nullable=True))
    op.add_column("trade_trips", sa.Column("event", sa.String(16), nullable=True))
    op.add_column("trade_trips", sa.Column("order_crates", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "trade_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city", sa.String(16), nullable=False),
        sa.Column("good_id", sa.String(32), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("left", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_orders_expires_at", "trade_orders", ["expires_at"])
    op.create_table(
        "faction_weeks",
        sa.Column("city", sa.String(16), primary_key=True),
        sa.Column("week_start", sa.Date(), primary_key=True),
        sa.Column("first_id", sa.Integer(), nullable=True),
        sa.Column("second_id", sa.Integer(), nullable=True),
        sa.Column("third_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "faction_payouts",
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("gold", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("gems", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("faction_payouts")
    op.drop_table("faction_weeks")
    op.drop_index("ix_trade_orders_expires_at", table_name="trade_orders")
    op.drop_table("trade_orders")
    op.drop_column("trade_trips", "order_crates")
    op.drop_column("trade_trips", "event")
    op.drop_column("trade_carts", "event")
