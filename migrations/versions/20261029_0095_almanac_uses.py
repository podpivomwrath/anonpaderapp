"""Альманах на срабатываниях (2026-10-29): сколько из запаса уже потрачено.
Страницы альманаха лежат в count той же строки."""
import sqlalchemy as sa
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_craft_gear", sa.Column("used", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("character_craft_gear", "used")
