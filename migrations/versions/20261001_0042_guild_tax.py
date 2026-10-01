"""Налог гильдии на золото участников."""
import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("guilds", sa.Column("gold_tax", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("guilds", sa.Column("tax_collected", sa.BigInteger(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("guilds", "tax_collected")
    op.drop_column("guilds", "gold_tax")
