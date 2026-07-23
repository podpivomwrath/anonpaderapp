"""character_unlocked_buffs + character_trial_progress + characters.subclass_select_state
(патч 12: подклассы 30 ур. и классовые испытания).

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("subclass_select_state", sa.String(32), nullable=True))

    op.create_table(
        "character_unlocked_buffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("buff_id", sa.String(64), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("character_id", "buff_id", name="uq_character_unlocked_buffs_character_buff"),
    )
    op.create_index(
        "ix_character_unlocked_buffs_character_id", "character_unlocked_buffs", ["character_id"]
    )

    op.create_table(
        "character_trial_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("trial_id", sa.String(64), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("character_id", "trial_id", name="uq_character_trial_progress_character_trial"),
    )
    op.create_index(
        "ix_character_trial_progress_character_id", "character_trial_progress", ["character_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_character_trial_progress_character_id", table_name="character_trial_progress")
    op.drop_table("character_trial_progress")
    op.drop_index("ix_character_unlocked_buffs_character_id", table_name="character_unlocked_buffs")
    op.drop_table("character_unlocked_buffs")
    op.drop_column("characters", "subclass_select_state")
