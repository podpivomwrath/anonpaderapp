"""Биржа: состояние курса в базе (чистый объём проданных самоцветов)."""
import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "exchange_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("net_sold", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("exchange_state")
