"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-16

ВНИМАНИЕ: схема будет расширяться по мере добавления механик:
  - заточка потребует таблицу истории апгрейдов предметов;
  - гильдии/группы пока не включены;
  - у exchange_orders появится цена/курс вместе с алгоритмом биржи.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("vk_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("vk_id", name="uq_users_vk_id"),
    )
    op.create_index("ix_users_vk_id", "users", ["vk_id"])

    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        # base_class: warrior | rogue | mage (models.enums.BaseClass, хранится как VARCHAR)
        sa.Column("base_class", sa.String(20), nullable=False),
        sa.Column("subclass", sa.String(32), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("experience", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index("ix_characters_user_id", "characters", ["user_id"])

    op.create_table(
        "character_stats",
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("str", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("agi", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("int", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("vit", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("wil", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("unspent_points", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "character_buff_presets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("buff_ids", sa.JSON(), nullable=False),  # JSON-массив id баффов
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_character_buff_presets_character_id", "character_buff_presets", ["character_id"]
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slot", sa.String(32), nullable=False),
        sa.Column("base_stats", sa.JSON(), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False, server_default="gray"),
        sa.Column("enchant_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("awakened", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "inventory",
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("equipped", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "wallets",
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("farm_currency", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("donate_currency", sa.BigInteger(), nullable=False, server_default="0"),
    )

    op.create_table(
        "exchange_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "character_id",
            sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # direction: buy | sell (models.enums.OrderDirection)
        sa.Column("direction", sa.String(4), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_exchange_orders_character_id", "exchange_orders", ["character_id"])

    op.create_table(
        "combat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        # type: pve | pvp; status: pending | active | finished (models.enums)
        sa.Column("type", sa.String(4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("tick_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "combat_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("combat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=True),
        sa.Column("mob_id", sa.String(64), nullable=True),
        sa.Column("current_hp", sa.Integer(), nullable=False),
        # Объявленное действие на тик; сбрасывается в NULL после каждого резолва
        sa.Column("declared_action", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "(character_id IS NOT NULL) OR (mob_id IS NOT NULL)",
            name="ck_combat_participants_character_or_mob",
        ),
    )
    op.create_index("ix_combat_participants_session_id", "combat_participants", ["session_id"])


def downgrade() -> None:
    op.drop_table("combat_participants")
    op.drop_table("combat_sessions")
    op.drop_table("exchange_orders")
    op.drop_table("wallets")
    op.drop_table("inventory")
    op.drop_table("items")
    op.drop_table("character_buff_presets")
    op.drop_table("character_stats")
    op.drop_table("characters")
    op.drop_table("users")
