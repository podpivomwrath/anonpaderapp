"""Рейтинг PvP - PTS: очки персонажа и сезон, к которому они относятся."""
import sqlalchemy as sa
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("pts", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("characters", sa.Column("pts_season", sa.String(7), nullable=True))
    op.create_index("ix_characters_pts", "characters", [sa.text("pts DESC")])
    # Старый топ по победам обнуляется целиком: рейтинг начинается с чистого
    # листа, у всех 1 000 PTS и ноль боёв (2026-10-13, решение владельца).
    op.execute("UPDATE characters SET pvp_wins = 0, pvp_losses = 0")


def downgrade():
    op.drop_index("ix_characters_pts", table_name="characters")
    op.drop_column("characters", "pts_season")
    op.drop_column("characters", "pts")
