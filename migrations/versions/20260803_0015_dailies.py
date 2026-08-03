"""Ежедневные задания, стрики, награды за вход, титулы (патч 23).

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "characters", sa.Column("login_streak", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "characters", sa.Column("daily_streak", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("characters", sa.Column("last_login_date", sa.Date(), nullable=True))
    op.add_column("characters", sa.Column("last_daily_completed_date", sa.Date(), nullable=True))
    op.add_column(
        "characters", sa.Column("login_cycle_day", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("characters", sa.Column("active_title_id", sa.String(32), nullable=True))

    op.create_table(
        "character_dailies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("quest_id", sa.String(64), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("date", sa.Date(), nullable=False),
        sa.UniqueConstraint("character_id", "quest_id", "date", name="uq_character_dailies_char_quest_date"),
    )
    op.create_index("ix_character_dailies_character_id", "character_dailies", ["character_id"])
    op.create_index("ix_character_dailies_date", "character_dailies", ["date"])

    op.create_table(
        "character_titles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("title_id", sa.String(32), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("character_id", "title_id", name="uq_character_titles_char_title"),
    )
    op.create_index("ix_character_titles_character_id", "character_titles", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_character_titles_character_id", table_name="character_titles")
    op.drop_table("character_titles")
    op.drop_index("ix_character_dailies_date", table_name="character_dailies")
    op.drop_index("ix_character_dailies_character_id", table_name="character_dailies")
    op.drop_table("character_dailies")
    op.drop_column("characters", "active_title_id")
    op.drop_column("characters", "login_cycle_day")
    op.drop_column("characters", "last_daily_completed_date")
    op.drop_column("characters", "last_login_date")
    op.drop_column("characters", "daily_streak")
    op.drop_column("characters", "login_streak")
