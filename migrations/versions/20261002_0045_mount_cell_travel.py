"""Поездка на маунте идёт по клеткам: шаг, номер клетки на пути, время следующего шага."""
import sqlalchemy as sa
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("mount_travels", sa.Column("step_seconds", sa.Float(), nullable=False, server_default="10"))
    op.add_column("mount_travels", sa.Column("cell_index", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mount_travels", sa.Column("next_cell_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("mount_travels", "next_cell_at")
    op.drop_column("mount_travels", "cell_index")
    op.drop_column("mount_travels", "step_seconds")
