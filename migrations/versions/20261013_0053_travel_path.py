"""Поездка верхом хранит свой маршрут: безопасный путь идёт не по прямой."""
import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mount_travels", sa.Column("path", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("mount_travels", "path")
