"""Выбранная рамка венца."""
import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    # nullable: NULL значит «не выбирал», и это не то же самое, что «снял».
    # Смешать их нельзя - снятая рамка возвращалась бы сама при получении
    # следующего венца.
    op.add_column("characters", sa.Column("crown_frame", sa.String(32), nullable=True))


def downgrade():
    op.drop_column("characters", "crown_frame")
