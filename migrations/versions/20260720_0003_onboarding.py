"""onboarding: регион, состояние создания, уникальный никнейм

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Стартовый регион (ridge|woods|docks|scorched) — постоянный выбор
    op.add_column("characters", sa.Column("region", sa.String(16), nullable=True))
    # Шаг FSM создания; NULL = создание завершено (все существующие — завершены)
    op.add_column("characters", sa.Column("creation_state", sa.String(32), nullable=True))
    # Никнейм уникален без учёта регистра
    op.create_index(
        "uq_characters_name_lower",
        "characters",
        [sa.text("lower(name)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_characters_name_lower", table_name="characters")
    op.drop_column("characters", "creation_state")
    op.drop_column("characters", "region")
