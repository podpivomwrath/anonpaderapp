"""Курьер (2026-10-19): питомец-доставщик и посылки в пути."""
import sqlalchemy as sa
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("has_courier", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "courier_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("characters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ref", sa.String(64), nullable=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("reveal_sender", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("phase", sa.String(10), nullable=False, server_default="pickup"),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("last_step_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("waiting", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_courier_deliveries_sender_id", "courier_deliveries", ["sender_id"])
    op.create_index("ix_courier_deliveries_recipient_id", "courier_deliveries", ["recipient_id"])
    op.create_index("ix_courier_deliveries_status", "courier_deliveries", ["status"])


def downgrade():
    op.drop_table("courier_deliveries")
    op.drop_column("characters", "has_courier")
