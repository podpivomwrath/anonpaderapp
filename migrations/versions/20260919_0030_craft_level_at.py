"""When the current craft level was reached - tiebreaker for the boards."""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    # Ничью в топах ремёсел разрешали по числу PvP-поражений — к рыбалке и
    # горному делу это отношения не имеет. Теперь выше тот, кто взял уровень
    # раньше. NULL у действующих персонажей — они попадут в конец при равенстве,
    # пока не возьмут следующий уровень; переписывать историю задним числом
    # нечем, её просто нет.
    op.add_column(
        "characters",
        sa.Column("fishing_level_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "characters",
        sa.Column("mining_level_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("characters", "mining_level_at")
    op.drop_column("characters", "fishing_level_at")
