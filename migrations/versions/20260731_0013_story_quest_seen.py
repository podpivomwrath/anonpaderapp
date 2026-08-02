"""character_story_progress.quest_seen (патч 21: пометка наставника ❗ + пинг).

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "character_story_progress",
        sa.Column("quest_seen", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("character_story_progress", "quest_seen")
