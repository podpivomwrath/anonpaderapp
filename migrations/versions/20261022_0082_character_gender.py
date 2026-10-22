"""Пол персонажа (2026-10-22): силуэт героя в мини-аппе, мужской или женский."""
import sqlalchemy as sa
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("gender", sa.String(1), nullable=False, server_default="m"))


def downgrade():
    op.drop_column("characters", "gender")
