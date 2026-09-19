"""Mining dig can be paused: time only runs while the player is in the vein."""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    # Время добычи идёт только пока игрок в забое. На паузе абсолютного срока
    # быть не может — он продолжал бы тикать сам, поэтому остаток хранится
    # отдельным числом.
    op.add_column(
        "characters",
        sa.Column("mining_left_seconds", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("characters", "mining_left_seconds")
