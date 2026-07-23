"""world: позиция персонажа, перемещение, квесты

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from game.content_loader import load_quest_defs

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("pos_x", sa.Integer(), nullable=True))
    op.add_column("characters", sa.Column("pos_y", sa.Integer(), nullable=True))
    op.add_column("characters", sa.Column("travel_target_x", sa.Integer(), nullable=True))
    op.add_column("characters", sa.Column("travel_target_y", sa.Integer(), nullable=True))
    op.add_column(
        "characters",
        sa.Column("travel_arrives_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "quests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("title", sa.String(64), nullable=False),
        sa.Column("progress_label", sa.String(64), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("xp_reward", sa.Integer(), nullable=False),
        sa.Column("gold_reward", sa.Integer(), nullable=False),
        sa.UniqueConstraint("code", name="uq_quests_code"),
    )

    op.create_table(
        "character_quests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quest_id", sa.Integer(), sa.ForeignKey("quests.id"), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        # active | ready | completed (models.enums.QuestStatus)
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.UniqueConstraint(
            "character_id", "quest_id", name="uq_character_quests_character_quest"
        ),
    )
    op.create_index(
        "ix_character_quests_character_id", "character_quests", ["character_id"]
    )

    # Сид квестов — единственный источник данных content/quests.json,
    # тот же файл читают тесты (quest_service тесты сеют из него же).
    quests_table = sa.table(
        "quests",
        sa.column("code", sa.String),
        sa.column("region", sa.String),
        sa.column("title", sa.String),
        sa.column("progress_label", sa.String),
        sa.column("target_count", sa.Integer),
        sa.column("xp_reward", sa.Integer),
        sa.column("gold_reward", sa.Integer),
    )
    op.bulk_insert(quests_table, [d.model_dump() for d in load_quest_defs()])


def downgrade() -> None:
    op.drop_table("character_quests")
    op.drop_table("quests")
    op.drop_column("characters", "travel_arrives_at")
    op.drop_column("characters", "travel_target_y")
    op.drop_column("characters", "travel_target_x")
    op.drop_column("characters", "pos_y")
    op.drop_column("characters", "pos_x")
