"""Склад гильдии (2026-10-23): припасы стаком - травы, рыба, блюда, зелья."""
import sqlalchemy as sa
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "guild_stock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("guild_id", sa.Integer(), sa.ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("ref", sa.String(32), nullable=False),
        sa.Column("grade", sa.String(16), nullable=False, server_default=""),
        sa.Column("count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("guild_id", "kind", "ref", "grade", name="uq_guild_stock"),
    )
    op.create_index("ix_guild_stock_guild_id", "guild_stock", ["guild_id"])


def downgrade():
    op.drop_index("ix_guild_stock_guild_id", "guild_stock")
    op.drop_table("guild_stock")
