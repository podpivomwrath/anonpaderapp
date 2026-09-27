"""Пепельный ларец - предмет в сумке, открывается вручную (патч 106)."""
import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    # Все старые строки - уже открытые ларцы (раньше открывались сразу).
    op.add_column("character_lootboxes",
                  sa.Column("status", sa.String(8), nullable=False, server_default="opened"))
    op.add_column("character_lootboxes", sa.Column("streak", sa.Integer(), nullable=True))
    op.add_column("character_lootboxes", sa.Column(
        "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True))
    op.alter_column("character_lootboxes", "grade", existing_type=sa.String(16), nullable=True)
    op.alter_column("character_lootboxes", "reward_summary", existing_type=sa.String(256), nullable=True)
    op.alter_column("character_lootboxes", "opened_at", existing_type=sa.DateTime(timezone=True),
                    nullable=True, server_default=None)
    op.execute("UPDATE character_lootboxes SET granted_at = opened_at")
    op.create_index("ix_character_lootboxes_char_status", "character_lootboxes", ["character_id", "status"])


def downgrade():
    op.execute("DELETE FROM character_lootboxes WHERE status <> 'opened'")
    op.drop_index("ix_character_lootboxes_char_status", "character_lootboxes")
    op.alter_column("character_lootboxes", "opened_at", existing_type=sa.DateTime(timezone=True),
                    nullable=False, server_default=sa.func.now())
    op.alter_column("character_lootboxes", "reward_summary", existing_type=sa.String(256), nullable=False)
    op.alter_column("character_lootboxes", "grade", existing_type=sa.String(16), nullable=False)
    op.drop_column("character_lootboxes", "granted_at")
    op.drop_column("character_lootboxes", "streak")
    op.drop_column("character_lootboxes", "status")
