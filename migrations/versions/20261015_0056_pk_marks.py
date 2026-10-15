"""Пепельное клеймо: метки убийцы слабых, награда за голову, право мести."""
import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("characters", sa.Column("pk_marks", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("characters", sa.Column("pk_marks_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("characters", sa.Column("pk_bounty", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("characters", sa.Column("revenge_target_id", sa.Integer(), nullable=True))
    op.add_column("characters", sa.Column("revenge_until", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for col in ("revenge_until", "revenge_target_id", "pk_bounty", "pk_marks_at", "pk_marks"):
        op.drop_column("characters", col)
