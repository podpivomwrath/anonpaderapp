"""Курьер носит пачку (2026-10-21): в ref - список позиций JSON, 64 символов мало."""
import sqlalchemy as sa
from alembic import op

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("courier_deliveries", "ref", type_=sa.Text(), existing_type=sa.String(64), existing_nullable=True)


def downgrade():
    op.alter_column("courier_deliveries", "ref", type_=sa.String(64), existing_type=sa.Text(), existing_nullable=True)
