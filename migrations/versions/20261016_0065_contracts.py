"""Заказы на игроков (2026-10-16): заказ и кто его взял."""
import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("orderer_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kills_total", sa.Integer(), nullable=False),
        sa.Column("kills_left", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_contracts_orderer_id", "contracts", ["orderer_id"])
    op.create_index("ix_contracts_target_id", "contracts", ["target_id"])
    op.create_index("ix_contracts_expires_at", "contracts", ["expires_at"])
    op.create_table(
        "contract_takers",
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("contracts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("taken_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contract_takers_character_id", "contract_takers", ["character_id"])


def downgrade():
    op.drop_index("ix_contract_takers_character_id", table_name="contract_takers")
    op.drop_table("contract_takers")
    op.drop_index("ix_contracts_expires_at", table_name="contracts")
    op.drop_index("ix_contracts_target_id", table_name="contracts")
    op.drop_index("ix_contracts_orderer_id", table_name="contracts")
    op.drop_table("contracts")
