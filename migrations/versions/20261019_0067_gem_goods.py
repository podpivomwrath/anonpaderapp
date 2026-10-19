"""Товары за самоцветы (2026-10-19): настойка пепла, секретный карман,
смена фракции."""
import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("ash_tincture_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "characters",
        sa.Column("secret_pocket", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("characters", sa.Column("faction_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("characters", "faction_changed_at")
    op.drop_column("characters", "secret_pocket")
    op.drop_column("characters", "ash_tincture_until")
