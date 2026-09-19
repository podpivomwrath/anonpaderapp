"""Drop the mining pause column: a dig is never resumed, leaving resets it."""
import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    # Возврат к прерванной добыче убран как механика: уход из забоя полностью
    # сбрасывает таймер. Остаток времени хранить стало незачем.
    op.drop_column("characters", "mining_left_seconds")


def downgrade():
    op.add_column(
        "characters",
        sa.Column("mining_left_seconds", sa.Integer(), nullable=True),
    )
