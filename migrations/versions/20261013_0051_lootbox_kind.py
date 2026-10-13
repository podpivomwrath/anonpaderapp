"""Ларцы кровавого разлома: у ларца в сумке появляется вид (пепельный,
руды, расходников)."""
import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "character_lootboxes",
        sa.Column("kind", sa.String(16), nullable=False, server_default="ashen"),
    )


def downgrade():
    op.drop_column("character_lootboxes", "kind")
