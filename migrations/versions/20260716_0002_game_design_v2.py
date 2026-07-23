"""game design v2: respawn, duel/pvp_group, stakes, upgrade history, gem socket

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Смерть/возрождение (п.5): NULL — жив
    op.add_column(
        "characters",
        sa.Column("respawn_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Боевые сессии: типы pve | pvp_group | duel + итог боя
    op.alter_column(
        "combat_sessions",
        "type",
        existing_type=sa.String(4),
        type_=sa.String(16),
        existing_nullable=False,
    )
    op.add_column(
        "combat_sessions",
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "combat_sessions", sa.Column("winner_side", sa.Integer(), nullable=True)
    )

    # Сторона (команда) участника — 0/1
    op.add_column(
        "combat_participants",
        sa.Column("side", sa.Integer(), nullable=False, server_default="0"),
    )

    # Экипировка: слот самоцвета (открывается пробуждением), тир 'grey' (имена v2)
    op.add_column(
        "items",
        sa.Column(
            "socketed_gem_id",
            sa.Integer(),
            sa.ForeignKey("items.id", name="fk_items_socketed_gem_id_items"),
            nullable=True,
        ),
    )
    op.alter_column("items", "tier", server_default="grey")

    # Биржа: сколько золота уплачено/получено по сделке
    op.add_column(
        "exchange_orders",
        sa.Column("gold_amount", sa.BigInteger(), nullable=False, server_default="0"),
    )

    # История заточки/пробуждения
    op.create_table(
        "item_upgrade_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        # SET NULL: при уничтожении предмета (пробуждение) история остаётся
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(16), nullable=False),  # enchant | awaken
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("level_before", sa.Integer(), nullable=False),
        sa.Column("level_after", sa.Integer(), nullable=False),
        sa.Column(
            "item_destroyed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_item_upgrade_history_item_id", "item_upgrade_history", ["item_id"])

    # Ставки PvP (п.4): переводы farm-валюты от проигравших победителям
    op.create_table(
        "pvp_stake_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("combat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "loser_character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id"),
            nullable=False,
        ),
        sa.Column(
            "winner_character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_pvp_stake_transfers_session_id", "pvp_stake_transfers", ["session_id"])


def downgrade() -> None:
    op.drop_table("pvp_stake_transfers")
    op.drop_table("item_upgrade_history")
    op.drop_column("exchange_orders", "gold_amount")
    op.alter_column("items", "tier", server_default="gray")
    op.drop_column("items", "socketed_gem_id")
    op.drop_column("combat_participants", "side")
    op.drop_column("combat_sessions", "winner_side")
    op.drop_column("combat_sessions", "finished_at")
    op.alter_column(
        "combat_sessions",
        "type",
        existing_type=sa.String(16),
        type_=sa.String(4),
        existing_nullable=False,
    )
    op.drop_column("characters", "respawn_at")
