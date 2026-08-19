"""Группы (патч 51, ч.2)

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "leader_character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_groups_leader_character_id", "groups", ["leader_character_id"])

    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_group_members_group_id", "group_members", ["group_id"])
    op.create_index(
        "ix_group_members_character_id", "group_members", ["character_id"], unique=True,
    )

    op.create_table(
        "group_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column(
            "from_character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "to_character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.create_index("ix_group_invites_group_id", "group_invites", ["group_id"])
    op.create_index("ix_group_invites_to_character_id", "group_invites", ["to_character_id"])


def downgrade() -> None:
    op.drop_index("ix_group_invites_to_character_id", table_name="group_invites")
    op.drop_index("ix_group_invites_group_id", table_name="group_invites")
    op.drop_table("group_invites")
    op.drop_index("ix_group_members_character_id", table_name="group_members")
    op.drop_index("ix_group_members_group_id", table_name="group_members")
    op.drop_table("group_members")
    op.drop_index("ix_groups_leader_character_id", table_name="groups")
    op.drop_table("groups")
