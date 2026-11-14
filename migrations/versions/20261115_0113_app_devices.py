"""Приложение «Монолит» (2026-11-15, владелец): подключённые устройства и
одноразовые коды привязки из мини-аппа (models/app_device.py)."""

import sqlalchemy as sa
from alembic import op

revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_devices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(48), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_app_devices_user_id", "app_devices", ["user_id"])
    op.create_table(
        "app_pair_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_app_pair_codes_user_id", "app_pair_codes", ["user_id"])


def downgrade():
    op.drop_index("ix_app_pair_codes_user_id", "app_pair_codes")
    op.drop_table("app_pair_codes")
    op.drop_index("ix_app_devices_user_id", "app_devices")
    op.drop_table("app_devices")
