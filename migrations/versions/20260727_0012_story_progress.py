"""character_story_progress (патч 18: сюжетные квесты — каркас).

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_story_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("region", sa.String(16), nullable=False),
        sa.Column("act", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("quest_step", sa.String(64), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("character_id", "region", name="uq_character_story_progress_character_region"),
    )
    op.create_index(
        "ix_character_story_progress_character_id", "character_story_progress", ["character_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_character_story_progress_character_id", table_name="character_story_progress")
    op.drop_table("character_story_progress")
