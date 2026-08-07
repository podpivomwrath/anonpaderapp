"""Админка: журнал действий, репорты багов, лог смертей, бан/активность (патч 27).

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "characters",
        sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("characters", sa.Column("ban_reason", sa.String(256), nullable=True))
    op.add_column("characters", sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "admin_actions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_vk_id", sa.BigInteger(), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column(
            "target_character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_admin_actions_target_character_id", "admin_actions", ["target_character_id"])

    op.create_table(
        "bug_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bug_reports_character_id", "bug_reports", ["character_id"])

    op.create_table(
        "character_deaths",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("pos_x", sa.Integer(), nullable=True),
        sa.Column("pos_y", sa.Integer(), nullable=True),
        sa.Column("cause", sa.String(8), nullable=False),
        sa.Column("died_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_character_deaths_character_id", "character_deaths", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_character_deaths_character_id", table_name="character_deaths")
    op.drop_table("character_deaths")
    op.drop_index("ix_bug_reports_character_id", table_name="bug_reports")
    op.drop_table("bug_reports")
    op.drop_index("ix_admin_actions_target_character_id", table_name="admin_actions")
    op.drop_table("admin_actions")

    op.drop_column("characters", "banned_until")
    op.drop_column("characters", "ban_reason")
    op.drop_column("characters", "is_banned")
    op.drop_column("characters", "last_active_at")
