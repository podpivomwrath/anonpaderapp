"""Удалена неподключённая механика ставок PvP (доля золота проигравшего).

В игре её никто не вызывал: проигравший теряет трофеи, а не золото. На проде
таблица была пуста. Решение владельца - удалить механику целиком.
"""
import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("pvp_stake_transfers")


def downgrade():
    op.create_table(
        "pvp_stake_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id", sa.Integer(),
            sa.ForeignKey("combat_sessions.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("loser_character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("winner_character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
