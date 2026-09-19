"""Mining telemetry: one row per ore spawn and per completed dig."""
import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    # Журнал событий, а не счётчики: по строкам можно задать вопрос, который
    # не предусмотрели заранее (скорость спавна, оборот, длительность добычи),
    # а по счётчикам — только тот, что заложили.
    op.create_table(
        "mining_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("mine_id", sa.String(48), nullable=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ore_id", sa.String(32), nullable=True),
        sa.Column("grade", sa.String(16), nullable=True),
        sa.Column("seconds", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mining_events_created_at", "mining_events", ["created_at"])
    op.create_index("ix_mining_events_kind_created", "mining_events", ["kind", "created_at"])


def downgrade():
    op.drop_index("ix_mining_events_kind_created", table_name="mining_events")
    op.drop_index("ix_mining_events_created_at", table_name="mining_events")
    op.drop_table("mining_events")
