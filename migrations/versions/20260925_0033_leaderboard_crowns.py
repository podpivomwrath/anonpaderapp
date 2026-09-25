"""Венцы топ-1: колонка на персонаже."""
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    # Колонка, а не отдельная таблица со связью. Бонус венца читается там,
    # где до базы уже не дотянуться: experience_service.add_experience
    # принимает готового персонажа и про сессию не знает. Связь пришлось бы
    # подгружать лениво, а ленивая подгрузка в асинхронном коде падает с
    # MissingGreenlet - это поймал тест, до прода не доехало.
    op.add_column(
        "characters",
        sa.Column("crowns", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade():
    op.drop_column("characters", "crowns")
