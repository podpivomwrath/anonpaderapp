"""Имя и фамилия игрока из VK - для поиска в админ-панели."""
import sqlalchemy as sa
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("vk_first_name", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("vk_last_name", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("vk_names_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for col in ("vk_names_at", "vk_last_name", "vk_first_name"):
        op.drop_column("users", col)
