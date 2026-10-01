"""Биржа: дневные снимки курса для графика."""
import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "exchange_daily",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("buy_lot", sa.BigInteger(), nullable=False),
        sa.Column("sell_lot", sa.BigInteger(), nullable=False),
        sa.Column("bought_lots", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sold_lots", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("exchange_daily")
