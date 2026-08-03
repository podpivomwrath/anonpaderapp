"""Пепельная Песнь (обрывки) + маунты (патч 25, пп.6-7).

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "character_song_fragments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("fragment_index", sa.Integer(), nullable=False),
        sa.UniqueConstraint("character_id", "fragment_index", name="uq_character_song_char_index"),
    )
    op.create_index(
        "ix_character_song_fragments_character_id", "character_song_fragments", ["character_id"]
    )

    op.create_table(
        "character_mounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("mount_id", sa.String(32), nullable=False),
        sa.Column("obtained_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("character_id", "mount_id", name="uq_character_mounts_char_mount"),
    )
    op.create_index("ix_character_mounts_character_id", "character_mounts", ["character_id"])

    op.create_table(
        "mount_travels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("mount_id", sa.String(32), nullable=False),
        sa.Column("from_x", sa.Integer(), nullable=False),
        sa.Column("from_y", sa.Integer(), nullable=False),
        sa.Column("to_x", sa.Integer(), nullable=False),
        sa.Column("to_y", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("arrives_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ambush_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ambush_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="traveling"),
    )
    op.create_index("ix_mount_travels_character_id", "mount_travels", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_mount_travels_character_id", table_name="mount_travels")
    op.drop_table("mount_travels")
    op.drop_index("ix_character_mounts_character_id", table_name="character_mounts")
    op.drop_table("character_mounts")
    op.drop_index("ix_character_song_fragments_character_id", table_name="character_song_fragments")
    op.drop_table("character_song_fragments")
