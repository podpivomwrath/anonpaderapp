"""Итоги сезона PvP (2026-10-30, владелец): места 1-5, титул и самоцветы."""
import sqlalchemy as sa
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pvp_season_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("season", sa.String(7), nullable=False),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pts", sa.Integer(), nullable=False),
        sa.Column("fights", sa.Integer(), nullable=False),
        sa.Column("title_id", sa.String(32), nullable=False),
        sa.Column("gems", sa.Integer(), nullable=False),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("season", "place", name="uq_pvp_season_place"),
        sa.UniqueConstraint("season", "character_id", name="uq_pvp_season_character"),
    )
    op.create_index("ix_pvp_season_results_season", "pvp_season_results", ["season"])
    op.create_index("ix_pvp_season_results_character_id", "pvp_season_results", ["character_id"])
    # Катсцена итога сезона: PTS до сжатия и какой итог уже показан.
    op.add_column("characters", sa.Column("pts_prev", sa.Integer(), nullable=True))
    op.add_column("characters", sa.Column("pvp_season_seen", sa.String(7), nullable=True))


def downgrade():
    op.drop_column("characters", "pvp_season_seen")
    op.drop_column("characters", "pts_prev")
    op.drop_table("pvp_season_results")
