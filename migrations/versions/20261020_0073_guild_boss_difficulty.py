"""Сложность Стража цитадели (2026-10-20): множители здоровья и награды."""
import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("guild_bosses", sa.Column("difficulty", sa.Integer(), nullable=False, server_default="1"))


def downgrade():
    op.drop_column("guild_bosses", "difficulty")
