"""quest xp_reward → из content (progression-patch-4: первый квест 500 опыта)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-20

Пересинхронизирует награды квестов с content/quests.json (миграция 0004
засеяла старые значения; xp_reward менялся патчем прогрессии).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from game.content_loader import load_quest_defs

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    quests = sa.table(
        "quests",
        sa.column("code", sa.String),
        sa.column("xp_reward", sa.Integer),
        sa.column("gold_reward", sa.Integer),
    )
    for d in load_quest_defs():
        op.execute(
            quests.update()
            .where(quests.c.code == op.inline_literal(d.code))
            .values(xp_reward=d.xp_reward, gold_reward=d.gold_reward)
        )


def downgrade() -> None:
    pass  # награды — справочные данные, откат не требуется
