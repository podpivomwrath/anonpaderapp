"""Мировые боссы (патч 104)."""
import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "world_bosses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("boss_id", sa.String(48), nullable=False),
        sa.Column("ring", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("max_hp", sa.BigInteger(), nullable=False),
        sa.Column("hp", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("spawned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_world_bosses_status", "world_bosses", ["status"])
    op.create_table(
        "world_boss_contributions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "world_boss_id", sa.Integer(),
            sa.ForeignKey("world_bosses.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("damage", sa.BigInteger(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("world_boss_id", "character_id", name="uq_world_boss_contribution"),
    )
    op.create_index(
        "ix_world_boss_contributions_world_boss_id", "world_boss_contributions", ["world_boss_id"]
    )
    op.create_index(
        "ix_world_boss_contributions_character_id", "world_boss_contributions", ["character_id"]
    )
    op.create_table(
        "world_boss_meter",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("explorations", sa.Integer(), nullable=False),
        sa.Column("last_spawn_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Строка счётчика одна на мир. Заводим сразу: при ленивом создании два
    # первых параллельных исследования вставили бы её оба и одно упало бы.
    op.execute("INSERT INTO world_boss_meter (id, explorations) VALUES (1, 0)")


def downgrade():
    op.drop_table("world_boss_meter")
    op.drop_table("world_boss_contributions")
    op.drop_table("world_bosses")
