"""Долгие путешествия (AFK): снаряжение и текущий поход персонажа."""
import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "character_voyages",
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("endurance", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("haul", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("guide", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(8), nullable=False, server_default="home"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hours_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trip_xp", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("trip_gold", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_event", sa.String(24), nullable=True),
        sa.Column("voyages_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_character_voyages_status", "character_voyages", ["status"])


def downgrade():
    op.drop_index("ix_character_voyages_status", table_name="character_voyages")
    op.drop_table("character_voyages")
