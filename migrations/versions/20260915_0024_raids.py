"""Рейд-лобби (патч 53)

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raid_lobbies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("raid_id", sa.String(32), nullable=False),
        sa.Column(
            "leader_character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="waiting"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_raid_lobbies_group_id", "raid_lobbies", ["group_id"])
    op.create_index("ix_raid_lobbies_leader_character_id", "raid_lobbies", ["leader_character_id"])

    op.create_table(
        "raid_lobby_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "lobby_id", sa.Integer(), sa.ForeignKey("raid_lobbies.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("ready", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_raid_lobby_members_lobby_id", "raid_lobby_members", ["lobby_id"])
    op.create_index(
        "ix_raid_lobby_members_character_id", "raid_lobby_members", ["character_id"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_raid_lobby_members_character_id", table_name="raid_lobby_members")
    op.drop_index("ix_raid_lobby_members_lobby_id", table_name="raid_lobby_members")
    op.drop_table("raid_lobby_members")
    op.drop_index("ix_raid_lobbies_leader_character_id", table_name="raid_lobbies")
    op.drop_index("ix_raid_lobbies_group_id", table_name="raid_lobbies")
    op.drop_table("raid_lobbies")
