"""Долгий путь: что найдено за поход (реликвии, ларцы) - для итога похода."""
import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("character_voyages", sa.Column("trip_items", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("character_voyages", "trip_items")
