"""Премиум-аккаунт (Метка Хранителя) + промокоды (патч 50)

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("premium_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "characters",
        sa.Column("premium_warn_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "characters",
        sa.Column("premium_expire_notified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "promo_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("rewards", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("max_activations", sa.Integer(), nullable=True),
        sa.Column("one_per_player", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_promo_codes_code", "promo_codes", ["code"], unique=True)

    op.create_table(
        "promo_activations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "promo_code_id", sa.Integer(),
            sa.ForeignKey("promo_codes.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "character_id", sa.Integer(),
            sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_promo_activations_promo_code_id", "promo_activations", ["promo_code_id"])
    op.create_index("ix_promo_activations_character_id", "promo_activations", ["character_id"])


def downgrade() -> None:
    op.drop_index("ix_promo_activations_character_id", table_name="promo_activations")
    op.drop_index("ix_promo_activations_promo_code_id", table_name="promo_activations")
    op.drop_table("promo_activations")
    op.drop_index("ix_promo_codes_code", table_name="promo_codes")
    op.drop_table("promo_codes")
    op.drop_column("characters", "premium_expire_notified")
    op.drop_column("characters", "premium_warn_sent")
    op.drop_column("characters", "premium_until")
