"""Отказ от подкласса у Хранителя Списков (2026-10-20): игрок остаётся
базовым классом и собирает пресеты из баффов своего базового класса."""
import sqlalchemy as sa
from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "characters", sa.Column("subclass_declined", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade():
    op.drop_column("characters", "subclass_declined")
