"""Торговля: повозки, давление рынка, караваны."""
import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_carts",
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("cart_x", sa.Integer(), nullable=False),
        sa.Column("cart_y", sa.Integer(), nullable=False),
        sa.Column("horses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("body", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plating", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("guard", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("durability", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("cargo", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("paid", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("trade_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trade_xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("profit_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "trade_markets",
        sa.Column("city", sa.String(16), primary_key=True),
        sa.Column("good_id", sa.String(32), primary_key=True),
        sa.Column("pressure", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "trade_caravans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("buys", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("sells", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trade_caravans_expires_at", "trade_caravans", ["expires_at"])


def downgrade():
    op.drop_index("ix_trade_caravans_expires_at", table_name="trade_caravans")
    op.drop_table("trade_caravans")
    op.drop_table("trade_markets")
    op.drop_table("character_carts")
