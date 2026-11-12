"""Топ руин (2026-11-13, владелец): пройденные этажи у каждого участника
забега, подведённые недели и призовые места.

Старые забеги заполняются: этаж засчитан, если хозяин этажа убит (вышли
живыми - всегда), иначе предыдущий. Изгнанным пройденное восстановить
нечем - у них ноль. Неделя 2026-11-02 отмечена подведённой: награды
начинаются с недели, в которую топ появился."""

import sqlalchemy as sa
from alembic import op

revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ruin_members", sa.Column("floors", sa.Integer, server_default="0", nullable=False))
    op.add_column("ruin_members", sa.Column("floors_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ruin_members_floors_at", "ruin_members", ["floors_at"])
    op.create_table(
        "ruin_weeks",
        sa.Column("week_start", sa.Date, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "ruin_week_results",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column("section", sa.String(8), nullable=False),
        sa.Column("place", sa.Integer, nullable=False),
        sa.Column("character_id", sa.Integer, sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("floors", sa.Integer, nullable=False),
        sa.Column("chests", sa.Integer, nullable=False),
        sa.Column("title_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("week_start", "section", "character_id", name="uq_ruin_week_result"),
    )
    op.create_index("ix_ruin_week_results_week_start", "ruin_week_results", ["week_start"])
    op.create_index("ix_ruin_week_results_character_id", "ruin_week_results", ["character_id"])
    op.execute(
        """
        UPDATE ruin_members AS m
        SET floors = CASE
                WHEN r.phase = 'cleared' OR (r.extra ->> 'boss_down') = 'true' THEN r.floor
                ELSE r.floor - 1
            END,
            floors_at = COALESCE(r.finished_at, r.last_action_at)
        FROM ruin_runs AS r
        WHERE r.id = m.run_id AND COALESCE(m.left_reason, '') <> 'kicked'
        """
    )
    op.execute("UPDATE ruin_members SET floors_at = NULL WHERE floors <= 0")
    op.execute("INSERT INTO ruin_weeks (week_start) VALUES ('2026-11-02')")


def downgrade():
    op.drop_index("ix_ruin_week_results_character_id", "ruin_week_results")
    op.drop_index("ix_ruin_week_results_week_start", "ruin_week_results")
    op.drop_table("ruin_week_results")
    op.drop_table("ruin_weeks")
    op.drop_index("ix_ruin_members_floors_at", "ruin_members")
    op.drop_column("ruin_members", "floors_at")
    op.drop_column("ruin_members", "floors")
